"""Tickets 19 and 22: one PO number is one case, however the mail carries it.

A mail with three of Velatrix's POs (the sample set's fictional customer and
its fixture files, three attachments) opens three cases on one message, the
inbox shows it once with its three cases, processing it again opens no
second set, and a reply in its thread reaches the three as ticket 24 says. A
portal export naming three PO numbers (`po_groups.per_po`) is three POs. Two
files of the same PO (M45's workbook and print, whose dates differ) are one
case with a blocking `files_disagree` citing both, neither winning. And a
file's name suggests a revision (`revision_hints`), which never decides.
"""

from __future__ import annotations

import hashlib
import uuid
from collections import defaultdict
from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from dw_agent_runtime.model.interpretation import InterpretationPort, ModelUnavailableError
from dw_kernel.errors import ConflictError
from dw_platform.domain.messages import Attachment, AttachmentContent
from dw_sales.adapters.mock.fixtures import ATTACHMENTS_DIR
from dw_sales.adapters.order_rules import load_order_rules
from dw_sales.adapters.readers.export import read_export
from dw_sales.application.views import message_disposition
from dw_sales.domain.dispositions import CaseKind, DispositionKind, MessageDisposition
from dw_sales.domain.order_checks import check_document
from dw_sales.domain.orders import FindingCode, OrderCase, PoDocument, Unreadable
from dw_sales.domain.po_groups import ReadFile, one_per_po, per_po
from dw_sales.domain.print_pairs import one_po
from dw_sales.domain.revision_hints import name_revision
from dw_sales.evals.graders import AN, CALLERS
from dw_sales.evals.recorded import ByPrompt, Recorded
from dw_sales.evals.world import ALPHA, SampleSet, SampleWith, World, open_world

from .test_blank_dates_and_print_pairs import _pair
from .test_portal_export_and_upload import CAPS, MAPPING, REF, _row, export

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
RULES = load_order_rules(REPO / "configs" / "policies" / "sales_order_rules@1.13.0.yaml")
VLX = "an.trinh@velatrix.example"
DAY = datetime(2026, 10, 3, 8, 0, tzinfo=UTC)
PASS = {"spf": "pass", "dkim": "pass", "dmarc": "pass"}
# Three of Velatrix's fixture POs, each its own PO number.
FILES = (
    "M21_VLX-PO-2609-0131.xlsx",
    "M33_VLX-PO-2610-0004.xlsx",
    "M44_VLX-PO-2610-0011.xlsx",
)
NUMBERS = ("VLX-PO-2609-0131", "VLX-PO-2610-0004", "VLX-PO-2610-0011")


def _id(name: str) -> str:
    return f"<{name}@mail.velatrix.example>"


def _mail(
    message_id: str,
    minutes: int,
    *,
    files: Sequence[str] = (),
    references: Sequence[str] = (),
    body: str = "Gửi anh chị 3 PO.",
) -> dict[str, Any]:
    return {
        "message_id": message_id,
        "sender": VLX,
        "subject": f"PO {message_id}",
        "received_at": (DAY + timedelta(minutes=minutes)).isoformat(),
        "body": body,
        "authentication": PASS,
        "internet_message_id": _id(message_id.lower()),
        "references": list(references),
        "attachments": [
            {
                "attachment_id": f"{message_id}-A{index}",
                "name": name,
                "media_type": "application/octet-stream",
                "file": ATTACHMENTS_DIR / name,
            }
            for index, name in enumerate(files, start=1)
        ],
    }


MAILS = [
    _mail("P3", 0, files=FILES),
    _mail("Q1", 30, references=[_id("p3")], body="Nhờ xác nhận ngày giao PO VLX-PO-2610-0004."),
    _mail("Q2", 40, references=[_id("p3")], body="Cảm ơn anh chị, đã nhận."),
]


@pytest.fixture
def sample() -> Iterator[Any]:
    with SampleWith(MAILS) as sample:
        yield sample


def _intent_says(*numbers: str) -> InterpretationPort:
    off = Recorded(failure=ModelUnavailableError("not this step"))
    intent = Recorded(
        raw={"language": "vi", "referenced_number_spans": list(numbers), "kind": "reply_to_case"}
    )
    return ByPrompt(defaultdict(lambda: off, {"sales.message_intent": intent}))


