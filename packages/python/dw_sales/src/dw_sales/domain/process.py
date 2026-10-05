"""The surveyed process steps, and where DW1 meets each one.

`WIV_STEPS` is the one owner of the mapping the spec's "Process map" table
describes: for each step of WIV-03-012 (order entry, ``O1``-``O11``) and
WIV-03-023 (quotation, ``Q1``-``Q12``), the case states and artifacts it
produces and whether this slice covers it. The overview (ticket 05) and its
page (08) read it; the per-step export of time spent is keyed by these ids.

State names are CONTEXT.md's. An order step's states are checked against
`OrderStatus` by a test; a quote step's belong to `QuoteCase`, whose
transitions ticket 03 owns.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class Procedure(StrEnum):
    ORDER_ENTRY = "WIV-03-012"
    QUOTATION = "WIV-03-023"


class Coverage(StrEnum):
    """How far this slice takes the step."""

    YES = "yes"
    # DW1 proposes; a person decides outside the portal (O4's date).
    SUGGESTION = "suggestion"
    # Built on mock data until the company grants access (Q4, Q11, Q12).
    MOCK = "mock"
    # Another worker's (DW2) or outside this slice.
    OUT = "out"


class ProcessStep(BaseModel):
    model_config = _FROZEN

    step_id: str = Field(pattern=r"^[OQ]\d{1,2}$")
    procedure: Procedure
    number: int = Field(ge=1)
    coverage: Coverage
    states: tuple[str, ...] = ()
    artifacts: tuple[str, ...] = ()


_PREFIX: Final = {Procedure.ORDER_ENTRY: "O", Procedure.QUOTATION: "Q"}


def _step(
    procedure: Procedure,
    number: int,
    coverage: Coverage,
    states: tuple[str, ...],
    artifacts: tuple[str, ...] = (),
) -> ProcessStep:
    return ProcessStep(
        step_id=f"{_PREFIX[procedure]}{number}",
        procedure=procedure,
        number=number,
        coverage=coverage,
        states=states,
        artifacts=artifacts,
    )


def _o(number: int, coverage: Coverage, *rest: tuple[str, ...]) -> ProcessStep:
    return _step(Procedure.ORDER_ENTRY, number, coverage, *rest)


def _q(number: int, coverage: Coverage, *rest: tuple[str, ...]) -> ProcessStep:
    return _step(Procedure.QUOTATION, number, coverage, *rest)


_YES, _SUGGESTION, _MOCK, _OUT = Coverage.YES, Coverage.SUGGESTION, Coverage.MOCK, Coverage.OUT

WIV_STEPS: Final[tuple[ProcessStep, ...]] = (
    _o(1, _YES, ("received",), ("message_disposition",)),
    _o(2, _YES, ("checked",), ("convert_list_proposal",)),
    _o(3, _YES, ("uploaded_to_bravo",), ("bravo_upload_file",)),
    _o(4, _SUGGESTION, (), ("suggested_delivery_date", "confirmed_delivery_date")),
    _o(5, _OUT, ()),
    _o(6, _YES, ("in_review",), ("findings",)),
    _o(7, _YES, ("prepared", "uploaded_to_bravo"), ("coverage_statement",)),
    _o(8, _YES, ("correction_requested",), ("correction_draft",)),
    _o(9, _YES, ("cross_checked",), ("cross_check_sheet",)),
    _o(10, _YES, ("confirmed",), ("confirmation_draft",)),
    _o(11, _OUT, ()),
    _q(1, _YES, ("received",)),
    _q(2, _YES, ("ycbg_drafted", "ycbg_recorded"), ("ycbg_draft",)),
    _q(3, _YES, ("sent_to_design",), ("design_request_draft",)),
    _q(4, _MOCK, ("design_replied",), ("ycbg_waiting_list",)),
    _q(5, _YES, ("declined",), ("decline_draft",)),
    _q(6, _YES, ("spec_discussion",), ("spec_discussion_draft",)),
    _q(7, _YES, ("priced",), ("price_evidence",)),
    _q(8, _YES, (), ("quotation_document",)),
    _q(9, _YES, ("pending_approval", "approved", "returned"), ("approval_pack",)),
    _q(10, _YES, ("sent",), ("send_draft",)),
    _q(11, _MOCK, ("master_list_recorded",), ("master_list_row",)),
    _q(12, _MOCK, (), ("screening_report",)),
)


def step(step_id: str) -> ProcessStep:
    """The step with this id; a KeyError for one the survey does not have."""
    for candidate in WIV_STEPS:
        if candidate.step_id == step_id:
            return candidate
    raise KeyError(step_id)
