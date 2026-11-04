"""How far DW2 goes on its own, step by step (Đạt, 2026-11-01).

Every step of DW2 has one switch with three levels, the tenant's to set
(`purchasing_automation@<version>`, a rule like any other: proposed, decided
by a second person, the head's own applied at once):

- **AI tự làm** (`ai_auto`): DW2 does the step and records it; a person is
  told only when it could not.
- **AI làm, người duyệt** (`ai_review`): DW2 prepares the step and a person
  finishes it with one press.
- **Người làm** (`person`): DW2 does not touch the step.

What a tenant may set is held by what the product promises, in code, never in
a rule (`STEPS`):

- a **ceiling** per step: money, approvals, mail leaving the company and
  Bravo always have a person (CLAUDE.md, ADR 0005/0006/0007 of dw_sales as
  DW2 applies them), so those steps stop at `ai_review` whatever is set;
- the **model steps** a step runs on: `ai_auto` takes effect only while every
  one of them has a live measurement at its bar on the plant's model
  (`dw_agent_runtime.model.readiness`); until then the step runs at
  `ai_review`, and the settings page says why in words.

A step with no model step (sending a checked request to its approver,
drafting the orders) is code's alone, so `ai_auto` needs no measurement.

A version written before a step existed does not name it: the step reads as
`person` there, what DW2 did before it had the step, never more than the
tenant chose. The platform's own file names every step.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

POLICY_ID: Final = "purchasing_automation"


class AutomationLevel(StrEnum):
    AI_AUTO = "ai_auto"
    AI_REVIEW = "ai_review"
    PERSON = "person"


# How far each level goes, for "at most".
_RANK: Final = {AutomationLevel.PERSON: 0, AutomationLevel.AI_REVIEW: 1, AutomationLevel.AI_AUTO: 2}


def at_most(level: AutomationLevel, ceiling: AutomationLevel) -> AutomationLevel:
    return level if _RANK[level] <= _RANK[ceiling] else ceiling


class AutomationStep(StrEnum):
    """The steps of DW2 that have a switch: each one code reads where the
    step happens. The other steps of the twelve (CONTEXT.md, "Automation")
    get theirs the day they are built, never before (failure-modes #1)."""

    # A new mail in the purchasing mailbox sorted by who sent it: a request
    # from the company, or for a person to read.
    MAIL_SORTING = "mail_sorting"
    # A request's case opened from a mail the model read.
    PR_DRAFTING = "pr_drafting"
    # A checked request sent to the approver its amount names.
    SUBMISSION = "submission"
    # The RFQs of an approved request drafted (sending is a buyer's).
    RFQ = "rfq"
    # The orders of a request whose suppliers are chosen drafted, with the
    # Bravo file (importing it is a buyer's).
    PO_DRAFTING = "po_drafting"
    # A supplier's reply to an RFQ read into the offers it holds (choosing
    # among them is a buyer's).
    QUOTE_READING = "quote_reading"
    # A supplier's confirmation of an order read and held to the order; one
    # that differs in nothing accepted (one that differs is a buyer's).
    CONFIRMATION_READING = "confirmation_reading"


class PurchasingModelStep(StrEnum):
    """The model calls a step's `ai_auto` waits on, each measured on its own
    (`dw_purchasing.application.automation.BARS`)."""

    PR_MAIL_READING = "purchasing_pr_mail_reading"
    SUPPLIER_QUOTE_READING = "purchasing_supplier_quote_reading"
    ORDER_CONFIRMATION_READING = "purchasing_order_confirmation_reading"


@dataclass(frozen=True, slots=True)
class StepSpec:
    # The furthest a tenant may set the step.
    ceiling: AutomationLevel
    # What `ai_auto` waits on; empty: the step is code's alone.
    model_steps: tuple[PurchasingModelStep, ...]


STEPS: Final[Mapping[AutomationStep, StepSpec]] = MappingProxyType(
    {
        # Code sorts by sender (a company domain, verified by the mail system).
        AutomationStep.MAIL_SORTING: StepSpec(AutomationLevel.AI_AUTO, ()),
        # The model reads, code keeps what it finds; unasked only once the
        # reading is measured on the plant's model.
        AutomationStep.PR_DRAFTING: StepSpec(
            AutomationLevel.AI_AUTO, (PurchasingModelStep.PR_MAIL_READING,)
        ),
        # The approver decides, so sending unasked decides nothing.
        AutomationStep.SUBMISSION: StepSpec(AutomationLevel.AI_AUTO, ()),
        # Mail to a supplier leaves the company: a buyer sends it.
        AutomationStep.RFQ: StepSpec(AutomationLevel.AI_REVIEW, ()),
        # Drafts only: Bravo records nothing until a buyer imports the file.
        AutomationStep.PO_DRAFTING: StepSpec(AutomationLevel.AI_AUTO, ()),
        # Offers recorded from the supplier's own words, each figure in the
        # mail; the comparison is code's and the choice a buyer's.
        AutomationStep.QUOTE_READING: StepSpec(
            AutomationLevel.AI_AUTO, (PurchasingModelStep.SUPPLIER_QUOTE_READING,)
        ),
        # Accepted unasked only when it differs from the order in nothing.
        AutomationStep.CONFIRMATION_READING: StepSpec(
            AutomationLevel.AI_AUTO, (PurchasingModelStep.ORDER_CONFIRMATION_READING,)
        ),
    }
)

_Version = Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]


class PurchasingAutomation(BaseModel):
    """One version of the tenant's switches: a level for every step, none
    above its ceiling."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        hide_input_in_errors=True,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
    )

    policy_id: Literal["purchasing_automation"] = POLICY_ID
    version: _Version = Field(alias="policy_version")
    steps: Mapping[AutomationStep, AutomationLevel]

    @model_validator(mode="before")
    @classmethod
    def _unnamed_steps_to_a_person(cls, data: object) -> object:
        if isinstance(data, Mapping) and isinstance(data.get("steps"), Mapping):
            named = {str(step) for step in data["steps"]}
            unnamed = {
                s.value: AutomationLevel.PERSON.value
                for s in AutomationStep
                if s.value not in named
            }
            return {**data, "steps": {**unnamed, **data["steps"]}}
        return data

    @model_validator(mode="after")
    def _every_step_within_its_ceiling(self) -> Self:
        above = [s for s, level in self.steps.items() if at_most(level, STEPS[s].ceiling) != level]
        if above:
            raise ValueError(f"above what the product allows: {sorted(above)}")
        return self

    @property
    def ref(self) -> str:
        return f"{POLICY_ID}@{self.version}"


Why = Literal["set", "not_measured", "unreadable"]


@dataclass(frozen=True, slots=True)
class Effective:
    """A step's level as it runs now, and why it is not the one set."""

    step: AutomationStep
    chosen: AutomationLevel
    level: AutomationLevel
    why: Why
    # The model steps that kept `ai_auto` from taking effect.
    waiting_on: tuple[PurchasingModelStep, ...] = ()
