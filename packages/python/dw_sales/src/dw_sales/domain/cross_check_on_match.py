"""The cross-check passed on a matching read-back (dw_sales ticket 81, ADR
0016, Proposed; off unless the tenant's rules say `cross_check_on_match`).

WIV-03-012 step 9 has a second person check the Bravo entry against the case
as approved. When DW reads the sales order back from Bravo through the
gateway and it holds exactly the paste sheet's rows, that check repeats what
the comparison already showed, for an order where nothing else needed a
person's judgement. Such an order may pass its cross-check on the read-back,
by DW, within ADR 0015's measured error and audit sample; everything else
stays the second person's.

This module names what the verdict reads and why it refuses
(`OnMatchException`); the verdict itself is the case's
(`OrderCase.on_match_exceptions`), which the transition re-asks
(`OrderCase.cross_checked_on_match`), so nothing reaches `cross_checked` by
DW without it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal, NamedTuple

# What a measured outcome is counted under: a new comparison (what `compare`
# reads, what the verdict refuses) starts from no cases, as a new prompt
# version does under ADR 0015.
ON_MATCH_BASIS: Final = "cross_check_on_match@1.0.0"

# Where a read-back came from: an export a person uploaded, or the gateway.
ReadBackSource = Literal["export", "gateway"]


class ReadBackFacts(NamedTuple):
    """What the verdict reads of a read-back: where it came from, the case
    version it was compared against, how many differences it found, and the
    sales-order number Bravo holds the PO under."""

    source: ReadBackSource
    case_version: int
    differences: int
    so_no: str


class OnMatchException(StrEnum):
    """Why an order's cross-check stays a person's. Shown to the
    cross-checker, so they know what to look at; never "sample"."""

    # The rules stamped on the case do not say so (None reads as off).
    RULES_OFF = "rules_off"
    # The order is not waiting on its cross-check, or a decision on it was
    # recorded and not applied.
    NOT_AWAITING = "not_awaiting"
    # Read from an export a person uploaded: only Bravo itself may vouch.
    NOT_FROM_BRAVO = "not_from_bravo"
    # Compared against another version of the case.
    STALE_READ_BACK = "stale_read_back"
    # Bravo holds something else than the paste sheet.
    DIFFERS = "differs"
    # Bravo holds the PO under another SO number than the one the PIC
    # recorded: the recorded one is what the confirmation prints.
    SO_NO_DIFFERS = "so_no_differs"
    # A check raised something, whatever was decided about it.
    FINDING = "finding"
    # A person typed a value, a PRV code, PC's dates, or took a change.
    TYPED_BY_A_PERSON = "typed_by_a_person"
    # A value or a code DW applied by itself (ADR 0015), or a file opened
    # with a password (ticket 80): no person looked at it either.
    APPLIED_BY_DW = "applied_by_dw"
    # A revised PO, or a customer's change in the update loop.
    REVISED = "revised"


# The order the cross-checker reads them in.
EXCEPTION_ORDER: Final = tuple(OnMatchException)
