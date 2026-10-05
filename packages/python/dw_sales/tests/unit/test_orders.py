"""`OrderCase`: the WIV-03-012 state machine, maker/checker, dispositions and stamps.

Built by hand so each test holds exactly the finding or line it is about; the
intake tests (`test_order_intake.py`) drive the same model from the mock
mailbox. Every refusal named in ticket 02's acceptance list has a test here.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from dw_kernel.errors import ConflictError, DomainError, PermissionDeniedError
from dw_sales.domain.anchors import SourceAnchor
from dw_sales.domain.orders import (
    MAKER_CHECKER_RULE,
    Accepted,
    Actor,
    AskCustomer,
    Capability,
    CloseReason,
    CorrectedBySales,
    Finding,
    FindingCode,
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
    Severity,
    transition,
)
from dw_sales.domain.process import WIV_STEPS, Coverage, Procedure, step

pytestmark = pytest.mark.unit

RULES = "sales_order_rules@1.0.0"
SHA = "a" * 64
T0 = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
# Principal ids, as `AccessContext.principal_id` carries them (fictional).
AN = Actor(user_id=uuid.UUID(int=0xA1))
DIEU = Actor(user_id=uuid.UUID(int=0xD1))
GIANG = Actor(user_id=uuid.UUID(int=0x61))
EXPORT_PIC = Actor(
    user_id=uuid.UUID(int=0xA1), capabilities=frozenset({Capability.ACKNOWLEDGE_EXPORT_CONTROL})
)
S = OrderStatus


def _anchor(cell: str) -> SourceAnchor:
    return SourceAnchor(attachment_id="A1", attachment_sha256=SHA, cell_ref=f"PO!{cell}")


def _po_line(number: int, **values: Any) -> PoLine:
    row = 9 + number
    fields = {
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
            **values,
            "anchors": PoLineAnchors(**{f: _anchor(f"{c}{row}") for f, c in columns.items()}),
        }
    )


def _document(lines: Sequence[PoLine], revision: int = 0) -> PoDocument:
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
    )
    return PoDocument(
        attachment_id="A1",
        attachment_sha256=SHA,
        parser_version="excel_po_reader@1.1.0",
        header=header,
        lines=tuple(lines),
        rows_printed=len(lines),
        regions=("PO",),
    )


def _mapped(code: str) -> LineMapping:
    return LineMapping(status=MappingStatus.EXACT, prv_code=code)


def _basis(code: str | None = "HW-1001", candidates: tuple[str, ...] = ()) -> LineBasis:
    item = (
        ItemBasis(
            prv_code=code,
            uom="m",
            moq=Decimal(6100),
            pack_multiple=Decimal(610),
            standard_lead_time_days=21,
        )
        if code is not None
        else None
    )
    run: tuple[Any, ...] = (
        ("read", "mapping", "uom", "moq", "pack") if item else ("read", "mapping")
    )
    return LineBasis(candidates=candidates, item=item, checks_run=run)


def _line(number: int, mapping: LineMapping | None = None, **values: Any) -> OrderLine:
    mapping = mapping or _mapped(f"HW-{1000 + number}")
    code = mapping.checked_against
    return OrderLine(
        po_line=_po_line(number, **values),
        mapping=mapping,
        basis=_basis(code, mapping.candidates),
    )


def _finding(code: FindingCode, line_no: int | None = None, **values: Any) -> Finding:
    severity = Severity.WARNING if code in _WARNINGS else Severity.ERROR
    return Finding(code=code, severity=severity, line_no=line_no, rule_version=RULES, **values)


_WARNINGS = {
    FindingCode.REQUESTED_DATE_SHORT_LT,
    FindingCode.MISSING_NOC_ESF,
    FindingCode.REVISED_PO,
    FindingCode.REVISION_WITHOUT_BASE,
    FindingCode.CUSTOMER_TEMPORARY,
    FindingCode.SENDER_UNVERIFIED,
}


def _checked(
    findings: Sequence[Finding] = (),
    lines: Sequence[OrderLine] | None = None,
    *,
    revision: int = 0,
    cross_check_required: bool = True,
    mode: Any = "warn",
    message_id: str = "M01",
    **stamps: Any,
) -> OrderCase:
    lines = lines or (_line(1), _line(2))
    received = OrderCase(
        case_id=uuid.UUID(int=1),
        case_version=1,
        customer_code="VLX",
        message_id=message_id,
        received_at=T0,
        document=_document([x.po_line for x in lines], revision),
        lines=tuple(lines),
        status=S.RECEIVED,
    )
    return received.checked(
        findings=findings,
        rules_version=RULES,
        catalog_as_of=T0,
        cross_check_required=cross_check_required,
        export_control_mode=mode,
        **stamps,
    )


def _review(*findings: Finding, lines: Sequence[OrderLine] | None = None, **kw: Any) -> OrderCase:
    return _checked(findings, lines, **kw).start_review()


def _accept(case: OrderCase, key: str, actor: Actor = AN) -> OrderCase:
    return case.dispose(key, Accepted(reason="đã kiểm tra", by=actor.user_id, at=T0), actor)


def _prepared(case: OrderCase | None = None) -> OrderCase:
    return (case or _review()).prepare(AN, T0)


def _uploaded(case: OrderCase | None = None) -> OrderCase:
    return _prepared(case).record_bravo_entry("SO26-1001", AN, T0, entry_compared=True)


def _dates(case: OrderCase) -> dict[int, date]:
    return {line.line_no: date(2026, 11, 27) for line in case.lines}


# --------------------------------------------------------------- happy path --


def test_an_order_walks_wiv_03_012_with_a_new_case_version_at_every_step() -> None:
    checked = _checked()
    review = checked.start_review()
    prepared = review.prepare(AN, T0)
    uploaded = prepared.record_bravo_entry("SO26-1001", AN, T0, entry_compared=True)
    crossed = uploaded.cross_check(DIEU, T0)
    confirmed = crossed.confirm(AN, T0, _dates(crossed))

    steps = [checked, review, prepared, uploaded, crossed, confirmed]
    assert [c.status for c in steps] == [
        S.CHECKED,
        S.IN_REVIEW,
        S.PREPARED,
        S.UPLOADED_TO_BRAVO,
        S.CROSS_CHECKED,
        S.CONFIRMED,
    ]
    assert [c.case_version for c in steps] == [2, 3, 4, 5, 6, 7]
    assert (confirmed.prepared_by, confirmed.bravo_recorded_by, confirmed.cross_checked_by) == (
        AN.user_id,
        AN.user_id,
        DIEU.user_id,
    )
    assert (confirmed.bravo_so_no, confirmed.bravo_entry_compared) == ("SO26-1001", True)
    assert {line.confirmed_delivery_date for line in confirmed.lines} == {date(2026, 11, 27)}
    assert confirmed.confirmed_by == AN.user_id


@pytest.mark.parametrize("required", [True, False])
def test_cross_check_required_decides_whether_an_upload_goes_straight_to_confirmed(
    required: bool,
) -> None:
    uploaded = _uploaded(_review(cross_check_required=required))

    if required:
        with pytest.raises(ConflictError, match="cross-checked before it is confirmed"):
            uploaded.confirm(AN, T0, _dates(uploaded))
        assert (
            uploaded.cross_check(DIEU, T0).confirm(AN, T0, _dates(uploaded)).status is S.CONFIRMED
        )
    else:
        confirmed = uploaded.confirm(AN, T0, _dates(uploaded))
        assert (confirmed.status, confirmed.cross_checked_by) == (S.CONFIRMED, None)


def test_a_move_the_state_machine_does_not_have_is_refused_naming_both_states() -> None:
    with pytest.raises(ConflictError) as refused:
        transition(S.CHECKED, S.CONFIRMED)

    assert refused.value.details == {"from": "checked", "to": "confirmed"}
    with pytest.raises(ConflictError):
        _checked().prepare(AN, T0)


def test_every_line_gets_its_confirmed_date() -> None:
    crossed = _uploaded().cross_check(DIEU, T0)

    with pytest.raises(DomainError, match="every line"):
        crossed.confirm(AN, T0, {1: date(2026, 11, 27)})


# ------------------------------------------------------------ maker/checker --


def test_the_preparer_cannot_cross_check() -> None:
    uploaded = _prepared().record_bravo_entry("SO26-1001", DIEU, T0, entry_compared=True)

    with pytest.raises(ConflictError, match=MAKER_CHECKER_RULE) as refused:
        uploaded.cross_check(AN, T0)
    assert refused.value.details["rule"] == "maker_checker"


def test_the_bravo_recorder_cannot_cross_check() -> None:
    uploaded = _prepared().record_bravo_entry("SO26-1001", DIEU, T0, entry_compared=True)

    with pytest.raises(ConflictError, match=MAKER_CHECKER_RULE):
        uploaded.cross_check(DIEU, T0)
    assert uploaded.cross_check(GIANG, T0).cross_checked_by == GIANG.user_id


def test_whoever_typed_a_corrected_value_still_on_the_case_cannot_cross_check() -> None:
    case = _review(_finding(FindingCode.LINE_TOTAL_MISMATCH, expected="1", actual="2"))
    corrected = case.dispose(
        "line_total_mismatch:-",
        CorrectedBySales(value="total 2", source="printed total misread", by=DIEU.user_id, at=T0),
        DIEU,
    )
    uploaded = _uploaded(corrected)

    assert DIEU.user_id in uploaded.makers
    with pytest.raises(ConflictError, match=MAKER_CHECKER_RULE):
        uploaded.cross_check(DIEU, T0)


def test_whoever_typed_a_prv_code_for_an_unmapped_line_cannot_cross_check() -> None:
    unmapped = _line(2, LineMapping(status=MappingStatus.UNMAPPED))
    case = _review(_finding(FindingCode.CODE_UNMAPPED, 2), lines=(_line(1), unmapped))
    recheck = LineCheck(line=_line(2, _mapped("CB-2009")))

    typed = case.confirm_mapping(2, "CB-2009", DIEU, T0, recheck)

    assert typed.line(2).mapping.hand_entered
    assert typed.finding("code_unmapped:2").disposition.kind == "corrected_by_sales"
    # The typed code is still on the line when its finding is reopened: its
    # author is still a maker, whatever the finding now says.
    reopened = typed.dispose("code_unmapped:2", Open(), AN)
    assert DIEU.user_id in reopened.makers
    uploaded = _uploaded(typed)
    with pytest.raises(ConflictError, match=MAKER_CHECKER_RULE):
        uploaded.cross_check(DIEU, T0)
    assert uploaded.cross_check(GIANG, T0).status is S.CROSS_CHECKED


def test_a_case_whose_cross_checker_is_its_preparer_cannot_exist() -> None:
    """The model's own invariant, which the CHECK on order_cases mirrors (04)."""
    crossed = _uploaded().cross_check(DIEU, T0)

    with pytest.raises(ValidationError, match="maker of the case"):
        OrderCase.model_validate({**dict(crossed), "cross_checked_by": AN.user_id})


