"""The morning brief written by the model (the AI list, item 10).

The 07:30 brief (ticket 42) is counts in fixed sentences. Đạt, 2026-10-29:
the model writes, code checks. Where the tenant's `sales_followups` leaves
`morning_brief.model_opening` on and a model is wired, the model writes a
few sentences of what to take first today, from facts code gathers (the
brief's counts and the person's most pressing cases: reference, customer
code, who it waits on, due date and next step; never an amount, a price or a
name). It is not a step of either surveyed lane, so it is no `ModelStep`:
like an explanation or a summary, it is marked as the machine's, checked
figure by figure, and never the only thing the reader gets.

- **Code checks** every number, date and code in the text is among the facts
  (`figure_check`); otherwise, or with no model, the brief goes out as it
  always did. The counts follow the text in every case, so what a person
  acts on is never only the model's.
- **As the person it is for**: the call runs as the recipient (their access
  now, through the platform's membership lookup), so their plan's allowance
  counts it; a person whose membership is gone gets the plain brief.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from pydantic import BaseModel, ConfigDict, Field

from dw_agent_runtime.model.figure_check import unsupported
from dw_kernel.errors import QuotaExceededError
from dw_kernel.ports import IdGenerator
from dw_platform.application.identity import context_from
from dw_sales.application.access import SalesScopes, sales_scope
from dw_sales.application.model_reading import InterpretationPort, ModelUnavailableError, PromptRef
from dw_sales.application.ports import SalesScope
from dw_sales.application.runs import caller_run
from dw_sales.domain.process import DW_NAMES

if TYPE_CHECKING:
    # Not at run time: `model_readiness` imports this module for its bar,
    # and `processing` reaches `model_readiness` through the inbox.
    from dw_sales.application.processing import RequesterAccessPort

# The prompt the brief is written with. Its file is
# `configs/prompts/sales/morning_brief@1.0.0.yaml`; a test holds the two
# together, and the rendered prompt under `PROMPT_TOKENS`.
MORNING_BRIEF: Final = PromptRef("sales.morning_brief", "1.0.0")
PROMPT_TOKENS: Final = 800
_OUTPUT_TOKENS: Final = 500
# The call runs as the recipient, cut to reading cases: nothing it does
# needs more.
BRIEF_CEILING: Final = frozenset({SalesScopes.CASE_READ.value})
_LANE_CHANNEL: Final = "sales_followups"

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class ModelBrief(BaseModel):
    """What the model writes: a few sentences."""

    model_config = _FROZEN

    text: str = Field(min_length=1, max_length=700)


@dataclass(frozen=True)
class BriefWriter:
    """Implements `BriefWriterPort` (`dw_sales.application.followups`)."""

    model: InterpretationPort
    access: RequesterAccessPort
    ids: IdGenerator
    worker_id: str
    worker_version: str

    async def write(
        self, scope: SalesScope, person: uuid.UUID, facts: Mapping[str, Any]
    ) -> str | None:
        """The model's sentences for ``person``, or None: the person gone, no
        usable answer, or a figure the facts do not hold."""
        access = await self.access.find_linked_access(
            person, scope.tenant_id.value, scope.workspace_id.value, BRIEF_CEILING
        )
        if access is None:
            return None
        context = context_from(access)
        if sales_scope(context) != scope:
            return None
        text = json.dumps(facts, ensure_ascii=False, indent=1)
        try:
            answer = await self.model.interpret(
                MORNING_BRIEF,
                {"facts": text},
                ModelBrief,
                run=caller_run(
                    context,
                    run_id=self.ids.new_uuid(),
                    worker_id=self.worker_id,
                    worker_version=self.worker_version,
                    trace="sales-brief",
                    subject_ref=f"sales_workspace:{scope.workspace_id.value}",
                    channel=_LANE_CHANNEL,
                ),
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except (ModelUnavailableError, QuotaExceededError):
            return None
        if unsupported(answer.text, text, names=DW_NAMES):
            return None
        return answer.text.strip()
