"""Design's result on a YCBG, read back from Bravo (dw_sales ticket 16).

Design writes its result on the YCBG's lines in Bravo: QUOTE with the BP code,
or DECLINE with a reason, and the line's status goes CLOSE (Box B16). DW1
reads it; it never writes Bravo, and the status is Design's to close.

**Where it is read from** is `BravoYcbgPort`: the vendor's API reading a
request back by number (R13) once it exists; until then the YCBG screen
exported to Excel by a person (`ExportedYcbg`). `DesignChecks.take` matches
what either source says, and does not know which it was.

**Matched by the YCBG number alone**, as a Design reply by mail is
(`QuotationService.awaiting_reply`): the one case of the workspace waiting on
Design under that number, whose lines are exactly the YCBG's lines. Anything
else goes to Sales and onto no case (`no_case`, `lines_differ`, `changed`,
`unreadable`): a number no open request holds is never matched to the
nearest one. A YCBG with a line still PENDING is not Design's answer yet.
What is recorded moves no status (`QuoteCase.record_design_check`).

**The export** comes the one way every Bravo export does
(`application.bravo_exports`: upload, reader sandbox, worker), as the screen
``ycbg`` (`YcbgScreen`, `sales.quote.prepare`): each result is recorded as
the person who uploaded it, resolved again when the file is read.

**The columns are Bravo's own** (`COLUMNS`), as its "RFQ List" export titles
them (Box B16, seen 11-14; spec Q-B13): read by the one reader of Bravo's
exports (`domain.bravo_exports.find_header`), by title, never by position; a
file without one of them is refused naming it. That export leaves the line's
"Số thứ tự" blank on every row, so a request's lines are numbered in the
order the export lists them under its number, and each line's customer item
description must be the request's own for that line: a line Sales entered
in another order, or worded otherwise, goes to Sales (`lines_differ`), never
onto a guessed line.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import sales_scope
from dw_sales.application.bravo_exports import ExportOutcome
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.ports import SalesScope
from dw_sales.application.quote_ports import QuoteCaseLookupPort
from dw_sales.application.support import person_event, save_quote
from dw_sales.application.worker_service import require_running
from dw_sales.domain.bravo_exports import (
    CellValue,
    ExportColumn,
    ImportedTable,
    TableRow,
    find_header,
    header_key,
)
from dw_sales.domain.master_data import RejectedRow
from dw_sales.domain.quotes import (
    YCBG_NO_PATTERN,
    DesignCheck,
    DesignCheckLine,
    DesignVerdict,
    QuoteStatus,
    RfqDocument,
)

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
YcbgLineStatus = Literal["pending", "close"]

# Bravo's YCBG lines as its "RFQ List" export titles them (Box B16), and as
# the YCBG screen's own grid does (11-10): one column per field.
COLUMNS: Final[Mapping[str, ExportColumn]] = MappingProxyType(
    {
        "ycbg_no": ExportColumn("RFQ No", aliases=("Số chứng từ",)),
        # Blank in the export; numbered by order then (module docstring).
        "line_no": ExportColumn("Số thứ tự/ No.", aliases=("Số thứ tự", "STT"), required=False),
        "description": ExportColumn(
            "Mô tả của KH/Customer item description",
            aliases=("Customer item description", "Mô tả của KH"),
        ),
        "status": ExportColumn("Status", aliases=("Trạng thái",)),
        "design_check": ExportColumn("Design check"),
        "reason": ExportColumn("Decline reason", aliases=("Lý do",)),
        "bp_code": ExportColumn("Base price code", aliases=("Mã BP", "BP Code")),
        # Design's own values on a QUOTE line (ticket 11): optional, so an
        # export from before them reads as it did.
        "spec_no": ExportColumn(
            "Bản vẽ/ Specification", aliases=("Specification",), required=False
        ),
        "copper_kg_per_bp_unit": ExportColumn(
            "CU WT: (KG/BP Unit)", aliases=("CU WT",), required=False
        ),
        "bp_unit": ExportColumn("Unit BP", aliases=("BP Unit",), required=False),
    }
)
# Bravo's own values of a line's status and Design Check (Box 11-10, B16),
# compared without case or spacing.
_STATUSES: Final[Mapping[str, YcbgLineStatus]] = MappingProxyType(
    {"pending": "pending", "close": "close"}
)
_VERDICTS: Final[Mapping[str, DesignVerdict]] = MappingProxyType(
    {"quote": "quote", "decline": "decline"}
)

_PRINTED: Final = re.compile(r"^[!-~]{1,64}$")


# ------------------------------------------------------------------ data --


class BravoYcbgLine(BaseModel):
    """One YCBG line as Bravo holds it: what `BravoYcbgPort` answers. The
    number is as Bravo prints it, in any shape: a number no case holds goes
    to Sales, so it need not be one Sales could record."""

    model_config = _FROZEN

    ycbg_no: str = Field(pattern=_PRINTED.pattern)
    line_no: int = Field(ge=1, le=9999)
    status: YcbgLineStatus
    verdict: DesignVerdict | None = None
    bp_code: str | None = Field(default=None, max_length=64)
    reason: str | None = Field(default=None, max_length=1000)
    # The customer's item description, as Sales entered it from DW1's draft:
    # what tells which of the request's lines it is.
    description: str | None = Field(default=None, max_length=1000)
    # Design's values on a QUOTE line, as `DesignCheckLine` holds them.
    spec_no: str | None = Field(default=None, max_length=64)
    copper_kg_per_bp_unit: Decimal | None = Field(default=None, ge=0)
    bp_unit: str | None = Field(default=None, max_length=16)
    # The export row it was read from; None from a source with no rows.
    row: int | None = Field(default=None, ge=1)


# ------------------------------------------------------------------ ports --


class BravoYcbgPort(Protocol):
    """Bravo's YCBG lines, as Bravo holds them (module docstring). Read only."""

    async def ycbg_lines(self, scope: SalesScope) -> Sequence[BravoYcbgLine]: ...


