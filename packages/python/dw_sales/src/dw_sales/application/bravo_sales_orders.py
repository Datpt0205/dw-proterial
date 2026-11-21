"""After the paste, DW1 reads the sales order back from Bravo and compares it
with the case as approved (dw_sales ticket 03; ADR 0026).

**Where it is read from** is `BravoSalesOrdersPort`: the vendor's API (R10)
once it exists; until then the "Customer order information (Form 1)" screen
exported by Sales and uploaded (`bravo_exports`, screen ``sales_orders``,
`sales.order.prepare`), read by Bravo's own column titles (`SO_COLUMNS`, Box
B02: 81 columns, header on row 2, a SUBTOTAL row under it).
`SalesOrderScreen.take` does not know which it was.

**Matched by customer and PO number**: Bravo's direct customer code and its
"PO Number" find the one case of the workspace for that customer's PO
waiting on its Bravo entry or already entered (`prepared`,
`uploaded_to_bravo`). Another customer's SO under the same PO number is
never that case (acceptance 2). No case, several cases, or a PO Bravo holds
under several sales orders (B02 has POs under two and four, Q-B6) go to
Sales uncompared.

**Compared with what was prepared**: the case's paste-sheet rows
(`order_artifacts.upload_rows`, the one source of what is entered), row by
row (`domain.bravo_sales_orders.compare`). The result is kept for the case
(`BravoReadBack`), the latest replacing the one before, stamped with the
case version it was compared against and the file it came from, and audited
as the person who uploaded it. It decides nothing: the PIC still records the
entry, and the cross-checker reads the comparison beside it. Nothing here
writes the case.

With no export read (the API down, nothing uploaded) there is no read-back
and the case says so; the PIC's manual path stays (acceptance 3).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import MappingProxyType, TracebackType
from typing import Final, Protocol, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from dw_kernel.errors import ConflictError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.ports import AuditRepositoryPort
from dw_platform.domain.audit import AuditEvent
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.bravo_exports import ExportOutcome
from dw_sales.application.bravo_line_writes import BravoUnreachableError
from dw_sales.application.case_store import STALE_CASE_VERSION, SalesUnitOfWorkFactory
from dw_sales.application.order_artifacts import upload_rows
from dw_sales.application.order_ports import OrderCaseLookupPort
from dw_sales.application.ports import SalesScope
from dw_sales.application.support import stored_order
from dw_sales.domain.bravo_exports import CellValue, ExportColumn, ImportedTable, find_header
from dw_sales.domain.bravo_sales_orders import (
    BravoSalesOrder,
    BravoSoRow,
    PreparedRow,
    SoDifference,
    compare,
)
from dw_sales.domain.master_data import RejectedRow, read_date, read_decimal
from dw_sales.domain.orders import OrderCase, OrderStatus

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
_RESOURCE: Final = "sales_order_bravo_read_back"

# Bravo's "Customer order information (Form 1)" as its export titles it (Box
# B02, 11-13): one column per field read.
SO_COLUMNS: Final[Mapping[str, ExportColumn]] = MappingProxyType(
    {
        "so_no": ExportColumn("Sale order No", aliases=("SO order", "Số đơn hàng")),
        "customer_code": ExportColumn("Direct customer code", aliases=("KH trực tiếp",)),
        "po_no": ExportColumn("PO Number", aliases=("PO No.",)),
        "po_line": ExportColumn("PO line"),
        "item_code": ExportColumn("Item code", aliases=("Mã hàng",)),
        "quantity": ExportColumn("Quantity", aliases=("Số lượng",)),
        "unit_price": ExportColumn("Original Price", aliases=("Đơn giá",)),
        "requested_date": ExportColumn(
            "PO Request date", aliases=("Ngày KH yêu cầu",), required=False
        ),
    }
)
# The statuses a case is read back in: waiting on its Bravo entry, or entered.
READ_BACK_ON: Final = frozenset({OrderStatus.PREPARED, OrderStatus.UPLOADED_TO_BRAVO})


class BravoReadBack(BaseModel):
    """A case's sales order as Bravo held it when last read, against the case
    version it was compared with (module docstring)."""

    model_config = _FROZEN

    case_id: uuid.UUID
    case_version: int = Field(ge=1)
    po_no: str = Field(min_length=1, max_length=64)
    so_no: str = Field(min_length=1, max_length=64)
    differences: tuple[SoDifference, ...]
    rows_read: int = Field(ge=1)
    file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    read_by: uuid.UUID
    read_at: AwareDatetime

    @property
    def equal(self) -> bool:
        return not self.differences


def require_bravo_agrees(read_back: BravoReadBack | None, case: OrderCase) -> None:
    """ "Kiểm chéo đạt" is refused while Bravo's sales order, read back at this
    case version, differs from the paste sheet (decided 2026-11-17): Bravo's
    import skips a refused row without a log, so a difference is a line Bravo
    lost or holds wrong. Nothing read, or read at an older version, refuses
    nothing: the case page says which, and the manual path stays."""
    if read_back is None or read_back.equal or read_back.case_version != case.case_version:
        return
    raise ConflictError(
        f"SO {read_back.so_no} đọc lại từ Bravo khác bản đã duyệt ở "
        f"{len(read_back.differences)} chỗ: sửa trên Bravo rồi đọc lại, hoặc trả lại hồ sơ",
        details={
            "rule": "bravo_read_back_differs",
            "case_id": str(case.case_id),
            "differences": len(read_back.differences),
        },
    )


# ------------------------------------------------------------------ ports --


class BravoCustomerPoPort(Protocol):
    """A customer's PO as Bravo holds it now, read through the gateway
    (ticket 51); the rows carry Bravo's confirmed dates."""

    async def by_customer_po(
        self, scope: SalesScope, customer_code: str, po_no: str
    ) -> tuple[BravoSalesOrder, str] | None:
        """The PO's rows under that direct customer and the answer's sha256;
        None when Bravo holds none; `BravoUnreachableError` when not asked."""
        ...


