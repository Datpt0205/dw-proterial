"""`MemberAccountsService`: the sign-in accounts an Org Admin creates.

Over the real `TenantMembersService` and `ScopeAuthorizationService`, with
the repository, the identity provider and the unit of work faked honestly:
`MemoryLoginAccounts` (`dw_platform.testing`) holds the identity provider's
contract, and `Uow` keeps an audit event only when the transaction commits.
"""

from __future__ import annotations

import string
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType

import pytest

from dw_kernel.errors import ConflictError, DomainError, NotFoundError, PermissionDeniedError
from dw_kernel.ids import UserId
from dw_kernel.ports import SystemClock, Uuid4Generator
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.application.member_accounts import (
    LoginAccount,
    MemberAccountsService,
    temporary_password,
)
from dw_platform.application.membership_admin import UserRef
from dw_platform.application.tenant_members import (
    InviteMember,
    MembershipChange,
    MemberWorkspace,
    Roles,
    TenantMember,
    TenantMembersService,
    WorkspaceRoles,
)
from dw_platform.domain.audit import AuditEvent
from dw_platform.testing.login_accounts import HeldAccount, MemoryLoginAccounts

pytestmark = pytest.mark.unit

TENANT, OTHER_TENANT, WS = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
ADMIN, LAN, HEAD_OF_IT = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
CATALOG = {
    "member": frozenset({"crm.read"}),
    "sales_pic": frozenset({"sales.case.read"}),
    "org_admin": frozenset({"platform.members.read", "platform.members.write"}),
}


def _context(
    *, roles: frozenset[str] = frozenset({"org_admin"}), scopes: frozenset[str] | None = None
) -> AccessContext:
    return AccessContext(
        tenant_id=TENANT,
        workspace_id=WS,
        principal_id=ADMIN,
        roles=roles,
        scopes=CATALOG["org_admin"] if scopes is None else scopes,
        plan_id="professional",
    )


def _member(user_id: uuid.UUID, email: str, roles: tuple[str, ...]) -> TenantMember:
    return TenantMember(
        user_id=user_id,
        display_name=email.split("@")[0],
        email=email,
        status="active",
        memberships=(MemberWorkspace(WS, "Sales", roles),),
    )


class Repo:
    """Lan (sales) and the head of IT (an administrator) are in the tenant."""

    def __init__(self) -> None:
        self.members = [
            _member(LAN, "lan@example.test", ("sales_pic",)),
            _member(HEAD_OF_IT, "it.head@example.test", ("org_admin",)),
        ]
        self.audits: list[AuditEvent] = []

    async def role_catalog(self) -> dict[str, frozenset[str]]:
        return dict(CATALOG)

    async def list_members(self, context: AccessContext) -> list[TenantMember]:
        return list(self.members)

    async def replace_memberships(
        self,
        context: AccessContext,
        *,
        user_id: uuid.UUID,
        plan: Callable[[Roles], Roles],
        audit: Callable[[MembershipChange], AuditEvent],
    ) -> list[MembershipChange]:
        raise NotImplementedError("not exercised by the account tests")

    async def invite(
        self,
        context: AccessContext,
        *,
        display_name: str,
        email: str,
        memberships: Roles,
        audit: Callable[[uuid.UUID, uuid.UUID, frozenset[str]], AuditEvent],
    ) -> UserRef:
        if any(m.email == email for m in self.members):
            raise ConflictError(
                "already a member", details={"reason_code": "member_email_exists_in_tenant"}
            )
        user_id = uuid.uuid4()
        self.audits += [audit(user_id, ws, roles) for ws, roles in memberships.items()]
        self.members.append(_member(user_id, email, tuple(sorted(memberships[WS]))))
        return UserRef(user_id=user_id, email=email, display_name=display_name)


class Audit:
    def __init__(self, sink: list[AuditEvent]) -> None:
        self.sink = sink
        self.pending: list[AuditEvent] = []

    async def append(self, event: AuditEvent) -> None:
        self.pending.append(event)


