"""The drop lane's decisions (ticket 43), over fakes: which files it reads,
which wait, which it refuses for good, and whose mail it takes; and that
what it could not do is told to a person, never only logged."""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from dw_kernel.ids import TenantId, WorkspaceId
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import AuditEvent
from dw_platform.domain.messages import EmailAddress, InboundMessage
from dw_sales.adapters.order_rules import load_order_rules
from dw_sales.adapters.reader_client import ReaderUnavailableError
from dw_sales.application.mail_drop import (
    SETTLE,
    DroppedFile,
    DropTick,
    MailDrop,
    MailDropNotices,
    MailFile,
    MailRefused,
)
from dw_sales.application.ports import SalesScope
from dw_sales.domain.order_checks import OrderRules

NOW = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)
SCOPE = SalesScope(TenantId(uuid.uuid4()), WorkspaceId(uuid.uuid4()))
REPO = Path(__file__).resolve().parents[5]


def _message(data: bytes, sender: str) -> InboundMessage:
    return InboundMessage(
        message_id="eml-" + hashlib.sha256(data).hexdigest(),
        sender=EmailAddress(address=sender),
        subject="PO",
        received_at=NOW,
        body_text="",
    )


class Folder:
    """`DropFolderPort` over a dict of file names and bytes, all changed at
    ``modified``."""

    def __init__(self, content: dict[str, bytes], *, modified: datetime = NOW - SETTLE * 2) -> None:
        self.content = content
        self.modified = modified
        self.reads: list[str] = []

    async def files(self) -> list[DroppedFile]:
        return [
            DroppedFile(name=name, size=len(data), modified_at=self.modified)
            for name, data in self.content.items()
        ]

    async def read(self, dropped: DroppedFile, limit: int) -> bytes:
        self.reads.append(dropped.name)
        return self.content[dropped.name][: limit + 1]


class Reader:
    """Reads ``b"from:<address>"``; anything else is refused."""

    def __init__(self, *, down: bool = False) -> None:
        self.down = down
        self.calls = 0

    async def read_mail(self, data: bytes) -> MailFile | MailRefused:
        self.calls += 1
        if self.down:
            raise ReaderUnavailableError("down")
        if not data.startswith(b"from:"):
            return MailRefused("the mail names no sender")
        return MailFile(message=_message(data, data[5:].decode()), contents={})


class Store:
    def __init__(self, handled: frozenset[str] = frozenset()) -> None:
        self.handled = set(handled)
        self.stored: dict[str, MailFile] = {}
        self.refused: dict[str, str] = {}
        self.events: list[AuditEvent] = []

    async def handled_sources(self, scope: SalesScope) -> frozenset[str]:
        return frozenset(self.handled)

    async def refuse(self, scope: SalesScope, *, source: str, reason: str) -> None:
        self.handled.add(source)
        self.refused[source] = reason

    async def store(
        self, scope: SalesScope, mail: MailFile, *, source: str, event: AuditEvent
    ) -> bool:
        self.handled.add(source)
        if mail.message.message_id in self.stored:
            return False
        self.stored[mail.message.message_id] = mail
        self.events.append(event)
        return True


class Notices:
    """`MailDropNoticePort` recording what it was asked to tell; ``down``
    raises as a notification store that does not answer would."""

    def __init__(self, *, down: bool = False) -> None:
        self.down = down
        self.told_refused: list[tuple[str, str]] = []
        self.told_unreachable: list[date] = []

    async def refused(self, scope: SalesScope, *, source: str, reason: str) -> None:
        if self.down:
            raise OSError("notifications down")
        self.told_refused.append((source, reason))

    async def unreachable(self, scope: SalesScope, *, day: date) -> None:
        self.told_unreachable.append(day)


def _lane(
    folder: Folder,
    reader: Reader,
    store: Store,
    notices: Notices | None = None,
) -> MailDrop:
    return MailDrop(
        folder,
        reader,
        store,
        notices or Notices(),
        FixedClock(NOW),
        Uuid4Generator(),
        max_bytes=64,
    )


def _tick(lane: MailDrop) -> DropTick:
    return asyncio.run(lane.tick(SCOPE))


def test_each_new_eml_file_is_stored_once_with_its_audit_event() -> None:
    folder = Folder({"1.eml": b"from:a@velatrix.example", "note.txt": b"x"})
    store = Store()
    lane = _lane(folder, Reader(), store)

    first, second = _tick(lane), _tick(lane)

    assert first.stored == ("1.eml",) and second.stored == ()
    assert folder.reads == ["1.eml"]
    (event,) = store.events
    assert event.action == "sales.mail.stored"
    assert event.details["actor"] == "system:sales_mail_drop"
    assert event.details["source"] == "1.eml"


def test_a_file_still_arriving_waits_and_is_read_once_it_settles() -> None:
    folder = Folder({"1.eml": b"from:a@velatrix.example"}, modified=NOW - timedelta(seconds=5))
    store = Store()
    lane = _lane(folder, Reader(), store)
    assert _tick(lane).waiting == 1 and not store.stored
    folder.modified = NOW - SETTLE
    assert _tick(lane).stored == ("1.eml",)


def test_an_empty_file_waits() -> None:
    lane = _lane(Folder({"1.eml": b""}), Reader(), Store())
    assert _tick(lane).waiting == 1


def test_a_file_handled_before_a_restart_is_not_read_again() -> None:
    folder = Folder({"1.eml": b"from:a@velatrix.example"})
    reader = Reader()
    _tick(_lane(folder, reader, Store(handled=frozenset({"1.eml"}))))
    assert reader.calls == 0