# ---------------------------------------------------------- self-check (7-8) --


def test_prepare_is_refused_while_a_blocking_finding_is_open_naming_each() -> None:
    case = _review(
        _finding(FindingCode.PRICE_MISMATCH, 1, expected="0.0420 USD", actual="0.040 USD"),
        _finding(FindingCode.REQUESTED_DATE_SHORT_LT, 2),
    )

    with pytest.raises(ConflictError, match="not complete") as refused:
        case.prepare(AN, T0)
    assert refused.value.details["open_findings"] == [
        "price_mismatch:1",
        "requested_date_short_lt:2",
    ]
    for value in ("0.0420", "0.040"):
        assert value not in str(refused.value) + str(refused.value.details)


def test_missing_noc_esf_left_open_does_not_hold_up_the_preparation() -> None:
    case = _review(_finding(FindingCode.MISSING_NOC_ESF))

    assert case.prepare(AN, T0).status is S.PREPARED


def test_ask_customer_moves_the_case_to_correction_requested() -> None:
    case = _review(_finding(FindingCode.PRICE_MISMATCH, 1))
    with pytest.raises(ConflictError, match="no finding is sent back"):
        case.request_correction()

    asked = case.dispose("price_mismatch:1", AskCustomer(by=AN.user_id, at=T0), AN)
    with pytest.raises(ConflictError, match="not complete"):
        asked.prepare(AN, T0)
    assert asked.request_correction().status is S.CORRECTION_REQUESTED


