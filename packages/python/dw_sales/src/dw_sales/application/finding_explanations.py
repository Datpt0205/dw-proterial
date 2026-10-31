"""A finding explained in words, by the model (the AI list, item 12).

Đạt, 2026-10-29: "không nên cho code viết ... cứ dồn việc cho nó làm đi". A
finding is a code and two values compared (`expected`, `actual`); a person
had to know what each code means and look the rest up. On request, the model
writes what the finding means for this line and what to check, in Vietnamese,
from **facts code gathers**: the finding, the PO's header and line, what the
line was checked against (`LineBasis`), and the customer's other quotations
for the item valid today. Code then refuses an answer that holds a number, a
date or a code no fact holds, so every figure in it is one the case has.

- Who sees which amounts is the case view's rule (`PriceView`): a caller who
  reads no price is given no amount among the facts, and a price-bearing
  finding is not explained to them at all.
- The model never decides: it does not dispose of a finding, and is asked
  not to advise accepting one; the person still decides and writes the
  reason (ADR 0005, "what stays human").
- Nothing is stored. Each request is one call through the one-call door, as
  the caller (their plan's allowance); no model, an unusable answer or a
  refused one says DW1 could not explain it.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from dw_agent_runtime.model.figure_check import unsupported
from dw_kernel.errors import NotFoundError, PermissionDeniedError, QuotaExceededError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, PriceView, SalesScopes, sales_scope
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.model_reading import InterpretationPort, ModelUnavailableError, PromptRef
from dw_sales.application.ports import SalesCatalogPort, SalesScope
from dw_sales.application.runs import caller_run
from dw_sales.application.support import stored_order
from dw_sales.application.views import PRICE_BEARING_ORDER_CODES
from dw_sales.domain.orders import Finding, OrderCase
from dw_sales.domain.process import DW_NAMES

# The prompt a finding is explained with. Its file is
# `configs/prompts/sales/finding_explanation@1.0.0.yaml`; a test holds the two
# together, and the rendered prompt under `PROMPT_TOKENS`.
FINDING_EXPLANATION: Final = PromptRef("sales.finding_explanation", "1.0.0")
PROMPT_TOKENS: Final = 1300
_OUTPUT_TOKENS: Final = 600
_ORDER: Final = "sales_order_case"

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class ModelExplanation(BaseModel):
    """What the model writes: the meaning, and what to check (optional)."""

    model_config = _FROZEN

    explanation: str = Field(min_length=1, max_length=700)
    check: str | None = Field(default=None, max_length=300)


class FindingExplanationView(BaseModel):
    """An explanation, or why there is none; always marked as the model's."""

    model_config = ConfigDict(frozen=True)

    finding_key: str
    status: Literal["explained", "unavailable", "refused"]
    explanation: str | None = None
    check: str | None = None
    prompt_ref: str | None = None
    model_profile: str | None = None


def unsupported_figures(answer: ModelExplanation, facts: str) -> set[str]:
    """The figures the answer holds that no fact holds (`figure_check`)."""
    return unsupported(f"{answer.explanation} {answer.check or ''}", facts, names=DW_NAMES)


def _text(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, date):
        return value.isoformat()
    return value


