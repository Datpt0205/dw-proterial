"""Building the trusted AccessContext from verified identity + membership.

The client may REQUEST a tenant/workspace, but access is granted only when the
database confirms membership. Nothing client-supplied is
trusted directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Protocol
from uuid import UUID

from dw_kernel.autonomy import FAIL_CLOSED_LEVEL, AutonomyLevel
from dw_kernel.errors import PermissionDeniedError, TenantContextMissingError
from dw_platform.application.access_context import AccessContext
from dw_platform.application.ports import TokenVerifierPort, VerifiedIdentity

# The subject of a service account: a context's digital worker acting on its
# own (`SqlMembershipLookup.find_service_access`), such as Sales' DW1 in its
# mailbox lane. It signs in nowhere, so no sign-in resolves one.
SERVICE_SUBJECT_PREFIX: Final = "service|"


def service_subject(worker_id: str, tenant_id: UUID) -> str:
    """The subject of ``worker_id``'s service account in one tenant. The tenant
    is part of it: a subject is unique across the platform."""
    return f"{SERVICE_SUBJECT_PREFIX}{worker_id}|{tenant_id}"


@dataclass(frozen=True)
class ServiceSubjectsRefused:
    """`TokenVerifierPort` around the deployment's verifier: a token naming a
    service account's subject is refused, whoever issued it.

    Every sign-in path (a request's context, the bootstrap, support,
    provisioning) starts from this verifier, so one refusal here covers them
    all; `SqlMembershipLookup.find_access` also never resolves a service
    account, for a subject mapped to one by hand.
    """

    inner: TokenVerifierPort

    async def verify(self, token: str) -> VerifiedIdentity:
        identity = await self.inner.verify(token)
        if identity.subject.startswith(SERVICE_SUBJECT_PREFIX):
            raise PermissionDeniedError(
                "a service account does not sign in", details={"rule": "service_subject"}
            )
        return identity


@dataclass(frozen=True, slots=True)
class VerifiedClaims:
    """Concrete VerifiedIdentity produced by token verifier adapters."""

    subject: str
    email: str | None
    issuer: str
    name: str | None = None
    # `amr` and `acr`. Empty / None when the token carries neither: no second
    # factor is ever assumed.
    auth_methods: frozenset[str] = frozenset()
    acr: str | None = None


@dataclass(frozen=True, slots=True)
class MembershipAccess:
    """Resolved membership snapshot returned by the lookup port."""

    tenant_id: UUID
    workspace_id: UUID
    principal_id: UUID
    roles: frozenset[str]
    scopes: frozenset[str]
    groups: frozenset[str]
    clearance: str
    plan_id: str
    feature_flags: frozenset[str]
    record_visibility: str = "open"
    visible_owners: frozenset[UUID] | None = None
    # Most restrictive by default, for the reason given on AccessContext.
    max_autonomy_level: AutonomyLevel = FAIL_CLOSED_LEVEL


class MembershipLookupPort(Protocol):
    """Confirms (subject, tenant, workspace) membership against the database."""

    async def find_access(
        self,
        subject: str,
        issuer: str,
        tenant_id: UUID,
        workspace_id: UUID,
    ) -> MembershipAccess | None: ...


def context_from(access: MembershipAccess) -> AccessContext:
    """The access context for a membership the database confirmed.

    One mapping for every way a context is built — a signed-in request here, a
    linked chat in ``channel_access`` — so a field added to the snapshot cannot
    reach one path and silently default on the other.
    """
    return AccessContext(
        tenant_id=access.tenant_id,
        workspace_id=access.workspace_id,
        principal_id=access.principal_id,
        roles=access.roles,
        groups=access.groups,
        scopes=access.scopes,
        clearance=access.clearance,
        plan_id=access.plan_id,
        feature_flags=access.feature_flags,
        record_visibility=access.record_visibility,
        visible_owners=access.visible_owners,
        max_autonomy_level=access.max_autonomy_level,
    )


@dataclass(frozen=True)
class DbAccessContextFactory:
    """Implements ``AccessContextFactoryPort`` on top of the membership lookup."""

    membership_lookup: MembershipLookupPort

    async def build(
        self,
        identity: VerifiedIdentity,
        requested_tenant_id: UUID | None,
        requested_workspace_id: UUID | None,
    ) -> AccessContext:
        if requested_tenant_id is None or requested_workspace_id is None:
            raise TenantContextMissingError("X-Tenant-Id and X-Workspace-Id headers are required")
        access = await self.membership_lookup.find_access(
            subject=identity.subject,
            issuer=identity.issuer,
            tenant_id=requested_tenant_id,
            workspace_id=requested_workspace_id,
        )
        if access is None:
            # Same response for "tenant does not exist" and "not a member":
            # do not leak tenant existence to non-members.
            raise PermissionDeniedError(
                "no membership for the requested tenant/workspace",
                details={"tenant_id": str(requested_tenant_id)},
            )
        return context_from(access)
