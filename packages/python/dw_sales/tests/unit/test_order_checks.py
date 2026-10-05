"""The order checks, one rule at a time, and the policy fields each one reads.

The golden tests in `test_order_intake.py` show the shipped policy on the mock
emails; these show that each policy value is read (a different value gives a
different answer), where every boundary falls, and that each check stamps
the basis it compared against.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from dw_sales.adapters.order_rules import load_order_rules
from dw_sales.domain.anchors import SourceAnchor
from dw_sales.domain.catalog import BravoOrder, ConvertEntry, Customer, Item, LmeMonth, Quotation
from dw_sales.domain.messages import MailAuthentication
from dw_sales.domain.order_checks import (
    SAME_REVISION_CHANGED,
    MappedLine,
    OrderRules,
    check_customer,
    check_document,
    check_history,
    check_line,
    current_quotation,
    known_uom,
    map_line,
    received_date,
)
from dw_sales.domain.orders import (
    FindingCode,
    FlaggedValue,
    LineBasis,
    LineMapping,
    MappingStatus,
    OrderCase,
    OrderLine,
    OrderStatus,
    PoDocument,
    PoHeader,
    PoHeaderAnchors,
    PoLine,
    PoLineAnchors,
    PrintedTotal,
    RegionFlag,
    Severity,
)

pytestmark = pytest.mark.unit

POLICY = Path(__file__).resolve().parents[5] / "configs" / "policies"
SHIPPED = load_order_rules(POLICY / "sales_order_rules@1.0.0.yaml")
PO_DATE = date(2026, 9, 24)
# 2026-09-24 20:00 UTC is already 25 September in Hanoi.
RECEIVED = datetime(2026, 9, 24, 20, 0, tzinfo=UTC)
SHA = "b" * 64


def _rules(**changes: Any) -> OrderRules:
    dumped = SHIPPED.model_dump(by_alias=True)
    for key, value in changes.items():
        if isinstance(value, dict):
            dumped[key] = {**dumped[key], **value}
        else:
            dumped[key] = value
    return OrderRules.model_validate(dumped)


def _anchor(cell: str = "B10") -> SourceAnchor:
    return SourceAnchor(attachment_id="A1", attachment_sha256=SHA, cell_ref=f"PO!{cell}")


def _po_line(line_no: int = 1, **values: Any) -> PoLine:
    fields: dict[str, Any] = {
        "line_no": line_no,
        "customer_item_code": "NV-CB4-22-GY",
        "description": "",
        "quantity": Decimal(3600),
        "uom": "m",
        "unit_price": Decimal("0.6980"),
        "amount": Decimal("2512.8"),
        "requested_date": date(2026, 12, 4),
    } | values
    anchors = PoLineAnchors(**dict.fromkeys(PoLineAnchors.model_fields, _anchor()))
    return PoLine(**fields, anchors=anchors)


def _document(
    *lines: PoLine, revision: int = 0, po_no: str = "NRV-PO-26-0457", **extra: Any
) -> PoDocument:
    lines = lines or (_po_line(),)
    anchor = _anchor("B4")
    header = PoHeader(
        po_no=po_no,
        revision=revision,
        po_date=PO_DATE,
        currency="USD",
        anchors=PoHeaderAnchors(po_no=anchor, revision=anchor, po_date=anchor, currency=anchor),
        flags=extra.pop("header_flags", ()),
    )
    return PoDocument(
        attachment_id="A1",
        attachment_sha256=SHA,
        parser_version="excel_po_reader@1.1.0",
        header=header,
        lines=lines,
        rows_printed=extra.pop("rows_printed", len(lines)),
        regions=("PO",),
        **extra,
    )


def _item(**overrides: Any) -> Item:
    return Item.model_validate(
        {
            "prv_code": "CB-2007",
            "family": "multi_core_cable",
            "attributes": {
                "cores": 4,
                "stranding": "stranded",
                "gauge": "AWG22",
                "conductor": "tinned_copper",
                "shield": "braid",
                "colour": "grey",
                "packaging": "reel",
                "spec_no": "SP-5406",
            },
            "uom": "m",
            "moq": "3000",
            "pack_multiple": "300",
            "standard_lead_time_days": 35,
        }
        | overrides
    )


def _quotation(**overrides: Any) -> Quotation:
    return Quotation.model_validate(
        {
            "quote_no": "Q26-0122",
            "customer_code": "NRV",
            "prv_code": "CB-2007",
            "unit_price": "0.6980",
            "currency": "USD",
            "uom": "m",
            "moq": "3000",
            "lead_time_days": 28,
            "copper_basis": {"kind": "fixed"},
            "valid_from": "2026-07-01",
            "valid_to": "2026-12-31",
        }
        | overrides
    )


BAND = {"kind": "lme_band", "low_usd_per_tonne": "10500", "high_usd_per_tonne": "11000"}


def _exact(item: Item | None = None) -> MappedLine:
    item = item or _item()
    return MappedLine(
        LineMapping(status=MappingStatus.EXACT, prv_code=item.prv_code), item, item.prv_code
    )


def _run(
    po_line: PoLine | None = None,
    *,
    mapped: MappedLine | None = None,
    quotation: Quotation | None = None,
    lme: LmeMonth | None = None,
    currency: str = "USD",
    rules: OrderRules = SHIPPED,
) -> Any:
    return check_line(
        po_line or _po_line(),
        mapped or _exact(),
        currency=currency,
        po_date=PO_DATE,
        received_at=RECEIVED,
        quotation=quotation,
        lme=lme,
        rules=rules,
    )


def _codes(check: Any) -> list[tuple[str, str | None, str | None]]:
    return [(f.code.value, f.expected, f.actual) for f in check.findings]


# ------------------------------------------------------------------- rules --


def test_the_shipped_rules_stamp_their_version_and_severity_on_a_finding() -> None:
    finding = SHIPPED.finding(FindingCode.REVISED_PO)

    assert (finding.rule_version, finding.severity) == ("sales_order_rules@1.0.0", Severity.WARNING)
    assert SHIPPED.cross_check_required is True
    assert SHIPPED.export_control_mode == "warn"


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"short_lead_time": {"day_basis": "working"}}, "day_basis"),
        ({"short_lead_time": {"from": "order_entry"}}, "from"),
        ({"export_control_mode": "ignore"}, "export_control_mode"),
    ],
    ids=["working days", "unknown start", "unknown export mode"],
)
def test_a_policy_value_the_code_does_not_implement_is_refused(
    change: dict[str, Any], match: str
) -> None:
    with pytest.raises(ValidationError, match=match):
        _rules(**change)


def test_the_received_date_is_the_sales_offices_calendar_day() -> None:
    assert received_date(RECEIVED) == date(2026, 9, 25)


# ----------------------------------------------------------------- mapping --


def test_a_convert_entry_maps_exactly_and_names_its_code() -> None:
    entry = ConvertEntry(customer_code="NRV", customer_item_code="NV-CB4-22-GY", prv_code="CB-2007")

    mapped = map_line(_po_line(), entry=entry, items=[_item()])

    assert (mapped.mapping.status, mapped.mapping.prv_code, mapped.convert_prv_code) == (
        MappingStatus.EXACT,
        "CB-2007",
        "CB-2007",
    )


def test_a_convert_entry_whose_item_is_missing_is_unmapped_not_guessed() -> None:
    entry = ConvertEntry(customer_code="NRV", customer_item_code="NV-CB4-22-GY", prv_code="CB-9999")
    described = _po_line(description="MULTI-CORE CABLE 4C AWG22")

    mapped = map_line(described, entry=entry, items=[_item()])

    assert (mapped.mapping.status, mapped.item, mapped.convert_prv_code) == (
        MappingStatus.UNMAPPED,
        None,
        "CB-9999",
    )


def test_a_description_that_fits_one_item_is_a_candidate_sales_must_confirm() -> None:
    mapped = map_line(
        _po_line(description="MULTI-CORE CABLE 4C AWG22 GREY"), entry=None, items=[_item()]
    )

    assert mapped.mapping.status is MappingStatus.CANDIDATE
    assert mapped.mapping.candidates == ("CB-2007",)
    assert mapped.mapping.prv_code is None and not mapped.mapping.ready
    assert mapped.item is not None and mapped.item.prv_code == "CB-2007"


def test_a_description_that_fits_several_items_is_ambiguous() -> None:
    drum = _item(
        prv_code="CB-2008", attributes={**_item().attributes.model_dump(), "packaging": "drum"}
    )

    mapped = map_line(
        _po_line(description="MULTI-CORE CABLE 4C AWG22"), entry=None, items=[drum, _item()]
    )

    assert (mapped.mapping.status, mapped.mapping.candidates, mapped.item) == (
        MappingStatus.AMBIGUOUS,
        ("CB-2007", "CB-2008"),
        None,
    )


def test_a_description_with_a_word_outside_the_vocabulary_matches_nothing() -> None:
    mapped = map_line(
        _po_line(description="MULTI-CORE CABLE 4C HALOGEN-FREE"), entry=None, items=[_item()]
    )

    assert mapped.mapping.status is MappingStatus.UNMAPPED


def test_of_two_valid_quotations_the_later_issue_applies() -> None:
    older = _quotation(quote_no="Q26-0100", valid_from="2026-01-01")
    newer = _quotation(quote_no="Q26-0122", valid_from="2026-07-01")

    found = current_quotation([older, newer], customer_code="NRV", prv_code="CB-2007", day=PO_DATE)

    assert found is newer


# -------------------------------------------------------------- line checks --


def test_a_clean_line_has_no_finding_and_still_stamps_its_whole_basis() -> None:
    check = _run(quotation=_quotation())

    assert check.findings == ()
    basis = check.line.basis
    assert basis.convert_prv_code == "CB-2007"
    assert basis.item is not None and (basis.item.moq, basis.item.pack_multiple) == (
        Decimal(3000),
        Decimal(300),
    )
    assert basis.quotation is not None
    assert (
        basis.quotation.quote_no,
        basis.quotation.unit_price,
        basis.quotation.lead_time_days,
    ) == (
        "Q26-0122",
        Decimal("0.6980"),
        28,
    )
    assert (basis.lead_time_days, basis.lead_time_source) == (35, "item_standard")
    assert basis.checks_run == (
        "read",
        "mapping",
        "uom",
        "quotation",
        "currency",
        "price",
        "moq",
        "pack",
        "lead_time",
    )


def test_a_price_outside_the_policy_tolerance_is_a_mismatch_and_inside_it_is_not() -> None:
    under = _po_line(unit_price=Decimal("0.6840"))

    assert _codes(_run(under, quotation=_quotation())) == [
        ("price_mismatch", "0.6980 USD", "0.6840 USD")
    ]
    assert (
        _run(
            under, quotation=_quotation(), rules=_rules(price={"relative_tolerance": "0.03"})
        ).findings
        == ()
    )


def test_another_currency_is_a_currency_mismatch_never_a_converted_price() -> None:
    check = _run(_po_line(unit_price=Decimal(105)), quotation=_quotation(), currency="JPY")

    assert _codes(check) == [("currency_mismatch", "USD", "JPY")]
    assert "price" not in check.line.basis.checks_run


@pytest.mark.parametrize(
    ("uom", "item_uom", "expected"),
    [("FT", "m", "m"), ("M", None, "a known unit")],
    ids=["unknown unit", "item unit unknown"],
)
def test_a_unit_that_is_unknown_or_differs_is_a_uom_mismatch_and_skips_quantity_checks(
    uom: str, item_uom: str | None, expected: str
) -> None:
    item = _item(uom=item_uom)
    tiny = _po_line(uom=uom, quantity=Decimal(7), unit_price=Decimal(9))

    check = _run(tiny, mapped=_exact(item), quotation=_quotation())

    assert _codes(check) == [("uom_mismatch", expected, uom)]
    assert not {"price", "moq", "pack"} & set(check.line.basis.checks_run)


def test_a_known_unit_is_read_whatever_its_case() -> None:
    assert (known_uom("M"), known_uom("m"), known_uom("FT")) == ("m", "m", None)


def test_without_a_quotation_the_items_moq_applies() -> None:
    check = _run(_po_line(quantity=Decimal(2800)))

    assert _codes(check) == [
        ("quotation_missing", "valid on 2026-09-24", None),
        ("moq_violation", "3000", "2800"),
        ("pack_multiple", "300", "2800"),
    ]
    assert check.line.basis.quotation is None


def test_a_banded_quotation_is_held_to_the_policys_lme_month_and_stamps_it() -> None:
    banded = _quotation(copper_basis=BAND)
    inside = LmeMonth(month="2026-08", usd_per_tonne=Decimal(10600))
    outside = LmeMonth(month="2026-08", usd_per_tonne=Decimal(11000))

    clean = _run(quotation=banded, lme=inside)
    assert clean.findings == ()
    assert clean.line.basis.lme is not None
    assert (clean.line.basis.lme.month, clean.line.basis.lme.usd_per_tonne) == (
        "2026-08",
        Decimal(10600),
    )
    assert _codes(_run(quotation=banded, lme=outside)) == [
        ("lme_band_mismatch", "10500-11000 USD/t", "11000 USD/t (2026-08)")
    ]
    assert _codes(_run(quotation=banded, lme=None)) == [
        ("lme_band_mismatch", "10500-11000 USD/t", "no LME price for 2026-08")
    ]
    same_month = _rules(lme_band={"months_before_po_date": 0})
    with pytest.raises(ValueError, match="checked against LME 2026-09"):
        _run(quotation=banded, lme=inside, rules=same_month)


def test_a_short_lead_time_counts_from_the_received_date_and_the_suggestion_follows() -> None:
    # Received 25 September (Hanoi) + 35 days = 30 October.
    asked = _po_line(requested_date=date(2026, 10, 29))

    check = _run(asked, quotation=_quotation())

    assert _codes(check) == [("requested_date_short_lt", "2026-10-30", "2026-10-29")]
    assert check.line.suggested_delivery_date == date(2026, 10, 30)
    on_time = _run(_po_line(requested_date=date(2026, 10, 30)), quotation=_quotation())
    assert on_time.findings == ()
    assert on_time.line.suggested_delivery_date == date(2026, 10, 30)


def test_the_policy_chooses_the_start_day_and_the_lead_time_table() -> None:
    asked = _po_line(requested_date=date(2026, 10, 29))

    from_po_date = _run(
        asked, quotation=_quotation(), rules=_rules(short_lead_time={"from": "po_date"})
    )
    quoted = _run(
        asked, quotation=_quotation(), rules=_rules(short_lead_time={"lead_time": "quotation"})
    )

    # From the PO date (24 September) + 35 days is 29 October: not short.
    assert from_po_date.findings == ()
    assert from_po_date.line.suggested_delivery_date == date(2026, 10, 29)
    assert quoted.findings == ()
    assert (quoted.line.basis.lead_time_days, quoted.line.basis.lead_time_source) == (
        28,
        "quotation",
    )


def test_an_unmapped_line_raises_its_mapping_finding_and_has_no_item_basis() -> None:
    mapped = MappedLine(LineMapping(status=MappingStatus.UNMAPPED), None)

    check = _run(mapped=mapped)

    assert _codes(check) == [("code_unmapped", None, "NV-CB4-22-GY")]
    assert (check.line.basis.item, check.line.suggested_delivery_date) == (None, None)


def test_a_line_read_from_a_flagged_region_is_value_uncertain() -> None:
    hidden = _po_line(
        flags=(
            FlaggedValue(field="quantity", flag=RegionFlag.HIDDEN_ROW),
            FlaggedValue(field="unit_price", flag=RegionFlag.FONT_MATCHES_FILL),
        )
    )

    assert _codes(_run(hidden, quotation=_quotation())) == [
        ("value_uncertain", None, "font_matches_fill,hidden_row")
    ]


def test_a_quotation_for_another_item_or_day_is_a_bug_not_a_finding() -> None:
    with pytest.raises(ValueError, match="quotation for its item and date"):
        _run(quotation=_quotation(prv_code="CB-2008"))


# ----------------------------------------------------------- completeness --


def test_a_complete_po_raises_nothing() -> None:
    total = PrintedTotal(amount=Decimal("5025.6"), anchor=_anchor("G12"))

    assert check_document(_document(_po_line(1), _po_line(2), total=total), SHIPPED) == ()


@pytest.mark.parametrize(
    ("lines", "rows", "total", "expected", "actual"),
    [
        ((1, 2, 4), 3, None, "lines 1-3", "lines 1-2, 4"),
        ((1, 2), 3, None, "lines 1-3", "lines 1-2"),
        ((1, 2), 2, "5000", "total 5000", "sum of lines 5025.6"),
    ],
    ids=["a number skipped", "a row not read", "total differs"],
)
def test_a_po_whose_lines_do_not_add_up_is_line_total_mismatch(
    lines: tuple[int, ...], rows: int, total: str | None, expected: str, actual: str
) -> None:
    printed = PrintedTotal(amount=Decimal(total), anchor=_anchor("G12")) if total else None
    document = _document(*(_po_line(n) for n in lines), rows_printed=rows, total=printed)

    (finding,) = check_document(document, SHIPPED)

    assert (finding.code, finding.line_no, finding.expected, finding.actual) == (
        FindingCode.LINE_TOTAL_MISMATCH,
        None,
        expected,
        actual,
    )


def test_a_flagged_header_or_an_unchecked_sheet_is_value_uncertain_on_the_po() -> None:
    document = _document(
        header_flags=(FlaggedValue(field="po_no", flag=RegionFlag.HIDDEN_COLUMN),),
        unchecked_regions=("Notes",),
    )

    (finding,) = check_document(document, SHIPPED)

    assert (finding.code, finding.line_no, finding.actual) == (
        FindingCode.VALUE_UNCERTAIN,
        None,
        "hidden_column,unchecked_region",
    )


# ------------------------------------------------------- customer and sender --


def _customer(**overrides: Any) -> Customer:
    compliance = {
        "noc_confirmed": True,
        "esf_fiscal_year": 2026,
        "denial_list_checked_on": "2026-09-01",
    }
    return Customer.model_validate(
        {
            "code": "NRV",
            "name": "Norvanta Automotive Components Vietnam Co., Ltd.",
            "email_domains": ["norvanta.example"],
            "contacts": [{"address": "po-desk@norvanta.example"}],
            "language": "en",
            "intra_group": False,
            "compliance": compliance | overrides.pop("compliance", {}),
            "status": "official",
            "confirmation_channel": "email",
            "sales_pic": None,
        }
        | overrides
    )


def _customer_findings(customer: Customer, *, rules: OrderRules = SHIPPED, **kw: Any) -> list[str]:
    found = check_customer(
        customer,
        attributed_by_document=kw.get("attributed", False),
        authentication=kw.get("auth", MailAuthentication(spf="pass", dkim="pass", dmarc="pass")),
        po_date=PO_DATE,
        received_at=RECEIVED,
        rules=rules,
    )
    return [f.code.value for f in found]


def test_a_known_screened_customer_on_a_verified_mail_raises_nothing() -> None:
    assert _customer_findings(_customer()) == []


def test_a_customer_taken_from_the_document_is_unknown_until_sales_confirms() -> None:
    assert _customer_findings(_customer(), attributed=True) == ["customer_unknown"]


def test_a_temporary_code_is_flagged() -> None:
    assert _customer_findings(_customer(status="temporary")) == ["customer_temporary"]


@pytest.mark.parametrize(
    ("compliance", "missing"),
    [
        ({"noc_confirmed": False}, True),
        ({"esf_fiscal_year": 2025}, True),
        ({"denial_list_checked_on": None}, True),
        # Received 25 September: 90 days back is 27 June.
        ({"denial_list_checked_on": "2026-06-26"}, True),
        ({"denial_list_checked_on": "2026-06-27"}, False),
    ],
    ids=["no NOC", "last year's ESF", "never screened", "91 days", "90 days"],
)
def test_missing_noc_esf_covers_noc_esf_and_the_denial_list_age(
    compliance: dict[str, Any], missing: bool
) -> None:
    found = _customer_findings(_customer(compliance=compliance))

    assert found == (["missing_noc_esf"] if missing else [])


def test_the_denial_list_age_and_the_fiscal_year_are_the_policys() -> None:
    stale = _customer(compliance={"denial_list_checked_on": "2026-06-26"})
    last_years = _customer(compliance={"esf_fiscal_year": 2025})

    assert (
        _customer_findings(stale, rules=_rules(export_control={"denial_list_max_age_days": 91}))
        == []
    )
    # With an October fiscal year, 24 September 2026 is still in FY2025.
    assert _customer_findings(last_years, rules=_rules(fiscal_year_start_month=10)) == []


@pytest.mark.parametrize("result", ["fail", "softfail", "none", "temperror"])
def test_any_mail_result_short_of_pass_leaves_the_sender_unverified(result: str) -> None:
    auth = MailAuthentication.model_validate({"spf": "pass", "dkim": result, "dmarc": "pass"})

    assert _customer_findings(_customer(), auth=auth) == ["sender_unverified"]


# ------------------------------------------------------------------ history --


def _case(
    document: PoDocument, *, case_id: int = 1, findings: tuple[Any, ...] = (), **stamps: Any
) -> OrderCase:
    lines = tuple(
        OrderLine(
            po_line=line,
            mapping=LineMapping(status=MappingStatus.EXACT, prv_code="CB-2007"),
            basis=LineBasis(checks_run=("read",)),
        )
        for line in document.lines
    )
    received = OrderCase(
        case_id=uuid.UUID(int=case_id),
        case_version=1,
        customer_code="NRV",
        message_id=f"M{case_id:02d}",
        received_at=RECEIVED,
        document=document,
        lines=lines,
        status=OrderStatus.RECEIVED,
    )
    return received.checked(
        findings=findings,
        rules_version=SHIPPED.version,
        catalog_as_of=RECEIVED,
        cross_check_required=True,
        export_control_mode="warn",
        **stamps,
    )


def _bravo(revision: int = 0, **line: Any) -> BravoOrder:
    return BravoOrder.model_validate(
        {
            "so_no": "SO26-0919",
            "customer_code": "NRV",
            "po_no": "NRV-PO-26-0457",
            "po_revision": revision,
            "order_date": "2026-09-25",
            "currency": "USD",
            "lines": [
                {
                    "line_no": 1,
                    "prv_code": "CB-2007",
                    "quantity": "3600",
                    "unit_price": "0.6980",
                    "delivery_date": "2026-12-04",
                }
                | line
            ],
        }
    )


CODES = {1: "CB-2007"}


def _history(
    document: PoDocument, cases: tuple[OrderCase, ...] = (), orders: tuple[BravoOrder, ...] = ()
) -> Any:
    return check_history("NRV", document, CODES, cases, orders, rules=SHIPPED)


def test_a_first_revision_zero_has_no_history() -> None:
    assert _history(_document()).finding is None


def test_a_revision_with_no_base_anywhere_is_revision_without_base() -> None:
    history = _history(_document(revision=1))

    assert (history.finding.code, history.base, history.base_so_no) == (
        FindingCode.REVISION_WITHOUT_BASE,
        None,
        None,
    )


def test_the_same_revision_with_identical_lines_is_a_duplicate_of_that_case() -> None:
    original = _case(_document())

    history = _history(_document(), (original,))

    assert (history.finding.code, history.duplicate_of_case, history.base) == (
        FindingCode.DUPLICATE_PO,
        original.case_id,
        None,
    )


def test_a_resend_of_a_superseded_revision_is_a_duplicate_of_the_case_holding_it() -> None:
    first = _case(_document())
    revised_po = SHIPPED.finding(FindingCode.REVISED_PO, expected="0", actual="1")
    revision = _case(
        _document(_po_line(unit_price=Decimal("0.71")), revision=1),
        case_id=7,
        findings=(revised_po,),
    )
    case = first.revise(revision)

    history = _history(_document(), (case,))

    assert (history.finding.code, history.duplicate_of_case) == (
        FindingCode.DUPLICATE_PO,
        case.case_id,
    )


def test_the_same_revision_with_other_lines_is_revised_and_joins_the_case() -> None:
    original = _case(_document())

    history = _history(_document(_po_line(quantity=Decimal(3900))), (original,))

    assert (history.finding.code, history.finding.actual, history.base) == (
        FindingCode.REVISED_PO,
        SAME_REVISION_CHANGED,
        original,
    )


def test_a_higher_revision_is_revised_and_joins_the_case() -> None:
    original = _case(_document())

    history = _history(_document(revision=1), (original,))

    assert (history.finding.code, history.finding.expected, history.finding.actual) == (
        FindingCode.REVISED_PO,
        "0",
        "1",
    )
    assert history.base is original


def test_a_revision_joins_the_original_case_never_the_duplicate_of_it() -> None:
    original = _case(_document())
    duplicate = _case(
        _document(),
        case_id=2,
        findings=(SHIPPED.finding(FindingCode.DUPLICATE_PO),),
        duplicate_of_case=original.case_id,
    )

    # Listed first on purpose: the store's order must not pick the base.
    history = _history(_document(revision=1), (duplicate, original))

    assert history.base is original


def test_an_older_revision_arriving_late_is_stale_not_a_revision() -> None:
    newer = _case(_document(revision=2))

    history = _history(_document(_po_line(quantity=Decimal(3900)), revision=1), (newer,))

    assert (history.stale, history.finding, history.base) == (True, None, None)


def test_a_po_keyed_in_bravo_by_hand_is_a_duplicate_of_its_sales_order() -> None:
    history = _history(_document(), orders=(_bravo(),))

    assert (history.finding.code, history.duplicate_of_so, history.duplicate_of_case) == (
        FindingCode.DUPLICATE_PO,
        "SO26-0919",
        None,
    )


@pytest.mark.parametrize(
    "line",
    [{"prv_code": "CB-2008"}, {"quantity": "3900"}, {"delivery_date": "2026-12-11"}],
    ids=["another item", "another quantity", "another date"],
)
def test_a_bravo_entry_that_differs_on_a_line_makes_the_po_a_revision_of_it(
    line: dict[str, Any],
) -> None:
    history = _history(_document(), orders=(_bravo(**line),))

    assert (history.finding.code, history.base_so_no, history.base) == (
        FindingCode.REVISED_PO,
        "SO26-0919",
        None,
    )


def test_a_revision_of_a_bravo_order_names_the_sales_order_as_its_base() -> None:
    history = _history(_document(revision=1), orders=(_bravo(),))

    assert (history.finding.code, history.base_so_no) == (FindingCode.REVISED_PO, "SO26-0919")


def test_another_customers_po_with_the_same_number_is_not_history() -> None:
    other = _bravo().model_copy(update={"customer_code": "VLX"})

    assert check_history("NRV", _document(), CODES, [], [other], rules=SHIPPED).finding is None
