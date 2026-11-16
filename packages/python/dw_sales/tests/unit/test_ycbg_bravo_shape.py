"""Ticket 16: the YCBG in Bravo's shape.

The number Sales records is Bravo's (``RFQ`` + yymmdd + ``-`` + nnn), and
Design's result is read back from Bravo's YCBG export: matched by its number
to the one case waiting on Design, never to a guessed one, and recorded as
the person who uploaded it. The column's own CHECK is tested against the
database in `test_ycbg_exports_db.py`.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from dw_kernel.errors import ConflictError, DomainError, PermissionDeniedError
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.application.malware import ScanVerdict
from dw_sales.adapters.reader_client import client_readers
from dw_sales.adapters.readers.operations import InProcessReaderTransport
from dw_sales.application.worker_service import WorkerService
from dw_sales.application.ycbg_exports import (
    COLUMNS,
    STALE_AFTER,
    YCBG_EXPORT_UPLOADED,
    BravoYcbgLine,
    DesignChecks,
    ExportedYcbg,
    YcbgExportReading,
    YcbgExportService,
    YcbgOutcome,
    parse_export,
)
from dw_sales.domain.master_data import CellValue, ImportedTable, TableRow
from dw_sales.domain.quotes import (
    DeclineReason,
    DesignCheck,
    DesignCheckLine,
    QuoteStatus,
    YcbgNo,
)
from dw_sales.evals.graders import CALLERS, DIEU, READER
from dw_sales.evals.world import ALPHA, BETA, NOW, Caller, Directory, SampleSet, World, open_world
from dw_sales.presentation.routes import YcbgBody
from dw_sales.testing.bravo_ycbg_export import ExportRow, ycbg_export_xlsx
from dw_sales.testing.ycbg_export_store import MemoryYcbgExportStore

REPO = Path(__file__).resolve().parents[5]
M10_YCBG = "RFQ260930-030"
SHA = "a" * 64


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS)


async def _waiting(world: World, ycbg_no: str = M10_YCBG, scope_caller: Caller = DIEU) -> uuid.UUID:
    """M10 recorded under ``ycbg_no`` and sent to Design."""
    seen = await world.process_each(scope_caller, ["M10"])
    case_id = seen["M10"][0].case_id
    assert case_id is not None
    commands = world.services.quote_commands

    def version() -> int:
        return world.quote(case_id).case_version

    context = scope_caller.context()
    await commands.ycbg(context, case_id, case_version=version(), ycbg_no=None)
    await commands.ycbg(context, case_id, case_version=version(), ycbg_no=ycbg_no)
    await commands.design_sent(context, case_id, case_version=version())
    return case_id


def _checks(world: World) -> DesignChecks:
    return DesignChecks(world.store, world.store, FixedClock(NOW), Uuid4Generator())


def _line(
    number: str = M10_YCBG,
    *,
    line_no: int = 1,
    status: str = "close",
    verdict: str | None = "quote",
    bp: str | None = "BP-26-0187",
    reason: str | None = None,
) -> BravoYcbgLine:
    return BravoYcbgLine.model_validate(
        {
            "ycbg_no": number,
            "line_no": line_no,
            "status": status,
            "verdict": verdict,
            "bp_code": bp,
            "reason": reason,
        }
    )


async def _take(world: World, *lines: BravoYcbgLine, caller: Caller = DIEU) -> list[YcbgOutcome]:
    return list(
        await _checks(world).take(caller.context(), ExportedYcbg(tuple(lines)), file_sha256=SHA)
    )


# ------------------------------------------------- the number's shape (1) --


@pytest.mark.parametrize("number", ["RFQ261110-002", "RFQ000101-000", "RFQ991231-999"])
def test_bravos_number_is_the_shape_sales_records(number: str) -> None:
    assert TypeAdapter(YcbgNo).validate_python(number) == number
    assert YcbgBody.model_validate({"case_version": 1, "ycbg_no": number}).ycbg_no == number


REFUSED = [
    "RFQ2611-2",
    "YCBG-2609-030",
    "rfq261110-002",
    "RFQ261110-02",
    "RFQ261110-0021",
    "RFQ2611100-002",
    "RFQ261110002",
    " RFQ261110-002",
    "RFQ261110-002\n",
    "RFQ26111O-002",
]


@pytest.mark.parametrize("number", REFUSED)
def test_any_other_shape_is_refused_by_the_route_body(number: str) -> None:
    with pytest.raises(ValidationError):
        YcbgBody.model_validate({"case_version": 1, "ycbg_no": number})


@pytest.mark.parametrize("number", REFUSED)
async def test_any_other_shape_is_refused_by_the_case(number: str) -> None:
    """The case's own guard, whatever path reaches it (a worker, an eval)."""
    world = _world()
    seen = await world.process_each(DIEU, ["M10"])
    case_id = seen["M10"][0].case_id
    assert case_id is not None
    case = world.quote(case_id)
    # Complete on arrival: DW1 drafted its YCBG at once.
    assert case.status is QuoteStatus.YCBG_DRAFTED

    with pytest.raises(DomainError) as refused:
        case.record_ycbg(number, by=DIEU.user_id, at=NOW)

    assert refused.value.details["field"] == "ycbg_no"
    assert number not in str(refused.value)
    assert case.record_ycbg("RFQ261110-002", by=DIEU.user_id, at=NOW).ycbg is not None


