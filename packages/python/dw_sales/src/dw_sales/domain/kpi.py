"""`sales_kpi`: the targets and the manual baseline the overview reports against.

`configs/policies/sales_kpi@<version>.yaml`, versioned like every Sales rule.
The committed values are fictional; the customer's own figures arrive as a
tenant version of the policy, never as an edit to the file (spec decision 14).

Every key is read by the overview (ticket 05), and nothing else is here: a
target nobody reports against reads like a commitment and is decoration
(failure-modes #1). The results are reported without a pass/fail verdict
(spec "Interim behaviour", acceptance criteria): a target is shown beside what
was measured.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dw_sales.domain.process import WIV_STEPS

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class SalesKpi(BaseModel):
    """What the overview measures against.

    ``order_confirmation_target_hours``: from the PO's arrival to the order
    confirmed. ``quotation_target_days``: from the request's arrival to the
    quotation sent (1, Đạt 2026-10-05). ``manual_baseline_minutes``: what one
    pass of each surveyed step (O1 … Q12) takes by hand today, the column the
    per-step export carries beside its counts. Every surveyed step is listed:
    a step without a baseline would export as if it took no time.
    """

    model_config = _FROZEN

    schema_version: str = Field(pattern=r"^1\.0$")
    policy_id: Literal["sales_kpi"]
    policy_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    order_confirmation_target_hours: int = Field(gt=0, le=24 * 30)
    quotation_target_days: int = Field(gt=0, le=90)
    manual_baseline_minutes: Mapping[str, int]

    @model_validator(mode="after")
    def _every_surveyed_step_has_a_baseline(self) -> Self:
        steps = {step.step_id for step in WIV_STEPS}
        if missing := sorted(steps - self.manual_baseline_minutes.keys()):
            raise ValueError(f"no manual baseline for {missing}")
        if unknown := sorted(self.manual_baseline_minutes.keys() - steps):
            raise ValueError(f"baselines for steps the survey does not have: {unknown}")
        if any(minutes < 0 for minutes in self.manual_baseline_minutes.values()):
            raise ValueError("a manual baseline is a number of minutes, not below zero")
        return self

    @property
    def version(self) -> str:
        return f"{self.policy_id}@{self.policy_version}"
