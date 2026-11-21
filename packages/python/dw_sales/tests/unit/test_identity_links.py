"""Ticket 64's acceptance, each a test: a rename keeps the link; a re-created
account re-links only after the old one is disabled; two Bravo users for a
code, no match or several matches queue for the admin; Bravo unasked links
nothing; a link by hand needs the right and one active Bravo user."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from dw_kernel.errors import ConflictError, PermissionDeniedError
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.domain.audit import AuditEvent
from dw_sales.application.identity_links import (
    BravoPeopleUnavailableError,
    IdentityLinks,
    Link,
    Linked,
    Person,
    Queued,
    QueueReason,
    Unchanged,
    decide,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 21, 3, tzinfo=UTC)
TENANT, WORKSPACE = uuid.uuid4(), uuid.uuid4()
OLD, NEW = uuid.uuid4(), uuid.uuid4()


@dataclass
class Bravo:
    users: dict[str, int] = field(default_factory=lambda: {"NV001": 1})
    emails: dict[str, list[str]] = field(default_factory=dict)
    down: bool = False

    async def codes_for_email(self, tenant_id: uuid.UUID, email: str) -> Sequence[str]:
        if self.down:
            raise BravoPeopleUnavailableError()
        return self.emails.get(email, [])

    async def active_users(self, tenant_id: uuid.UUID, employee_code: str) -> int:
        if self.down:
            raise BravoPeopleUnavailableError()
        return self.users.get(employee_code, 0)


async def _decide(
    person: Person, links: list[Link], enabled: dict[uuid.UUID, bool], bravo: Bravo
) -> object:
    return await decide(
        person,
        tenant_id=TENANT,
        link_of_subject={k.subject: k for k in links}.get,
        link_of_code={k.employee_code: k for k in links}.get,
        enabled=enabled.get,
        bravo=bravo,
    )


async def test_a_renamed_login_is_the_same_subject_so_the_link_stands() -> None:
    linked = Link(OLD, "NV001", "employee_id")
    renamed = Person(OLD, enabled=True, employee_id="NV001", email="new.name@x.vn")

    assert await _decide(renamed, [linked], {OLD: True}, Bravo()) == Unchanged()


async def test_a_unique_exact_match_links_itself() -> None:
    assert await _decide(Person(NEW, True, employee_id="NV001"), [], {}, Bravo()) == Linked(
        "NV001", "employee_id"
    )
    by_mail = Bravo(emails={"a@x.vn": ["NV001"]})
    assert await _decide(Person(NEW, True, email="A@x.vn "), [], {}, by_mail) == Linked(
        "NV001", "email"
    )


async def test_a_recreated_account_relinks_only_after_the_old_one_is_disabled() -> None:
    held = [Link(OLD, "NV001", "employee_id")]
    person = Person(NEW, True, employee_id="NV001")

    assert await _decide(person, held, {OLD: True, NEW: True}, Bravo()) == Queued(
        "relink_while_old_live", "NV001"
    )
    assert await _decide(person, held, {OLD: False, NEW: True}, Bravo()) == Linked(
        "NV001", "employee_id", retire=OLD
    )


@pytest.mark.parametrize(
    ("person", "bravo", "reason"),
    [
        (Person(NEW, True, employee_id="NV001"), Bravo(users={"NV001": 2}), "two_bravo_users"),
        (Person(NEW, True, employee_id="NV009"), Bravo(), "no_match"),
        (Person(NEW, True), Bravo(), "no_match"),
        (
            Person(NEW, True, email="a@x.vn"),
            Bravo(emails={"a@x.vn": ["NV1", "NV2"]}),
            "several_matches",
        ),
        (Person(NEW, True, email="a@x.vn"), Bravo(), "no_match"),
    ],
    ids=["two_bravo_users", "no_bravo_user", "nothing_to_match", "several_emails", "unknown_email"],
)
async def test_what_is_not_unique_waits_for_the_admin(
    person: Person, bravo: Bravo, reason: str
) -> None:
    outcome = await _decide(person, [], {}, bravo)

    assert isinstance(outcome, Queued) and outcome.reason == reason


async def test_a_disabled_account_is_never_linked() -> None:
    assert await _decide(Person(NEW, False, employee_id="NV001"), [], {}, Bravo()) == Unchanged()


@dataclass
class Store:
    saved: list[tuple[Link, uuid.UUID | None, uuid.UUID | None]] = field(default_factory=list)
    queued: list[tuple[uuid.UUID, str, str | None]] = field(default_factory=list)
    existing: list[Link] = field(default_factory=list)

    async def links(self, tenant_id: uuid.UUID) -> Sequence[Link]:
        return self.existing

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
        self.saved.append((link, linked_by, retire))

    async def queue(
        self,
        tenant_id: uuid.UUID,
        subject: uuid.UUID,
        reason: QueueReason,
        code: str | None,
        at: datetime,
    ) -> None:
        self.queued.append((subject, reason, code))

    async def open_items(self, tenant_id: uuid.UUID) -> Sequence[tuple[uuid.UUID, str, str | None]]:
        return self.queued


@dataclass
class People:
    people_: list[Person]

    async def people(self, tenant_id: uuid.UUID) -> Sequence[Person]:
        return self.people_


@dataclass
class Told:
    links: list[Link] = field(default_factory=list)

    async def linked(self, tenant_id: uuid.UUID, link: Link) -> None:
        self.links.append(link)


class _Clock:
    def now(self) -> datetime:
        return NOW


class _Ids:
    def new_uuid(self) -> uuid.UUID:
        return uuid.uuid4()


def _service(
    people: list[Person], bravo: Bravo, store: Store | None = None
) -> tuple[IdentityLinks, Store, Told]:
    store, told = store or Store(), Told()
    service = IdentityLinks(
        store,
        People(people),
        bravo,
        told,
        ScopeAuthorizationService(),
        _Clock(),
        _Ids(),  # type: ignore[arg-type]
    )
    return service, store, told


async def test_the_sweep_links_queues_and_announces() -> None:
    service, store, told = _service(
        [Person(NEW, True, employee_id="NV001"), Person(OLD, True, employee_id="NV777")], Bravo()
    )

    counts = await service.sweep(TENANT, WORKSPACE)

    assert counts == {"linked": 1, "queued": 1, "unasked": 0}
    assert [s[0] for s in store.saved] == [Link(NEW, "NV001", "employee_id")]
    assert store.queued == [(OLD, "no_match", "NV777")]
    assert told.links == [Link(NEW, "NV001", "employee_id")]


async def test_bravo_unasked_links_nothing() -> None:
    service, store, _ = _service([Person(NEW, True, employee_id="NV001")], Bravo(down=True))

    counts = await service.sweep(TENANT, WORKSPACE)

    assert counts["unasked"] == 1 and store.saved == [] and store.queued == []


def _admin(*scopes: str) -> AccessContext:
    return AccessContext(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        principal_id=uuid.uuid4(),
        roles=frozenset(),
        scopes=frozenset(scopes),
        plan_id="professional",
    )


async def test_a_link_by_hand_needs_the_right_where_it_is_written() -> None:
    service, store, _ = _service([], Bravo())

    with pytest.raises(PermissionDeniedError):
        await service.link_by_hand(_admin("sales.case.read"), NEW, "NV001")
    assert store.saved == []

    admin = _admin("sales.identity.link")
    await service.link_by_hand(admin, NEW, "NV001")
    assert store.saved == [(Link(NEW, "NV001", "admin"), admin.principal_id, None)]


async def test_a_link_by_hand_needs_exactly_one_active_bravo_user() -> None:
    service, store, _ = _service([], Bravo(users={"NV001": 2}))

    with pytest.raises(ConflictError):
        await service.link_by_hand(_admin("sales.identity.link"), NEW, "NV001")
    assert store.saved == []