class BravoSalesOrdersPort(Protocol):
    """Bravo's sales orders, as Bravo holds them. Read only."""

    async def by_customer_po(
        self, scope: SalesScope, customer_code: str, po_no: str
    ) -> BravoSalesOrder | None:
        """The PO's rows under that direct customer; None when Bravo holds none."""
        ...

    async def orders(self, scope: SalesScope) -> Sequence[BravoSalesOrder]:
        """Every customer PO the source holds, in the order it lists them."""
        ...


@dataclass(frozen=True, slots=True)
class ExportedSalesOrders:
    """`BravoSalesOrdersPort` over one export a person uploaded."""

    rows: tuple[BravoSoRow, ...]

    async def orders(self, scope: SalesScope) -> Sequence[BravoSalesOrder]:
        grouped: dict[tuple[str, str], list[BravoSoRow]] = {}
        for row in self.rows:
            grouped.setdefault((row.customer_code, row.po_no), []).append(row)
        return [
            BravoSalesOrder(customer_code=customer, po_no=po_no, rows=tuple(rows))
            for (customer, po_no), rows in grouped.items()
        ]

    async def by_customer_po(
        self, scope: SalesScope, customer_code: str, po_no: str
    ) -> BravoSalesOrder | None:
        found = [
            o
            for o in await self.orders(scope)
            if (o.customer_code, o.po_no) == (customer_code, po_no)
        ]
        return found[0] if found else None


class ReadBackStorePort(Protocol):
    """The workspace's read-backs inside a unit of work (RLS-bound)."""

    async def put(self, read_back: BravoReadBack) -> None:
        """The case's read-back, replacing the one before."""
        ...

    async def get(self, case_id: uuid.UUID) -> BravoReadBack | None: ...


class ReadBackUnitOfWork(Protocol):
    @property
    def read_backs(self) -> ReadBackStorePort: ...

    @property
    def audit(self) -> AuditRepositoryPort: ...

    async def commit(self) -> None: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...


class ReadBackUnitOfWorkFactory(Protocol):
    def __call__(self, scope: SalesScope) -> ReadBackUnitOfWork: ...


# --------------------------------------------------------- reading rows --


def _text(cell: CellValue) -> str | None:
    if cell is None or isinstance(cell, bool):
        return None
    if isinstance(cell, float) and cell.is_integer():
        cell = int(cell)
    text = str(cell).strip()
    return text or None


def _number(cell: CellValue, field: str) -> Decimal:
    found = read_decimal(cell)
    if found is None:
        raise ValueError(field)
    return found