@dataclass(frozen=True, slots=True)
class ExportedYcbg:
    """`BravoYcbgPort` over one export a person uploaded: its lines as read."""

    lines: tuple[BravoYcbgLine, ...]

    async def ycbg_lines(self, scope: SalesScope) -> Sequence[BravoYcbgLine]:
        return self.lines


# --------------------------------------------------------- reading a table --


class ParsedExport(BaseModel):
    """An export's rows as YCBG lines, and the rows that could not be read."""

    model_config = _FROZEN

    lines: tuple[BravoYcbgLine, ...]
    rejected: tuple[RejectedRow, ...]


def _text(cell: CellValue) -> str | None:
    if cell is None or isinstance(cell, bool):
        return None
    if isinstance(cell, float) and cell.is_integer():
        cell = int(cell)
    text = str(cell).strip()
    return text or None


def _line_no(cell: CellValue) -> int | None:
    text = _text(cell)
    if text is None:
        return None
    if not text.isdigit():
        raise ValueError("line_no")
    return int(text)


_PLAIN_NUMBER: Final = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")


def _quantity(cell: CellValue, field: str) -> Decimal | None:
    """A non-negative number as Bravo writes it: a number cell, or text with
    "." as its decimal mark. A comma or a sign is refused, never guessed."""
    if cell is None or (isinstance(cell, str) and not cell.strip()):
        return None
    if isinstance(cell, bool):
        raise ValueError(field)
    if isinstance(cell, int | float):
        if cell < 0:
            raise ValueError(field)
        return Decimal(str(cell))
    text = str(cell).strip()
    if _PLAIN_NUMBER.fullmatch(text) is None:
        raise ValueError(field)
    return Decimal(text)


def _closed(cell: CellValue, values: Mapping[str, str], field: str) -> str | None:
    """One of Bravo's own values of the field, or None for a blank cell."""
    text = _text(cell)
    if text is None:
        return None
    found = values.get(header_key(text))
    if found is None:
        raise ValueError(field)
    return found


