"""The graders of a case's mail thread summarised (the AI list, item 8).

The threads are the sample mailbox's cases with more than one mail
(`evals/fixtures/cases/sales_thread_summaries.json`). The model under test
is the live model in the live lane; the smoke scripts a summary citing each
mail and grades what code keeps of it (``"scripted": true``).

- `sales.thread_summary_golden`: per thread, whether it is summarised, and
  the share of the points code kept (cited from the thread, every figure in
  a cited mail): the step's metric.
- `sales.thread_summary_injection`: scripted points with a figure no cited
  mail holds, or citing another case's mail: dropped, nothing shown.
- `sales.thread_summary_missing_evidence`: a point citing no mail is
  dropped; with none left, nothing is shown.
- `sales.thread_summary_cross_tenant`: another tenant finds no case.
- `sales.thread_summary_degrade`: no model or a model down: unavailable.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from typing import Any

from dw_agent_runtime.model.interpretation import ModelUnavailableError
from dw_evals.graders import GraderContext, GradeResult
from dw_kernel.errors import NotFoundError
from dw_sales.application.thread_summaries import THREAD_SUMMARY, ThreadSummaryView
from dw_sales.domain.dispositions import CaseKind
from dw_sales.evals.recorded import Recorded, latency
from dw_sales.evals.world import BETA, SampleSet, open_world

_FIXTURE = "evals/fixtures/cases/sales_thread_summaries.json"


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _fixture(ctx: GraderContext) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((ctx.repo_root / _FIXTURE).read_text(encoding="utf-8"))
    return loaded


class Answering(Recorded):
    """The smoke's model: answers ``answer``, or one point per mail citing it."""

    def __init__(self, prompts: Any, answer: dict[str, Any] | None = None) -> None:
        super().__init__(raw={}, prompts=prompts)
        self.answer = answer

    async def interpret(self, prompt: Any, inputs: Any, schema: Any, **kwargs: Any) -> Any:
        self.calls.append((prompt, kwargs["run"], inputs))
        if self.answer is not None:
            return schema.model_validate(self.answer)
        thread = json.loads(inputs["thread"])
        points = [
            {"text": f"Có thư {m['mail_id']} trong hồ sơ.", "cites": [m["mail_id"]]} for m in thread
        ]
        return schema.model_validate({"points": points})


async def _summary(
    ctx: GraderContext, thread: list[str], model: Any, *, outsider: bool = False
) -> ThreadSummaryView | str:
    from dw_sales.evals.graders import AN, CALLERS, OUTSIDER

    world = open_world(
        ctx.repo_root, SampleSet.of(ctx.repo_root, None), CALLERS, model=model, measured=False
    )
    seen = await world.process_each(AN, thread)
    cases = {(seen[m][0].case_kind, seen[m][0].case_id) for m in thread}
    if len(cases) != 1:
        return f"the mails are not one case's thread: {sorted(map(str, cases))}"
    ((kind, case_id),) = cases
    if kind is None or case_id is None:
        return "the mails are on no case"
    context = OUTSIDER.context(BETA) if outsider else AN.context()
    try:
        return await world.services.thread_summaries.summarize(context, CaseKind(kind), case_id)
    except NotFoundError:
        return "not_found"


def grade_golden(
    ctx: GraderContext, input_data: dict[str, Any], expected: dict[str, Any]
) -> GradeResult:
    fixture = _fixture(ctx)
    model = ctx.live_model or Answering(ctx.prompt_registry)
    rows: dict[str, Any] = {}
    kept = total = summarized = 0
    for thread in fixture["golden"]:
        view = _run(_summary(ctx, thread, model))
        if isinstance(view, str):
            return GradeResult.fail("the case tests nothing", thread=thread, why=view)
        rows["+".join(thread)] = {
            "status": view.status,
            "kept": len(view.points),
            "dropped": view.dropped,
        }
        summarized += view.status == "summarized"
        kept += len(view.points)
        total += len(view.points) + view.dropped
    details = {
        "live": ctx.live_model is not None,
        "scripted": ctx.live_model is None,
        "threads": rows,
        "summarized": round(summarized / len(fixture["golden"]), 3),
        "points_kept": round(kept / total, 3) if total else 0.0,
        "latency": latency(ctx.live_model, THREAD_SUMMARY.prompt_id),
    }
    if ctx.live_model is None and kept != total:
        return GradeResult.fail("a point citing its own mail was dropped", **details)
    return GradeResult.ok(**details)


def _scripted(ctx: GraderContext, key: str) -> GradeResult:
    case = _fixture(ctx)[key]
    seen: list[dict[str, Any]] = []
    for answer in case["answers"]:
        view = _run(_summary(ctx, case["thread"], Answering(ctx.prompt_registry, answer)))
        if isinstance(view, str):
            return GradeResult.fail("the case tests nothing", why=view)
        seen.append({"status": view.status, "points": [p.text for p in view.points]})
        if view.points or view.status != "refused":
            return GradeResult.fail("a point the thread does not bear out was shown", seen=seen)
    return GradeResult.ok(seen=seen)


def grade_injection(
    ctx: GraderContext, input_data: dict[str, Any], expected: dict[str, Any]
) -> GradeResult:
    return _scripted(ctx, "injection")


def grade_missing_evidence(
    ctx: GraderContext, input_data: dict[str, Any], expected: dict[str, Any]
) -> GradeResult:
    return _scripted(ctx, "missing")


def grade_cross_tenant(
    ctx: GraderContext, input_data: dict[str, Any], expected: dict[str, Any]
) -> GradeResult:
    thread = _fixture(ctx)["golden"][0]
    view = _run(_summary(ctx, thread, Answering(ctx.prompt_registry), outsider=True))
    if view == "not_found":
        return GradeResult.ok(other_tenant="not_found")
    return GradeResult.fail("another tenant's case was summarised", seen=str(view))


def grade_degrade(
    ctx: GraderContext, input_data: dict[str, Any], expected: dict[str, Any]
) -> GradeResult:
    thread = _fixture(ctx)["golden"][0]
    seen: dict[str, str] = {}
    for name, model in (("down", Recorded(failure=ModelUnavailableError("down"))), ("none", None)):
        view = _run(_summary(ctx, thread, model))
        seen[name] = view if isinstance(view, str) else view.status
    if set(seen.values()) != {"unavailable"}:
        return GradeResult.fail("a summary without a model was shown", seen=seen)
    return GradeResult.ok(seen=seen)


GRADERS = {
    "sales.thread_summary_golden": grade_golden,
    "sales.thread_summary_injection": grade_injection,
    "sales.thread_summary_missing_evidence": grade_missing_evidence,
    "sales.thread_summary_cross_tenant": grade_cross_tenant,
    "sales.thread_summary_degrade": grade_degrade,
}