def test_prepare_is_refused_while_a_candidate_is_not_confirmed() -> None:
    candidate = _line(1, LineMapping(status=MappingStatus.CANDIDATE, candidates=("CB-2005",)))
    case = _review(lines=(candidate, _line(2)))

    with pytest.raises(ConflictError) as refused:
        case.prepare(AN, T0)
    assert refused.value.details["lines_not_mapped"] == [1]
    confirmed = case.confirm_mapping(
        1, "CB-2005", AN, T0, LineCheck(line=_line(1, _mapped("CB-2005")))
    )
    assert confirmed.line(1).mapping.status is MappingStatus.CANDIDATE_CONFIRMED
    assert not confirmed.line(1).mapping.hand_entered
    assert confirmed.prepare(AN, T0).status is S.PREPARED


def test_confirming_a_code_outside_the_candidates_is_refused() -> None:
    ambiguous = _line(
        1, LineMapping(status=MappingStatus.AMBIGUOUS, candidates=("CB-2001", "CB-2002"))
    )
    case = _review(_finding(FindingCode.CODE_AMBIGUOUS, 1), lines=(ambiguous, _line(2)))

    with pytest.raises(ConflictError, match="not among the line's candidates"):
        case.confirm_mapping(1, "CB-2005", AN, T0, LineCheck(line=_line(1, _mapped("CB-2005"))))
    picked = case.confirm_mapping(
        1, "CB-2002", AN, T0, LineCheck(line=_line(1, _mapped("CB-2002")))
    )
    assert picked.line(1).mapping.prv_code == "CB-2002"
    assert picked.line(1).mapping.candidates == ("CB-2001", "CB-2002")


