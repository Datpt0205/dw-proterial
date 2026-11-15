"""Where labelled cases are written and read (ticket 43; the cases are
`dw_sales.domain.labelled_cases.LabelledCase`).

- `LabelledCaseLogPort`: a member of every `SalesUnitOfWork`, so a case is
  written in the transaction of the person's decision it records, by the
  step's own service, and commits or rolls back with it. One writer per
  step: `OrderCommands.confirm_mapping` (`description_attributes`),
  `OrderCommands.correct_value` (`po_body_extraction`),
  `QuoteCommands.answer_finding` (`rfq_extraction`), `ChangeRequests.confirm`
  and `.reject` (`change_request`), `LayoutService.propose`
  (`layout_proposal`).
- `LabelledCaseReadPort`: one workspace's cases, read under its RLS: a
  step's newest first (and one customer's), and the counts per step that
  shadow mode and the thresholds of ticket 44 start from.
- `label_summary`: the head's view of those counts, per step: how many, and
  the share a person kept as the model proposed (the observed accuracy on
  real work). Counts only, never a value: a value may be a price.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Protocol

from pydantic import BaseModel, ConfigDict

from dw_sales.application.ports import SalesScope
from dw_sales.domain.labelled_cases import LabelledCase, Verdict
from dw_sales.domain.order_checks import ModelStep

_FROZEN = ConfigDict(frozen=True, extra="forbid")

# The most cases one read returns: what a step's examples or a replay page
# reads at once.
MAX_READ: Final = 500


class LabelledCaseLogPort(Protocol):
    """Where a decision's labelled cases are written, in its unit of work."""

    async def append(self, cases: Sequence[LabelledCase]) -> None: ...


@dataclass(frozen=True, slots=True)
class StepLabels:
    """How many cases a person decided on one step's proposals, by verdict."""

    confirmed: int = 0
    corrected: int = 0
    rejected: int = 0

    @property
    def total(self) -> int:
        return self.confirmed + self.corrected + self.rejected

    def counted(self, verdict: Verdict, count: int = 1) -> StepLabels:
        return StepLabels(
            confirmed=self.confirmed + (count if verdict == "confirmed" else 0),
            corrected=self.corrected + (count if verdict == "corrected" else 0),
            rejected=self.rejected + (count if verdict == "rejected" else 0),
        )


class LabelledCaseReadPort(Protocol):
    """The labelled cases of one workspace, read under its RLS."""

    async def latest(
        self,
        scope: SalesScope,
        step: ModelStep,
        *,
        customer_code: str | None = None,
        limit: int = MAX_READ,
    ) -> Sequence[LabelledCase]:
        """``step``'s cases, newest first, at most ``limit`` (and at most
        `MAX_READ`); one customer's when ``customer_code`` is given."""
        ...

    async def counts(self, scope: SalesScope) -> Mapping[ModelStep, StepLabels]:
        """Each step's cases by verdict; a step with none is left out."""
        ...


class StepLabelView(BaseModel):
    """One step's line on the head's view."""

    model_config = _FROZEN

    step: ModelStep
    total: int
    confirmed: int
    corrected: int
    rejected: int
    # The share a person kept as proposed; None with no case yet.
    confirmed_share: float | None


class LabelSummaryView(BaseModel):
    """Per step, the cases people decided on its proposals (ticket 43)."""

    model_config = _FROZEN

    steps: tuple[StepLabelView, ...]


def label_summary(counts: Mapping[ModelStep, StepLabels]) -> LabelSummaryView:
    """Every model step in its declared order, one with no case at zero."""
    steps = []
    for step in ModelStep:
        labels = counts.get(step, StepLabels())
        total = labels.total
        steps.append(
            StepLabelView(
                step=step,
                total=total,
                confirmed=labels.confirmed,
                corrected=labels.corrected,
                rejected=labels.rejected,
                confirmed_share=labels.confirmed / total if total else None,
            )
        )
    return LabelSummaryView(steps=tuple(steps))
