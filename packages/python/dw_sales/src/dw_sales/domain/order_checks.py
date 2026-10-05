"""The checks of WIV-03-012 steps 1, 2, 4 and 6, and the versioned rules they read.

Each function decides from what it is given: a PO, the master data the
application fetched for it, and `OrderRules`, the policy
`configs/policies/sales_order_rules@<version>.yaml`. Nothing here reads a
message body or a remark: the values that decide come from the PO's cells and
the master data, so text that reads like an instruction changes nothing.

Every finding is made by `OrderRules.finding`, which stamps the severity and
the rules' version on it, and every line checked carries its `LineBasis`: what
it was compared against, stamped when the check ran (spec decision 11).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Final, Literal, NamedTuple, Self, assert_never, get_args
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dw_sales.domain.catalog import (
    BravoOrder,
    ConvertEntry,
    Customer,
    Item,
    LmeBand,
    LmeMonth,
    Quotation,
    Uom,
    fiscal_year,
    month_key,
)
from dw_sales.domain.descriptions import candidates, read_description
from dw_sales.domain.messages import MailAuthentication
from dw_sales.domain.orders import (
    CheckName,
    ExportControlMode,
    Finding,
    FindingCode,
    ItemBasis,
    LeadTimeSource,
    LineBasis,
    LineCheck,
    LineMapping,
    LmeBasis,
    MappingStatus,
    OrderCase,
    OrderLine,
    PoDocument,
    PoLine,
    QuotationBasis,
    Severity,
    diff_lines,
)

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

# Where the received date is counted: the Sales office's own calendar day.
SALES_TIME_ZONE: Final = ZoneInfo("Asia/Ho_Chi_Minh")


class PriceRule(BaseModel):
    model_config = _FROZEN

    # A PO price passes within this fraction of the quoted price; 0 = equal.
    relative_tolerance: Decimal = Field(ge=0, lt=1)


class LmeBandRule(BaseModel):
    model_config = _FROZEN

    # The month whose LME price a band is held to, counted back from the month
    # of the PO date: 0 = that month, 1 = the month before.
    months_before_po_date: int = Field(ge=0, le=12)


class ShortLeadTimeRule(BaseModel):
    model_config = _FROZEN

    # The day the lead time is counted from: the day the PO was received (in
    # the Sales office's time zone), or the date the PO prints.
    start: Literal["received_date", "po_date"] = Field(alias="from")
    # item_standard: the item's standard lead time. quotation: the lead time
    # quoted to the customer, or the item's when the line has no quotation.
    lead_time: LeadTimeSource
    # Calendar days only: a working-day count needs a holiday calendar nobody
    # has supplied, so no other value is accepted until one is.
    day_basis: Literal["calendar"]


class ExportControlRule(BaseModel):
    model_config = _FROZEN

    # A denial-list check older than this, on the day the PO is received, is
    # no check (`missing_noc_esf`).
    denial_list_max_age_days: int = Field(ge=1, le=3650)


class IntakeCaps(BaseModel):
    """How much of a sender's file a reader opens before refusing it (decision 13)."""

    model_config = _FROZEN

    max_attachment_bytes: int = Field(ge=1)
    # What an .xlsx may unpack to: a zip bomb is refused before it is expanded.
    max_unpacked_bytes: int = Field(ge=1)
    max_sheets: int = Field(ge=1)
    max_pages: int = Field(ge=1)
    max_cells: int = Field(ge=1)