async def test_the_command_refuses_a_number_bravo_cannot_have_given() -> None:
    world = _world()
    seen = await world.process_each(DIEU, ["M10"])
    case_id = seen["M10"][0].case_id
    assert case_id is not None
    commands = world.services.quote_commands
    version = world.quote(case_id).case_version

    with pytest.raises(DomainError):
        await commands.ycbg(DIEU.context(), case_id, case_version=version, ycbg_no="RFQ2611-2")

    assert world.quote(case_id).ycbg is None


# ------------------------------------------------ the draft in Bravo's shape --


async def test_the_draft_carries_the_subject_and_each_lines_customers() -> None:
    world = _world()
    case_id = await _waiting(world)
    service = world.services.quotes.service

    draft = await service.design_request(ALPHA, world.quote(case_id))

    assert draft.description == "見積依頼 KMH-RFQ-260930-02"
    (line,) = draft.lines
    assert (line.direct_customer, line.indirect_customer) == ("KMH", None)
    assert line.description  # the customer's own words for the item


async def test_an_indirect_customer_is_named_as_one_and_the_direct_left_to_sales() -> None:
    world = _world()
    case_id = await _waiting(world)
    service = world.services.quotes.service
    catalog = service.catalog

    class _Indirect:
        """The catalog, with Bravo filing KMH as an indirect customer."""

        def __getattr__(self, name: str) -> object:
            return getattr(catalog, name)

        async def customer_by_code(self, scope: object, code: str) -> object:
            found = await catalog.customer_by_code(scope, code)  # type: ignore[arg-type]
            assert found.data is not None
            return replace(found, data=found.data.model_copy(update={"group": "indirect"}))

    draft = await replace(service, catalog=_Indirect()).design_request(  # type: ignore[arg-type]
        ALPHA, world.quote(case_id)
    )

    (line,) = draft.lines
    assert (line.direct_customer, line.indirect_customer) == (None, "KMH")


# ----------------------------------------------- reading the export's rows --


def _table(*rows: list[CellValue], heading: bool = True) -> ImportedTable:
    titles = [
        COLUMNS[f] for f in ("ycbg_no", "line_no", "status", "design_check", "reason", "bp_code")
    ]
    head: list[list[CellValue]] = [["Phiếu yêu cầu báo giá"]] if heading else []
    body: list[list[CellValue]] = [*head, list(titles), *rows]
    return ImportedTable(
        sheet="YCBG",
        rows=[TableRow(row=i + 1, cells=cells) for i, cells in enumerate(body)],
    )


