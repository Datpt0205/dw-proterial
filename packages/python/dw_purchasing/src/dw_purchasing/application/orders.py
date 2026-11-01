"""Draft purchase orders and the Bravo import file (DW02 function 4).

- **Draft** (`draft`, a case whose suppliers are chosen): one order per chosen
  supplier from the chosen offers (`domain.orders.draft_orders`), the
  supplier's name from the master data, the order date today; the tenant's
  Bravo layout (`purchasing_rules.bravo_po`) and the rules it came from are
  stamped beside them. The total of the orders is the selection's, already
  held to what the approver approved; a draft that disagrees is refused.
- **The file** (`bravo_file`): drawn from the stamp, never from the rules in
  force, so the file downloaded tomorrow is the file of the draft. A buyer
  imports it into Bravo; DW2 records nothing there.

Nothing here asks a model: every value in an order is the request's, the
chosen offer's or the master data's.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from pydantic import BaseModel, ConfigDict

from dw_kernel.errors import ConflictError, NotFoundError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import AuditEvent
from dw_purchasing.application.access import Gate, PurchasingScopes
from dw_purchasing.application.intake import CaseChange
from dw_purchasing.application.ports import MasterDataPort, PurchasingUnitOfWork, SpreadsheetPort
from dw_purchasing.application.rules import PurchasingRuleBook
from dw_purchasing.domain.cases import CaseStatus, PurchaseCase
from dw_purchasing.domain.orders import PoRound, bravo_rows, draft_orders

_RESOURCE: Final = "purchase_case"
NO_LAYOUT: Final = "quy tắc mua hàng đang áp dụng chưa có mẫu file Bravo: chưa soạn PO được"
MOCK_LAYOUT: Final = (
    "mẫu file nhập Bravo vẫn là mẫu thử của hệ thống: cài mẫu Bravo của công ty"
    " (Cài đặt DW2) rồi soạn PO"
)
XLSX: Final = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class BravoDownload(BaseModel):
    model_config = ConfigDict(frozen=True)

    filename: str
    media_type: str
    data: bytes


@dataclass(frozen=True)
class PurchaseOrders:
    uow: PurchasingUnitOfWork
    gate: Gate
    rules: PurchasingRuleBook
    master: MasterDataPort
    spreadsheet: SpreadsheetPort
    clock: UtcClock
    ids: IdGenerator
    # A deployed profile (`settings.is_deployed`): the platform's stand-in
    # Bravo layout is refused there.
    deployed: bool = False

    async def draft(
        self, context: AccessContext, case_id: uuid.UUID, *, case_version: int
    ) -> CaseChange:
        await self.gate.require(
            context, PurchasingScopes.PO_PREPARE, resource_type=_RESOURCE, resource_id=str(case_id)
        )
        case = await self._get(context, case_id)
        if case.case_version != case_version:
            raise ConflictError(
                "hồ sơ đã thay đổi: tải lại",
                details={"case_id": str(case_id), "rule": "stale_version"},
            )
        if case.status is not CaseStatus.SUPPLIER_SELECTED or case.selection is None:
            raise ConflictError(
                "chỉ soạn PO khi đã chọn nhà cung cấp cho mọi dòng",
                details={"case_id": str(case_id), "status": case.status.value},
            )
        rules = await self.rules.resolve(context)
        if rules.bravo_po is None:
            raise ConflictError(NO_LAYOUT, details={"rules_ref": rules.ref, "rule": "no_layout"})
        if self.deployed and rules.bravo_po.mock:
            raise ConflictError(
                MOCK_LAYOUT, details={"rules_ref": rules.ref, "rule": "mock_layout"}
            )
        master = await self.master.for_context(context)
        names: dict[str, str] = {}
        for choice in case.selection.choices:
            supplier = master.supplier(choice.supplier_code)
            if supplier is None:
                raise ConflictError(
                    "nhà cung cấp đã chọn không còn trong dữ liệu chủ",
                    details={"supplier_code": choice.supplier_code, "rule": "supplier_gone"},
                )
            names[supplier.code] = supplier.name
        orders = draft_orders(case.request, case.selection, case.offers, names)
        if sum((o.total for o in orders), Decimal(0)) != case.selection.total:
            raise ConflictError(
                "tổng PO khác tổng đã chọn: chọn lại nhà cung cấp",
                details={"case_id": str(case_id), "rule": "total_mismatch"},
            )
        now = self.clock.now()
        round_ = PoRound(
            order_date=now.date(),
            drafted_by=context.principal_id,
            drafted_at=now,
            orders=orders,
            layout=rules.bravo_po,
            rules_ref=rules.ref,
        )
        drafted = PurchaseCase.model_validate(
            {
                **case.model_dump(),
                "case_version": case.case_version + 1,
                "status": CaseStatus.PO_DRAFTED,
                "po": round_,
            }
        )
        async with self.uow(context) as work:
            await work.cases.save(drafted, expected_version=case.case_version)
            await work.audit.append(
                self._audit(
                    context,
                    "purchasing.po.drafted",
                    drafted,
                    {"po_refs": ",".join(o.po_ref for o in orders), "rules_ref": rules.ref},
                )
            )
        return CaseChange(
            case_id=drafted.case_id, case_version=drafted.case_version, status=drafted.status
        )

    async def bravo_file(self, context: AccessContext, case_id: uuid.UUID) -> BravoDownload:
        await self.gate.require(
            context, PurchasingScopes.PO_PREPARE, resource_type=_RESOURCE, resource_id=str(case_id)
        )
        case = await self._get(context, case_id)
        if case.po is None:
            raise ConflictError(
                "hồ sơ chưa có PO nháp", details={"case_id": str(case_id), "rule": "no_po"}
            )
        layout = case.po.layout
        data = self.spreadsheet.write(
            layout.sheet,
            bravo_rows(case.po, case.request),
            date_format=layout.date_format,
            at=case.po.drafted_at,
        )
        async with self.uow(context) as work:
            await work.audit.append(
                self._audit(
                    context, "purchasing.po.exported", case, {"rules_ref": case.po.rules_ref}
                )
            )
        return BravoDownload(
            # A request's number may hold `/`: not in a file name.
            filename=f"bravo-po-{re.sub(r'[^A-Za-z0-9._-]', '_', case.request.pr_no)}.xlsx",
            media_type=XLSX,
            data=data,
        )

    async def _get(self, context: AccessContext, case_id: uuid.UUID) -> PurchaseCase:
        async with self.uow(context) as work:
            case = await work.cases.get(case_id)
        if case is None:
            raise NotFoundError("không có yêu cầu mua hàng này", details={"case_id": str(case_id)})
        return case

    def _audit(
        self,
        context: AccessContext,
        action: str,
        case: PurchaseCase,
        details: dict[str, object],
    ) -> AuditEvent:
        # Ids, refs and the version: no line and no amount.
        return AuditEvent(
            id=self.ids.new_uuid(),
            tenant_id=TenantId(context.tenant_id),
            workspace_id=WorkspaceId(context.workspace_id),
            actor_id=UserId(context.principal_id),
            action=action,
            resource_type=_RESOURCE,
            resource_id=str(case.case_id),
            occurred_at=self.clock.now(),
            details={"case_version": case.case_version, **details},
        )