def test_a_line_is_rechecked_against_the_code_confirmed_not_another() -> None:
    candidate = _line(1, LineMapping(status=MappingStatus.CANDIDATE, candidates=("CB-2005",)))
    case = _review(lines=(candidate, _line(2)))

    with pytest.raises(DomainError, match="another item"):
        case.confirm_mapping(1, "CB-2005", AN, T0, LineCheck(line=_line(1, _mapped("CB-2006"))))


def test_a_mapping_finding_is_corrected_by_confirming_the_mapping_not_by_typing() -> None:
    case = _review(_finding(FindingCode.CODE_AMBIGUOUS, 1))

    with pytest.raises(ConflictError, match="confirming the line's mapping"):
        case.dispose(
            "code_ambiguous:1",
            CorrectedBySales(value="CB-2001", source="x", by=AN.user_id, at=T0),
            AN,
        )


@pytest.mark.parametrize(
    ("code", "line", "disposition"),
    [
        (FindingCode.DUPLICATE_PO, None, Accepted(reason="r", by=AN.user_id, at=T0)),
        (FindingCode.CODE_UNMAPPED, 1, Accepted(reason="r", by=AN.user_id, at=T0)),
        (
            FindingCode.PRICE_MISMATCH,
            1,
            CorrectedBySales(value="0.05", source="s", by=AN.user_id, at=T0),
        ),
        (FindingCode.MISSING_NOC_ESF, None, AskCustomer(by=AN.user_id, at=T0)),
    ],
    ids=["duplicate accepted", "unmapped accepted", "price typed", "noc asked"],
)
def test_a_disposition_the_findings_table_does_not_allow_is_refused(
    code: FindingCode, line: int | None, disposition: Any
) -> None:
    stamps: dict[str, Any] = (
        {"duplicate_of_so": "SO26-0919"} if code is FindingCode.DUPLICATE_PO else {}
    )
    case = _review(_finding(code, line), **stamps)

    with pytest.raises(ConflictError, match="cannot be"):
        case.dispose(_finding(code, line).key, disposition, EXPORT_PIC)