class Uow:
    """Audit events reach `committed` only on commit, as in one transaction."""

    def __init__(self) -> None:
        self.committed: list[AuditEvent] = []

    def __call__(self, context: AccessContext) -> Uow:
        self.audit = Audit(self.committed)
        return self

    async def __aenter__(self) -> Uow:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.audit.pending.clear()

    async def commit(self) -> None:
        self.committed += self.audit.pending
        self.audit.pending.clear()


@dataclass
class World:
    service: MemberAccountsService
    repo: Repo
    accounts: MemoryLoginAccounts
    uow: Uow


def _world() -> World:
    repo, accounts, uow = Repo(), MemoryLoginAccounts(), Uow()
    authz = ScopeAuthorizationService()
    members = TenantMembersService(repo, authz, SystemClock(), Uuid4Generator())
    service = MemberAccountsService(
        members=members,
        accounts=accounts,
        uow=uow,  # type: ignore[arg-type]  # the audit-only slice of the unit of work
        authz=authz,
        clock=SystemClock(),
        ids=Uuid4Generator(),
    )
    return World(service, repo, accounts, uow)


def _invite(
    email: str = "Minh.Vu@Example.test ", roles: frozenset[str] = frozenset({"sales_pic"})
) -> InviteMember:
    return InviteMember(
        display_name=" Vũ Minh ", email=email, memberships=(WorkspaceRoles(WS, roles),)
    )


async def test_creating_makes_the_account_and_the_member_together() -> None:
    world = _world()
    created = await world.service.create(_context(), _invite())

    held = world.accounts.held["minh.vu@example.test"]
    assert (held.tenant_id, held.password) == (TENANT, created.temporary_password)
    assert created.member.email == "minh.vu@example.test"
    [event] = world.repo.audits
    assert event.action == "platform.member.invited"
    assert event.details["login_account"] is True
    assert event.details["roles"] == ["sales_pic"]


async def test_a_refused_invitation_leaves_no_sign_in_behind() -> None:
    # An org admin may not hand out an administrative role: the invitation is
    # refused after the account was made, and the account goes with it.
    world = _world()
    with pytest.raises(PermissionDeniedError):
        await world.service.create(_context(), _invite(roles=frozenset({"org_admin"})))
    assert world.accounts.held == {}
    assert world.repo.audits == []


async def test_an_email_already_in_the_tenant_keeps_its_own_account() -> None:
    world = _world()
    await world.accounts.create(
        tenant_id=TENANT, email="lan@example.test", display_name="Lan", temporary_password="x"
    )
    with pytest.raises(ConflictError):
        await world.service.create(_context(), _invite(email="lan@example.test"))
    # The conflict came from the identity provider, before anything was made:
    # Lan's account and password are untouched.
    assert world.accounts.held["lan@example.test"].password == "x"


async def test_a_malformed_invitation_never_reaches_the_identity_provider() -> None:
    world = _world()
    with pytest.raises(DomainError):
        await world.service.create(_context(), _invite(email="not-an-email"))
    with pytest.raises(DomainError):
        await world.service.create(_context(), _invite(roles=frozenset()))
    assert world.accounts.calls == 0


async def test_without_members_write_nothing_is_created() -> None:
    world = _world()
    reader = _context(roles=frozenset({"member"}), scopes=frozenset({"platform.members.read"}))
    with pytest.raises(PermissionDeniedError):
        await world.service.create(reader, _invite())
    with pytest.raises(PermissionDeniedError):
        await world.service.reset_password(reader, LAN)
    assert world.accounts.calls == 0


async def test_a_reset_gives_a_new_password_and_is_audited() -> None:
    world = _world()
    await world.accounts.create(
        tenant_id=TENANT, email="lan@example.test", display_name="Lan", temporary_password="old"
    )
    password = await world.service.reset_password(_context(), LAN)

    assert world.accounts.held["lan@example.test"].password == password != "old"
    [event] = world.uow.committed
    assert (event.action, event.resource_id, event.actor_id) == (
        "platform.login_account.password_reset",
        str(LAN),
        UserId(ADMIN),
    )
    assert password not in str(event.details)


