"""One person, many accounts: identity anchored on the employee code (ticket 64).

A Bravo write is the PIC's own (ADR 0027 decision 5), so DW links each
person, as the Keycloak subject that a renamed AD login keeps (measured on
Keycloak 26.7.2 with LDAP, ticket 64), to an employee code. The Bravo user
is looked up by that code at each write, by the gateway, never stored here.

Automatic, never a guess (`decide`): a unique exact match links itself and
is audited and announced; anything else waits for an admin, with why. A
link by hand is an act of a holder of `sales.identity.link`, checked where
the link is written; it keeps the same invariants (one live link per person
and per code, a code held by a live account is never taken over).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, Protocol

from dw_kernel.errors import ConflictError, DomainError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import AuditEvent, system_actor
from dw_sales.application.access import SalesAuthorizationPort, SalesScopes

LinkedHow = Literal["employee_id", "email", "admin"]
QueueReason = Literal[
    "two_live_accounts", "two_bravo_users", "no_match", "several_matches", "relink_while_old_live"
]
LINKED_ACTION: Final = "sales.identity.linked"


class BravoPeopleUnavailableError(Exception):
    """Bravo could not be asked: nothing is linked (never a guess)."""


@dataclass(frozen=True)
class Person:
    """A DW principal as the identity provider knows it."""

    subject: uuid.UUID
    enabled: bool
    employee_id: str | None = None  # the AD's employeeID, when IT fills it
    email: str | None = None


@dataclass(frozen=True)
class Link:
    subject: uuid.UUID
    employee_code: str
    how: LinkedHow


@dataclass(frozen=True)
class Linked:
    code: str
    how: LinkedHow
    retire: uuid.UUID | None = None  # the old account's subject, disabled


@dataclass(frozen=True)
class Queued:
    reason: QueueReason
    code: str | None = None


@dataclass(frozen=True)
class Unchanged:
    pass


Outcome = Linked | Queued | Unchanged


async def decide(
    person: Person,
    *,
    tenant_id: uuid.UUID,
    link_of_subject: Callable[[uuid.UUID], Link | None],
    link_of_code: Callable[[str], Link | None],
    enabled: Callable[[uuid.UUID], bool | None],
    bravo: BravoPeoplePort,
) -> Outcome:
    """Ticket 64's rules, in order; the first that applies decides. Bravo
    not answering raises `BravoPeopleUnavailableError`: nothing is decided."""
    if not person.enabled or link_of_subject(person.subject) is not None:
        # Linked already (a renamed login is the same subject), or disabled.
        return Unchanged()
    how: LinkedHow
    if person.employee_id and person.employee_id.strip():
        code, how = person.employee_id.strip(), "employee_id"
    elif person.email and person.email.strip():
        codes = sorted(set(await bravo.codes_for_email(tenant_id, person.email.strip().lower())))
        if not codes:
            return Queued("no_match")
        if len(codes) > 1:
            return Queued("several_matches")
        code, how = codes[0], "email"
    else:
        return Queued("no_match")
    users = await bravo.active_users(tenant_id, code)
    if users == 0:
        return Queued("no_match", code)
    if users > 1:
        return Queued("two_bravo_users", code)
    holder = link_of_code(code)
    if holder is None:
        return Linked(code, how)
    if enabled(holder.subject) is False:
        # A re-created account: the old one is disabled, so the code moves.
        return Linked(code, how, retire=holder.subject)
    return Queued("relink_while_old_live", code)


class IdentityLinkStorePort(Protocol):
    async def links(self, tenant_id: uuid.UUID) -> Sequence[Link]: ...

    async def save(
        self,
        tenant_id: uuid.UUID,
        link: Link,
        *,
        linked_by: uuid.UUID | None,
        retire: uuid.UUID | None,
        at: datetime,
        audit: AuditEvent,
    ) -> None:
        """The link, the old one retired, its open queue item resolved and the
        audit row, in one transaction; `ConflictError` when a live link on the
        person or the code stands in the way."""
        ...

    async def queue(
        self,
        tenant_id: uuid.UUID,
        subject: uuid.UUID,
        reason: QueueReason,
        code: str | None,
        at: datetime,
    ) -> None:
        """Open an item, or leave the open one for this subject as it is."""
        ...

    async def open_items(
        self, tenant_id: uuid.UUID
    ) -> Sequence[tuple[uuid.UUID, str, str | None]]: ...


class PeoplePort(Protocol):
    async def people(self, tenant_id: uuid.UUID) -> Sequence[Person]: ...


class BravoPeoplePort(Protocol):
    """Bravo's employee record and users, read through the gateway."""

    async def codes_for_email(self, tenant_id: uuid.UUID, email: str) -> Sequence[str]: ...

    async def active_users(self, tenant_id: uuid.UUID, employee_code: str) -> int: ...


