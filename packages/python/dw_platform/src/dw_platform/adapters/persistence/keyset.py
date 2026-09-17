"""The SQL half of keyset pagination: one predicate, one ordering.

`dw_kernel.pagination` owns the cursor; this owns the two SQL clauses that have
to agree with it. They live together because getting them apart is how the bug
happens: a ``<`` written as ``<=`` repeats the boundary row on every page, an
ORDER BY that lists the tiebreaker in the other direction skips tied rows, and
neither mistake shows up until two rows share a timestamp in production.

SQL expression helpers, not an adapter — nothing here holds a session or a
connection, so a gateway in another package may import it without acquiring a
concrete dependency.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.sql import ColumnElement

from dw_kernel.pagination import CursorPosition


def after_position(
    sort_column: sa.ColumnElement[object],
    id_column: sa.ColumnElement[object],
    after: CursorPosition | None,
) -> ColumnElement[bool]:
    """Rows strictly past ``after`` in descending ``(sort_column, id_column)``.

    A row-value comparison rather than the ``sort < k OR (sort = k AND id < i)``
    it expands to, because PostgreSQL can drive an index scan from the row-value
    form and because the expanded form is where the tie handling gets written
    wrong. ``after`` of ``None`` is the first page and matches everything.
    """
    if after is None:
        return sa.true()
    return sa.tuple_(sort_column, id_column) < sa.tuple_(
        sa.literal(after.sort_value, sort_column.type),
        sa.literal(after.tiebreaker, id_column.type),
    )


def newest_first(
    sort_column: sa.ColumnElement[object],
    id_column: sa.ColumnElement[object],
) -> tuple[ColumnElement[object], ColumnElement[object]]:
    """The ORDER BY that :func:`after_position` assumes.

    Returned as a pair so a query cannot order by the sort column and forget the
    tiebreaker, which would make the position of a tied row depend on whatever
    order the planner happened to return it in — and therefore make a page
    boundary that lands inside a tie non-deterministic.
    """
    return (sort_column.desc(), id_column.desc())
