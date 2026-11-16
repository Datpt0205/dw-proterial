"""A case's Bravo upload file filled with its customer's SalesOrder skill,
where the tenant's rules turn the step on and its live eval met the bar
(ticket 41, dw_sales ADR 0013 as amended under ADR 0014).

`CaseSalesOrderFill.fill_case` is asked by the artifact service before it
draws a case's ``bravo_upload`` file (`artifacts_service.ArtifactService`,
`order_artifacts.bravo_upload`). It fills nothing, and the customer's learned
rules (ADR 0013) fill the file as before, unless every one of these holds:

- the tenant's order rules turn `ModelStep.SALESORDER_SKILL` on and its
  live eval met the bar for the model and prompt it runs on now
  (`ModelStepGatePort`, `model_readiness`): off is the fallback;
- the case's lines are all mapped (the file is refused otherwise, as before);
- the model gave a usable answer within the caller's plan (the one-call
  door): no answer, or the plan's day spent, is the fallback.

Then the rows are the file's own (`order_artifacts.upload_rows`, the case's
values as entered: Sales' corrections, Sales' PRV codes), the tools are bound
to the case's customer, the skill is the customer's in force for the
caller's tenant, and every cell is traced (`salesorder_fill.trace`). What
cannot be traced is left blank and listed in the file for the PIC. The file
is still approved by a person before it reaches Bravo (ADR 0026): the step's
tier is T2 (`domain.autonomy.STEP_TIERS`), so nothing of it applies itself.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from dw_agent_runtime.context import caller_run
from dw_agent_runtime.model.interpretation import ModelUnavailableError
from dw_kernel.errors import ConflictError, QuotaExceededError
from dw_kernel.ports import IdGenerator
from dw_platform.application.access_context import AccessContext
from dw_platform.application.rule_versions import ContextScope
from dw_sales.application.access import sales_scope
from dw_sales.application.drafting import ArtifactCopyPort
from dw_sales.application.local_time import local_day
from dw_sales.application.order_artifacts import file_rows, upload_rows
from dw_sales.application.order_ports import ModelStepGatePort, OrderRulesPort
from dw_sales.application.ports import SalesScope, Snapshot
from dw_sales.application.salesorder_fill import (
    PO_FIELDS,
    PoRow,
    SalesOrderFiller,
    SalesOrderTools,
    TracedFill,
)
from dw_sales.application.salesorder_skills import customer_skill
from dw_sales.application.skills import SkillBook
from dw_sales.domain.catalog import ConvertEntry, Customer, Item
from dw_sales.domain.order_checks import ModelStep
from dw_sales.domain.orders import OrderCase

__all__ = ["CaseSalesOrderFill", "case_rows"]

_LOG = logging.getLogger("dw_sales.salesorder_case_fill")


class FillCatalogPort(Protocol):
    """What a case's fill reads of the master data (`SalesCatalogPort`'s own
    methods): the customer's record, the convert list and the items, which
    its tools are bound to."""

    async def customer_by_code(self, scope: SalesScope, code: str) -> Snapshot[Customer | None]: ...

    async def convert_list(self, scope: SalesScope) -> Snapshot[Sequence[ConvertEntry]]: ...

    async def items(self, scope: SalesScope) -> Snapshot[Sequence[Item]]: ...


def case_rows(case: OrderCase, received: date) -> list[PoRow]:
    """The case's upload rows, a row per delivery as the file holds them
    (`order_artifacts.file_rows`), each at its anchors. Raises
    `ConflictError` for a line with no PRV code, as drawing the file does."""
    deliveries = (row for line in case.lines for row in upload_rows(case, line))
    rows = file_rows(deliveries, received)
    return [
        PoRow(number, {name: row.get(name) for name in PO_FIELDS})
        for number, row in enumerate(rows, start=1)
    ]


@dataclass(frozen=True)
class CaseSalesOrderFill:
    """Fills a case's upload file with its customer's skill (module docstring)."""

    rules: OrderRulesPort
    gate: ModelStepGatePort
    copy: ArtifactCopyPort
    catalog: FillCatalogPort
    book: SkillBook
    filler: SalesOrderFiller
    ids: IdGenerator
    worker_id: str
    worker_version: str

    async def fill_case(self, context: AccessContext, case: OrderCase) -> TracedFill | None:
        """The case's rows filled and traced; None where the step does not
        run for the tenant or gave no usable answer: the rules fill it."""
        scope = sales_scope(context)
        rules = await self.rules.rules(scope)
        if not await self.gate.allows(scope, rules, ModelStep.SALESORDER_SKILL):
            return None
        customer = (await self.catalog.customer_by_code(scope, case.customer_code)).data
        if customer is None:
            return None
        copy = await self.copy.artifact_copy(scope, [])
        try:
            rows = case_rows(case, local_day(case.received_at, copy.zone))
        except ConflictError:
            return None
        tools = SalesOrderTools.bound(
            customer,
            (await self.catalog.convert_list(scope)).data,
            (await self.catalog.items(scope)).data,
        )
        skill = await customer_skill(self.book, ContextScope.of(context), case.customer_code)
        run = caller_run(
            context,
            run_id=self.ids.new_uuid(),
            worker_id=self.worker_id,
            worker_version=self.worker_version,
            trace="sales-salesorder-fill",
            subject_ref=f"sales_order_case:{case.case_id}",
        )
        try:
            return await self.filler.fill(
                layout=copy.upload, rows=rows, tools=tools, skill=skill, run=run
            )
        except (ModelUnavailableError, QuotaExceededError) as fallback:
            # Ids and the reason's type only: the learned rules fill it.
            _LOG.info(
                "SalesOrder skill not used for case %s of tenant %s: %s",
                case.case_id,
                scope.tenant_id.value,
                type(fallback).__name__,
            )
            return None
