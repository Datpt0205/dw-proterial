"""Ticket 17: a PO file with a password, opened with its own mail's password.

The candidates a mail carries (`domain.file_passwords`); what the bytes say
(`adapters.formats`); the door handing a locked file over (`ScannedInbox`);
the wire keeping the candidates out of every repr and error; and the whole
of DW1 over the in-memory world: a locked workbook and a locked PDF whose
mail carries the password are read with every value flagged, the same files
with a wrong password or none are routed `attachment_locked`, and nothing
the reading leaves behind (a stored row, a log record, an audit event, a
span) holds the password.

Every fixture is made here: the sample set's own M01 workbook and M03 PDF,
encrypted at test time with a synthetic password.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import io
import json
import logging
import shutil
import types
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from msoffcrypto.format.ooxml import OOXMLFile
from pydantic import ValidationError
from pypdf import PdfReader, PdfWriter

from dw_kernel.ids import TenantId, WorkspaceId
from dw_observability.telemetry import RecordingTelemetry
from dw_platform.domain.messages import AttachmentContent, InboundMessage
from dw_platform.testing.scanners import NoMalware
from dw_sales.adapters.formats import encrypted, refusal, sniff
from dw_sales.adapters.mock import MockInbox
from dw_sales.adapters.mock.fixtures import ATTACHMENTS_DIR, DATA_DIR
from dw_sales.adapters.reader_client import ClientPoReaders
from dw_sales.adapters.reader_wire import ReaderArgs, ReaderOp, ReaderReply, ReaderRequest
from dw_sales.adapters.readers.operations import InProcessReaderTransport
from dw_sales.application.ports import SalesScope
from dw_sales.application.scanned_inbox import LockedContent, ScannedInbox
from dw_sales.domain.file_passwords import MAX_PASSWORDS, password_candidates
from dw_sales.domain.layouts import COLUMN_FIELDS, HEADER_FIELDS
from dw_sales.domain.orders import OrderCase, RegionFlag
from dw_sales.evals.graders import AN, CALLERS
from dw_sales.evals.world import ALPHA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
# Synthetic, and unlike anything else in the sample set, so a search finds
# only a copy of it.
PASSWORD = "Qz7-Lantern-4417"
WRONG = "Not-The-One-0000"
M01_FILE = "M01_VLX-PO-2609-0118.xlsx"
M03_FILE = "M03_BRN-PO-2609-031.pdf"


def _locked_xlsx(plain: bytes, password: str = PASSWORD) -> bytes:
    out = io.BytesIO()
    OOXMLFile(io.BytesIO(plain)).encrypt(password, out)
    return out.getvalue()


def _locked_pdf(plain: bytes, password: str = PASSWORD) -> bytes:
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(plain)))
    writer.encrypt(user_password=password, owner_password=f"{password}-owner", algorithm="AES-256")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


LOCKED_M01 = _locked_xlsx((ATTACHMENTS_DIR / M01_FILE).read_bytes())
LOCKED_M03 = _locked_pdf((ATTACHMENTS_DIR / M03_FILE).read_bytes())


# ------------------------------------------------------------- candidates --


def test_the_text_after_a_colon_comes_first_then_the_words() -> None:
    mail = "Dear Sales,\nPlease find our PO attached.\nPassword: Abc-123!\nThanks."

    assert password_candidates(mail) == (
        # The only line with a colon: what follows it, as written.
        "Abc-123!",
        # Then each word of 4 characters or more, trailing punctuation stripped.
        "Dear",
        "Sales",
        "Please",
        "find",
        "attached",
        "Password",
        "Abc-123",
        "Thanks",
    )


def test_a_full_width_colon_introduces_a_value_as_an_ascii_one_does() -> None:
    mail = "いつもお世話になっております。\nパスワード\uff1aKp9x7Lm2\n宜しくお願いします。"

    assert password_candidates(mail)[0] == "Kp9x7Lm2"


def test_the_last_colon_on_a_line_wins_and_candidates_are_unique() -> None:
    mail = "Ghi chú: mật khẩu: Zx81-q\nZx81-q\nZx81-q"

    assert password_candidates(mail) == ("Zx81-q", "khẩu")


def test_no_more_than_the_cap_and_nothing_over_64_characters() -> None:
    mail = "\n".join(f"word{index:04d}" for index in range(100)) + "\nkey: " + "x" * 65

    found = password_candidates(mail)

    assert len(found) == MAX_PASSWORDS
    assert all(len(candidate) <= 64 for candidate in found)


# ------------------------------------------------------------- the bytes --


def test_a_locked_workbook_and_pdf_are_encrypted_and_not_refused_by_their_names() -> None:
    assert (encrypted(LOCKED_M01), sniff(LOCKED_M01)) == (True, "encrypted")
    assert (encrypted(LOCKED_M03), sniff(LOCKED_M03)) == (True, "pdf")
    assert refusal("po.xlsx", LOCKED_M01) is None
    assert refusal("po.pdf", LOCKED_M03) is None
    plain = (ATTACHMENTS_DIR / M01_FILE).read_bytes()
    assert not encrypted(plain)
    assert not encrypted((ATTACHMENTS_DIR / M03_FILE).read_bytes())


# ------------------------------------------------------------- the door --


class _Locked:
    """The mock mailbox with M01's workbook locked."""

    def __init__(self, inbox: MockInbox) -> None:
        self._inbox = inbox

    async def list_messages(self, scope: SalesScope) -> list[InboundMessage]:
        return list(await self._inbox.list_messages(scope))

    async def get_message(self, scope: SalesScope, message_id: str) -> InboundMessage | None:
        message = await self._inbox.get_message(scope, message_id)
        if message is None:
            return None
        return message.model_copy(update={"body_text": f"Mật khẩu: {PASSWORD}"})

    async def read_attachment(
        self, scope: SalesScope, message_id: str, attachment_id: str
    ) -> AttachmentContent | None:
        content = await self._inbox.read_attachment(scope, message_id, attachment_id)
        if content is None or attachment_id != "M01-A1":
            return content
        attachment = content.attachment.model_copy(
            update={"size": len(LOCKED_M01), "sha256": hashlib.sha256(LOCKED_M01).hexdigest()}
        )
        return AttachmentContent(attachment=attachment, data=LOCKED_M01)