def test_rows_are_read_by_their_titles_below_a_heading() -> None:
    parsed = parse_export(
        _table(
            [M10_YCBG, 1, "CLOSE", "QUOTE", None, "BP-26-0187"],
            ["RFQ261110-002", "2", " pending ", None, None, None],
            ["RFQ261110-003", 1.0, "Close", "decline", "không làm được", None],
        )
    )

    assert parsed is not None and parsed.rejected == ()
    assert [(line.ycbg_no, line.line_no, line.status, line.verdict) for line in parsed.lines] == [
        (M10_YCBG, 1, "close", "quote"),
        ("RFQ261110-002", 2, "pending", None),
        ("RFQ261110-003", 1, "close", "decline"),
    ]


def test_a_value_outside_bravos_own_is_a_rejected_row_naming_its_column() -> None:
    parsed = parse_export(
        _table(
            [M10_YCBG, 1, "DONE", "QUOTE", None, "BP-1"],
            [M10_YCBG, 1, "CLOSE", "MAYBE", None, "BP-1"],
            [M10_YCBG, "one", "CLOSE", "QUOTE", None, "BP-1"],
        )
    )

    assert parsed is not None and parsed.lines == ()
    assert [r.column for r in parsed.rejected] == [
        COLUMNS["status"],
        COLUMNS["design_check"],
        COLUMNS["line_no"],
    ]
    assert all("DONE" not in r.reason and "MAYBE" not in r.reason for r in parsed.rejected)


def test_a_file_without_every_title_is_not_read_by_position() -> None:
    table = _table([M10_YCBG, 1, "CLOSE", "QUOTE", None, "BP-1"])
    without_bp = ImportedTable(
        sheet="YCBG",
        rows=[TableRow(row=r.row, cells=r.cells[:5]) if r.row == 2 else r for r in table.rows],
    )

    assert parse_export(without_bp) is None


# ------------------------------------------- Design's result, matched (2) --


async def test_a_quote_is_recorded_on_the_one_case_waiting_under_its_number() -> None:
    world = _world()
    case_id = await _waiting(world)
    before = world.quote(case_id)

    (outcome,) = await _take(world, _line())

    assert outcome.outcome == "recorded" and outcome.case_id == case_id
    case = world.quote(case_id)
    assert case.design_check is not None and not case.design_check.declined
    assert case.design_check.read_by == DIEU.user_id
    assert case.design_check.lines[0].bp_code == "BP-26-0187"
    # The status is Design's answer read, never a step it decided.
    assert case.status is QuoteStatus.SENT_TO_DESIGN
    assert case.case_version == before.case_version + 1
    events = [e.action for e in world.store.state(ALPHA).events if e.case_id == case_id]
    assert events[-1] == "quote.design_checked"


async def test_a_decline_is_recorded_for_sales_to_decide_and_declines_nothing() -> None:
    world = _world()
    case_id = await _waiting(world)

    (outcome,) = await _take(world, _line(verdict="decline", bp=None, reason="không có vật liệu"))

    assert outcome.outcome == "recorded" and outcome.declined
    case = world.quote(case_id)
    assert case.status is QuoteStatus.SENT_TO_DESIGN and case.decline is None
    assert case.design_check is not None and case.design_check.declined


async def test_a_number_no_open_request_holds_goes_to_sales_and_onto_no_case() -> None:
    """Acceptance 2: never the nearest number, never the only case waiting."""
    world = _world()
    case_id = await _waiting(world)
    before = world.quote(case_id)

    outcomes = await _take(
        world,
        _line("RFQ260930-031"),  # one digit off the waiting case's
        _line("YCBG-2609-030"),  # the old shape of the same number
    )

    assert [(o.outcome, o.case_id) for o in outcomes] == [
        ("no_case", None),
        ("no_case", None),
    ]
    assert world.quote(case_id) == before