class AnnouncePort(Protocol):
    async def linked(self, tenant_id: uuid.UUID, link: Link) -> None:
        """Tell the person and the admins that DW linked this account."""
        ...


@dataclass(frozen=True)
class IdentityLinks:
    store: IdentityLinkStorePort
    people: PeoplePort
    bravo: BravoPeoplePort
    announce: AnnouncePort
    authz: SalesAuthorizationPort
    clock: UtcClock
    ids: IdGenerator

    async def sweep(self, tenant_id: uuid.UUID, workspace_id: uuid.UUID) -> Mapping[str, int]:
        """Link what is unambiguous, queue the rest; Bravo unasked links nothing."""
        people = await self.people.people(tenant_id)
        links = {link.subject: link for link in await self.store.links(tenant_id)}
        by_code = {link.employee_code: link for link in links.values()}
        accounts = {p.subject: p.enabled for p in people}
        counts = {"linked": 0, "queued": 0, "unasked": 0}
        for person in people:
            try:
                outcome = await decide(
                    person,
                    tenant_id=tenant_id,
                    link_of_subject=links.get,
                    link_of_code=by_code.get,
                    enabled=accounts.get,
                    bravo=self.bravo,
                )
            except BravoPeopleUnavailableError:
                counts["unasked"] += 1
                break
            now = self.clock.now()
            if isinstance(outcome, Linked):
                link = Link(person.subject, outcome.code, outcome.how)
                await self.store.save(
                    tenant_id,
                    link,
                    linked_by=None,
                    retire=outcome.retire,
                    at=now,
                    audit=self._audit(tenant_id, workspace_id, None, link, now),
                )
                links[person.subject] = by_code[outcome.code] = link
                await self.announce.linked(tenant_id, link)
                counts["linked"] += 1
            elif isinstance(outcome, Queued):
                await self.store.queue(tenant_id, person.subject, outcome.reason, outcome.code, now)
                counts["queued"] += 1
        return counts

    async def queue(self, context: AccessContext) -> Sequence[tuple[uuid.UUID, str, str | None]]:
        await self._require(context)
        return await self.store.open_items(context.tenant_id)

    async def link_by_hand(
        self, context: AccessContext, subject: uuid.UUID, employee_code: str
    ) -> Link:
        await self._require(context)
        code = employee_code.strip()
        if not 1 <= len(code) <= 24:
            raise DomainError("mã nhân viên có 1-24 ký tự")
        try:
            users = await self.bravo.active_users(context.tenant_id, code)
        except BravoPeopleUnavailableError:
            raise ConflictError("chưa hỏi được Bravo: thử lại sau") from None
        if users != 1:
            raise ConflictError(
                "mã nhân viên này không ứng với đúng một user Bravo đang hoạt động",
                details={"active_bravo_users": users},
            )
        link = Link(subject, code, "admin")
        now = self.clock.now()
        await self.store.save(
            context.tenant_id,
            link,
            linked_by=context.principal_id,
            retire=None,
            at=now,
            audit=self._audit(
                context.tenant_id, context.workspace_id, context.principal_id, link, now
            ),
        )
        return link

    async def _require(self, context: AccessContext) -> None:
        await self.authz.require(
            context=context,
            action=SalesScopes.IDENTITY_LINK,
            resource_type="workspace",
            resource_id=str(context.workspace_id),
        )

    def _audit(
        self,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        actor: uuid.UUID | None,
        link: Link,
        at: datetime,
    ) -> AuditEvent:
        return AuditEvent(
            id=self.ids.new_uuid(),
            tenant_id=TenantId(tenant_id),
            workspace_id=WorkspaceId(workspace_id),
            actor_id=UserId(actor) if actor else system_actor("identity_links"),
            action=LINKED_ACTION,
            resource_type="person_link",
            resource_id=str(link.subject),
            occurred_at=at,
            details={"how": link.how},
        )