async def test_a_person_outside_the_tenant_is_not_found() -> None:
    world = _world()
    with pytest.raises(NotFoundError):
        await world.service.reset_password(_context(), uuid.uuid4())
    assert world.accounts.calls == 0


async def test_an_account_this_tenant_did_not_create_is_not_reached() -> None:
    # Lan is a member here, but her sign-in belongs to another tenant: that
    # tenant's admin controls it, and this audit is never committed.
    world = _world()
    await world.accounts.create(
        tenant_id=OTHER_TENANT,
        email="lan@example.test",
        display_name="Lan",
        temporary_password="theirs",
    )
    with pytest.raises(NotFoundError):
        await world.service.reset_password(_context(), LAN)
    with pytest.raises(NotFoundError):
        await world.service.set_enabled(_context(), LAN, enabled=False)
    assert world.accounts.held["lan@example.test"] == HeldAccount(OTHER_TENANT, "theirs", True)
    assert world.uow.committed == []


async def test_an_administrators_sign_in_is_a_platform_admins_alone() -> None:
    # Resetting the head of IT's password would be signing in as them.
    world = _world()
    await world.accounts.create(
        tenant_id=TENANT, email="it.head@example.test", display_name="IT", temporary_password="kept"
    )
    with pytest.raises(PermissionDeniedError) as caught:
        await world.service.reset_password(_context(), HEAD_OF_IT)
    assert caught.value.details["reason_code"] == "administrator_sign_in"
    with pytest.raises(PermissionDeniedError):
        await world.service.set_enabled(_context(), HEAD_OF_IT, enabled=False)
    assert world.accounts.held["it.head@example.test"] == HeldAccount(TENANT, "kept", True)

    platform_admin = _context(roles=frozenset({"platform_admin"}))
    await world.service.set_enabled(platform_admin, HEAD_OF_IT, enabled=False)
    assert world.accounts.held["it.head@example.test"].enabled is False


async def test_locking_and_unlocking_are_audited() -> None:
    world = _world()
    await world.accounts.create(
        tenant_id=TENANT, email="lan@example.test", display_name="Lan", temporary_password="pw"
    )
    await world.service.set_enabled(_context(), LAN, enabled=False)
    assert world.accounts.held["lan@example.test"].enabled is False
    await world.service.set_enabled(_context(), LAN, enabled=True)
    assert world.accounts.held["lan@example.test"] == HeldAccount(TENANT, "pw", True)
    assert [e.action for e in world.uow.committed] == [
        "platform.login_account.locked",
        "platform.login_account.unlocked",
    ]


async def test_an_admin_cannot_lock_their_own_sign_in() -> None:
    world = _world()
    with pytest.raises(DomainError) as caught:
        await world.service.set_enabled(_context(), ADMIN, enabled=False)
    assert caught.value.details["reason_code"] == "own_sign_in"


async def test_the_list_holds_this_tenants_accounts_only() -> None:
    world = _world()
    await world.accounts.create(
        tenant_id=TENANT, email="lan@example.test", display_name="Lan", temporary_password="a"
    )
    await world.accounts.create(
        tenant_id=OTHER_TENANT, email="x@other.test", display_name="X", temporary_password="b"
    )
    assert await world.service.list_accounts(_context()) == [
        LoginAccount(email="lan@example.test", enabled=True)
    ]


def test_a_temporary_password_passes_the_realm_policy_and_reads_aloud() -> None:
    passwords = {temporary_password() for _ in range(200)}
    assert len(passwords) == 200
    for password in passwords:
        groups = password.split("-")
        assert [len(g) for g in groups] == [4, 4, 4]
        assert len(password) >= 10  # the realm's length(10)
        assert not set("".join(groups)) & set("0O1lI")
        assert set("".join(groups)) <= set(string.ascii_letters + string.digits)