def test_a_decision_is_recorded_as_the_actor_who_makes_it() -> None:
    case = _review(_finding(FindingCode.PRICE_MISMATCH, 1))

    with pytest.raises(DomainError, match="its actor's"):
        case.dispose("price_mismatch:1", Accepted(reason="r", by=DIEU.user_id, at=T0), AN)


def test_a_decision_can_be_taken_back_to_open() -> None:
    accepted = _accept(_review(_finding(FindingCode.PRICE_MISMATCH, 1)), "price_mismatch:1")

    assert accepted.dispose("price_mismatch:1", Open(), AN).finding("price_mismatch:1").is_open


def test_customer_unknown_is_confirmed_only_for_the_customer_the_case_was_checked_for() -> None:
    case = _review(_finding(FindingCode.CUSTOMER_UNKNOWN))

    with pytest.raises(ConflictError, match="checked for"):
        case.dispose(
            "customer_unknown:-",
            CorrectedBySales(value="NRV", source="forwarded portal PO", by=AN.user_id, at=T0),
            AN,
        )
    confirmed = case.dispose(
        "customer_unknown:-",
        CorrectedBySales(value="VLX", source="forwarded portal PO", by=AN.user_id, at=T0),
        AN,
    )
    assert not confirmed.finding("customer_unknown:-").is_open


# --------------------------------------------------------------- export (9) --


def test_only_the_export_control_pic_acknowledges_missing_noc_esf() -> None:
    case = _review(_finding(FindingCode.MISSING_NOC_ESF))

    with pytest.raises(PermissionDeniedError):
        _accept(case, "missing_noc_esf:-", DIEU)
    acknowledged = _accept(case, "missing_noc_esf:-", EXPORT_PIC)
    assert acknowledged.status is S.IN_REVIEW


def test_confirmation_is_refused_while_missing_noc_esf_is_open() -> None:
    crossed = _uploaded(_review(_finding(FindingCode.MISSING_NOC_ESF))).cross_check(DIEU, T0)

    with pytest.raises(ConflictError, match="not acknowledged"):
        crossed.confirm(AN, T0, _dates(crossed))
    acknowledged = _accept(crossed, "missing_noc_esf:-", EXPORT_PIC)
    assert acknowledged.status is S.CROSS_CHECKED
    assert acknowledged.confirm(AN, T0, _dates(acknowledged)).status is S.CONFIRMED


def test_block_confirmation_refuses_even_an_acknowledged_missing_noc_esf() -> None:
    case = _review(_finding(FindingCode.MISSING_NOC_ESF), mode="block_confirmation")
    crossed = _uploaded(_accept(case, "missing_noc_esf:-", EXPORT_PIC)).cross_check(DIEU, T0)

    with pytest.raises(ConflictError, match="export control blocks"):
        crossed.confirm(AN, T0, _dates(crossed))


def test_a_short_lead_time_needs_a_pc_date_before_confirmation() -> None:
    case = _accept(
        _review(_finding(FindingCode.REQUESTED_DATE_SHORT_LT, 2)), "requested_date_short_lt:2"
    )
    crossed = _uploaded(case).cross_check(DIEU, T0)

    with pytest.raises(ConflictError, match="no PC-confirmed date") as refused:
        crossed.confirm(AN, T0, _dates(crossed))
    assert refused.value.details["lines"] == [2]
    with pytest.raises(ConflictError, match="not short"):
        crossed.record_pc_confirmation(1, AN, T0)
    agreed = crossed.record_pc_confirmation(2, AN, T0)
    assert agreed.confirm(AN, T0, _dates(agreed)).status is S.CONFIRMED


