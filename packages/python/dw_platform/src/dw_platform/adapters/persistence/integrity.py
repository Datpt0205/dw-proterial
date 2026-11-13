"""Which constraint the database named when it refused a write.

One function, read by every repository that turns a refusal into a conflict:
the name comes from the driver's typed field, never from searching the error's
text, where a constraint whose name contains another's (or a detail that quotes
one) would match the wrong rule.
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError


def constraint_of(error: IntegrityError) -> str | None:
    """The constraint (or unique index) the database named, or None when the
    driver gave none."""
    # asyncpg's own exception carries it; SQLAlchemy wraps it as the cause of
    # the DBAPI error it raises.
    cause = getattr(error.orig, "__cause__", None)
    name = getattr(cause, "constraint_name", None)
    return name if isinstance(name, str) else None
