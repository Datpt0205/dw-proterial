"""Who is calling and what they may do in Purchasing.

Everything is resolved from the platform's verified `AccessContext`, never
from a request: the tenant and workspace a call reads and the principal a
case is stamped with. The scope names are the ones the purchasing migration
declares; which role holds which is the platform catalogue's to say.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from dw_platform.application.access_context import AccessContext


class PurchasingScopes(StrEnum):
    """The `purchasing.*` scopes a route or a step asks for."""

    # Read the purchase cases and the mailbox DW2 reads requests from.
    REQUEST_READ = "purchasing.request.read"
    # Receive a request: enter a form, or have DW2 read a mail.
    REQUEST_INTAKE = "purchasing.request.intake"
    # Check a request and send it to the approver its amount names.
    REQUEST_SUBMIT = "purchasing.request.submit"
    # Decide a request, by tier: which band of amounts each decides is the
    # tenant's rule (`ApprovalRules`), who holds each the platform's catalogue.
    APPROVE_TIER1 = "purchasing.approve.tier1"
    APPROVE_TIER2 = "purchasing.approve.tier2"
    APPROVE_TIER3 = "purchasing.approve.tier3"
    # Draft the RFQs of an approved request, record what suppliers offer,
    # choose a supplier per line.
    RFQ_PREPARE = "purchasing.rfq.prepare"


class PurchasingAuthorizationPort(Protocol):
    """The platform's scope check (`ScopeAuthorizationService`): `require`
    raises `PermissionDeniedError`, `is_allowed` answers without raising."""

    async def require(
        self,
        *,
        context: AccessContext,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
    ) -> None: ...

    def is_allowed(self, context: AccessContext, action: str) -> bool: ...


@dataclass(frozen=True)
class Gate:
    """Scope checks, raised as the platform raises them (403, naming the scope)."""

    authz: PurchasingAuthorizationPort

    async def require(
        self,
        context: AccessContext,
        scope: PurchasingScopes,
        *,
        resource_type: str = "purchasing",
        resource_id: str | None = None,
    ) -> None:
        await self.authz.require(
            context=context,
            action=scope.value,
            resource_type=resource_type,
            resource_id=resource_id,
        )