def explanation_facts(
    case: OrderCase,
    finding: Finding,
    prices: PriceView,
    other_quotations: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    """What the model is told: code-built, amounts only for a caller who reads
    them."""
    header = case.effective_header
    facts: dict[str, Any] = {
        "finding": {
            "code": finding.code.value,
            "severity": finding.severity.value,
            "line_no": finding.line_no,
            "expected": finding.expected,
            "actual": finding.actual,
            "rules": finding.rule_version,
        },
        "po": {
            "customer_code": case.customer_code,
            "po_no": header.po_no,
            "po_date": header.po_date.isoformat(),
            "currency": header.currency,
            "received_on": case.received_at.date().isoformat(),
        },
    }
    if finding.line_no is not None:
        line = case.line(finding.line_no)
        printed = line.effective
        facts["line"] = {
            "customer_item_code": printed.customer_item_code,
            "description": printed.description,
            "quantity": _text(printed.quantity),
            "uom": printed.uom,
            "requested_date": _text(printed.requested_date),
            "prv_code": line.mapping.prv_code,
            "mapping": line.mapping.status.value,
            **({"unit_price": _text(printed.unit_price)} if prices.amounts else {}),
        }
        basis = line.basis
        checked: dict[str, Any] = {"lead_time_days": basis.lead_time_days}
        if basis.item is not None:
            checked["item"] = {
                "prv_code": basis.item.prv_code,
                "moq": _text(basis.item.moq),
                "pack_multiple": _text(basis.item.pack_multiple),
                "standard_lead_time_days": basis.item.standard_lead_time_days,
            }
        if basis.quotation is not None:
            quote = basis.quotation
            checked["quotation"] = {
                "quote_no": quote.quote_no,
                "valid_from": quote.valid_from.isoformat(),
                "valid_to": quote.valid_to.isoformat(),
                "moq": _text(quote.moq),
                "lead_time_days": quote.lead_time_days,
                **(
                    {"unit_price": _text(quote.unit_price), "currency": quote.currency}
                    if prices.amounts
                    else {}
                ),
            }
        facts["checked_against"] = checked
        if other_quotations:
            facts["other_quotations_valid_today"] = list(other_quotations)
    return facts


@dataclass(frozen=True)
class FindingExplanations:
    """`GET /orders/{case_id}/findings/{key}/explanation` (module docstring)."""

    uow: SalesUnitOfWorkFactory
    gate: Gate
    catalog: SalesCatalogPort
    model: InterpretationPort | None
    clock: UtcClock
    ids: IdGenerator
    worker_id: str
    worker_version: str

    async def explain(
        self, context: AccessContext, case_id: uuid.UUID, finding_key: str
    ) -> FindingExplanationView:
        await self.gate.require(
            context, SalesScopes.CASE_READ, resource_type=_ORDER, resource_id=str(case_id)
        )
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
        finding = next((f for f in case.findings if f.key == finding_key), None)
        if finding is None:
            raise NotFoundError("no such finding", details={"finding_key": finding_key})
        prices = PriceView.of(context, self.gate.authz)
        if finding.code in PRICE_BEARING_ORDER_CODES and not prices.amounts:
            raise PermissionDeniedError(
                "giải thích cờ này cần quyền xem giá",
                details={"action": SalesScopes.PRICE_READ.value, "resource_type": _ORDER},
            )
        if self.model is None:
            return FindingExplanationView(finding_key=finding_key, status="unavailable")
        facts = json.dumps(
            explanation_facts(
                case, finding, prices, await self._others(scope, case, finding, prices)
            ),
            ensure_ascii=False,
            indent=1,
        )
        stamp = {
            "finding_key": finding_key,
            "prompt_ref": str(FINDING_EXPLANATION),
            "model_profile": self.model.model_profile,
        }
        try:
            answer = await self.model.interpret(
                FINDING_EXPLANATION,
                {"facts": facts},
                ModelExplanation,
                run=caller_run(
                    context,
                    run_id=self.ids.new_uuid(),
                    worker_id=self.worker_id,
                    worker_version=self.worker_version,
                    trace="sales-explain",
                    subject_ref=f"{_ORDER}:{case_id}",
                ),
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except (ModelUnavailableError, QuotaExceededError):
            return FindingExplanationView(**stamp, status="unavailable")
        if unsupported_figures(answer, facts):
            return FindingExplanationView(**stamp, status="refused")
        return FindingExplanationView(
            **stamp, status="explained", explanation=answer.explanation, check=answer.check
        )

    async def _others(
        self, scope: SalesScope, case: OrderCase, finding: Finding, prices: PriceView
    ) -> list[dict[str, Any]]:
        """The customer's quotations for the line's item valid today: what a
        person would look up next. Only for a caller who reads amounts."""
        if finding.line_no is None or not prices.amounts:
            return []
        prv = case.line(finding.line_no).mapping.prv_code
        if prv is None:
            return []
        today = self.clock.now().date()
        found = await self.catalog.quotations_valid_on(scope, case.customer_code, prv, today)
        return [
            {
                "quote_no": q.quote_no,
                "unit_price": _text(q.unit_price),
                "currency": q.currency,
                "valid_from": q.valid_from.isoformat(),
                "valid_to": q.valid_to.isoformat(),
            }
            for q in found.data
        ][:5]