def _world(sample: Any, model: InterpretationPort | None = None) -> World:
    return open_world(REPO, sample, CALLERS, model=model)


async def _three(world: World) -> dict[str, uuid.UUID]:
    """P3 processed: its cases by PO number."""
    ((disposition, _),) = (await world.process_each(AN, ["P3"])).values()
    assert disposition.kind == "case_created", disposition
    logged = world.store.state(ALPHA).messages["P3"].disposition
    cases = [world.order(case_id) for case_id in logged.case_ids]
    return {case.header.po_no: case.case_id for case in cases}


# ---------------------------------------------------- ticket 19: one mail --


async def test_a_mail_with_three_pos_opens_three_cases_whose_lines_are_the_files(
    sample: Any,
) -> None:
    """Acceptance 1."""
    world = _world(sample)
    cases = await _three(world)

    assert sorted(cases) == sorted(NUMBERS)
    state = world.store.state(ALPHA)
    opened = [world.order(case_id) for case_id in cases.values()]
    assert {case.message_id for case in opened} == {"P3"}
    assert len(state.orders) == 3
    # Each case is its own file's lines, with their sources; together, every line.
    assert sorted(case.document.attachment_id or "" for case in opened) == [
        "P3-A1",
        "P3-A2",
        "P3-A3",
    ]
    assert sum(len(case.lines) for case in opened) == sum(
        case.document.rows_printed for case in opened
    )
    for case in opened:
        anchors = {a.attachment_id for line in case.lines for _, a in line.po_line.anchors}
        assert anchors == {case.document.attachment_id}
    # One message, one disposition naming the three, in the mail's order.
    logged = state.messages["P3"].disposition
    assert logged.case_ids == tuple(cases[number] for number in NUMBERS)
    assert len(logged.more_cases) == 2


async def test_the_inbox_shows_the_mail_once_with_its_three_cases(sample: Any) -> None:
    world = _world(sample)
    cases = await _three(world)

    shown = [m for m in await world.services.inbox.messages(AN.context()) if m.message_id == "P3"]

    assert len(shown) == 1
    assert [(c.case_id, c.number) for c in shown[0].disposition.order_cases] == [
        (cases[number], number) for number in NUMBERS
    ]


async def test_processing_the_mail_again_opens_no_second_set(sample: Any) -> None:
    """Acceptance 2: the message's disposition is its key, and every case of
    it is written with it."""
    world = _world(sample)
    await _three(world)

    with pytest.raises(ConflictError):
        await world.process_each(AN, ["P3"])

    assert len(world.store.state(ALPHA).orders) == 3


async def test_a_reply_in_the_thread_naming_one_po_joins_that_case(sample: Any) -> None:
    """Ticket 24's rules over the three cases one message opened."""
    world = _world(sample, _intent_says("VLX-PO-2610-0004"))
    cases = await _three(world)

    ((disposition, _),) = (await world.process_each(AN, ["Q1"])).values()

    assert disposition.kind == "attached_to_case"
    assert disposition.case_id == cases["VLX-PO-2610-0004"]
    assert disposition.reply is not None and disposition.reply.linked_to == "P3"


async def test_a_reply_naming_none_is_offered_the_three_cases(sample: Any) -> None:
    world = _world(sample)
    cases = await _three(world)

    ((disposition, _),) = (await world.process_each(AN, ["Q2"])).values()

    assert (disposition.kind, disposition.reason) == ("routed_to_sales", "reply_to_case")
    (shown,) = [
        m for m in await world.services.inbox.messages(AN.context()) if m.message_id == "Q2"
    ]
    assert {c.case_id: c.number for c in shown.disposition.thread_cases} == {
        case_id: number for number, case_id in cases.items()
    }


async def test_each_case_shows_the_one_mail_it_came_from(sample: Any) -> None:
    """The talk before a case reads every case of the message (`is_on`)."""
    world = _world(sample)
    cases = await _three(world)

    for case_id in cases.values():
        view = await world.services.orders.get(AN.context(), case_id)
        assert view.message_id == "P3"
        assert view.thread_before == []