# ---------------------------------------------------------- edits and Bravo --


def test_recording_the_bravo_entry_needs_the_comparison_statement() -> None:
    with pytest.raises(DomainError, match="compared with the PO"):
        _prepared().record_bravo_entry("SO26-1001", AN, T0, entry_compared=False)


def test_an_edit_in_prepared_reopens_the_self_check_with_a_new_case_version() -> None:
    short = _review(_finding(FindingCode.REQUESTED_DATE_SHORT_LT, 2))
    prepared = _prepared(_accept(short, "requested_date_short_lt:2"))

    edited = prepared.dispose("requested_date_short_lt:2", Open(), AN)

    assert (edited.status, edited.prepared_by) == (S.IN_REVIEW, None)
    assert edited.case_version == prepared.case_version + 1


def test_nothing_is_edited_in_place_after_the_upload() -> None:
    short = _review(_finding(FindingCode.REQUESTED_DATE_SHORT_LT, 2))
    uploaded = _uploaded(_accept(short, "requested_date_short_lt:2"))

    with pytest.raises(ConflictError, match="not edited in uploaded_to_bravo"):
        uploaded.dispose("requested_date_short_lt:2", Open(), AN)


def test_returning_from_the_cross_check_clears_the_preparation_and_the_bravo_entry() -> None:
    uploaded = _uploaded()

    returned = uploaded.return_from_cross_check("sai số lượng dòng 2", DIEU, T0)

    assert returned.status is S.IN_REVIEW
    assert (returned.prepared_by, returned.bravo_so_no, returned.bravo_entry_compared) == (
        None,
        None,
        False,
    )
    assert (returned.returned_by, returned.returned_reason) == (DIEU.user_id, "sai số lượng dòng 2")
    again = returned.prepare(AN, T0).record_bravo_entry("SO26-1001", AN, T0, entry_compared=True)
    assert again.cross_check(DIEU, T0).status is S.CROSS_CHECKED


def test_an_earlier_round_s_preparer_stays_a_maker_after_a_return() -> None:
    # An prepared and keyed round one; Giang re-prepares and re-keys round two.
    returned = _uploaded().return_from_cross_check("sai số lượng dòng 2", DIEU, T0)
    again = returned.prepare(GIANG, T0).record_bravo_entry(
        "SO26-1001", GIANG, T0, entry_compared=True
    )

    assert again.earlier_makers == {AN.user_id}
    assert again.makers == {AN.user_id, GIANG.user_id}
    # Refused by the case itself, with the rule named, before any store sees it.
    with pytest.raises(ConflictError, match="tách nhiệm") as refused:
        again.cross_check(AN, T0)
    assert refused.value.details["rule"] == "maker_checker"
    assert again.cross_check(DIEU, T0).cross_checked_by == DIEU.user_id


def test_the_bravo_recorder_a_change_replaced_stays_a_maker() -> None:
    # An prepared, Giang keyed the first entry, Diệu cross-checked it.
    keyed = _prepared().record_bravo_entry("SO26-1001", GIANG, T0, entry_compared=True)
    crossed = keyed.cross_check(DIEU, T0)
    review = _accept(
        crossed.revise(_revision(crossed, _line(1), _line(2, quantity=Decimal(12200)))),
        "revised_po:-",
    )

    applied = review.apply_change(AN, T0, entry_compared=True)

    assert applied.bravo_recorded_by == AN.user_id
    assert applied.earlier_makers == {GIANG.user_id}
    with pytest.raises(ConflictError, match="tách nhiệm"):
        applied.cross_check(GIANG, T0)
    assert applied.cross_check(DIEU, T0).status is S.CROSS_CHECKED