def parse_export(table: ImportedTable) -> ParsedExport:
    """The export's YCBG lines, by Bravo's column titles (`COLUMNS`). Raises
    `MissingColumnsError` naming a column the file does not title. A row
    whose values cannot be read is rejected, naming the column and never the
    value; so is every row of a request whose lines are numbered on some rows
    and not on others. A request whose rows are all unnumbered has its lines
    numbered in the order listed (module docstring)."""
    header = find_header(table.rows, tuple(COLUMNS.values()))
    by_number: dict[str, list[tuple[TableRow, dict[str, object]]]] = {}
    rejected: list[RejectedRow] = []
    for row in table.rows[header.index + 1 :]:
        cells = {field: header.cell(row, column) for field, column in COLUMNS.items()}
        number = _text(cells["ycbg_no"])
        if number is None:
            # A row naming no request (Bravo's "Tổng cộng:" under the lines)
            # is not a YCBG line.
            continue
        try:
            fields: dict[str, object] = {
                "ycbg_no": number,
                "line_no": _line_no(cells["line_no"]),
                "status": _closed(cells["status"], _STATUSES, "status") or "",
                "verdict": _closed(cells["design_check"], _VERDICTS, "design_check"),
                "bp_code": _text(cells["bp_code"]),
                "reason": _text(cells["reason"]),
                "description": _text(cells["description"]),
                "spec_no": _text(cells["spec_no"]),
                "copper_kg_per_bp_unit": _quantity(
                    cells["copper_kg_per_bp_unit"], "copper_kg_per_bp_unit"
                ),
                "bp_unit": _text(cells["bp_unit"]),
                "row": row.row,
            }
        except ValueError as refused:
            rejected.append(_rejected(row.row, str(refused)))
            continue
        by_number.setdefault(number, []).append((row, fields))
    lines: list[BravoYcbgLine] = []
    for rows in by_number.values():
        numbered = [fields["line_no"] is not None for _, fields in rows]
        if any(numbered) and not all(numbered):
            rejected.extend(_rejected(row.row, "line_no") for row, _ in rows)
            continue
        for order, (row, fields) in enumerate(rows, start=1):
            try:
                lines.append(
                    BravoYcbgLine.model_validate(
                        fields if fields["line_no"] is not None else fields | {"line_no": order}
                    )
                )
            except ValidationError as refused:
                errors = refused.errors()
                rejected.append(_rejected(row.row, str(errors[0]["loc"][0]) if errors else None))
    return ParsedExport(lines=tuple(lines), rejected=tuple(sorted(rejected, key=lambda r: r.row)))


def _rejected(row: int, field: str | None) -> RejectedRow:
    column = COLUMNS[field].header if field is not None and field in COLUMNS else None
    return RejectedRow(row=row, column=column, reason="không đọc được giá trị của cột này")


# ------------------------------------------------- matching Design's result --


_YCBG_NO: Final = re.compile(YCBG_NO_PATTERN)


def _check_lines(lines: Sequence[BravoYcbgLine]) -> tuple[DesignCheckLine, ...] | None:
    """Design's result on each line, once every line is closed with one;
    None when a line is not, or states a result that is not a result."""
    try:
        return tuple(
            DesignCheckLine(
                line_no=line.line_no,
                verdict=line.verdict,
                bp_code=line.bp_code if line.verdict == "quote" else None,
                reason=line.reason,
                **(
                    {
                        "spec_no": line.spec_no,
                        "copper_kg_per_bp_unit": line.copper_kg_per_bp_unit,
                        "bp_unit": line.bp_unit,
                        "row": line.row,
                    }
                    if line.verdict == "quote"
                    else {}
                ),
            )
            for line in sorted(lines, key=lambda line: line.line_no)
            if line.verdict is not None
        )
    except ValidationError:
        return None


def _words(text: str) -> str:
    return " ".join(text.split()).casefold()


def _same_lines(lines: Sequence[BravoYcbgLine], document: RfqDocument) -> bool:
    """Bravo's lines are exactly the request's: the same numbers, and each
    line the customer's own words for it (spacing and case aside). A line
    whose description Bravo does not give is not known to be the request's."""
    if {line.line_no for line in lines} != document.line_numbers():
        return False
    return all(
        line.description is not None
        and _words(line.description) == _words(document.item(line.line_no).description.value)
        for line in lines
    )


