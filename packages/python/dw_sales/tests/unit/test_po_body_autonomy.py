"""Which values of a PO written in the mail may apply themselves, and the
gate stamped on each at intake (ticket 44; Đạt, 2026-11-18). Nothing applies
a PO's value yet: a value that clears the threshold is logged as `shadow`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from dw_agent_runtime.model.scoring import Scored
from dw_sales.application.po_body_reading import PO_BODY_EXTRACTION
from dw_sales.domain.autonomy import StepThreshold, Tier
from dw_sales.domain.order_checks import ModelStep
from dw_sales.domain.orders import FindingCode, OrderCase, RegionFlag
from dw_sales.domain.po_body_autonomy import may_apply_itself
from dw_sales.evals.graders import AN, CALLERS
from dw_sales.evals.recorded import ByPrompt, Recorded
from dw_sales.evals.world import ALPHA, SampleWith, open_world

from .test_po_body import REPO, VI, _model, _process

pytestmark = pytest.mark.unit


async def _case() -> OrderCase:
    _, _, case = await _process(_model(VI["answer"]))
    assert isinstance(case, OrderCase)
    return case


def _without(case: OrderCase, code: FindingCode, line_no: int | None) -> OrderCase:
    kept = tuple(f for f in case.findings if not (f.code is code and f.line_no == line_no))
    return case.model_copy(update={"findings": kept})


def _gate(case: OrderCase, line_no: int | None, field: str) -> str | None:
    flags = case.header.flags if line_no is None else case.line(line_no).po_line.flags
    (flag,) = [f for f in flags if f.field == field and f.flag is RegionFlag.MODEL_READ]
    return flag.gate


async def test_the_pos_own_values_may_while_no_other_finding_of_the_po_stands() -> None:
    case = await _case()
    for field in ("po_no", "revision", "po_date", "currency"):
        assert may_apply_itself(case, None, field)
    # Another finding of the PO (a duplicate) keeps all of them a person's.
    (uncertain,) = [f for f in case.findings if f.line_no is None and f.is_open]
    duplicate = uncertain.model_copy(update={"code": FindingCode.DUPLICATE_PO})
    blocked = case.model_copy(update={"findings": (*case.findings, duplicate)})
    assert not any(may_apply_itself(blocked, None, f) for f in ("po_no", "currency"))
    # A PO read from a file is never put to this gate.
    filed = case.model_copy(update={"document": case.document.model_copy(update={"body": None})})
    assert not may_apply_itself(filed, None, "po_no")


async def test_a_lines_price_and_quantity_may_only_where_they_match_and_nothing_else_stands() -> (
    None
):
    case = await _case()
    # Line 1 is short of its lead time: nothing of it applies itself.
    assert not may_apply_itself(case, 1, "unit_price")
    clear = _without(case, FindingCode.REQUESTED_DATE_SHORT_LT, 1)
    # The price equals the quotation's; the item states MOQ and pack multiple.
    assert may_apply_itself(clear, 1, "unit_price") and may_apply_itself(clear, 1, "quantity")
    # Everything else of a line stays a person's.
    for field in ("description", "customer_item_code", "uom", "requested_date", "amount"):
        assert not may_apply_itself(clear, 1, field)
    line = clear.line(1)
    assert line.basis.quotation is not None
    other_price = line.basis.quotation.model_copy(
        update={"unit_price": line.po_line.unit_price + 1}
    )
    repriced = clear.model_copy(
        update={
            "lines": tuple(
                ln.model_copy(
                    update={"basis": ln.basis.model_copy(update={"quotation": other_price})}
                )
                if ln.line_no == 1
                else ln
                for ln in clear.lines
            )
        }
    )
    assert not may_apply_itself(repriced, 1, "unit_price")
    assert line.basis.item is not None
    unstated = clear.model_copy(
        update={
            "lines": tuple(
                ln.model_copy(
                    update={
                        "basis": ln.basis.model_copy(
                            update={"item": line.basis.item.model_copy(update={"moq": None})}
                        )
                    }
                )
                if ln.line_no == 1
                else ln
                for ln in clear.lines
            )
        }
    )
    assert not may_apply_itself(unstated, 1, "quantity")


async def test_with_no_threshold_every_value_read_is_stamped_for_a_person() -> None:
    case = await _case()
    assert _gate(case, None, "po_no") == "person"
    assert _gate(case, 1, "unit_price") == "person"


class _Sure(ByPrompt):
    """Every PO value read at 0.99, every other call unscored."""

    async def interpret_scored(self, prompt: Any, inputs: Any, schema: Any, **kw: Any) -> Any:
        answer = await self.interpret(prompt, inputs, schema, **kw)
        spans = ("po_no_span", "po_date_span", "currency_span", "lines.0.description_span")
        return Scored(answer, dict.fromkeys(spans, 0.99))


async def test_a_value_that_clears_the_threshold_is_logged_as_shadow_and_never_applied() -> None:
    """Nothing applies a PO's value yet (its effect and undo are the next
    slice): above a certified threshold, an eligible value is `shadow`, one
    the rule keeps a person's stays `person` whatever its confidence."""
    intent = Recorded(raw={"language": "vi", "referenced_number_spans": [], "kind": "po"})
    model = _Sure(
        {"sales.message_intent": intent, PO_BODY_EXTRACTION.prompt_id: Recorded(raw=VI["answer"])}
    )
    spec = VI["message"]
    with SampleWith([spec]) as sample:
        world = open_world(REPO, sample, CALLERS, model=model)
        threshold = StepThreshold(
            step=ModelStep.PO_BODY_EXTRACTION,
            prompt=str(PO_BODY_EXTRACTION),
            model_profile="onprem",
            tier=Tier.APPLIES_ITSELF,
            target=0.05,
            needed=59,
            cases=100,
            threshold=0.5,
            accepted=80,
            errors=0,
            audits=0,
            audit_errors=0,
            stopped=False,
            computed_at=datetime(2026, 11, 18, tzinfo=UTC),
        )
        await world.store.save(ALPHA, [threshold], [])
        ((_, case),) = (await world.process_each(AN, [spec["message_id"]])).values()
        served = await world.services.orders.get(AN.context(), case.case_id)
    assert isinstance(case, OrderCase)
    gates = {f: _gate(case, None, f) for f in ("po_no", "po_date", "currency")}
    assert set(gates.values()) <= {"shadow", "audit"} and "shadow" in gates.values()
    # The PO number's span is the revision's too; the description is never
    # put to the gate, however sure the model was.
    assert _gate(case, None, "revision") in {"shadow", "audit"}
    assert _gate(case, 1, "description") == "person"
    flags = [*case.header.flags, *(f for ln in case.lines for f in ln.po_line.flags)]
    assert all(f.gate != "applied" for f in flags)
    # The case page is never served the gate: a value sampled for the audit
    # reaches its person as any other does, or the audit would not be blind.
    assert '"gate"' not in served.model_dump_json()
    assert any(f.confidence is not None for f in served.header_flags)
