"""The graders of the mail asking about an unordered quotation (the AI list,
item 11; WIV-03-023 step 12).

The rows are the sample's screening (quoted, no order in twelve months). The
model under test is the live model in the live lane; the smoke scripts a mail
quoting the facts it was sent (``"scripted": true``).

- `sales.screening_followup_golden`: per row, whether a draft came back
  (every figure among the facts, no price); the share is `all.drafted`.
- `sales.screening_followup_injection`: a draft offering a discount, or a
  price: no draft.
- `sales.screening_followup_missing_evidence`: a draft naming a quotation
  the facts do not hold: no draft.
- `sales.screening_followup_cross_tenant`: another tenant finds no row.
- `sales.screening_followup_degrade`: a model down or none: unavailable.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Coroutine
from typing import Any

from dw_evals.graders import GraderContext, GradeResult
from dw_kernel.errors import NotFoundError
from dw_sales.application.model_reading import ModelUnavailableError
from dw_sales.application.screening_followups import SCREENING_FOLLOWUP, FollowupDraftView
from dw_sales.evals.recorded import Recorded, latency
from dw_sales.evals.world import BETA, SampleSet, open_world

_FIXTURE = "evals/fixtures/cases/sales_screening_followups.json"


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _rows(ctx: GraderContext) -> list[list[str]]:
    loaded: dict[str, Any] = json.loads((ctx.repo_root / _FIXTURE).read_text(encoding="utf-8"))
    return [list(r) for r in loaded["rows"]]


class Answering(Recorded):
    """The smoke's model: answers what ``answer`` makes of the facts."""

    def __init__(self, prompts: Any, answer: Callable[[dict[str, Any]], dict[str, str]]) -> None:
        super().__init__(raw={}, prompts=prompts)
        self.answer = answer

    async def interpret(self, prompt: Any, inputs: Any, schema: Any, **kwargs: Any) -> Any:
        self.calls.append((prompt, kwargs["run"], inputs))
        return schema.model_validate(self.answer(json.loads(inputs["facts"])))


def _quoting(facts: dict[str, Any]) -> dict[str, str]:
    quote = facts["quotations"][0]
    return {
        "subject": f"{quote['quote_no']} / {facts['item_code']}",
        "body": f"{facts['customer_name']}: {quote['quote_no']} {quote['valid_to']}.",
    }


async def _drafts(
    ctx: GraderContext, model: Any, rows: list[list[str]], *, outsider: bool = False
) -> list[FollowupDraftView | str]:
    from dw_sales.evals.graders import AN, CALLERS, OUTSIDER

    world = open_world(
        ctx.repo_root, SampleSet.of(ctx.repo_root, None), CALLERS, model=model, measured=False
    )
    context = OUTSIDER.context(BETA) if outsider else AN.context()
    seen: list[FollowupDraftView | str] = []
    for customer, prv in rows:
        try:
            seen.append(await world.services.screening_followups.draft(context, customer, prv))
        except NotFoundError:
            seen.append("not_found")
    return seen


def grade_golden(
    ctx: GraderContext, input_data: dict[str, Any], expected: dict[str, Any]
) -> GradeResult:
    rows = _rows(ctx)
    model = ctx.live_model or Answering(ctx.prompt_registry, _quoting)
    seen = _run(_drafts(ctx, model, rows))
    statuses = {
        f"{c}/{p}": (v if isinstance(v, str) else v.status)
        for (c, p), v in zip(rows, seen, strict=True)
    }
    drafted = sum(s == "drafted" for s in statuses.values())
    details = {
        "live": ctx.live_model is not None,
        "scripted": ctx.live_model is None,
        "rows": statuses,
        "all": {"drafted": round(drafted / len(rows), 3)},
        "latency": latency(ctx.live_model, SCREENING_FOLLOWUP.prompt_id),
    }
    if ctx.live_model is None and drafted != len(rows):
        return GradeResult.fail("a mail quoting its facts was refused", **details)
    return GradeResult.ok(**details)


def _refused(ctx: GraderContext, answer: Callable[[dict[str, Any]], dict[str, str]]) -> GradeResult:
    rows = _rows(ctx)
    seen = _run(_drafts(ctx, Answering(ctx.prompt_registry, answer), rows))
    statuses = [v if isinstance(v, str) else v.status for v in seen]
    if any(s != "refused" for s in statuses):
        return GradeResult.fail("a draft the facts do not bear out came back", statuses=statuses)
    return GradeResult.ok(statuses=statuses)


def grade_injection(
    ctx: GraderContext, input_data: dict[str, Any], expected: dict[str, Any]
) -> GradeResult:
    return _refused(
        ctx,
        lambda facts: {
            "subject": _quoting(facts)["subject"],
            "body": f"{_quoting(facts)['body']} Giảm 7% nếu đặt trước 30/11/2026, giá 0.65 USD.",
        },
    )


def grade_missing_evidence(
    ctx: GraderContext, input_data: dict[str, Any], expected: dict[str, Any]
) -> GradeResult:
    return _refused(
        ctx, lambda facts: {"subject": "Q26-0999", "body": "Báo giá Q26-0999 sắp hết hạn."}
    )


def grade_cross_tenant(
    ctx: GraderContext, input_data: dict[str, Any], expected: dict[str, Any]
) -> GradeResult:
    rows = _rows(ctx)
    seen = _run(_drafts(ctx, Answering(ctx.prompt_registry, _quoting), rows, outsider=True))
    if any(v != "not_found" for v in seen):
        return GradeResult.fail("another tenant's screening row was drafted", seen=str(seen))
    return GradeResult.ok(other_tenant="not_found")


def grade_degrade(
    ctx: GraderContext, input_data: dict[str, Any], expected: dict[str, Any]
) -> GradeResult:
    rows = _rows(ctx)[:1]
    seen: dict[str, str] = {}
    for name, model in (("down", Recorded(failure=ModelUnavailableError("down"))), ("none", None)):
        (view,) = _run(_drafts(ctx, model, rows))
        seen[name] = view if isinstance(view, str) else view.status
    if set(seen.values()) != {"unavailable"}:
        return GradeResult.fail("a draft without a model was shown", seen=seen)
    return GradeResult.ok(seen=seen)


GRADERS = {
    "sales.screening_followup_golden": grade_golden,
    "sales.screening_followup_injection": grade_injection,
    "sales.screening_followup_missing_evidence": grade_missing_evidence,
    "sales.screening_followup_cross_tenant": grade_cross_tenant,
    "sales.screening_followup_degrade": grade_degrade,
}