def parse_sales_orders(
    table: ImportedTable,
) -> tuple[tuple[BravoSoRow, ...], tuple[RejectedRow, ...]]:
    """The export's sales-order rows, by Bravo's column titles (`SO_COLUMNS`).
    Raises `MissingColumnsError` naming a column the file does not title. A
    row naming no sales order (Bravo's SUBTOTAL) is skipped; a row whose
    values cannot be read is rejected naming its column, never its value."""
    header = find_header(table.rows, tuple(SO_COLUMNS.values()))
    rows: list[BravoSoRow] = []
    rejected: list[RejectedRow] = []
    for row in table.rows[header.index + 1 :]:
        cells = {field: header.cell(row, column) for field, column in SO_COLUMNS.items()}
        if _text(cells["so_no"]) is None:
            continue
        try:
            line = _text(cells["po_line"])
            if line is None or not line.isdigit():
                raise ValueError("po_line")
            requested: date | None = None
            if _text(cells["requested_date"]) is not None:
                requested = read_date(cells["requested_date"])
                if requested is None:
                    raise ValueError("requested_date")
            price = (
                None
                if _text(cells["unit_price"]) is None
                else _number(cells["unit_price"], "unit_price")
            )
            rows.append(
                BravoSoRow(
                    row=row.row,
                    so_no=_text(cells["so_no"]) or "",
                    customer_code=_text(cells["customer_code"]) or "",
                    po_no=_text(cells["po_no"]) or "",
                    po_line=int(line),
                    item_code=_text(cells["item_code"]),
                    quantity=_number(cells["quantity"], "quantity"),
                    unit_price=price,
                    requested_date=requested,
                )
            )
        except ValidationError as refused:
            errors = refused.errors()
            rejected.append(_rejected(row.row, str(errors[0]["loc"][0]) if errors else None))
        except ValueError as refused:
            rejected.append(_rejected(row.row, str(refused)))
    return tuple(rows), tuple(rejected)


def _rejected(row: int, field: str | None) -> RejectedRow:
    column = SO_COLUMNS[field].header if field is not None and field in SO_COLUMNS else None
    return RejectedRow(row=row, column=column, reason="không đọc được giá trị của cột này")


def prepared_rows(case: OrderCase) -> tuple[PreparedRow, ...]:
    """The case's paste-sheet rows as approved: what Bravo should now hold."""
    return tuple(
        PreparedRow(
            po_no=str(values["po_no"]),
            line_no=int(str(values["line_no"])),
            prv_code=str(values["prv_code"]),
            quantity=Decimal(str(values["quantity"])),
            unit_price=Decimal(str(values["unit_price"])),
            requested_date=values["requested_date"]
            if isinstance(values["requested_date"], date)
            else None,
            confirmed_date=confirmed
            if isinstance(confirmed := values.get("confirmed_date"), date)
            else None,
        )
        for line in case.lines
        for values in upload_rows(case, line)
    )


# ----------------------------------------------------------- the screen --


@dataclass(frozen=True)
class SalesOrderScreen:
    """The ``sales_orders`` screen's reader (`bravo_exports.ScreenReader`)."""

    cases: OrderCaseLookupPort
    uow: ReadBackUnitOfWorkFactory
    clock: UtcClock
    ids: IdGenerator

    async def take(
        self, context: AccessContext, table: ImportedTable, *, file_sha256: str
    ) -> tuple[tuple[ExportOutcome, ...], tuple[RejectedRow, ...]]:
        rows, rejected = parse_sales_orders(table)
        source = ExportedSalesOrders(rows)
        scope = sales_scope(context)
        outcomes = [
            await self._one(context, scope, order, file_sha256)
            for order in await source.orders(scope)
        ]
        return tuple(outcomes), rejected

    async def _one(
        self, context: AccessContext, scope: SalesScope, order: BravoSalesOrder, file_sha256: str
    ) -> ExportOutcome:
        key = f"{order.customer_code} · {order.po_no}"[:64]
        found = [
            case
            for case in await self.cases.cases_for_po(scope, order.customer_code, order.po_no)
            if case.status in READ_BACK_ON
        ]
        if not found:
            return ExportOutcome(key=key, outcome="no_case")
        if len(found) > 1:
            return ExportOutcome(key=key, outcome="several_cases")
        (case,) = found
        if order.so_no is None:
            return ExportOutcome(key=key, outcome="several_sos", case_id=case.case_id)
        try:
            prepared = prepared_rows(case)
        except ConflictError:
            return ExportOutcome(key=key, outcome="no_case")
        differences = compare(prepared, order)
        await store_read_back(
            self.uow, self.ids, self.clock, context, case, order, differences, file_sha256
        )
        return ExportOutcome(
            key=key,
            outcome="differs" if differences else "equal",
            case_id=case.case_id,
            differences=len(differences),
        )


async def store_read_back(
    uow: ReadBackUnitOfWorkFactory,
    ids: IdGenerator,
    clock: UtcClock,
    context: AccessContext,
    case: OrderCase,
    order: BravoSalesOrder,
    differences: tuple[SoDifference, ...],
    source_sha256: str,
) -> BravoReadBack:
    """The case's read-back, replacing the one before, with its audit row in
    the same transaction. ``source_sha256``: the export file's, or the
    gateway's answer's (`read_from_bravo`)."""
    assert order.so_no is not None  # compared only under one SO
    now = clock.now()
    read_back = BravoReadBack(
        case_id=case.case_id,
        case_version=case.case_version,
        po_no=order.po_no,
        so_no=order.so_no,
        differences=differences,
        rows_read=len(order.rows),
        file_sha256=source_sha256,
        read_by=context.principal_id,
        read_at=now,
    )
    scope = sales_scope(context)
    async with uow(scope) as work:
        await work.read_backs.put(read_back)
        await work.audit.append(
            AuditEvent(
                id=ids.new_uuid(),
                tenant_id=TenantId(context.tenant_id),
                workspace_id=WorkspaceId(context.workspace_id),
                actor_id=UserId(context.principal_id),
                action="sales.order.bravo_read_back",
                resource_type=_RESOURCE,
                resource_id=str(case.case_id),
                occurred_at=now,
                details={
                    "case_id": str(case.case_id),
                    "case_version": case.case_version,
                    "differences": len(differences),
                    "rows_read": len(order.rows),
                    "file_sha256": source_sha256,
                },
            )
        )
        await work.commit()
    return read_back


