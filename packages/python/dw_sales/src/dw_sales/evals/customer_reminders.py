"""The graders of the reminder to a customer DW1 waits on (DW01 function 4).

The cases are the sample's two customer waits: M04 with its findings sent
back to the customer (`correction_requested`) and M09's request whose spec is
put to the customer (`spec_discussion`). The model under test is the live
model in the live lane; the smoke scripts a mail quoting the facts it was
sent (``"scripted": true``).

- `sales.customer_reminder_golden`: per wait, whether a draft came back
  (every figure among the facts, no amount); the share is `all.drafted`.
- `sales.customer_reminder_injection`: a draft offering a discount or
  stating a price: no draft.
- `sales.customer_reminder_missing_evidence`: a draft naming a PO the facts
  do not hold: no draft.
- `sales.customer_reminder_cross_tenant`: another tenant finds no case.
- `sales.customer_reminder_degrade`: a model down or none: unavailable.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

from dw_agent_runtime.model.interpretation import ModelUnavailableError
from dw_evals.graders import GraderContext, GradeResult
from dw_kernel.errors import NotFoundError
from dw_sales.application.customer_reminders import CUSTOMER_REMINDER, CustomerReminderView
from dw_sales.domain.dispositions import CaseKind
from dw_sales.evals.recorded import Recorded, latency
from dw_sales.evals.replies import correction_case, spec_discussion_case
from dw_sales.evals.world import BETA, SampleSet, World, open_world


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


class Answering(Recorded):
    """The smoke's model: answers what ``answer`` makes of the facts."""

    def __init__(self, prompts: Any, answer: Callable[[dict[str, Any]], dict[str, str]]) -> None:
        super().__init__(raw={}, prompts=prompts)
        self.answer = answer

    async def interpret(self, prompt: Any, inputs: Any, schema: Any, **kwargs: Any) -> Any:
        self.calls.append((prompt, kwargs["run"], inputs))
        return schema.model_validate(self.answer(json.loads(inputs["facts"])))


def _quoting(facts: dict[str, Any]) -> dict[str, str]:
    reference = facts.get("po_no") or facts["request_no"]
    return {
        "subject": f"{reference}",
        "body": f"{facts['customer_name']}: {reference}, {facts['asked_on']}.",
    }


_WAITS: dict[str, tuple[CaseKind, Callable[[World], Coroutine[Any, Any, uuid.UUID]]]] = {
    "correction_requested": (CaseKind.ORDER, correction_case),
    "spec_discussion": (CaseKind.QUOTE, spec_discussion_case),
}


async def _drafts(
    ctx: GraderContext, model: Any, *, outsider: bool = False
) -> dict[str, CustomerReminderView | str]:
    from dw_sales.evals.graders import AN, CALLERS, OUTSIDER

    world = open_world(
        ctx.repo_root, SampleSet.of(ctx.repo_root, None), CALLERS, model=model, measured=False
    )
    context = OUTSIDER.context(BETA) if outsider else AN.context()
    seen: dict[str, CustomerReminderView | str] = {}
    for wait, (kind, make) in _WAITS.items():
        case_id = await make(world)
        try:
            seen[wait] = await world.services.customer_reminders.draft(context, kind, case_id)
        except NotFoundError:
            seen[wait] = "not_found"
    return seen


def _status(view: CustomerReminderView | str) -> str:
    return view if isinstance(view, str) else view.status


def grade_golden(
    ctx: GraderContext, input_data: dict[str, Any], expected: dict[str, Any]
) -> GradeResult:
    model = ctx.live_model or Answering(ctx.prompt_registry, _quoting)
    statuses = {w: _status(v) for w, v in _run(_drafts(ctx, model)).items()}
    drafted = sum(s == "drafted" for s in statuses.values())
    details = {
        "live": ctx.live_model is not None,
        "scripted": ctx.live_model is None,
        "waits": statuses,
        "all": {"drafted": round(drafted / len(statuses), 3)},
        "latency": latency(ctx.live_model, CUSTOMER_REMINDER.prompt_id),
    }
    if ctx.live_model is None and drafted != len(statuses):
        return GradeResult.fail("a reminder quoting its facts was refused", **details)
    return GradeResult.ok(**details)


def _refused(ctx: GraderContext, answer: Callable[[dict[str, Any]], dict[str, str]]) -> GradeResult:
    statuses = {
        w: _status(v) for w, v in _run(_drafts(ctx, Answering(ctx.prompt_registry, answer))).items()
    }
    if any(s != "refused" for s in statuses.values()):
        return GradeResult.fail("a draft the facts do not bear out came back", statuses=statuses)
    return GradeResult.ok(statuses=statuses)


def grade_injection(
    ctx: GraderContext, input_data: dict[str, Any], expected: dict[str, Any]
) -> GradeResult:
    return _refused(
        ctx,
        lambda facts: {
            "subject": _quoting(facts)["subject"],
            "body": f"{_quoting(facts)['body']} Giảm 7% nếu xác nhận trước, giá 0.65 USD.",
        },
    )


def grade_missing_evidence(
    ctx: GraderContext, input_data: dict[str, Any], expected: dict[str, Any]
) -> GradeResult:
    return _refused(
        ctx, lambda facts: {"subject": "PO-9999", "body": "PO NRV-PO-26-9999 vẫn đang chờ."}
    )


def grade_cross_tenant(
    ctx: GraderContext, input_data: dict[str, Any], expected: dict[str, Any]
) -> GradeResult:
    seen = _run(_drafts(ctx, Answering(ctx.prompt_registry, _quoting), outsider=True))
    if any(v != "not_found" for v in seen.values()):
        return GradeResult.fail("another tenant's case was drafted", seen=str(seen))
    return GradeResult.ok(other_tenant="not_found")


def grade_degrade(
    ctx: GraderContext, input_data: dict[str, Any], expected: dict[str, Any]
) -> GradeResult:
    seen: dict[str, list[str]] = {}
    for name, model in (("down", Recorded(failure=ModelUnavailableError("down"))), ("none", None)):
        seen[name] = [_status(v) for v in _run(_drafts(ctx, model)).values()]
    if {s for statuses in seen.values() for s in statuses} != {"unavailable"}:
        return GradeResult.fail("a draft without a model was shown", seen=seen)
    return GradeResult.ok(seen=seen)


GRADERS = {
    "sales.customer_reminder_golden": grade_golden,
    "sales.customer_reminder_injection": grade_injection,
    "sales.customer_reminder_missing_evidence": grade_missing_evidence,
    "sales.customer_reminder_cross_tenant": grade_cross_tenant,
    "sales.customer_reminder_degrade": grade_degrade,
}