async def test_a_case_not_waiting_on_design_is_not_one_to_record_on() -> None:
    world = _world()
    seen = await world.process_each(DIEU, ["M10"])
    case_id = seen["M10"][0].case_id
    assert case_id is not None
    commands = world.services.quote_commands
    version = world.quote(case_id).case_version
    await commands.ycbg(DIEU.context(), case_id, case_version=version, ycbg_no=M10_YCBG)

    (outcome,) = await _take(world, _line())

    assert outcome.outcome == "no_case"
    assert world.quote(case_id).design_check is None


async def test_another_workspaces_case_under_the_same_number_is_never_found() -> None:
    world = _world()
    case_id = await _waiting(world)

    # The same number read in tenant beta: alpha's waiting case is not found.
    (other,) = await _checks(world).take(
        DIEU.context(BETA), ExportedYcbg((_line(bp="BP-99-0001"),)), file_sha256=SHA
    )

    assert (other.outcome, other.case_id) == ("no_case", None)
    assert world.quote(case_id).design_check is None


async def test_a_line_still_pending_is_not_designs_answer_yet() -> None:
    world = _world()
    case_id = await _waiting(world)

    (outcome,) = await _take(world, _line(status="pending", verdict=None, bp=None))

    assert outcome.outcome == "pending"
    assert world.quote(case_id).design_check is None


@pytest.mark.parametrize(
    "line",
    [
        _line(verdict=None, bp=None),  # closed with no Design Check
        _line(bp=None),  # a QUOTE naming no BP code
        _line(bp="bp 26/0187"),  # not a BP code
        _line(verdict="decline", bp=None, reason=None),  # a DECLINE with no reason
    ],
)
async def test_a_result_that_is_not_one_goes_to_sales(line: BravoYcbgLine) -> None:
    world = _world()
    case_id = await _waiting(world)

    (outcome,) = await _take(world, line)

    assert outcome.outcome == "unreadable"
    assert world.quote(case_id).design_check is None


async def test_lines_other_than_the_requests_go_to_sales() -> None:
    world = _world()
    case_id = await _waiting(world)

    (outcome,) = await _take(world, _line(), _line(line_no=2))

    assert (outcome.outcome, outcome.case_id) == ("lines_differ", case_id)
    assert world.quote(case_id).design_check is None


async def test_the_same_result_read_again_changes_nothing_and_another_goes_to_sales() -> None:
    world = _world()
    case_id = await _waiting(world)
    await _take(world, _line())
    recorded = world.quote(case_id)

    (again,) = await _take(world, _line())
    (other,) = await _take(world, _line(bp="BP-26-0999"))

    assert again.outcome == "unchanged" and other.outcome == "changed"
    assert world.quote(case_id) == recorded


def test_a_check_names_every_line_once_with_what_its_verdict_needs() -> None:
    with pytest.raises(ValidationError):
        DesignCheckLine(line_no=1, verdict="quote")
    with pytest.raises(ValidationError):
        DesignCheckLine(line_no=1, verdict="decline", bp_code="BP-1")
    line = DesignCheckLine(line_no=1, verdict="quote", bp_code="BP-1")
    with pytest.raises(ValidationError):
        DesignCheck(
            ycbg_no=M10_YCBG, lines=(line, line), file_sha256=SHA, read_by=DIEU.user_id, read_at=NOW
        )
    with pytest.raises(ValidationError):
        DesignCheck(
            ycbg_no="RFQ2611-2", lines=(line,), file_sha256=SHA, read_by=DIEU.user_id, read_at=NOW
        )


async def test_a_check_on_another_ycbg_or_before_design_cannot_be_on_the_case() -> None:
    world = _world()
    case_id = await _waiting(world)
    case = world.quote(case_id)
    line = DesignCheckLine(line_no=1, verdict="quote", bp_code="BP-1")
    other = DesignCheck(
        ycbg_no="RFQ261110-002", lines=(line,), file_sha256=SHA, read_by=DIEU.user_id, read_at=NOW
    )

    declined = case.decline_request(by=DIEU.user_id, at=NOW, reason=DeclineReason.COMMERCIAL)

    with pytest.raises(ValidationError):
        case.record_design_check(other)
    with pytest.raises(ConflictError):
        declined.record_design_check(other.model_copy(update={"ycbg_no": M10_YCBG}))