# ------------------------------------------------------------ the view --


class ReadBackView(BaseModel):
    """A case's read-back as its page shows it. ``stale``: the case changed
    since it was compared. A unit price's values are left out for a viewer
    who may not read prices."""

    model_config = ConfigDict(frozen=True)

    read_back: BravoReadBack | None
    stale: bool
    prices_hidden: bool


def without_prices(read_back: BravoReadBack) -> BravoReadBack:
    """``read_back`` for a caller who may not read prices: a unit price's
    difference keeps its line and field, never its values."""
    return read_back.model_copy(
        update={
            "differences": tuple(
                d.model_copy(update={"expected": None, "actual": None})
                if d.field == "unit_price"
                else d
                for d in read_back.differences
            )
        }
    )


@dataclass(frozen=True)
class ReadBackService:
    """The case page's side: the case's latest read-back, for whoever may
    read the case (`stored_order`: another workspace's case is not found)."""

    sales: SalesUnitOfWorkFactory
    uow: ReadBackUnitOfWorkFactory
    gate: Gate
    # Bravo through the gateway (ticket 51); None: only an uploaded export
    # is read back.
    bravo: BravoCustomerPoPort | None = None
    clock: UtcClock | None = None
    ids: IdGenerator | None = None

    async def latest(self, context: AccessContext, case_id: uuid.UUID) -> ReadBackView:
        await self.gate.require(
            context, SalesScopes.CASE_READ, resource_type=_RESOURCE, resource_id=str(case_id)
        )
        scope = sales_scope(context)
        async with self.sales(scope) as work:
            stored = await stored_order(work, case_id, viewer=context)
        async with self.uow(scope) as work:
            found = await work.read_backs.get(case_id)
        if found is None:
            return ReadBackView(read_back=None, stale=False, prices_hidden=False)
        hidden = not self.gate.prices(context).amounts
        if hidden:
            found = without_prices(found)
        return ReadBackView(
            read_back=found,
            stale=found.case_version != stored.case.case_version,
            prices_hidden=hidden,
        )

    async def read_from_bravo(
        self, context: AccessContext, case_id: uuid.UUID, *, case_version: int
    ) -> ReadBackView:
        """The case's SO read back from Bravo through the gateway and compared
        with the paste sheet as approved, confirmed dates included (ticket
        51): what the PIC asks for after entering the SO. A PO Bravo holds
        under several SOs, none, or a Bravo that did not answer is said, and
        nothing is stored."""
        await self.gate.require(
            context,
            SalesScopes.CASE_READ,
            SalesScopes.ORDER_PREPARE,
            resource_type=_RESOURCE,
            resource_id=str(case_id),
        )
        if self.bravo is None or self.clock is None or self.ids is None:
            raise ConflictError("Bravo chưa nối với DW: đọc lại bằng tệp xuất từ Bravo")
        scope = sales_scope(context)
        async with self.sales(scope) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
        if case.case_version != case_version:
            raise ConflictError(STALE_CASE_VERSION, details={"rule": "stale_case_version"})
        if case.status not in READ_BACK_ON:
            raise ConflictError(
                "đơn chưa ở bước nhập Bravo: chưa có gì để đọc lại",
                details={"status": case.status.value, "rule": "not_entered"},
            )
        try:
            found = await self.bravo.by_customer_po(scope, case.customer_code, case.header.po_no)
        except BravoUnreachableError:
            raise ConflictError("chưa đọc được Bravo: thử lại sau") from None
        if found is None:
            raise ConflictError(
                "Bravo chưa có SO nào cho PO này của khách", details={"rule": "no_so"}
            )
        order, digest = found
        if order.so_no is None:
            raise ConflictError(
                "PO này nằm ở nhiều SO trong Bravo: không so tự động",
                details={"so_numbers": list(order.so_numbers), "rule": "several_sos"},
            )
        differences = compare(prepared_rows(case), order, confirmed_dates=True)
        await store_read_back(
            self.uow, self.ids, self.clock, context, case, order, differences, digest
        )
        return await self.latest(context, case_id)