def test_a_refused_or_oversized_file_is_refused_once_and_not_read_again() -> None:
    folder = Folder({"bad.eml": b"garbage", "big.eml": b"from:" + b"x" * 100})
    reader, store, notices = Reader(), Store(), Notices()
    lane = _lane(folder, reader, store, notices=notices)

    first = _tick(lane)
    _tick(lane)

    expected = {"bad.eml": "the mail names no sender", "big.eml": "the file is over 0 MB"}
    assert dict(first.refused) == expected
    assert reader.calls == 1
    # Recorded with its reason, and told to a person, once each.
    assert store.refused == expected
    assert dict(notices.told_refused) == expected
    assert len(notices.told_refused) == 2


def test_a_refused_file_is_not_refused_again_after_a_restart() -> None:
    folder = Folder({"bad.eml": b"garbage"})
    store, notices = Store(), Notices()
    _tick(_lane(folder, Reader(), store, notices=notices))

    reader = Reader()
    restarted = _tick(_lane(folder, reader, store, notices=notices))

    assert restarted.refused == ()
    assert reader.calls == 0
    assert len(notices.told_refused) == 1


def test_a_refusal_no_one_could_be_told_of_is_left_for_the_next_tick() -> None:
    folder = Folder({"bad.eml": b"garbage"})
    store = Store()
    with pytest.raises(OSError):
        _tick(_lane(folder, Reader(), store, notices=Notices(down=True)))
    assert store.refused == {}

    notices = Notices()
    _tick(_lane(folder, Reader(), store, notices=notices))
    assert notices.told_refused == [("bad.eml", "the mail names no sender")]


class GoneFolder(Folder):
    async def files(self) -> list[DroppedFile]:
        raise FileNotFoundError("the share is gone")


def test_a_folder_that_cannot_be_listed_is_told_and_the_tick_fails() -> None:
    notices = Notices()
    lane = _lane(GoneFolder({}), Reader(), Store(), notices=notices)
    with pytest.raises(FileNotFoundError):
        _tick(lane)
    assert notices.told_unreachable == [NOW.date()]


def test_a_reader_that_does_not_answer_marks_nothing() -> None:
    folder = Folder({"1.eml": b"from:a@velatrix.example"})
    store = Store()
    with pytest.raises(ReaderUnavailableError):
        _tick(_lane(folder, Reader(down=True), store))
    assert _tick(_lane(folder, Reader(), store)).stored == ("1.eml",)


def test_internal_mail_is_stored_like_any_other() -> None:
    """Đạt, 2026-11-02: no sender is left out; DW1's model sorts every mail."""
    folder = Folder(
        {
            "1.eml": b"from:hr@vn.proterial.example",
            "2.eml": b"from:design@proterial.example",
            "3.eml": b"from:buyer@velatrix.example",
        }
    )
    tick = _tick(_lane(folder, Reader(), Store()))
    assert tick.stored == ("1.eml", "2.eml", "3.eml")


def test_a_version_naming_ignored_sender_domains_still_reads() -> None:
    """1.7.0 and 1.8.0 carried the key, and a tenant's own version may: it is
    no longer read, and a version holding it must not stop reading."""
    document = yaml.safe_load(
        (REPO / "configs/policies/sales_order_rules@1.8.0.yaml").read_text(encoding="utf-8")
    )
    document["ignored_sender_domains"] = ["proterial.example"]
    rules = OrderRules.model_validate(document)
    assert "ignored_sender_domains" not in rules.model_dump()
    current = load_order_rules(REPO / "configs/policies/sales_order_rules@1.9.0.yaml")
    assert "ignored_sender_domains" not in current.model_dump()


class Holders:
    def __init__(self, members: list[uuid.UUID]) -> None:
        self.members = members
        self.asked: list[frozenset[str]] = []

    async def holding(
        self, tenant_id: uuid.UUID, workspace_id: uuid.UUID, scopes: frozenset[str]
    ) -> list[uuid.UUID]:
        self.asked.append(scopes)
        return self.members


class Inbox:
    def __init__(self) -> None:
        self.sent: dict[str, tuple[list[uuid.UUID], str]] = {}

    async def deliver(
        self,
        context: AccessContext,
        *,
        recipients: Sequence[uuid.UUID],
        source_key: str,
        title: str,
        body: str,
        link: str | None,
    ) -> None:
        assert context.scopes == frozenset() and context.tenant_id == SCOPE.tenant_id.value
        self.sent.setdefault(source_key, (list(recipients), body))


def test_the_people_who_process_the_mailbox_are_told_once_per_file_and_day() -> None:
    pic = uuid.uuid4()
    holders, inbox = Holders([pic]), Inbox()
    notices = MailDropNotices(holders, inbox)

    async def run() -> None:
        await notices.refused(SCOPE, source="bad.eml", reason="the mail names no sender")
        await notices.refused(SCOPE, source="bad.eml", reason="the mail names no sender")
        await notices.unreachable(SCOPE, day=date(2026, 10, 29))
        await notices.unreachable(SCOPE, day=date(2026, 10, 29))
        await notices.unreachable(SCOPE, day=date(2026, 10, 30))

    asyncio.run(run())

    assert holders.asked[0] == frozenset({"sales.inbox.process"})
    assert len(inbox.sent) == 3
    recipients, body = inbox.sent[f"sales.mail_drop.refused:{SCOPE.workspace_id.value}:bad.eml"]
    assert recipients == [pic] and "bad.eml" in body


def test_a_mailbox_no_one_processes_is_logged_not_dropped_silently(
    caplog: pytest.LogCaptureFixture,
) -> None:
    inbox = Inbox()
    asyncio.run(MailDropNotices(Holders([]), inbox).unreachable(SCOPE, day=NOW.date()))
    assert inbox.sent == {}
    assert "no one processes this mailbox" in caplog.text