def test_a_disposition_lists_further_cases_only_on_order_cases_and_once() -> None:
    first, second = uuid.uuid4(), uuid.uuid4()
    on = {"message_id": "P3", "kind": DispositionKind.CASE_CREATED, "case_kind": CaseKind.ORDER}

    disposition = MessageDisposition.model_validate(
        {**on, "case_id": first, "more_cases": (second,)}
    )
    assert disposition.case_ids == (first, second)
    assert disposition.is_on(CaseKind.ORDER, second)
    assert not disposition.is_on(CaseKind.QUOTE, second)
    for refused in (
        {**on, "case_id": first, "more_cases": (first,)},
        {**on, "case_id": first, "case_kind": CaseKind.QUOTE, "more_cases": (second,)},
        {"message_id": "P3", "kind": DispositionKind.NOT_YET_PROCESSED, "more_cases": (second,)},
    ):
        with pytest.raises(ValueError, match="several order cases"):
            MessageDisposition.model_validate(refused)


# ------------------------------------------------- ticket 19: one file --


def _export_content(data: bytes) -> AttachmentContent:
    return AttachmentContent(
        attachment=Attachment(
            attachment_id="A1",
            name="ORD_20261111_133453.csv",
            media_type="application/octet-stream",
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        ),
        data=data,
    )


def _three_po_export() -> PoDocument:
    rows = [
        _row("CVG-0001", "120", "26-11-17", "CVG-PO-2611-0001", "Firm Order"),
        _row("CVG-0003", "300", "26-12-01", "CVG-PO-2612-0101", "Forecast"),
        _row("CVG-0003", "1,500", "26-11-18", "CVG-PO-2611-0002", "Firm Order"),
        _row("CVG-0004", "50", "26-11-20", "CVG-PO-2611-0001", "Firm Order"),
        _row("CVG-0001", "80", "26-11-25", "CVG-PO-2611-0003", "Firm Order"),
    ]
    rows[2][8] = "26-11-06"  # the second PO was issued a day later
    document = read_export(_export_content(export(rows)), MAPPING, CAPS, layout_ref=REF)
    assert not isinstance(document, Unreadable), document
    return document


def test_an_export_naming_three_po_numbers_is_three_pos() -> None:
    document = _three_po_export()

    parts = per_po(document)

    assert [p.header.po_no for p in parts] == [
        "CVG-PO-2611-0001",
        "CVG-PO-2611-0002",
        "CVG-PO-2611-0003",
    ]
    # Every firm line once, numbered within its PO, its sources kept.
    assert [[line.customer_item_code for line in p.lines] for p in parts] == [
        ["CVG-0001", "CVG-0004"],
        ["CVG-0003"],
        ["CVG-0001"],
    ]
    assert sum(len(p.lines) for p in parts) == len(document.lines)
    assert [[line.line_no for line in p.lines] for p in parts] == [[1, 2], [1], [1]]
    assert [p.rows_printed for p in parts] == [2, 1, 1]
    assert parts[0].lines[1].anchors.quantity.cell_ref == "CSV!C5"
    # Each PO dated by its own first row, and named where that row prints it.
    assert [p.header.po_date for p in parts] == [
        date(2026, 11, 5),
        date(2026, 11, 6),
        date(2026, 11, 5),
    ]
    assert parts[1].header.anchors.po_no.cell_ref == "CSV!G4"
    assert parts[1].header.anchors.po_date.cell_ref == "CSV!I4"
    # The forecast rows are the file's, counted once.
    assert [p.forecast_rows for p in parts] == [1, 0, 0]
    for part in parts:
        assert not [
            f for f in check_document(part, RULES) if f.code is not FindingCode.VALUE_UNCERTAIN
        ]


def test_a_file_of_one_po_is_itself() -> None:
    workbook, _ = _pair()

    assert per_po(workbook) == (workbook,)


# ------------------------------------------ ticket 22: one PO, two files --


