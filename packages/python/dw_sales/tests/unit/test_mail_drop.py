"""The drop lane's decisions (ticket 43), over fakes: which files it reads,
which wait, which it refuses for good, and whose mail it takes."""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from dw_kernel.ids import TenantId, WorkspaceId
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.domain.audit import AuditEvent
from dw_sales.adapters.policy_files import load_order_rules
from dw_sales.adapters.reader_client import ReaderUnavailableError
from dw_sales.application.mail_drop import (
    SETTLE,
    DroppedFile,
    DropTick,
    MailDrop,
    MailFile,
    MailIntake,
    MailRefused,
)
from dw_sales.application.ports import SalesScope
from dw_sales.domain.messages import EmailAddress, InboundMessage
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
        self.left_out: list[str] = []
        self.events: list[AuditEvent] = []

    async def handled_sources(self, scope: SalesScope) -> frozenset[str]:
        return frozenset(self.handled)

    async def leave_out(self, scope: SalesScope, *, source: str) -> None:
        self.handled.add(source)
        self.left_out.append(source)

    async def store(
        self, scope: SalesScope, mail: MailFile, *, source: str, event: AuditEvent
    ) -> bool:
        self.handled.add(source)
        if mail.message.message_id in self.stored:
            return False
        self.stored[mail.message.message_id] = mail
        self.events.append(event)
        return True


class Intake:
    def __init__(self, intake: MailIntake) -> None:
        self.value = intake

    async def intake(self, scope: SalesScope) -> MailIntake:
        return self.value


def _lane(
    folder: Folder, reader: Reader, store: Store, intake: MailIntake | None = None
) -> MailDrop:
    return MailDrop(
        folder,
        reader,
        store,
        Intake(intake or MailIntake()),
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
    reader = Reader()
    lane = _lane(folder, reader, Store())

    first = _tick(lane)
    _tick(lane)

    assert dict(first.refused) == {
        "bad.eml": "the mail names no sender",
        "big.eml": "the file is over 0 MB",
    }
    assert reader.calls == 1


def test_a_reader_that_does_not_answer_marks_nothing() -> None:
    folder = Folder({"1.eml": b"from:a@velatrix.example"})
    store = Store()
    with pytest.raises(ReaderUnavailableError):
        _tick(_lane(folder, Reader(down=True), store))
    assert _tick(_lane(folder, Reader(), store)).stored == ("1.eml",)


def test_mail_from_an_ignored_domain_is_left_out_and_designs_is_taken() -> None:
    folder = Folder(
        {
            "1.eml": b"from:hr@vn.proterial.example",
            "2.eml": b"from:design@proterial.example",
            "3.eml": b"from:buyer@notproterial.example",
        }
    )
    store = Store()
    intake = MailIntake(
        ignored_domains=("proterial.example",), always_from=frozenset({"design@proterial.example"})
    )

    tick = _tick(_lane(folder, Reader(), store, intake))

    assert tick.left_out == ("1.eml",)
    assert tick.stored == ("2.eml", "3.eml")
    assert "1.eml" in store.handled


@pytest.mark.parametrize(
    ("sender", "taken"),
    [
        ("a@proterial.example", False),
        ("a@vn.proterial.example", False),
        ("A@PROTERIAL.EXAMPLE", False),
        ("a@proterial.example.evil", True),
        ("a@xproterial.example", True),
        ("Design@Proterial.example", True),
    ],
)
def test_an_ignored_domain_covers_its_subdomains_and_nothing_else(sender: str, taken: bool) -> None:
    intake = MailIntake(
        ignored_domains=("proterial.example",), always_from=frozenset({"design@proterial.example"})
    )
    assert intake.takes(EmailAddress(address=sender)) is taken


def test_an_empty_list_takes_every_mail() -> None:
    assert MailIntake().takes(EmailAddress(address="anyone@proterial.example"))


def _rules(**changes: object) -> OrderRules:
    base = load_order_rules(REPO / "configs/policies/sales_order_rules@1.7.0.yaml")
    return OrderRules.model_validate({**base.model_dump(by_alias=True), **changes})


def test_the_platform_rules_ignore_no_domain() -> None:
    assert _rules().ignored_sender_domains == ()


@pytest.mark.parametrize(
    "domains",
    [("Proterial.example",), ("proterial.example", "proterial.example"), ("not a domain",)],
)
def test_ignored_domains_are_lowercase_domains_listed_once(domains: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="ignored_sender_domains"):
        _rules(ignored_sender_domains=domains)