# ------------------------------------------------ the upload and the worker --


CLEAN = ScanVerdict.clean()


class _Scanner:
    def __init__(self, verdict: ScanVerdict = CLEAN) -> None:
        self.verdict = verdict

    async def scan(self, data: bytes) -> ScanVerdict:
        return self.verdict


def _service(world: World, store: MemoryYcbgExportStore, clock: FixedClock) -> YcbgExportService:
    return YcbgExportService(store, world.store, world.services.gate, clock, Uuid4Generator())


def _reading(
    world: World, store: MemoryYcbgExportStore, *, scanner: _Scanner | None = None
) -> YcbgExportReading:
    readers = client_readers(InProcessReaderTransport(), world.policies.order_rules.intake)
    return YcbgExportReading(
        uow=store,
        tables=readers.tables,
        scanner=scanner or _Scanner(),
        access=Directory(CALLERS),
        checks=_checks(world),
        clock=FixedClock(NOW),
        ids=Uuid4Generator(),
    )


EXPORT = ycbg_export_xlsx(
    [
        ExportRow(M10_YCBG, 1, "CLOSE", "QUOTE", None, "BP-26-0187"),
        ExportRow("RFQ260828-044", 1, "CLOSE", "DECLINE", "không có vật liệu"),
        ExportRow("RFQ261110-002", 1, "PENDING"),
    ]
)


async def test_an_uploaded_export_is_queued_then_read_as_the_uploader() -> None:
    world = _world()
    case_id = await _waiting(world)
    store = MemoryYcbgExportStore()

    queued = await _service(world, store, FixedClock(NOW)).upload(
        DIEU.context(), "ycbg.xlsx", EXPORT
    )

    assert queued.status == "queued"
    (event,) = [e for e in store.outbox.events if e.event_type == YCBG_EXPORT_UPLOADED]
    assert event.payload == {"export_id": str(queued.export_id)}
    assert await store(ALPHA).ycbg_exports.content(queued.export_id) == EXPORT

    assert await _reading(world, store).read(ALPHA, queued.export_id) == "export read"

    (read,) = await _service(world, store, FixedClock(NOW)).latest(DIEU.context())
    assert [(o.ycbg_no, o.outcome) for o in read.outcomes] == [
        (M10_YCBG, "recorded"),
        ("RFQ260828-044", "no_case"),
        ("RFQ261110-002", "pending"),
    ]
    assert await store(ALPHA).ycbg_exports.content(queued.export_id) is None
    assert world.quote(case_id).design_check is not None
    # Read again (the outbox delivers twice): nothing more happens.
    assert await _reading(world, store).read(ALPHA, queued.export_id) == "export not queued"
    audited = [e.action for e in store.audit.events]
    assert audited == ["sales.ycbg_export.uploaded", "sales.ycbg_export.read"]
    assert "RFQ" not in str([e.details for e in store.audit.events])


async def test_a_caller_who_may_not_prepare_quotations_cannot_upload() -> None:
    world = _world()
    store = MemoryYcbgExportStore()

    with pytest.raises(PermissionDeniedError):
        await _service(world, store, FixedClock(NOW)).upload(READER.context(), "y.xlsx", EXPORT)
    with pytest.raises(PermissionDeniedError):
        await _service(world, store, FixedClock(NOW)).latest(READER.context())

    assert store.outbox.events == []