def test_the_same_po_in_two_files_is_one_po_the_workbook_first() -> None:
    workbook, printed = _pair()

    grouped = one_per_po([ReadFile(printed, "pdf"), ReadFile(workbook, "xlsx")])

    assert not isinstance(grouped, str), grouped
    (paired,) = grouped
    assert paired.attachment_id == workbook.attachment_id
    assert paired.print_copy is not None
    assert paired.print_copy.attachment_id == printed.attachment_id


def test_two_files_of_one_po_that_are_not_one_po_or_three_are_for_sales() -> None:
    workbook, printed = _pair()
    later = printed.model_copy(update={"header": printed.header.model_copy(update={"revision": 1})})
    third = workbook.model_copy(update={"attachment_id": "A3"})

    assert "other revisions or lines" in str(
        one_per_po([ReadFile(workbook, "xlsx"), ReadFile(later, "pdf")])
    )
    assert "more than two attachments" in str(
        one_per_po([ReadFile(workbook, "xlsx"), ReadFile(printed, "pdf"), ReadFile(third, "xlsx")])
    )


def test_a_difference_cites_both_values_and_both_files() -> None:
    workbook, printed = _pair()
    day = workbook.lines[0].requested_date
    assert day is not None
    paired = one_po(
        workbook,
        printed.model_copy(
            update={
                "lines": (
                    printed.lines[0].model_copy(
                        update={"requested_date": day + timedelta(days=7), "unit_price": 9}
                    ),
                    *printed.lines[1:],
                )
            }
        ),
    )
    assert paired is not None

    (finding,) = [f for f in check_document(paired, RULES) if f.code is FindingCode.FILES_DISAGREE]

    assert finding.blocking and finding.line_no is None
    assert finding.expected is not None and finding.actual is not None
    assert finding.expected.startswith(f"{workbook.attachment_id}: ")
    assert finding.actual.startswith(f"{printed.attachment_id}: ")
    ours = workbook.lines[0].anchors.requested_date.cell_ref
    assert f"line 1 requested_date {day.isoformat()} [{ours}]" in finding.expected
    later = (day + timedelta(days=7)).isoformat()
    assert f"line 1 requested_date {later} [p1]" in finding.actual
    # An amount is named by its field and place, never its value: this
    # finding reaches a reader who may not see prices.
    assert "line 1 unit_price [" in finding.expected
    assert "line 1 unit_price [p1]" in finding.actual
    assert "9" not in finding.actual.split("unit_price")[1].split("]")[0]


def test_two_files_that_agree_raise_nothing() -> None:
    workbook, printed = _pair()
    agreeing = printed.model_copy(
        update={
            "lines": (
                printed.lines[0].model_copy(
                    update={"requested_date": workbook.lines[0].requested_date}
                ),
                *printed.lines[1:],
            )
        }
    )
    paired = one_po(workbook, agreeing)
    assert paired is not None

    assert FindingCode.FILES_DISAGREE not in {f.code for f in check_document(paired, RULES)}


async def test_m45_opens_one_case_with_a_blocking_finding_citing_both() -> None:
    """Ticket 22 acceptance 1: M45's workbook and print, whose dates differ."""
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    ((disposition, case),) = (await world.process_each(AN, ["M45"])).values()

    assert isinstance(case, OrderCase), disposition
    assert len(world.store.state(ALPHA).orders) == 1
    finding = case.finding("files_disagree:-")
    assert finding.blocking
    assert finding.expected == "M45-A1: line 1 requested_date 2026-11-16 [PO!H10]"
    assert finding.actual == "M45-A2: line 1 requested_date 2026-11-23 [p1]"
    # Neither file wins: the value the case holds waits for a person.
    assert case.finding("value_uncertain:1").blocking
    view = await world.services.orders.get(AN.context(), case.case_id)
    assert view.print_copy is not None
    ((difference),) = view.print_copy.differences
    assert (difference.ours, difference.theirs) == ("2026-11-16", "2026-11-23")


# ------------------------------------------------- ticket 22: the name --