def test_a_reopened_self_check_keeps_its_first_preparer_as_a_maker() -> None:
    prepared = _prepared(
        _accept(_review(_finding(FindingCode.PRICE_MISMATCH, 2)), "price_mismatch:2")
    )

    reopened = prepared.dispose("price_mismatch:2", Open(), AN)

    assert (reopened.status, reopened.prepared_by) == (S.IN_REVIEW, None)
    assert reopened.earlier_makers == {AN.user_id}


def test_a_case_whose_cross_checker_made_an_earlier_round_cannot_exist() -> None:
    crossed = _uploaded().cross_check(DIEU, T0)

    with pytest.raises(ValidationError, match="maker of the case"):
        OrderCase.model_validate({**dict(crossed), "earlier_makers": {DIEU.user_id}})


# --------------------------------------------------------------- revisions --


def _revision(case: OrderCase, *lines: OrderLine, revision: int = 1) -> OrderCase:
    return _checked(
        (_finding(FindingCode.REVISED_PO, expected=str(revision - 1), actual=str(revision)),),
        lines,
        revision=revision,
        message_id="M07",
    )


def test_a_revision_before_the_upload_supersedes_inside_the_case_and_reruns_the_checks() -> None:
    asked = _review(_finding(FindingCode.PRICE_MISMATCH, 2)).dispose(
        "price_mismatch:2", AskCustomer(by=AN.user_id, at=T0), AN
    )
    waiting = asked.request_correction()

    revised = waiting.revise(_revision(waiting, _line(1), _line(2, unit_price=Decimal("0.05"))))

    assert (revised.case_id, revised.status, revised.message_id) == (
        waiting.case_id,
        S.CHECKED,
        "M07",
    )
    assert revised.header.revision == 1
    assert [old.message_id for old in revised.superseded] == ["M01"]
    assert [(c.line_no, c.field, c.before, c.after) for c in revised.changes] == [
        (2, "unit_price", "0.042", "0.05")
    ]
    assert [f.code for f in revised.findings] == [FindingCode.REVISED_PO]


def test_a_revision_after_the_upload_goes_to_change_review_and_is_cross_checked_again() -> None:
    crossed = _uploaded().cross_check(DIEU, T0)

    review = crossed.revise(_revision(crossed, _line(1), _line(2, quantity=Decimal(12200))))

    assert review.status is S.CHANGE_REVIEW
    assert (review.bravo_so_no, review.cross_checked_by) == ("SO26-1001", None)
    with pytest.raises(ConflictError, match="not all decided"):
        review.apply_change(AN, T0, entry_compared=True)
    decided = _accept(review, "revised_po:-")
    with pytest.raises(DomainError, match="compared with the PO"):
        decided.apply_change(AN, T0, entry_compared=False)
    applied = decided.apply_change(AN, T0, entry_compared=True)
    assert applied.status is S.UPLOADED_TO_BRAVO
    with pytest.raises(ConflictError, match="cross-checked before"):
        applied.confirm(AN, T0, _dates(applied))


def test_a_revision_joins_a_case_only_as_a_checked_revised_po() -> None:
    case = _review()

    with pytest.raises(DomainError, match="revised PO"):
        case.revise(_checked())


# ------------------------------------------------------------------ closing --


def test_a_duplicate_is_closed_as_a_duplicate_and_only_a_duplicate_is() -> None:
    duplicate = _checked((_finding(FindingCode.DUPLICATE_PO),), duplicate_of_so="SO26-0919")

    with pytest.raises(ConflictError, match="closed as a duplicate"):
        duplicate.close(CloseReason.NOT_AN_ORDER, AN, T0)
    closed = duplicate.close(CloseReason.DUPLICATE, AN, T0)
    assert (closed.status, closed.close_reason, closed.duplicate_of_so) == (
        S.CLOSED,
        CloseReason.DUPLICATE,
        "SO26-0919",
    )
    with pytest.raises(ConflictError, match="closed as a duplicate"):
        _checked().close(CloseReason.DUPLICATE, AN, T0)