@pytest.mark.parametrize(
    ("name", "data", "rule"),
    [
        ("ycbg.pdf", EXPORT, "file_type"),
        ("ycbg.xlsx", b"", "file_empty"),
        ("ycbg.xlsx", b"x" * (2 * 1024 * 1024 + 1), "file_size"),
        ("../ycbg.xlsx", EXPORT, "file_name"),
    ],
    ids=["pdf", "empty", "too_big", "path"],
)
async def test_a_file_that_is_not_an_export_is_refused_at_the_door(
    name: str, data: bytes, rule: str
) -> None:
    world = _world()
    store = MemoryYcbgExportStore()

    with pytest.raises(DomainError) as refused:
        await _service(world, store, FixedClock(NOW)).upload(DIEU.context(), name, data)

    assert refused.value.details["rule"] == rule


async def test_an_upload_is_refused_while_dw1_is_paused() -> None:
    world = _world()
    worker: WorkerService = world.services.worker
    await worker.pause(DIEU.context(), reason="kiểm tra")
    store = MemoryYcbgExportStore()

    with pytest.raises(ConflictError):
        await _service(world, store, FixedClock(NOW)).upload(DIEU.context(), "y.xlsx", EXPORT)


async def test_an_uploader_who_lost_the_scope_records_nothing() -> None:
    world = _world()
    case_id = await _waiting(world)
    store = MemoryYcbgExportStore()
    queued = await _service(world, store, FixedClock(NOW)).upload(DIEU.context(), "y.xlsx", EXPORT)
    reading = _reading(world, store)
    lost = replace(reading, access=type(reading.access)(tuple(c for c in CALLERS if c is not DIEU)))  # type: ignore[call-arg]

    assert await lost.read(ALPHA, queued.export_id) == "export failed"

    assert world.quote(case_id).design_check is None


async def test_an_infected_file_is_failed_unread() -> None:
    world = _world()
    case_id = await _waiting(world)
    store = MemoryYcbgExportStore()
    queued = await _service(world, store, FixedClock(NOW)).upload(DIEU.context(), "y.xlsx", EXPORT)

    reading = _reading(world, store, scanner=_Scanner(ScanVerdict.infected("EICAR")))
    assert await reading.read(ALPHA, queued.export_id) == "export failed"

    (failed,) = await store(ALPHA).ycbg_exports.latest(1)
    assert failed.error == "tệp bị trình quét mã độc chặn" and failed.outcomes == ()
    assert world.quote(case_id).design_check is None


async def test_a_file_without_the_titles_fails_naming_them() -> None:
    world = _world()
    store = MemoryYcbgExportStore()
    other = ycbg_export_xlsx(
        [ExportRow(M10_YCBG, 1, "CLOSE", "QUOTE", None, "BP-1")], titles=["A", "B"]
    )
    queued = await _service(world, store, FixedClock(NOW)).upload(DIEU.context(), "y.xlsx", other)

    assert await _reading(world, store).read(ALPHA, queued.export_id) == "export failed"

    (failed,) = await store(ALPHA).ycbg_exports.latest(1)
    assert failed.error is not None and COLUMNS["design_check"] in failed.error


async def test_an_export_its_event_lost_is_failed_by_the_next_upload() -> None:
    world = _world()
    store = MemoryYcbgExportStore()
    early = await _service(world, store, FixedClock(NOW)).upload(DIEU.context(), "a.xlsx", EXPORT)

    later = FixedClock(NOW + STALE_AFTER + timedelta(minutes=1))
    await _service(world, store, later).upload(DIEU.context(), "b.xlsx", EXPORT)

    stale = await store(ALPHA).ycbg_exports.get(early.export_id)
    assert stale is not None and stale.status == "failed"
    assert await store(ALPHA).ycbg_exports.content(early.export_id) is None


async def test_another_workspaces_exports_are_not_listed() -> None:
    world = _world()
    store = MemoryYcbgExportStore()
    await _service(world, store, FixedClock(NOW)).upload(DIEU.context(), "a.xlsx", EXPORT)

    assert await _service(world, store, FixedClock(NOW)).latest(DIEU.context(BETA)) == []
