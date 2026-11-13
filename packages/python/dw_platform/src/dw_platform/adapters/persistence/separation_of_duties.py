"""The database's separation-of-duties refusal, read back as a domain error.

The rule has one owner: `platform.enforce_separation_of_duties`, the trigger
on `platform.memberships` (migration `b9862fa13a80`). It raises SQLSTATE
23514 with the broken rule's key, always `sod_…`, as the constraint name.
This module only recognizes that refusal and turns it into a 409 naming the
rule. It never re-derives which scopes conflict, so nothing here can drift
from the catalogue.
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from dw_kernel.errors import ConflictError
from dw_platform.adapters.persistence.integrity import constraint_of

_RULE_PREFIX = "sod_"


def refusal(error: IntegrityError) -> tuple[str, str] | None:
    """The constraint a refusal names and its detail, or None when the driver
    reported no constraint."""
    constraint = constraint_of(error)
    if constraint is None:
        return None
    # asyncpg's own exception carries the trigger's DETAIL too, as the cause
    # SQLAlchemy wraps.
    return constraint, getattr(getattr(error.orig, "__cause__", None), "detail", None) or ""


def separation_of_duties_conflict(error: IntegrityError) -> ConflictError | None:
    """The conflict `error` stands for, or None when it is some other
    integrity failure the caller must handle (or re-raise) itself."""
    refused = refusal(error)
    if refused is None or not refused[0].startswith(_RULE_PREFIX):
        return None
    rule, reason = refused
    return ConflictError(
        "these roles cannot be held together (separation of duties)",
        details={"rule": rule, "reason": reason},
    )