@pytest.mark.parametrize(
    ("name", "po_no", "hint"),
    [
        ("PO123-R1.xlsx", "PO123", "R1"),
        ("PO123R.xlsx", "PO123", "R"),
        ("PO123-2.pdf", "PO123", "2"),
        ("PO123-RE11.xlsx", "PO123", "RE11"),
        ("PO 123 RV.xlsx", "PO123", "RV"),
        ("po123_rev 2.xlsx", "PO123", "REV2"),
        ("PO123.xlsx", "PO123", None),
        ("PO123-signed.pdf", "PO123", None),
        ("PO123-2026.pdf", "PO123", None),
        ("ORDER-R1.xlsx", "PO123", None),
        ("PO123-R1 (copy).xlsx", "PO123", None),
    ],
)
def test_a_file_name_suggests_a_revision_only_after_the_po_number(
    name: str, po_no: str, hint: str | None
) -> None:
    assert name_revision(name, po_no) == hint


MAILS_NAMED = [
    _mail("N0", 0, files=["M21_VLX-PO-2609-0131.xlsx"]),
]


async def test_a_revision_named_by_the_file_is_shown_and_never_decides() -> None:
    """Ticket 22 acceptance 2: ``VLX-PO-2609-0131-R1.xlsx`` after the same PO
    with no suffix is flagged as a likely revision beside what decides: its
    printed revision and lines are the first's, so it is still a duplicate."""
    named = _mail("N1", 60, files=["M21_VLX-PO-2609-0131.xlsx"])
    named["attachments"][0]["name"] = "VLX-PO-2609-0131-R1.xlsx"
    with SampleWith([*MAILS_NAMED, named]) as sample:
        world = _world(sample)
        seen = await world.process_each(AN, ["N0", "N1"])

    first, second = (seen[m][1] for m in ("N0", "N1"))
    assert isinstance(first, OrderCase) and isinstance(second, OrderCase)
    assert first.document.name_revision is None
    assert second.document.name_revision == "R1"
    assert FindingCode.DUPLICATE_PO in {f.code for f in second.findings}
    view = await world.services.orders.get(AN.context(), second.case_id)
    assert view.name_revision == "R1"


async def test_two_files_of_one_po_printing_other_revisions_route_the_mail_whole() -> None:
    """Norvanta's PO and its Rev.1 in one mail: two files of one PO number
    that are not one PO. Neither is taken: the mail goes to Sales, and no
    case opens for it (all or nothing)."""
    pair = _mail("W2", 0, files=["M04_NRV-PO-26-0457.xlsx", "M07_NRV-PO-26-0457-Rev1.xlsx"])
    pair["sender"] = "hana.westbrook@norvanta.example"
    with SampleWith([pair]) as sample:
        world = _world(sample)
        ((disposition, case),) = (await world.process_each(AN, ["W2"])).values()

    assert case is None
    assert (disposition.kind, disposition.reason) == ("routed_to_sales", "other")
    assert disposition.detail is not None
    assert "NRV-PO-26-0457" in disposition.detail and "other revisions" in disposition.detail
    assert world.store.state(ALPHA).orders == {}


def test_a_rev1_file_name_after_the_po_number_is_a_hint() -> None:
    assert name_revision("M07_NRV-PO-26-0457-Rev1.xlsx", "NRV-PO-26-0457") == "REV1"


async def test_the_processing_audit_names_every_case_of_the_mail(sample: Any) -> None:
    world = _world(sample)
    cases = await _three(world)

    (processed,) = [
        e
        for e in world.audit(ALPHA)
        if e.action == "sales.message.processed" and e.resource_id == "P3"
    ]

    assert processed.details["case_id"] == str(cases[NUMBERS[0]])
    assert processed.details["more_case_ids"] == [str(cases[n]) for n in NUMBERS[1:]]


def test_a_case_the_reader_does_not_see_is_not_listed_on_the_mail() -> None:
    """The inbox lists only the cases the caller may see (`numbers` holds
    those): another PIC's PO of the same mail is left out, not named."""
    first, second = uuid.uuid4(), uuid.uuid4()
    disposition = MessageDisposition(
        message_id="P3",
        kind=DispositionKind.CASE_CREATED,
        case_kind=CaseKind.ORDER,
        case_id=first,
        more_cases=(second,),
    )

    view = message_disposition(disposition, None, None, {first: "PO-A"})

    assert [(c.case_id, c.number) for c in view.order_cases] == [(first, "PO-A")]
