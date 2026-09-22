"""`_quoted`'s identifier guard: the last line before a catalog-discovered
table name is string-formatted straight into a DELETE/SELECT statement.

A real schema/table from Postgres's own catalog always matches
`^[a-z_][a-z0-9_]*$` — this proves the converse: anything that does not match
is refused rather than interpolated, so a catalog result that somehow carried
something else could not turn into a second statement.
"""

from __future__ import annotations

import pytest

from dw_platform.adapters.persistence.offboarding import _quoted

pytestmark = pytest.mark.unit


def test_a_real_looking_identifier_is_quoted() -> None:
    assert _quoted("platform", "tenant_offboarding_requests") == (
        '"platform"."tenant_offboarding_requests"'
    )


@pytest.mark.parametrize(
    "schema,table",
    [
        ("public", "users; DROP TABLE platform.tenants; --"),
        ('public"; DROP TABLE x; --', "users"),
        ("public", "users WHERE 1=1"),
        ("public", "users--"),
        ("public", "users'"),
        ("public", ""),
    ],
)
def test_an_unsafe_identifier_is_refused_not_interpolated(schema: str, table: str) -> None:
    with pytest.raises(ValueError, match="unsafe catalog identifier"):
        _quoted(schema, table)
