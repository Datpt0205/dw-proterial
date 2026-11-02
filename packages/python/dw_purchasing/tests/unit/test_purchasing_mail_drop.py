"""DW2's drop lane (`purchasing_mail_drop`), over fakes: which files it reads,
which wait, which it refuses for good, which are past the mailbox's term, and
that what it could not do is told to whoever receives requests, never only
logged, and never with a word of the mail in the log."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

import pytest

from dw_kernel.errors import InfrastructureError
from dw_kernel.ids import TenantId, WorkspaceId
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.application.access_context import AccessContext
from dw_platform.application.drop_folder import DroppedFile
from dw_platform.application.rule_versions import ContextScope
from dw_platform.domain.audit import AuditEvent
from dw_platform.domain.messages import EmailAddress, InboundMessage
from dw_purchasing.application.mail_drop import (
    MAIL_DROP_LANE,
    SETTLE,
    DropTick,
    MailDrop,
    MailDropNotices,
    MailFile,
    MailRefused,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
SCOPE = ContextScope(TenantId(uuid.uuid4()), WorkspaceId(uuid.uuid4()))
SUBJECT = "Đề nghị mua 40 bộ găng tay chống cắt"
BODY = "Kính gửi phòng Mua hàng, xin mua găng tay cho tổ ép."


def _message(data: bytes, sender: str, internet_id: str | None = None) -> InboundMessage:
    return InboundMessage(
        message_id="eml-" + hashlib.sha256(data).hexdigest(),
        internet_message_id=internet_id,
        sender=EmailAddress(address=sender),
        subject=SUBJECT,
        received_at=NOW,
        body_text=BODY,
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
    """Reads ``b"from:<address>[|<Message-ID>]"``; anything else is refused."""

    def __init__(self, *, down: bool = False) -> None:
        self.down = down
        self.calls = 0

    async def read_mail(self, data: bytes) -> MailFile | MailRefused:
        self.calls += 1
        if self.down:
            raise InfrastructureError("the reader gave no answer")
        if not data.startswith(b"from:"):
            return MailRefused("the mail names no sender")
        sender, _, internet_id = data[5:].decode().partition("|")
        return MailFile(message=_message(data, sender, internet_id.strip() or None), contents={})


class Store:
    """`MailStorePort` keeping one mail per id and per (Message-ID, sender),
    as the SQL store does."""

    def __init__(self, handled: frozenset[str] = frozenset()) -> None:
        self.handled = set(handled)
        self.stored: dict[str, MailFile] = {}
        self.refused: dict[str, str] = {}
        self.events: list[AuditEvent] = []

    async def handled_sources(self, scope: ContextScope) -> frozenset[str]:
        return frozenset(self.handled)

    async def refuse(self, scope: ContextScope, *, source: str, reason: str) -> None:
        self.handled.add(source)
        self.refused[source] = reason

    async def store(
        self, scope: ContextScope, mail: MailFile, *, source: str, event: AuditEvent
    ) -> bool:
        self.handled.add(source)
        message = mail.message
        twin = message.internet_message_id is not None and any(
            (m.message.internet_message_id, m.message.sender.address)
            == (message.internet_message_id, message.sender.address)
            for m in self.stored.values()
        )
        if message.message_id in self.stored or twin:
            return False
        self.stored[message.message_id] = mail
        self.events.append(event)
        return True


class Notices:
    """`MailDropNoticePort` recording what it was asked to tell; ``down``
    raises as a notification store that does not answer would."""

    def __init__(self, *, down: bool = False) -> None:
        self.down = down
        self.told_refused: list[tuple[str, str]] = []
        self.told_unreachable: list[date] = []

    async def refused(self, scope: ContextScope, *, source: str, reason: str) -> None:
        if self.down:
            raise OSError("notifications down")
        self.told_refused.append((source, reason))

    async def unreachable(self, scope: ContextScope, *, day: date) -> None:
        self.told_unreachable.append(day)


class Term:
    def __init__(self, days: int | None) -> None:
        self.days = days

    async def kept_days(self, scope: ContextScope) -> int | None:
        return self.days


def _lane(
    folder: Folder,
    reader: Reader,
    store: Store,
    notices: Notices | None = None,
    *,
    term: int | None = 365,
) -> MailDrop:
    return MailDrop(
        folder,
        reader,
        store,
        Term(term),
        notices or Notices(),
        FixedClock(NOW),
        Uuid4Generator(),
        max_bytes=64,
    )


def _tick(lane: MailDrop) -> DropTick:
    return asyncio.run(lane.tick(SCOPE))


def test_each_new_eml_file_is_stored_once_audited_as_the_lane() -> None:
    folder = Folder({"1.eml": b"from:an@buyer.example", "note.txt": b"x"})
    store = Store()
    lane = _lane(folder, Reader(), store)

    first, second = _tick(lane), _tick(lane)

    assert first.stored == ("1.eml",) and second.stored == ()
    assert folder.reads == ["1.eml"]
    (event,) = store.events
    assert MAIL_DROP_LANE == "purchasing_mail_drop"
    assert event.action == "purchasing.mail.stored"
    assert event.resource_type == "purchasing.message"
    assert event.details["actor"] == "system:purchasing_mail_drop"
    assert event.details["source"] == "1.eml"
    assert (event.tenant_id, event.workspace_id) == (SCOPE.tenant_id, SCOPE.workspace_id)


def test_a_file_still_arriving_waits_and_is_read_once_it_settles() -> None:
    folder = Folder({"1.eml": b"from:an@buyer.example"}, modified=NOW - timedelta(seconds=5))
    store = Store()
    lane = _lane(folder, Reader(), store)
    assert _tick(lane).waiting == 1 and not store.stored and folder.reads == []
    folder.modified = NOW - SETTLE
    assert _tick(lane).stored == ("1.eml",)


def test_an_empty_file_waits_unread() -> None:
    store, folder = Store(), Folder({"1.eml": b""})
    assert _tick(_lane(folder, Reader(), store)).waiting == 1
    assert not store.handled and folder.reads == []


def test_a_file_handled_before_a_restart_is_not_read_again() -> None:
    folder = Folder({"1.eml": b"from:an@buyer.example"})
    reader = Reader()
    _tick(_lane(folder, reader, Store(handled=frozenset({"1.eml"}))))
    assert reader.calls == 0


def test_a_refused_or_oversized_file_is_refused_once_and_told_once() -> None:
    folder = Folder({"bad.eml": b"garbage", "big.eml": b"from:" + b"x" * 100})
    reader, store, notices = Reader(), Store(), Notices()
    lane = _lane(folder, reader, store, notices)

    first = _tick(lane)
    _tick(lane)

    expected = {"bad.eml": "the mail names no sender", "big.eml": "the file is over 0 MB"}
    assert dict(first.refused) == expected
    # The oversized file is not even opened, let alone handed to the reader.
    assert reader.calls == 1 and folder.reads == ["bad.eml"]
    assert store.refused == expected
    assert dict(notices.told_refused) == expected and len(notices.told_refused) == 2


def test_a_file_over_the_limit_by_what_was_read_is_refused() -> None:
    """The listing said small; the bytes said otherwise (still being written)."""

    class Growing(Folder):
        async def read(self, dropped: DroppedFile, limit: int) -> bytes:
            return b"from:" + b"x" * (limit + 1)

    store = Store()
    tick = _tick(_lane(Growing({"1.eml": b"tiny"}), Reader(), store))
    assert dict(tick.refused) == {"1.eml": "the file is over 0 MB"}


def test_a_refused_file_is_not_refused_again_after_a_restart() -> None:
    folder = Folder({"bad.eml": b"garbage"})
    store, notices = Store(), Notices()
    _tick(_lane(folder, Reader(), store, notices))

    reader = Reader()
    restarted = _tick(_lane(folder, reader, store, notices))

    assert restarted.refused == () and reader.calls == 0
    assert len(notices.told_refused) == 1


def test_a_refusal_no_one_could_be_told_of_is_left_for_the_next_tick() -> None:
    folder = Folder({"bad.eml": b"garbage"})
    store = Store()
    with pytest.raises(OSError):
        _tick(_lane(folder, Reader(), store, Notices(down=True)))
    assert store.refused == {}

    notices = Notices()
    _tick(_lane(folder, Reader(), store, notices))
    assert notices.told_refused == [("bad.eml", "the mail names no sender")]


def test_a_copy_of_a_file_and_one_mail_exported_twice_are_stored_once() -> None:
    folder = Folder(
        {
            "1.eml": b"from:an@buyer.example|<m1@buyer.example>",
            "2.eml": b"from:an@buyer.example|<m1@buyer.example> ",
            "3.eml": b"from:other@buyer.example|<m1@buyer.example>",
        }
    )
    store = Store()
    tick = _tick(_lane(folder, Reader(), store))
    # 2.eml is another file of the same mail; 3.eml shares the Message-ID
    # from another sender, so it is another mail.
    assert tick.stored == ("1.eml", "3.eml")
    assert tick.already_stored == ("2.eml",)
    assert len(store.events) == 2


def test_a_file_written_before_the_mailbox_s_term_is_not_read() -> None:
    """Its mail would be deleted by the next retention pass, and its name is
    forgotten once its term is over: reading it would bring it back."""
    folder = Folder({"old.eml": b"from:an@buyer.example"}, modified=NOW - timedelta(days=31))
    store = Store()
    tick = _tick(_lane(folder, Reader(), store, term=30))
    assert tick.expired == 1 and tick.stored == ()
    assert folder.reads == [] and not store.handled
    # A term long enough reads it; rules naming no term keep every mail.
    assert _tick(_lane(folder, Reader(), Store(), term=60)).stored == ("old.eml",)
    assert _tick(_lane(folder, Reader(), Store(), term=None)).stored == ("old.eml",)


def test_rules_that_do_not_read_end_the_tick_with_nothing_read_or_marked() -> None:
    """Without the tenant's term the lane cannot tell an expired file from a
    new one; it stores nothing until the rules read again."""

    class Unreadable(Term):
        async def kept_days(self, scope: ContextScope) -> int | None:
            raise ValueError("the stored version does not read")

    folder, store = Folder({"1.eml": b"from:an@buyer.example"}), Store()
    lane = MailDrop(
        folder, Reader(), store, Unreadable(None), Notices(), FixedClock(NOW), Uuid4Generator()
    )
    with pytest.raises(ValueError):
        _tick(lane)
    assert folder.reads == [] and not store.handled


class GoneFolder(Folder):
    async def files(self) -> list[DroppedFile]:
        raise FileNotFoundError("the share is gone")


def test_a_folder_that_cannot_be_listed_is_told_and_the_tick_fails() -> None:
    notices = Notices()
    with pytest.raises(FileNotFoundError):
        _tick(_lane(GoneFolder({}), Reader(), Store(), notices))
    assert notices.told_unreachable == [NOW.date()]


def test_a_reader_that_does_not_answer_marks_nothing() -> None:
    folder = Folder({"1.eml": b"from:an@buyer.example"})
    store = Store()
    with pytest.raises(InfrastructureError):
        _tick(_lane(folder, Reader(down=True), store))
    assert not store.handled
    assert _tick(_lane(folder, Reader(), store)).stored == ("1.eml",)


def test_no_word_of_a_mail_reaches_the_log(caplog: pytest.LogCaptureFixture) -> None:
    folder = Folder({"1.eml": b"from:an@buyer.example", "bad.eml": b"garbage"})
    with caplog.at_level(logging.DEBUG):
        _tick(_lane(folder, Reader(), Store()))
    assert caplog.records, "the refusal is logged by file name"
    for text in (SUBJECT, BODY, "an@buyer.example", "garbage"):
        assert text not in caplog.text


class Told:
    """`NoticesPort` keeping the first delivery per source key, as the
    platform's store does."""

    def __init__(self) -> None:
        self.sent: dict[str, tuple[AccessContext, frozenset[str], str, str | None]] = {}

    async def tell(
        self,
        context: AccessContext,
        *,
        scopes: frozenset[str],
        people: Sequence[uuid.UUID] = (),
        excluding: Sequence[uuid.UUID] = (),
        source_key: str,
        title: str,
        body: str,
        link: str | None,
    ) -> None:
        self.sent.setdefault(source_key, (context, scopes, body, link))


def test_whoever_receives_requests_is_told_once_per_file_and_once_a_day() -> None:
    told = Told()
    notices = MailDropNotices(told)

    async def run() -> None:
        await notices.refused(SCOPE, source="bad.eml", reason="the mail names no sender")
        await notices.refused(SCOPE, source="bad.eml", reason="the mail names no sender")
        await notices.unreachable(SCOPE, day=date(2026, 11, 2))
        await notices.unreachable(SCOPE, day=date(2026, 11, 2))
        await notices.unreachable(SCOPE, day=date(2026, 11, 3))

    asyncio.run(run())

    assert len(told.sent) == 3
    workspace = SCOPE.workspace_id.value
    context, scopes, body, link = told.sent[f"purchasing.mail_drop.refused:{workspace}:bad.eml"]
    assert scopes == frozenset({"purchasing.request.intake"})
    assert "bad.eml" in body and link == "/purchasing/mail"
    # Delivered as the lane: its own actor, no scope of its own.
    assert context.scopes == frozenset() and context.roles == frozenset()
    assert (context.tenant_id, context.workspace_id) == (SCOPE.tenant_id.value, workspace)
    assert f"purchasing.mail_drop.unreachable:{workspace}:2026-11-03" in told.sent