class OrderRules(BaseModel):
    """`sales_order_rules`: the fine print of the order checks, versioned.

    Every finding code has a severity, and a policy that leaves one out is
    refused: a code with no severity would be a check whose result blocks
    nothing, which reads as a safeguard and is not one.
    """

    model_config = _FROZEN

    schema_version: str = Field(pattern=r"^1\.0$")
    policy_id: Literal["sales_order_rules"]
    policy_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    price: PriceRule
    lme_band: LmeBandRule
    short_lead_time: ShortLeadTimeRule
    # WIV-03-012 step 9. False lets an order go from uploaded_to_bravo to
    # confirmed without a second person; stamped on each case when checked.
    cross_check_required: bool
    export_control_mode: ExportControlMode
    export_control: ExportControlRule
    intake: IntakeCaps
    # The month the fiscal year starts in; the ESF is renewed per fiscal year.
    fiscal_year_start_month: int = Field(ge=1, le=12)
    findings: Mapping[FindingCode, Severity]

    @model_validator(mode="after")
    def _every_finding_has_a_severity(self) -> Self:
        if missing := sorted(set(FindingCode) - self.findings.keys()):
            raise ValueError(f"no severity for {[code.value for code in missing]}")
        return self

    @property
    def version(self) -> str:
        """What a finding is stamped with: ``sales_order_rules@1.0.0``."""
        return f"{self.policy_id}@{self.policy_version}"

    def finding(
        self,
        code: FindingCode,
        *,
        line_no: int | None = None,
        expected: str | None = None,
        actual: str | None = None,
    ) -> Finding:
        return Finding(
            code=code,
            severity=self.findings[code],
            line_no=line_no,
            expected=expected,
            actual=actual,
            rule_version=self.version,
        )

    def lme_month(self, po_date: date) -> str:
        """The month (``YYYY-MM``) whose LME price a banded line is checked against."""
        months = po_date.year * 12 + po_date.month - 1 - self.lme_band.months_before_po_date
        return month_key(date(months // 12, months % 12 + 1, 1))

    def lead_time_start(self, *, po_date: date, received_at: datetime) -> date:
        """The day a line's lead time is counted from."""
        match self.short_lead_time.start:
            case "received_date":
                return received_date(received_at)
            case "po_date":
                return po_date
            case other:
                assert_never(other)


def received_date(received_at: datetime) -> date:
    """The calendar day a message arrived, in the Sales office's time zone."""
    return received_at.astimezone(SALES_TIME_ZONE).date()


# ----------------------------------------------------------------- mapping --


class MappedLine(NamedTuple):
    mapping: LineMapping
    # The item the line's checks run against: the exact one, or the single
    # candidate (which Sales must still confirm). None otherwise.
    item: Item | None
    # The convert list's code for the customer's code, when it had one.
    convert_prv_code: str | None = None


def map_line(po_line: PoLine, *, entry: ConvertEntry | None, items: Sequence[Item]) -> MappedLine:
    """The PRV code a line names: the convert list's, else candidates the description fits.

    A convert entry decides on its own. When its item is not in the item master
    the line is unmapped, not matched by description instead: the convert list
    has said which item this is, and a different item that happens to fit the
    words would be a guess against it.
    """
    if entry is not None:
        item = next((i for i in items if i.prv_code == entry.prv_code), None)
        if item is None:
            return MappedLine(LineMapping(status=MappingStatus.UNMAPPED), None, entry.prv_code)
        return MappedLine(
            LineMapping(status=MappingStatus.EXACT, prv_code=item.prv_code), item, entry.prv_code
        )
    stated = read_description(po_line.description)
    fitting = candidates(stated, items) if stated is not None else ()
    if not fitting:
        return MappedLine(LineMapping(status=MappingStatus.UNMAPPED), None)
    codes = tuple(i.prv_code for i in fitting)
    if len(fitting) == 1:
        return MappedLine(LineMapping(status=MappingStatus.CANDIDATE, candidates=codes), fitting[0])
    return MappedLine(LineMapping(status=MappingStatus.AMBIGUOUS, candidates=codes), None)


def current_quotation(
    quotations: Sequence[Quotation], *, customer_code: str, prv_code: str, day: date
) -> Quotation | None:
    """The customer's quotation for the item that applies on ``day``.

    Of two valid ones the later issue applies: a new quotation replaces the one
    before it. The fixtures never hold two, so this rule is the tie-break, not
    a path any golden case depends on.
    """
    valid = [
        q
        for q in quotations
        if q.customer_code == customer_code and q.prv_code == prv_code and q.is_valid_on(day)
    ]
    return max(valid, key=lambda q: (q.valid_from, q.quote_no), default=None)


def known_uom(printed: str) -> Uom | None:
    """DW1's word for the unit a PO prints, or None when it has none."""
    folded = printed.casefold()
    return next((u for u in get_args(Uom) if u.casefold() == folded), None)


# ------------------------------------------------------------- line checks --


def check_line(
    po_line: PoLine,
    mapped: MappedLine,
    *,
    currency: str,
    po_date: date,
    received_at: datetime,
    quotation: Quotation | None,
    lme: LmeMonth | None,
    rules: OrderRules,
) -> LineCheck:
    """Every finding about one line, with the basis each check compared against.

    ``quotation`` is the customer's quotation for ``mapped.item`` that applies
    on the PO date (`current_quotation`), and ``lme`` the price of
    `OrderRules.lme_month`, or None when there is none on record.
    """
    number = po_line.line_no
    mapping = mapped.mapping
    found: list[Finding] = []
    run: list[CheckName] = ["read", "mapping"]

    if mapping.status is MappingStatus.UNMAPPED:
        found.append(
            _on(rules, FindingCode.CODE_UNMAPPED, number, None, po_line.customer_item_code)
        )
    elif mapping.status is MappingStatus.AMBIGUOUS:
        found.append(
            _on(rules, FindingCode.CODE_AMBIGUOUS, number, None, po_line.customer_item_code)
        )
    if flags := sorted({flag.flag.value for flag in po_line.flags}):
        found.append(_on(rules, FindingCode.VALUE_UNCERTAIN, number, None, ",".join(flags)))

    item = mapped.item
    uom = known_uom(po_line.uom)
    run.append("uom")
    unit_differs = uom is None or (
        item is not None and (uom != item.uom or (quotation is not None and uom != quotation.uom))
    )
    if unit_differs:
        expected_unit = item.uom if item is not None else None
        found.append(
            _on(
                rules,
                FindingCode.UOM_MISMATCH,
                number,
                expected_unit or "a known unit",
                po_line.uom,
            )
        )

    basis = LineBasis(
        convert_prv_code=mapped.convert_prv_code,
        candidates=mapping.candidates,
        checks_run=tuple(run),
    )
    if item is None:
        return LineCheck(
            line=OrderLine(po_line=po_line, mapping=mapping, basis=basis), findings=tuple(found)
        )
    if quotation is not None and (
        quotation.prv_code != item.prv_code or not quotation.is_valid_on(po_date)
    ):
        raise ValueError(f"line {number} is checked against a quotation for its item and date")

    run.append("quotation")
    lme_basis: LmeBasis | None = None
    if quotation is None:
        found.append(
            _on(
                rules,
                FindingCode.QUOTATION_MISSING,
                number,
                f"valid on {po_date.isoformat()}",
                None,
            )
        )
    else:
        run.append("currency")
        if currency != quotation.currency:
            # Never converted: the exchange-rate rule is owed by the company.
            found.append(
                _on(rules, FindingCode.CURRENCY_MISMATCH, number, quotation.currency, currency)
            )
        elif not unit_differs:
            run.append("price")
            if price := _price_finding(po_line, quotation, rules):
                found.append(price)
        if isinstance(quotation.copper_basis, LmeBand):
            run.append("lme_band")
            lme_basis, band = _lme_check(number, quotation.copper_basis, lme, po_date, rules)
            if band is not None:
                found.append(band)

    moq = quotation.moq if quotation is not None else item.moq
    if not unit_differs:
        # A quantity in another unit is not comparable with a MOQ or a pack.
        run.extend(("moq", "pack"))
        if po_line.quantity < moq:
            found.append(
                _on(rules, FindingCode.MOQ_VIOLATION, number, str(moq), str(po_line.quantity))
            )
        if po_line.quantity % item.pack_multiple:
            found.append(
                _on(
                    rules,
                    FindingCode.PACK_MULTIPLE,
                    number,
                    str(item.pack_multiple),
                    str(po_line.quantity),
                )
            )

    run.append("lead_time")
    lead_time, source = _lead_time(item, quotation, rules)
    earliest = rules.lead_time_start(po_date=po_date, received_at=received_at) + timedelta(
        days=lead_time
    )
    if po_line.requested_date < earliest:
        found.append(
            _on(
                rules,
                FindingCode.REQUESTED_DATE_SHORT_LT,
                number,
                earliest.isoformat(),
                po_line.requested_date.isoformat(),
            )
        )
    basis = LineBasis(
        convert_prv_code=mapped.convert_prv_code,
        candidates=mapping.candidates,
        item=ItemBasis(
            prv_code=item.prv_code,
            uom=item.uom,
            moq=item.moq,
            pack_multiple=item.pack_multiple,
            standard_lead_time_days=item.standard_lead_time_days,
        ),
        quotation=_quotation_basis(quotation),
        lme=lme_basis,
        lead_time_days=lead_time,
        lead_time_source=source,
        checks_run=tuple(run),
    )
    line = OrderLine(
        po_line=po_line,
        mapping=mapping,
        basis=basis,
        # DW1's proposal, labelled as one: the requested date when the lead
        # time allows it, else the first day it does.
        suggested_delivery_date=max(po_line.requested_date, earliest),
    )
    return LineCheck(line=line, findings=tuple(found))


def _on(
    rules: OrderRules, code: FindingCode, line_no: int, expected: str | None, actual: str | None
) -> Finding:
    return rules.finding(code, line_no=line_no, expected=expected, actual=actual)


def _price_finding(po_line: PoLine, quotation: Quotation, rules: OrderRules) -> Finding | None:
    quoted = quotation.unit_price
    if abs(po_line.unit_price - quoted) <= quoted * rules.price.relative_tolerance:
        return None
    return rules.finding(
        FindingCode.PRICE_MISMATCH,
        line_no=po_line.line_no,
        expected=f"{quoted} {quotation.currency}",
        actual=f"{po_line.unit_price} {quotation.currency}",
    )


def _lme_check(
    line_no: int, band: LmeBand, lme: LmeMonth | None, po_date: date, rules: OrderRules
) -> tuple[LmeBasis, Finding | None]:
    month = rules.lme_month(po_date)
    if lme is not None and lme.month != month:
        raise ValueError(f"line {line_no} is checked against LME {month}, given {lme.month}")
    basis = LmeBasis(month=month, usd_per_tonne=lme.usd_per_tonne if lme is not None else None)
    expected = f"{band.low_usd_per_tonne}-{band.high_usd_per_tonne} USD/t"
    if lme is None:
        # A band nobody can check is not a band that holds.
        return basis, _on(
            rules, FindingCode.LME_BAND_MISMATCH, line_no, expected, f"no LME price for {month}"
        )
    if band.contains(lme.usd_per_tonne):
        return basis, None
    return basis, _on(
        rules,
        FindingCode.LME_BAND_MISMATCH,
        line_no,
        expected,
        f"{lme.usd_per_tonne} USD/t ({month})",
    )


def _lead_time(
    item: Item, quotation: Quotation | None, rules: OrderRules
) -> tuple[int, LeadTimeSource]:
    source = rules.short_lead_time.lead_time
    match source:
        case "item_standard":
            return item.standard_lead_time_days, "item_standard"
        case "quotation":
            if quotation is None:
                return item.standard_lead_time_days, "item_standard"
            return quotation.lead_time_days, "quotation"
        case _:
            assert_never(source)


def _quotation_basis(quotation: Quotation | None) -> QuotationBasis | None:
    if quotation is None:
        return None
    return QuotationBasis(
        quote_no=quotation.quote_no,
        unit_price=quotation.unit_price,
        currency=quotation.currency,
        uom=quotation.uom,
        moq=quotation.moq,
        lead_time_days=quotation.lead_time_days,
        copper_basis=quotation.copper_basis,
        valid_from=quotation.valid_from,
        valid_to=quotation.valid_to,
    )


# ---------------------------------------------------------- the PO as read --


def check_document(document: PoDocument, rules: OrderRules) -> tuple[Finding, ...]:
    """Whether every line printed was read, and read from a place a person sees.

    `line_total_mismatch`: the line numbers are not 1..N in reading order, a
    numbered row was not read, or the line amounts do not add up to the
    printed total. `value_uncertain` (PO level): a header value or the total
    read from a flagged region, or a sheet nothing reads. A line's own flags
    are its line's finding (`check_line`).
    """
    found: list[Finding] = []
    numbers = [line.line_no for line in document.lines]
    expected: list[str] = []
    actual: list[str] = []
    if numbers != list(range(1, len(numbers) + 1)) or document.rows_printed != len(numbers):
        expected.append(f"lines 1-{document.rows_printed}")
        actual.append(f"lines {_ranges(numbers)}")
    if document.total is not None:
        added = sum((line.amount for line in document.lines), Decimal(0))
        if added != document.total.amount:
            expected.append(f"total {document.total.amount}")
            actual.append(f"sum of lines {added}")
    if expected:
        found.append(
            rules.finding(
                FindingCode.LINE_TOTAL_MISMATCH,
                expected="; ".join(expected),
                actual="; ".join(actual),
            )
        )
    flags = {flag.flag.value for flag in document.header.flags}
    if document.total is not None:
        flags |= {flag.flag.value for flag in document.total.flags}
    if document.unchecked_regions:
        flags.add("unchecked_region")
    if flags:
        found.append(rules.finding(FindingCode.VALUE_UNCERTAIN, actual=",".join(sorted(flags))))
    return tuple(found)


def _ranges(numbers: Iterable[int]) -> str:
    """``1-4, 6-8`` for 1, 2, 3, 4, 6, 7, 8, in the order read."""
    runs: list[list[int]] = []
    for number in numbers:
        if runs and number == runs[-1][-1] + 1:
            runs[-1].append(number)
        else:
            runs.append([number])
    return ", ".join(f"{r[0]}-{r[-1]}" if len(r) > 1 else str(r[0]) for r in runs)


# --------------------------------------------------- who sent it, and to whom --


def check_customer(
    customer: Customer,
    *,
    attributed_by_document: bool,
    authentication: MailAuthentication,
    po_date: date,
    received_at: datetime,
    rules: OrderRules,
) -> tuple[Finding, ...]:
    """Findings about the customer and the sender, in the order shown.

    `customer_unknown` when the customer was taken from the buyer the document
    names rather than the sender's domain; `customer_temporary`;
    `missing_noc_esf` (DW1 warns and decides nothing about export control);
    `sender_unverified` when the mail system's results are not all ``pass``.
    """
    found: list[Finding] = []
    if attributed_by_document:
        found.append(
            rules.finding(
                FindingCode.CUSTOMER_UNKNOWN,
                expected="customer confirmed by Sales",
                actual=f"buyer named on the document: {customer.code}",
            )
        )
    if customer.status == "temporary":
        found.append(
            rules.finding(FindingCode.CUSTOMER_TEMPORARY, expected="official", actual="temporary")
        )
    if compliance := _compliance_finding(customer, po_date, received_date(received_at), rules):
        found.append(compliance)
    if not authentication.verified:
        results = (authentication.spf, authentication.dkim, authentication.dmarc)
        found.append(
            rules.finding(
                FindingCode.SENDER_UNVERIFIED,
                expected="spf=pass, dkim=pass, dmarc=pass",
                actual="spf={}, dkim={}, dmarc={}".format(*results),
            )
        )
    return tuple(found)


def _compliance_finding(
    customer: Customer, po_date: date, received: date, rules: OrderRules
) -> Finding | None:
    year = fiscal_year(po_date, start_month=rules.fiscal_year_start_month)
    compliance = customer.compliance
    max_age = rules.export_control.denial_list_max_age_days
    checked_on = compliance.denial_list_checked_on
    screened = checked_on is not None and (received - checked_on).days <= max_age
    if compliance.noc_confirmed and compliance.esf_fiscal_year == year and screened:
        return None
    noc = "NOC confirmed" if compliance.noc_confirmed else "no NOC"
    esf = f"ESF FY{compliance.esf_fiscal_year}" if compliance.esf_fiscal_year else "no ESF"
    denial = (
        f"denial-list check {checked_on.isoformat()}"
        if checked_on is not None
        else "no denial-list check"
    )
    return rules.finding(
        FindingCode.MISSING_NOC_ESF,
        expected=f"NOC confirmed, ESF FY{year}, denial-list check within {max_age} days",
        actual=f"{noc}, {esf}, {denial}",
    )


# ------------------------------------------------------------------ history --

SAME_REVISION_CHANGED: Final = "nội dung đổi mà không tăng revision"


class History(NamedTuple):
    """What the PO number already has, and what this revision is to it."""

    finding: Finding | None
    # The DW1 case this revision joins and supersedes.
    base: OrderCase | None = None
    duplicate_of_case: uuid.UUID | None = None
    duplicate_of_so: str | None = None
    # A revision whose base is a sales order Bravo holds and no DW1 case does.
    base_so_no: str | None = None
    # An earlier revision than the case already holds, arriving late: not a
    # duplicate (its lines differ), not something to supersede the case with.
    stale: bool = False


def check_history(
    customer_code: str,
    document: PoDocument,
    prv_codes: Mapping[int, str | None],
    earlier: Sequence[OrderCase],
    bravo_orders: Sequence[BravoOrder],
    *,
    rules: OrderRules,
) -> History:
    """Whether this PO number was seen before, in a DW1 case or in Bravo.

    Keyed by revision. The same revision with identical lines is
    `duplicate_po`. The same revision with other lines, or a higher revision,
    is `revised_po`: it joins the case that holds the PO, or names the Bravo
    order when only Bravo has it. A revision above 0 with no base in either
    source is `revision_without_base`, handled as a new PO. ``prv_codes`` maps
    each line to the code it was checked against, for the comparison with the
    Bravo entry, which holds PRV codes rather than the customer's.
    """
    header = document.header
    cases = [
        case
        for case in earlier
        if case.customer_code == customer_code and case.header.po_no == header.po_no
    ]
    orders = [
        order
        for order in bravo_orders
        if order.customer_code == customer_code and order.po_no == header.po_no
    ]
    if not cases and not orders:
        if header.revision == 0:
            return History(None)
        return History(
            rules.finding(
                FindingCode.REVISION_WITHOUT_BASE,
                expected=f"revision {header.revision - 1} seen first",
                actual=str(header.revision),
            )
        )

    same_case = next(
        (
            case
            for case in cases
            for revision in (case.document, *(old.document for old in case.superseded))
            if revision.header.revision == header.revision
            and not diff_lines(revision.lines, document.lines)
        ),
        None,
    )
    same_order = next(
        (
            order
            for order in orders
            if order.po_revision == header.revision and _same_entry(order, document, prv_codes)
        ),
        None,
    )
    known = [case.header.revision for case in cases] + [order.po_revision for order in orders]
    if same_case is not None or same_order is not None:
        return History(
            rules.finding(
                FindingCode.DUPLICATE_PO,
                expected=f"a revision after {max(known)}",
                actual=str(header.revision),
            ),
            duplicate_of_case=same_case.case_id if same_case is not None else None,
            duplicate_of_so=same_order.so_no if same_case is None and same_order else None,
        )

    originals = [c for c in cases if FindingCode.DUPLICATE_PO not in {f.code for f in c.findings}]
    base = max(originals or cases, key=lambda case: case.header.revision, default=None)
    latest_so = max(orders, key=lambda order: order.po_revision, default=None)
    held = max(known)
    if header.revision < held:
        return History(None, stale=True)
    if header.revision == held:
        expected, actual = str(header.revision), SAME_REVISION_CHANGED
    else:
        expected, actual = str(held), str(header.revision)
    finding = rules.finding(FindingCode.REVISED_PO, expected=expected, actual=actual)
    if base is not None:
        return History(finding, base=base)
    assert latest_so is not None  # no case for the PO, so Bravo holds it
    return History(finding, base_so_no=latest_so.so_no)


def _same_entry(
    order: BravoOrder, document: PoDocument, prv_codes: Mapping[int, str | None]
) -> bool:
    """The Bravo order holds this PO's lines: number, PRV code, quantity, price, date."""
    entered = {
        (line.line_no, line.prv_code, line.quantity, line.unit_price, line.delivery_date)
        for line in order.lines
    }
    printed = {
        (
            line.line_no,
            prv_codes.get(line.line_no),
            line.quantity,
            line.unit_price,
            line.requested_date,
        )
        for line in document.lines
    }
    return order.currency == document.header.currency and entered == printed