async def test_the_door_hands_a_locked_file_over_locked_with_its_own_mail() -> None:
    scope = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))
    door = ScannedInbox(
        _Locked(MockInbox.load(scope)),
        NoMalware(),
        ClientPoReaders(InProcessReaderTransport()),
    )

    content = await door.read_attachment(scope, "M01", "M01-A1")

    assert isinstance(content, LockedContent)
    assert content.passwords()[0] == PASSWORD
    # Never shown, never dumped.
    assert PASSWORD not in repr(content)
    assert set(content.model_dump()) == {"attachment", "data"}
    # A file that is not locked is handed over as before.
    plain = await door.read_attachment(scope, "M03", "M03-A1")
    assert plain is not None and not isinstance(plain, LockedContent)


# ------------------------------------------------------------- the wire --


def test_the_candidates_are_in_no_repr_and_no_error() -> None:
    args = ReaderArgs(passwords=(PASSWORD,))
    request = ReaderRequest.of(ReaderOp.PO_READ, data=b"x", args=args)

    assert PASSWORD not in repr(args) and PASSWORD not in repr(request)
    assert PASSWORD in request.model_dump_json()  # sent, to the reader only

    with pytest.raises(ValidationError) as refused:
        ReaderArgs(passwords=(PASSWORD + "x" * 64,))
    assert PASSWORD not in str(refused.value)


class _Spy:
    """The in-process reader, keeping every request and reply it carried."""

    def __init__(self) -> None:
        self.inner = InProcessReaderTransport()
        self.requests: list[ReaderRequest] = []
        self.replies: list[ReaderReply] = []

    async def call(self, request: ReaderRequest) -> ReaderReply:
        self.requests.append(request)
        reply = await self.inner.call(request)
        self.replies.append(reply)
        return reply


# ------------------------------------------------------------- the world --


