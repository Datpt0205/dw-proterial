"""The explicit half of tenant scoping — one line, one owner.

RLS (`tenant_session.bind_tenant`) already bounds every tenant-scoped query to
the caller's tenant at the database level. Every repository in this package
also names `tenant_id` explicitly in its own WHERE clause on top of that — a
belt beside the RLS brace, so a row from another tenant is refused even if a
policy were ever loosened (`admin_console_repo.py`'s own module docstring
states this convention). Until now that line was hand-typed at each of its
~22 call sites, with no single place naming the convention — this makes it one
call, greppable in a review the same way `keyset.py` makes pagination one call.

SQL expression helper, not an adapter — nothing here holds a session or a
connection, so a gateway in another package may import it without acquiring a
concrete dependency, the same shape as `keyset.py`. Unlike keyset's predicate,
this does not protect against a subtle bug — `col == value` has no wrong-
direction version — its value is a single greppable name for an invariant a
review has to check on every tenant-scoped query.
"""

from __future__ import annotations

import uuid

from sqlalchemy.sql import ColumnElement


def tenant_filter(
    tenant_id_column: ColumnElement[uuid.UUID], tenant_id: uuid.UUID
) -> ColumnElement[bool]:
    """The explicit tenant predicate, beside RLS rather than instead of it."""
    return tenant_id_column == tenant_id