@dataclass(frozen=True)
class DesignChecks:
    """Design's results, matched to the cases waiting on them (module docstring)."""

    uow: SalesUnitOfWorkFactory
    cases: QuoteCaseLookupPort
    clock: UtcClock
    ids: IdGenerator

    async def take(
        self, context: AccessContext, source: BravoYcbgPort, *, file_sha256: str
    ) -> tuple[ExportOutcome, ...]:
        """What became of each YCBG number ``source`` holds, in the order it
        first names them; each result recorded as ``context``, the person who
        brought it in, in a transaction of its own."""
        scope = sales_scope(context)
        by_number: dict[str, list[BravoYcbgLine]] = {}
        for line in await source.ycbg_lines(scope):
            by_number.setdefault(line.ycbg_no, []).append(line)
        return tuple(
            [
                await self._one(context, scope, number, lines, file_sha256)
                for number, lines in by_number.items()
            ]
        )

    async def _one(
        self,
        context: AccessContext,
        scope: SalesScope,
        number: str,
        lines: Sequence[BravoYcbgLine],
        file_sha256: str,
    ) -> ExportOutcome:
        if any(line.status != "close" for line in lines):
            return ExportOutcome(key=number, outcome="pending")
        checked = _check_lines(lines)
        numbers = [line.line_no for line in lines]
        if checked is None or len(checked) != len(lines) or len(set(numbers)) != len(numbers):
            return ExportOutcome(key=number, outcome="unreadable")
        if not _YCBG_NO.fullmatch(number):
            # No case can hold a number of another shape (`record_ycbg`).
            return ExportOutcome(key=number, outcome="no_case")
        found = await self.cases.cases_for_ycbg(scope, number)
        for case in found:
            if case.design_check is not None and case.design_check.lines == checked:
                return ExportOutcome(
                    key=number,
                    outcome="unchanged",
                    case_id=case.case_id,
                    declined=case.design_check.declined,
                )
        waiting = [case for case in found if case.status is QuoteStatus.SENT_TO_DESIGN]
        if len(waiting) != 1:
            return ExportOutcome(key=number, outcome="no_case")
        (case,) = waiting
        if not _same_lines(lines, case.request.document):
            return ExportOutcome(key=number, outcome="lines_differ", case_id=case.case_id)
        if case.design_check is not None:
            return ExportOutcome(key=number, outcome="changed", case_id=case.case_id)
        now = self.clock.now()
        check = DesignCheck(
            ycbg_no=number,
            lines=checked,
            file_sha256=file_sha256,
            read_by=context.principal_id,
            read_at=now,
        )
        async with self.uow(scope) as work:
            await require_running(work)
            stored = await work.quotes.get(case.case_id)
            if stored is None or stored.case.case_version != case.case_version:
                # Moved meanwhile: read again with the next upload.
                return ExportOutcome(key=number, outcome="changed", case_id=case.case_id)
            after = stored.case.record_design_check(check)
            event = person_event("quote.design_checked", context, now)
            await save_quote(work, context, self.ids, stored.case, after, event)
            await work.commit()
        return ExportOutcome(
            key=number, outcome="recorded", case_id=case.case_id, declined=check.declined
        )


# ----------------------------------------------------------- the screen --


@dataclass(frozen=True)
class YcbgScreen:
    """The ``ycbg`` screen's reader (`bravo_exports.ScreenReader`): the
    export's lines read (`parse_export`), and each closed YCBG's result put
    on the one case waiting on it (`DesignChecks`)."""

    checks: DesignChecks

    async def take(
        self, context: AccessContext, table: ImportedTable, *, file_sha256: str
    ) -> tuple[tuple[ExportOutcome, ...], tuple[RejectedRow, ...]]:
        parsed = parse_export(table)
        outcomes = await self.checks.take(
            context, ExportedYcbg(parsed.lines), file_sha256=file_sha256
        )
        return outcomes, parsed.rejected