def _sample(
    tmp_path: Path,
    body: str | None,
    password: str = PASSWORD,
    *,
    into: tuple[str, ...] = ("M01", "M03"),
) -> SampleSet:
    """The sample set with M01's workbook and M03's PDF locked with
    ``password``, and ``body`` (None: as they are) added to the mails
    ``into`` names (both, unless a test writes it elsewhere)."""
    attachments = tmp_path / "attachments"
    data = tmp_path / "data"
    shutil.copytree(ATTACHMENTS_DIR, attachments)
    shutil.copytree(DATA_DIR, data)
    (attachments / M01_FILE).write_bytes(
        _locked_xlsx((ATTACHMENTS_DIR / M01_FILE).read_bytes(), password)
    )
    (attachments / M03_FILE).write_bytes(
        _locked_pdf((ATTACHMENTS_DIR / M03_FILE).read_bytes(), password)
    )
    inbox = data / "inbox.json"
    messages = json.loads(inbox.read_text(encoding="utf-8"))
    for message in messages:
        if message["message_id"] in into and body is not None:
            message["body_text"] += "\n\n" + body
    inbox.write_text(json.dumps(messages, ensure_ascii=False, indent=1), encoding="utf-8")
    return SampleSet(data, attachments)


def _strings(*roots: object) -> Iterator[str]:
    """Every string and byte string reachable from ``roots``, through
    containers, dataclasses, pydantic models and plain objects: what the
    in-memory stores hold, whatever their shape. The customer's stored mail
    is left out (its body is where the password was written, kept whole by
    design), and so are the mailboxes that hold it."""
    skipped = (
        InboundMessage,
        MockInbox,
        ScannedInbox,
        int,
        float,
        complex,
        type,
        types.ModuleType,
        types.FunctionType,
        types.BuiltinFunctionType,
        types.MethodType,
    )
    seen: set[int] = set()
    stack: list[object] = list(roots)
    while stack:
        item = stack.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        if isinstance(item, str):
            yield item
        elif isinstance(item, bytes | bytearray | memoryview):
            yield bytes(item).decode("utf-8", "ignore")
        elif isinstance(item, skipped):
            continue
        elif isinstance(item, dict):
            stack.extend(item.keys())
            stack.extend(item.values())
        elif isinstance(item, list | tuple | set | frozenset):
            stack.extend(item)
        else:
            if dataclasses.is_dataclass(item):
                stack.extend(getattr(item, f.name) for f in dataclasses.fields(item))
            stack.extend(vars(item).values() if hasattr(item, "__dict__") else ())
            for cls in type(item).__mro__:
                for slot in getattr(cls, "__slots__", ()):
                    if isinstance(slot, str) and hasattr(item, slot):
                        stack.append(getattr(item, slot))


def _left_behind(world: World, telemetry: RecordingTelemetry) -> list[str]:
    """Every row the reading wrote (the Sales store, the runtime's runs,
    audit, outbox and ledger, the notifications and stored objects) and
    every span it opened."""
    return list(
        _strings(
            world.store,
            world.runtime,
            world.notifications,
            world.objects,
            world.catalog_store,
            world.draft_store,
            telemetry.spans,
            telemetry.metrics,
        )
    )