def test_closed_superseded_names_the_case_that_replaced_it() -> None:
    case = _review()

    with pytest.raises(DomainError, match="names the case"):
        case.close(CloseReason.SUPERSEDED, AN, T0)
    closed = case.close(CloseReason.SUPERSEDED, AN, T0, superseded_by=uuid.UUID(int=9))
    assert closed.superseded_by_case == uuid.UUID(int=9)


def test_a_case_in_bravo_is_not_closed() -> None:
    with pytest.raises(ConflictError, match="cannot move from uploaded_to_bravo to closed"):
        _uploaded().close(CloseReason.CANNOT_SUPPLY, AN, T0)


# ------------------------------------------------------------ the case data --


def test_the_coverage_statement_counts_lines_printed_read_checks_and_findings() -> None:
    case = _checked((_finding(FindingCode.PRICE_MISMATCH, 1),))

    coverage = case.coverage()

    assert (coverage.lines_printed, coverage.lines_read, coverage.regions) == (2, 2, ("PO",))
    assert (coverage.checks_run, coverage.findings) == (10, 1)


def test_a_checked_case_names_the_rules_and_the_snapshot_it_was_checked_with() -> None:
    with pytest.raises(ValidationError, match="names the rules"):
        OrderCase.model_validate({**dict(_checked()), "catalog_as_of": None})
    with pytest.raises(ValidationError, match="other rules"):
        _checked(
            (
                _finding(FindingCode.PRICE_MISMATCH, 1).model_copy(
                    update={"rule_version": "x@0.9.0"}
                ),
            )
        )


def test_a_finding_sits_at_its_level() -> None:
    with pytest.raises(ValidationError, match="about one line"):
        _finding(FindingCode.PRICE_MISMATCH)
    with pytest.raises(ValidationError, match="the PO as a whole"):
        _finding(FindingCode.MISSING_NOC_ESF, 1)
    assert _finding(FindingCode.VALUE_UNCERTAIN).key == "value_uncertain:-"
    assert _finding(FindingCode.VALUE_UNCERTAIN, 3).key == "value_uncertain:3"


def test_a_refused_value_is_named_by_its_field_never_echoed() -> None:
    secret = "VX-\x07HIDDEN-PRICE-0.0420"

    with pytest.raises(ValidationError) as refused:
        _po_line(1, customer_item_code=secret)

    assert "customer_item_code" in str(refused.value)
    assert "HIDDEN-PRICE" not in str(refused.value)


def test_the_suggested_date_and_a_pc_confirmation_name_who_and_when() -> None:
    with pytest.raises(ValidationError, match="who and when"):
        OrderLine.model_validate({**dict(_line(1)), "pc_confirmed_by": AN.user_id})
    assert _line(1).suggested_delivery_date is None
    later = T0 + timedelta(days=1)
    assert (
        OrderLine.model_validate(
            {**dict(_line(1)), "pc_confirmed_by": AN.user_id, "pc_confirmed_at": later}
        ).pc_confirmed_at
        == later
    )


# ------------------------------------------------------------- process map --


def test_every_surveyed_step_is_mapped_once_and_names_real_order_states() -> None:
    ids = [s.step_id for s in WIV_STEPS]
    assert ids == [f"O{n}" for n in range(1, 12)] + [f"Q{n}" for n in range(1, 13)]
    order_states = {
        state for s in WIV_STEPS if s.procedure is Procedure.ORDER_ENTRY for state in s.states
    }
    assert order_states <= {status.value for status in OrderStatus}
    assert {s.step_id for s in WIV_STEPS if s.coverage is Coverage.OUT} == {"O5", "O11"}
    assert step("O9").states == ("cross_checked",)
    with pytest.raises(KeyError):
        step("O12")
