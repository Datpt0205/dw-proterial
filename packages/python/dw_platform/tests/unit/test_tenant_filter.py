"""tenant_filter is a one-line wrapper; the test is that it wraps the right
line — the explicit tenant predicate every repository in this package already
writes by hand, not something new."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from dw_platform.adapters.persistence.tenant_filter import tenant_filter

pytestmark = pytest.mark.unit

_metadata = sa.MetaData()
_workspaces = sa.Table(
    "workspaces",
    _metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("tenant_id", sa.Uuid, nullable=False),
)


def test_matches_the_given_tenant_id() -> None:
    tenant_id = uuid.uuid4()
    query = sa.select(_workspaces).where(tenant_filter(_workspaces.c.tenant_id, tenant_id))
    compiled = query.compile(compile_kwargs={"literal_binds": True})
    assert "workspaces.tenant_id = " in str(compiled)
    assert tenant_id.hex in str(compiled)


def test_a_different_tenant_id_produces_a_different_predicate() -> None:
    """Not a tautology: confirms the value is actually threaded through, not a
    stray `True`/`1=1` a typo could produce."""
    first, second = uuid.uuid4(), uuid.uuid4()
    assert str(tenant_filter(_workspaces.c.tenant_id, first)) == str(
        tenant_filter(_workspaces.c.tenant_id, second)
    )
    compiled_first = tenant_filter(_workspaces.c.tenant_id, first).compile(
        compile_kwargs={"literal_binds": True}
    )
    compiled_second = tenant_filter(_workspaces.c.tenant_id, second).compile(
        compile_kwargs={"literal_binds": True}
    )
    assert str(compiled_first) != str(compiled_second)
