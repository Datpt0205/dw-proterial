"""Ticket 15: a `value_uncertain` is corrected field by field, and the typed
value is what the order carries from then on.

The first half builds cases by hand, so each refusal holds exactly the value
it is about; the second drives M27 (a hidden row, a hidden sheet) through
`OrderIntake.correct_value` against the mock master data, where the checks
really run again. The upload file and the cross-check sheet are
`test_artifacts.py`'s; the store and the API are the integration suites'.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from dw_kernel.errors import ConflictError, DomainError
from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
from dw_sales.adapters.order_rules import PlatformOrderRules, load_order_rules
from dw_sales.adapters.readers import mock_po_readers
from dw_sales.adapters.rfq_excel import ExcelQuoteForms
from dw_sales.application.access import PriceView
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.ports import SalesScope
from dw_sales.application.views import order_case, order_finding
from dw_sales.domain.anchors import SourceAnchor
from dw_sales.domain.order_checks import DOCUMENT_CHECK_CODES
from dw_sales.domain.orders import (
    Accepted,
    Actor,
    AskCustomer,
    CorrectedBySales,
    DeliverySchedule,
    Finding,
    FindingCode,
    FlaggedValue,
    ItemBasis,
    LineBasis,
    LineCheck,
    LineMapping,
    MappingStatus,
    Open,
    OrderCase,
    OrderLine,
    OrderStatus,
    PoDocument,
    PoHeader,
    PoHeaderAnchors,
    PoLine,
    PoLineAnchors,
    Recheck,
    RegionFlag,
    Severity,
    ValueCorrection,
)

pytestmark = pytest.mark.unit

RULES = "sales_order_rules@1.4.0"
SHA = "a" * 64
T0 = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
AN = Actor(user_id=uuid.UUID(int=0xA1))
DIEU = Actor(user_id=uuid.UUID(int=0xD1))
GIANG = Actor(user_id=uuid.UUID(int=0x61))
HIDDEN_ROW = RegionFlag.HIDDEN_ROW
KEY = "value_uncertain:2"


# ------------------------------------------------------------ by hand --


def _anchor(cell: str) -> SourceAnchor:
    return SourceAnchor(attachment_id="A1", attachment_sha256=SHA, cell_ref=f"PO!{cell}")


def _po_line(number: int, flagged: Sequence[str] = ()) -> PoLine:
    fields: dict[str, Any] = {
        "line_no": number,
        "customer_item_code": f"VX-{number:03d}",
        "description": "",
        "quantity": Decimal(6100),
        "uom": "m",
        "unit_price": Decimal("0.042"),
        "amount": Decimal("256.2"),
        "requested_date": date(2026, 11, 27),
    }
    columns = dict(zip(fields, "ABCDEFGH", strict=True))
    return PoLine.model_validate(
        {
            **fields,
            "anchors": PoLineAnchors(
                **{f: _anchor(f"{c}{9 + number}") for f, c in columns.items()}
            ),
            "flags": tuple(FlaggedValue(field=f, flag=HIDDEN_ROW) for f in flagged),
        }
    )


def _line(po_line: PoLine) -> OrderLine:
    code = f"HW-{1000 + po_line.line_no}"
    return OrderLine(
        po_line=po_line,
        mapping=LineMapping(status=MappingStatus.EXACT, prv_code=code),
        basis=LineBasis(
            item=ItemBasis(
                prv_code=code,
                uom="m",
                moq=Decimal(6100),
                pack_multiple=Decimal(610),
                standard_lead_time_days=21,
            ),
            checks_run=("read", "mapping", "uom", "moq", "pack"),
        ),
    )


def _finding(code: FindingCode, line_no: int | None = None, **values: Any) -> Finding:
    severity = Severity.WARNING if code is FindingCode.REQUESTED_DATE_SHORT_LT else Severity.ERROR
    return Finding(code=code, severity=severity, line_no=line_no, rule_version=RULES, **values)


def _uncertain(line_no: int | None = 2, actual: str = "hidden_row") -> Finding:
    return _finding(FindingCode.VALUE_UNCERTAIN, line_no, actual=actual)


def _case(
    *findings: Finding,
    flagged: Sequence[str] = ("quantity", "unit_price"),
    header_flagged: Sequence[str] = (),
    unchecked: Sequence[str] = (),
    price: Decimal | None = None,
    revision: int = 0,
    review: bool = True,
    split: bool = False,
) -> OrderCase:
    second = _po_line(2, flagged)
    if price is not None:
        second = second.model_copy(update={"unit_price": price})
    if split:
        # Line 2's 6100 m over two dates, on the schedule rows under it.
        printed = tuple(
            DeliverySchedule(quantity=Decimal(3050), requested_date=day, anchor=_anchor(cell))
            for day, cell in ((date(2026, 11, 27), "H12"), (date(2026, 12, 11), "H13"))
        )
        anchors = second.anchors.model_copy(update={"requested_date": printed[0].anchor})
        second = PoLine.model_validate(
            {**dict(second), "anchors": anchors, "printed_schedules": printed}
        )
    lines = (_line(_po_line(1)), _line(second))
    header = PoHeader(
        po_no="VLX-PO-2609-0118",
        revision=revision,
        po_date=date(2026, 9, 19),
        currency="USD",
        anchors=PoHeaderAnchors(
            po_no=_anchor("B4"),
            revision=_anchor("E4"),
            po_date=_anchor("B5"),
            currency=_anchor("E5"),
        ),
        flags=tuple(FlaggedValue(field=f, flag=HIDDEN_ROW) for f in header_flagged),
    )
    document = PoDocument(
        attachment_id="A1",
        attachment_sha256=SHA,
        parser_version="excel_po_reader@1.1.0",
        header=header,
        lines=tuple(line.po_line for line in lines),
        rows_printed=2,
        regions=("PO",),
        unchecked_regions=tuple(unchecked),
    )
    received = OrderCase(
        case_id=uuid.UUID(int=1),
        case_version=1,
        customer_code="VLX",
        message_id=f"M0{revision + 1}",
        received_at=T0,
        document=document,
        lines=lines,
        status=OrderStatus.RECEIVED,
    )
    checked = received.checked(
        findings=findings or (_uncertain(),),
        rules_version=RULES,
        catalog_as_of=T0,
        cross_check_required=True,
        export_control_mode="warn",
    )
    return checked.start_review() if review else checked


def _typed(field: str, value: str, actor: Actor = AN) -> ValueCorrection:
    return ValueCorrection(field=field, value=value, by=actor.user_id, at=T0)


def _same_checks(case: OrderCase, key: str, correction: ValueCorrection, actor: Actor) -> Recheck:
    """The checks run again and finding what they found before, raised anew."""
    corrected = case.corrected(key, correction, actor)
    lines = tuple(
        LineCheck(
            line=OrderLine(po_line=line.effective, mapping=line.mapping, basis=line.basis),
            findings=tuple(
                f.model_copy(update={"disposition": Open()})
                for f in case.findings
                if f.line_no == line.line_no
            ),
        )
        for line in corrected.lines
        if line.line_no in corrected.rechecked
    )
    po = tuple(
        f.model_copy(update={"disposition": Open()})
        for f in case.findings
        if f.line_no is None and f.code in DOCUMENT_CHECK_CODES
    )
    return Recheck(lines, po, DOCUMENT_CHECK_CODES)


def _correct(
    case: OrderCase, field: str, value: str, actor: Actor = AN, key: str = KEY
) -> OrderCase:
    correction = _typed(field, value, actor)
    return case.correct_value(key, correction, actor, _same_checks(case, key, correction, actor))


def test_a_correction_is_kept_beside_the_value_as_read() -> None:
    case = _case()

    corrected = _correct(case, "quantity", "6710")

    line = corrected.line(2)
    assert line.po_line.quantity == Decimal(6100)  # the evidence, as read
    assert line.effective.quantity == Decimal(6710)  # what the order carries
    assert line.correction("quantity") == _typed("quantity", "6710")
    assert corrected.document.lines[1].quantity == Decimal(6100)
    assert corrected.case_version == case.case_version + 1


def test_the_finding_is_resolved_only_once_every_flagged_field_is_typed() -> None:
    case = _case()

    half = _correct(case, "quantity", "6710")
    assert half.finding(KEY).is_open
    with pytest.raises(ConflictError, match="self-check is not complete"):
        half.prepare(AN, T0)

    whole = _correct(half, "unit_price", "0.042", actor=DIEU)
    resolved = whole.finding(KEY).disposition
    assert isinstance(resolved, CorrectedBySales)
    # Field names only: the values are on the line, never in the disposition.
    assert (resolved.value, resolved.by) == ("quantity,unit_price", DIEU.user_id)
    assert whole.prepare(AN, T0).status is OrderStatus.PREPARED


def test_a_field_the_finding_did_not_flag_is_refused() -> None:
    case = _case()

    with pytest.raises(DomainError, match="did not flag") as refused:
        case.corrected(KEY, _typed("requested_date", "2026-12-01"), AN)
    assert refused.value.details["field"] == "requested_date"


def test_a_value_is_validated_as_its_fields_type() -> None:
    case = _case()

    for field, value in (("quantity", "sáu nghìn"), ("quantity", "-1"), ("unit_price", "1/2")):
        with pytest.raises(ValidationError) as refused:
            case.corrected(KEY, _typed(field, value), AN)
        assert value not in str(refused.value)  # the input is never echoed


def test_a_line_number_is_confirmed_as_read_never_changed() -> None:
    case = _case(flagged=("line_no", "quantity"))

    with pytest.raises(ConflictError, match="asked of the customer"):
        case.corrected(KEY, _typed("line_no", "3"), AN)
    confirmed = _correct(case, "line_no", "2")
    assert confirmed.line(2).correction("line_no") is not None


def test_a_free_text_correction_of_a_value_uncertain_is_refused() -> None:
    case = _case()

    with pytest.raises(ConflictError, match="field by field"):
        case.dispose(KEY, CorrectedBySales(value="6100", source="bản in", by=AN.user_id, at=T0), AN)
    # Asking the customer is unchanged.
    asked = case.dispose(KEY, AskCustomer(by=AN.user_id, at=T0), AN)
    assert asked.finding(KEY).disposition.kind == "ask_customer"


def test_a_sheet_nothing_reads_is_noted_once_every_flagged_header_value_is_typed() -> None:
    finding = _uncertain(None, "hidden_row,unchecked_region")
    case = _case(finding, header_flagged=("po_date",), unchecked=("Notes",))
    note = CorrectedBySales(value="Notes: ghi chú", source="đã xem", by=AN.user_id, at=T0)
    key = "value_uncertain:-"

    with pytest.raises(ConflictError, match="field by field") as refused:
        case.dispose(key, note, AN)
    assert refused.value.details["fields"] == ["po_date"]

    typed = _correct(case, "po_date", "2026-09-20", key=key)
    # Typed, but the unchecked sheet is still nobody's: no field resolves it.
    assert typed.finding(key).is_open
    assert typed.effective_header.po_date == date(2026, 9, 20)
    assert typed.header.po_date == date(2026, 9, 19)
    assert typed.dispose(key, note, AN).finding(key).disposition == note


def test_the_screen_offers_a_note_only_where_the_case_takes_one() -> None:
    """The findings card offers what `dispose` takes: a free-text value on a
    `value_uncertain` only for the sheet nothing reads, once every flagged
    header value is typed (`OrderCase.takes_value_note`)."""
    prices = PriceView(amounts=True, other_customers=False)
    line = _case()
    finding = _uncertain(None, "hidden_row,unchecked_region")
    sheet = _case(finding, header_flagged=("po_date",), unchecked=("Notes",))
    key = "value_uncertain:-"
    typed = _correct(sheet, "po_date", "2026-09-20", key=key)

    assert order_finding(line, line.finding(KEY), prices).allowed == ["ask_customer"]
    assert order_finding(sheet, sheet.finding(key), prices).allowed == ["ask_customer"]
    assert order_finding(typed, typed.finding(key), prices).allowed == [
        "ask_customer",
        "corrected_by_sales",
    ]


def test_a_revision_s_change_list_carries_the_value_as_entered() -> None:
    """The change list is what the PIC applies in Bravo for a revised order:
    a corrected value of the revision is its after, as in the upload file."""
    revised_po = _finding(FindingCode.REVISED_PO, expected="0", actual="1")
    revision = _case(_uncertain(), revised_po, price=Decimal("0.05"), revision=1, review=False)
    case = _case().revise(revision).start_review()
    assert [(c.line_no, c.field, c.before, c.after) for c in case.changes] == [
        (2, "unit_price", "0.042", "0.05")
    ]

    # Typed back to the price held before: the revision changed no price.
    same = _correct(case, "unit_price", "0.0420")
    assert same.changes == ()
    # Another value typed: a change of its own, from the value held before.
    more = _correct(same, "quantity", "6710")
    assert [(c.line_no, c.field, c.before, c.after) for c in more.changes] == [
        (2, "quantity", "6100", "6710")
    ]
    # And a price typed otherwise is the after of the price's change.
    other = _correct(more, "unit_price", "0.048")
    assert [(c.field, c.after) for c in other.changes] == [
        ("quantity", "6710"),
        ("unit_price", "0.048"),
    ]
    assert Decimal(other.changes[1].before or "") == Decimal("0.042")


def test_whoever_typed_a_value_still_on_the_case_cannot_cross_check() -> None:
    corrected = _correct(_correct(_case(), "quantity", "6710", DIEU), "unit_price", "0.042")
    uploaded = corrected.prepare(AN, T0).record_bravo_entry(
        "SO26-1001", AN, T0, entry_compared=True
    )

    assert DIEU.user_id in uploaded.makers
    with pytest.raises(ConflictError, match="tách nhiệm"):
        uploaded.cross_check(DIEU, T0)
    assert uploaded.cross_check(GIANG, T0).status is OrderStatus.CROSS_CHECKED


def test_a_finding_raised_again_keeps_its_decision_while_its_values_did_not_change() -> None:
    moq = _finding(FindingCode.MOQ_VIOLATION, 2, expected="6100", actual="6000")
    price = _finding(FindingCode.PRICE_MISMATCH, 2, expected="0.04 USD", actual="0.042 USD")
    case = _case(_uncertain(), moq, price)
    for key in ("moq_violation:2", "price_mismatch:2"):
        case = case.dispose(key, Accepted(reason="đã xem", by=AN.user_id, at=T0), AN)
    correction = _typed("unit_price", "0.05")
    same = _same_checks(case, KEY, correction, AN)
    (line,) = same.lines
    # The price check found another price; the MOQ check compared the same.
    moved = price.model_copy(update={"actual": "0.05 USD"})
    findings = tuple(moved if f.code is FindingCode.PRICE_MISMATCH else f for f in line.findings)
    recheck = same._replace(lines=(line.model_copy(update={"findings": findings}),))

    corrected = case.correct_value(KEY, correction, AN, recheck)

    assert corrected.finding("moq_violation:2").disposition.kind == "accepted"
    assert corrected.finding("price_mismatch:2").is_open
    assert corrected.finding("price_mismatch:2").actual == "0.05 USD"


def test_checks_run_on_other_values_or_lines_are_refused() -> None:
    case = _case()
    correction = _typed("quantity", "6710")
    same = _same_checks(case, KEY, correction, AN)
    (line,) = same.lines
    as_read = line.line.model_copy(update={"po_line": case.line(2).po_line})

    with pytest.raises(DomainError, match="other values"):
        case.correct_value(KEY, correction, AN, same._replace(lines=(LineCheck(line=as_read),)))
    with pytest.raises(DomainError, match="other lines"):
        case.correct_value(KEY, correction, AN, same._replace(lines=()))
    other_rules = _uncertain().model_copy(update={"rule_version": "sales_order_rules@9.0.0"})
    with pytest.raises(ConflictError, match="other rules"):
        case.correct_value(
            KEY,
            correction,
            AN,
            same._replace(lines=(line.model_copy(update={"findings": (other_rules,)}),)),
        )


def test_a_value_is_corrected_only_where_values_are_decided() -> None:
    case = _correct(_case(), "quantity", "6710")
    uploaded = (
        _correct(case, "unit_price", "0.042")
        .prepare(AN, T0)
        .record_bravo_entry("SO26-1001", AN, T0, entry_compared=True)
    )

    with pytest.raises(ConflictError, match="not edited in uploaded_to_bravo"):
        uploaded.corrected(KEY, _typed("quantity", "6100"), AN)


def test_a_correction_is_another_maker_s_only_by_its_own_actor() -> None:
    with pytest.raises(DomainError, match="actor's"):
        _case().corrected(KEY, _typed("quantity", "6710", DIEU), AN)


def test_only_a_value_uncertain_is_corrected_field_by_field() -> None:
    case = _case(_uncertain(), _finding(FindingCode.MOQ_VIOLATION, 2, expected="1", actual="2"))

    with pytest.raises(ConflictError, match="not corrected field by field"):
        case.corrected("moq_violation:2", _typed("quantity", "6710"), AN)


# ------------------------------------------------------- M27, for real --

SCOPE = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))
POLICIES = Path(__file__).resolve().parents[5] / "configs" / "policies"


class _NoCases:
    async def cases_for_po(
        self, scope: SalesScope, customer_code: str, po_no: str
    ) -> Sequence[OrderCase]:
        return ()


def _intake() -> OrderIntake:
    return OrderIntake(
        catalog=MockSalesCatalog.load(SCOPE),
        inbox=MockInbox.load(SCOPE),
        reader=mock_po_readers(),
        quote_forms=ExcelQuoteForms(),
        rules=PlatformOrderRules(load_order_rules(POLICIES / "sales_order_rules@1.4.0.yaml")),
        cases=_NoCases(),
        new_case_id=uuid.uuid4,
    )


async def _m27() -> OrderCase:
    message = await MockInbox.load(SCOPE).get_message(SCOPE, "M27")
    assert message is not None
    outcome = await _intake().process(SCOPE, message)
    assert outcome.case is not None
    return outcome.case.start_review()


async def test_a_corrected_price_is_checked_again_and_raises_its_mismatch() -> None:
    case = await _m27()
    assert not any(f.code is FindingCode.PRICE_MISMATCH for f in case.findings)

    corrected = await _intake().correct_value(SCOPE, case, KEY, "unit_price", "0.0475", AN, T0)

    mismatch = corrected.finding("price_mismatch:2")
    assert mismatch.is_open and mismatch.actual == "0.0475 USD"
    # Only the corrected line was checked again; the others are as they were.
    assert [f for f in corrected.findings if f.line_no not in (None, 2)] == [
        f for f in case.findings if f.line_no not in (None, 2)
    ]
    assert corrected.case_version == case.case_version + 1


async def test_a_corrected_amount_is_added_up_with_the_total_again() -> None:
    case = await _m27()

    corrected = await _intake().correct_value(SCOPE, case, KEY, "amount", "300", AN, T0)

    total = corrected.finding("line_total_mismatch:-")
    assert total.is_open and total.expected == "total 10530.4"


async def test_a_value_typed_as_read_reopens_nothing() -> None:
    case = await _m27()
    line = case.line(2)

    for field in sorted(line.po_line.flagged):
        case = await _intake().correct_value(
            SCOPE, case, KEY, field, str(getattr(line.po_line, field)), AN, T0
        )

    assert {f.key for f in case.findings if f.is_open} == {
        "value_uncertain:4",
        "value_uncertain:5",
        "value_uncertain:6",
    }
    assert case.finding(KEY).disposition.kind == "corrected_by_sales"
    assert case.line(2).effective == line.po_line
    assert case.line(2).mapping == line.mapping


async def test_a_corrected_customer_code_is_mapped_again() -> None:
    case = await _m27()
    before = case.line(2).mapping.prv_code

    corrected = await _intake().correct_value(
        SCOPE, case, KEY, "customer_item_code", "CVG-0001", AN, T0
    )

    after = corrected.line(2).mapping
    assert after.status is MappingStatus.EXACT
    assert after.prv_code == case.line(1).mapping.prv_code != before
    item = corrected.line(2).basis.item
    assert item is not None and item.prv_code == after.prv_code


async def test_a_corrected_price_is_hidden_from_who_may_not_read_prices() -> None:
    case = await _intake().correct_value(SCOPE, await _m27(), KEY, "unit_price", "0.0475", AN, T0)
    case = await _intake().correct_value(SCOPE, case, KEY, "quantity", "6710", AN, T0)

    hidden = order_case(
        case,
        assigned_to=None,
        release_manifest_ref=None,
        prices=PriceView(amounts=False, other_customers=False),
    ).model_dump(mode="json")
    shown = order_case(
        case,
        assigned_to=None,
        release_manifest_ref=None,
        prices=PriceView(amounts=True, other_customers=False),
    ).model_dump(mode="json")

    line = next(x for x in hidden["lines"] if x["line_no"] == 2)
    typed = {c["field"]: c["value"] for c in line["corrections"]}
    assert typed == {"unit_price": {"hidden": True}, "quantity": "6710"}
    assert "0.0475" not in str(hidden)
    shown_line = next(x for x in shown["lines"] if x["line_no"] == 2)
    assert {c["field"]: c["value"] for c in shown_line["corrections"]}["unit_price"] == "0.0475"
    # Per field: typed, still uncertain, or as DW1 read it.
    states = line["value_states"]
    assert (states["unit_price"], states["quantity"], states["uom"]) == (
        "hand_entered",
        "hand_entered",
        "uncertain",
    )
    finding = next(f for f in hidden["findings"] if f["key"] == KEY)
    assert finding["fields"] == sorted(case.line(2).po_line.flagged)


# ---------------------------------------- delivery schedules (ticket 21) --


def test_the_dates_of_a_line_split_over_several_schedules_are_asked_not_typed() -> None:
    """One typed date cannot say which printed schedule it is: a flagged date
    on a split line goes back to the customer. Its other values are typed as
    on any line, and the screen offers only those."""
    prices = PriceView(amounts=True, other_customers=False)
    case = _case(flagged=("quantity", "requested_date"), split=True)

    with pytest.raises(ConflictError, match="asked of the customer") as refused:
        case.corrected(KEY, _typed("requested_date", "2026-11-27"), AN)
    assert refused.value.details["rule"] == "printed_schedules"
    assert order_finding(case, case.finding(KEY), prices).fields == ["quantity"]

    typed = _correct(case, "quantity", "6100")
    assert typed.finding(KEY).is_open
    asked = typed.dispose(KEY, AskCustomer(by=AN.user_id, at=T0), AN)
    assert asked.finding(KEY).disposition.kind == "ask_customer"


def test_a_line_printing_one_date_still_has_its_date_typed() -> None:
    prices = PriceView(amounts=True, other_customers=False)
    case = _case(flagged=("quantity", "requested_date"))

    assert order_finding(case, case.finding(KEY), prices).fields == ["quantity", "requested_date"]
    typed = _correct(case, "requested_date", "2026-12-01")
    assert [s.requested_date for s in typed.line(2).effective.schedules] == [date(2026, 12, 1)]