async def test_a_locked_workbook_and_pdf_whose_mail_carries_the_password_are_read_flagged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    telemetry = RecordingTelemetry()
    world = open_world(
        REPO,
        _sample(tmp_path, f"Mật khẩu mở file: {PASSWORD}"),
        CALLERS,
        telemetry=telemetry,
    )

    processed = await world.process_each(AN, ["M01", "M03"])

    for message_id, (disposition, case) in processed.items():
        assert (disposition.kind, message_id) == ("case_created", message_id)
        assert isinstance(case, OrderCase)
        document = case.document
        assert document.opened_with_password
        # Every value read waits for a person: each header field, each line's
        # every field and the total carry the flag.
        password = RegionFlag.OPENED_WITH_PASSWORD
        header = {f.field for f in document.header.flags if f.flag is password}
        assert header == set(HEADER_FIELDS)
        for line in document.lines:
            assert {f.field for f in line.flags if f.flag is password} == set(COLUMN_FIELDS)
        if document.total is not None:
            assert password in {f.flag for f in document.total.flags}
        # Every anchor names the customer's file, not the opened bytes.
        message = await world.inbox.get_message(ALPHA, message_id)
        assert message is not None
        (attachment,) = message.attachments
        assert {a.attachment_sha256 for a in document.anchors()} == {attachment.sha256}
        assert {a.derived_sha256 for a in document.anchors()} == {None}
        # The audit says it was opened with a password from its own mail.
        (row,) = [e for e in world.audit(ALPHA) if e.resource_id == message_id]
        assert row.details["encrypted_file"] == (
            f"{attachment.attachment_id}: encrypted, its contents not scannable by ClamAV;"
            " opened in the reader sandbox with a password from its own mail"
        )

    # A person opens the source of each, which the reader opens again with
    # the same mail's password.
    m01 = processed["M01"][1]
    m03 = processed["M03"][1]
    assert m01 is not None and m03 is not None
    sheet = await world.services.sources.order_source(
        AN.context(), m01.case_id, "M01-A1", page=None, sheet="PO"
    )
    page = await world.services.sources.order_source(
        AN.context(), m03.case_id, "M03-A1", page=1, sheet=None
    )
    assert sheet.grid is not None and sheet.grid.cells
    assert page.pdf_base64 is not None
    assert not PdfReader(io.BytesIO(base64.b64decode(page.pdf_base64))).is_encrypted

    # Acceptance 3: the password is in no row, log record, audit event or span.
    left = _left_behind(world, telemetry)
    assert any("VLX-PO-2609-0118" in text for text in left)  # the search sees the rows
    assert [text for text in left if PASSWORD in text] == []
    logged = [r.getMessage() + repr(r.args) + (r.exc_text or "") for r in caplog.records]
    assert [line for line in logged if PASSWORD in line] == []


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        (
            f"Mật khẩu mở file: {WRONG}",
            "the file has a password, and none its mail carries opens it",
        ),
        (None, "the file has a password, and none its mail carries opens it"),
    ],
    ids=["a wrong password", "no password line"],
)
async def test_a_locked_file_its_mail_does_not_open_goes_to_a_person_saying_why(
    tmp_path: Path, body: str | None, reason: str
) -> None:
    world = open_world(REPO, _sample(tmp_path, body), CALLERS)

    processed = await world.process_each(AN, ["M01", "M03"])

    for message_id, (disposition, case) in processed.items():
        attachment_id = f"{message_id}-A1"
        assert (disposition.kind, disposition.reason, case) == (
            "routed_to_sales",
            "attachment_locked",
            None,
        )
        assert disposition.detail == f"{attachment_id}: {reason}"
        (row,) = [e for e in world.audit(ALPHA) if e.resource_id == message_id]
        assert (row.details["reason"], row.details["encrypted_file"]) == (
            "attachment_locked",
            f"{attachment_id}: {reason}",
        )


async def test_a_password_written_in_another_mail_opens_nothing(tmp_path: Path) -> None:
    """The candidates come from the file's own mail only: the password in
    another mail of the same customer (M08, Velatrix's resend) does not
    open M01."""
    world = open_world(REPO, _sample(tmp_path, f"Mật khẩu: {PASSWORD}", into=("M08",)), CALLERS)

    processed = await world.process_each(AN, ["M01"])

    disposition, case = processed["M01"]
    assert (disposition.reason, case) == ("attachment_locked", None)
    assert disposition.detail == (
        "M01-A1: the file has a password, and none its mail carries opens it"
    )


async def test_the_password_travels_in_the_reader_request_only(tmp_path: Path) -> None:
    """Acceptance 4: the candidates go to the reader inside the request, for
    the locked file only, and come back in no reply."""
    spy = _Spy()
    world = open_world(
        REPO, _sample(tmp_path, f"Mật khẩu mở file: {PASSWORD}"), CALLERS, reader=spy
    )

    await world.process_each(AN, ["M01", "M02"])

    carrying = [r for r in spy.requests if PASSWORD in r.args.passwords]
    assert carrying  # the test sees it where it is meant to be
    assert {r.attachment.attachment_id for r in carrying if r.attachment} == {"M01-A1"}
    assert all(r.args.passwords == () for r in spy.requests if r not in carrying)
    assert [r for r in spy.requests if PASSWORD in repr(r)] == []
    assert [r for r in spy.replies if PASSWORD in r.model_dump_json()] == []
