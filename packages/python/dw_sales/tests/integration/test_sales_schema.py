"""The `sales` schema as the catalog reports it, against CLAUDE.md's data rules
and against the domain whose value sets it repeats.

A CHECK on a fixed set is a second copy of the domain's enum. These tests are
what make the two disagree loudly: a state added to `OrderStatus` and not to
the migration fails here, not as a refused write in a demo.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from enum import StrEnum
from typing import get_args

import pytest
import sqlalchemy as sa
from pg_test_db import DatabaseUrls
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from dw_sales.application.case_store import JobError, JobStatus
from dw_sales.application.catalog_imports import ImportSource, ImportStatus
from dw_sales.application.followups import BRIEF, BRIEF_STAGE
from dw_sales.application.rules import RuleKey
from dw_sales.domain import dispositions, followups, orders, quotes
from dw_sales.domain.master_data import CatalogList

pytestmark = pytest.mark.integration


@pytest.fixture
async def catalog(sales_db: DatabaseUrls) -> AsyncIterator[AsyncConnection]:
    engine = create_async_engine(sales_db.migrator, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            yield conn
    finally:
        await engine.dispose()


async def _constraint(conn: AsyncConnection, name: str) -> str:
    definition = await conn.scalar(
        sa.text(
            "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c"
            " JOIN pg_namespace n ON n.oid = c.connamespace"
            " WHERE n.nspname = 'sales' AND c.conname = :name"
        ),
        {"name": name},
    )
    assert definition is not None, f"no constraint {name}"
    return str(definition)


def _values(enum: type[StrEnum]) -> set[str]:
    return {member.value for member in enum}


_SETS: dict[str, set[str]] = {
    "ck_order_cases_status": _values(orders.OrderStatus),
    "ck_order_cases_close_reason": _values(orders.CloseReason),
    "ck_order_cases_export_control_mode": set(get_args(orders.ExportControlMode)),
    "ck_order_lines_mapping_status": _values(orders.MappingStatus),
    "ck_order_findings_code": _values(orders.FindingCode),
    "ck_order_findings_severity": _values(orders.Severity),
    "ck_order_findings_disposition": _values(orders.DispositionKind),
    "ck_messages_disposition": _values(dispositions.DispositionKind),
    "ck_messages_routing_reason": _values(dispositions.RoutingReason),
    "ck_quote_cases_status": _values(quotes.QuoteStatus),
    # The keys a tenant may hold its own version of (tickets 19 and 36).
    "ck_rule_versions_key": _values(RuleKey),
    # A message's processing job and why it failed (ticket 25).
    "ck_processing_jobs_status": set(get_args(JobStatus)),
    "ck_processing_jobs_error_code": set(get_args(JobError)),
    # What the follow-ups record (ticket 42).
    "ck_followup_deliveries_followup": _values(followups.Followup) | {BRIEF},
    "ck_followup_deliveries_stage": _values(followups.Stage) | {BRIEF_STAGE},
    # A master-data import's list and status (ticket 41).
    "ck_catalog_snapshots_list": _values(CatalogList),
    "ck_catalog_snapshots_status": set(get_args(ImportStatus)),
    "ck_catalog_snapshots_source": set(get_args(ImportSource)),
}


@pytest.mark.parametrize("name", sorted(_SETS))
async def test_each_check_holds_exactly_the_domains_values(
    catalog: AsyncConnection, name: str
) -> None:
    definition = await _constraint(catalog, name)
    assert set(re.findall(r"'([a-z_]+)'::text", definition)) == _SETS[name]


async def test_an_event_status_is_one_of_its_case_kinds(catalog: AsyncConnection) -> None:
    definition = await _constraint(catalog, "ck_case_events_status")
    order_part, quote_part = definition.split("ELSE", 1)
    assert set(re.findall(r"'([a-z_]+)'::text", order_part)) - {"order"} == _values(
        orders.OrderStatus
    )
    assert set(re.findall(r"'([a-z_]+)'::text", quote_part)) == _values(quotes.QuoteStatus)


async def test_a_check_basis_holds_the_keys_of_line_basis(catalog: AsyncConnection) -> None:
    definition = await _constraint(catalog, "ck_order_lines_check_basis")
    (listed,) = re.findall(r"ARRAY\[([^\]]+)\]", definition)
    assert set(re.findall(r"'([a-z_]+)'", listed)) == set(orders.LineBasis.model_fields)


@pytest.mark.parametrize(
    "name", ["ck_order_lines_corrections", "ck_order_revisions_header_corrections"]
)
async def test_a_correction_holds_the_keys_of_its_domain_record(
    catalog: AsyncConnection, name: str
) -> None:
    """Ticket 15: the CHECK names every field `ValueCorrection` writes, and
    refuses any other key."""
    definition = await _constraint(catalog, name)
    fields = set(orders.ValueCorrection.model_fields)
    assert set(re.findall(r'@\."key" == "([a-z_]+)"', definition)) == fields  # no other key
    assert set(re.findall(r'exists \(@\."([a-z_]+)"\)', definition)) == fields  # each one


async def test_a_decision_not_applied_holds_the_keys_of_its_domain_record(
    catalog: AsyncConnection,
) -> None:
    """Ids, an outcome, a version and a reason code (ticket 14): the CHECK
    refuses any other key, so a comment or an amount has no field there."""
    definition = await _constraint(catalog, "ck_order_cases_unapplied_decision")
    (listed,) = re.findall(r"ARRAY\[([^\]]+)\]", definition)
    assert set(re.findall(r"'([a-z_]+)'", listed)) == set(orders.UnappliedDecision.model_fields)
    assert "'uploaded_to_bravo'" in definition


async def test_every_foreign_key_says_what_a_delete_does_and_is_indexed(
    catalog: AsyncConnection,
) -> None:
    rows = (
        await catalog.execute(
            sa.text(
                """
                SELECT c.conname, c.confdeltype::text AS confdeltype,
                       c.conrelid::regclass::text AS tbl, c.conkey,
                       EXISTS (
                           SELECT 1 FROM pg_index i
                           WHERE i.indrelid = c.conrelid
                             AND (i.indkey::int2[])[0:cardinality(c.conkey) - 1] = c.conkey
                       ) AS indexed
                FROM pg_constraint c
                JOIN pg_namespace n ON n.oid = c.connamespace
                JOIN pg_class r ON r.oid = c.conrelid
                WHERE n.nspname = 'sales' AND c.contype = 'f' AND NOT r.relispartition
                """
            )
        )
    ).all()
    assert len(rows) >= 20, "found too few foreign keys: the query is wrong, not the schema"
    # 'a' is NO ACTION, what Postgres gives a key that said nothing.
    assert [r.conname for r in rows if r.confdeltype == "a"] == []
    assert [f"{r.tbl}.{r.conname}" for r in rows if not r.indexed] == []


# Tables whose rows belong to the whole tenant, not to one workspace, with why:
# policed by tenant alone, unique keys led by `tenant_id` alone. Every other
# Sales table is narrowed by workspace as well.
_TENANT_WIDE = {
    # A tenant's own rule version applies in every workspace of the tenant,
    # whichever it was proposed in (ticket 19, migration 57a241ea182b).
    "rule_versions",
}


async def test_every_table_is_policed_by_tenant_and_workspace_under_its_own_name(
    catalog: AsyncConnection,
) -> None:
    tables = (
        await catalog.execute(
            sa.text(
                "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity FROM pg_class c"
                " JOIN pg_namespace n ON n.oid = c.relnamespace"
                " WHERE n.nspname = 'sales' AND c.relkind IN ('r', 'p')"
            )
        )
    ).all()
    policies = {
        (r.tablename, r.policyname): (r.qual, r.with_check)
        for r in await catalog.execute(
            sa.text(
                "SELECT tablename, policyname, qual, with_check FROM pg_policies"
                " WHERE schemaname = 'sales'"
            )
        )
    }
    assert len(tables) >= 11
    for table in tables:
        assert table.relrowsecurity and table.relforcerowsecurity, table.relname
        named = [key for key in policies if key[0] == table.relname]
        assert named == [(table.relname, f"tenant_isolation_{table.relname}")], table.relname
        for predicate in policies[named[0]]:
            assert predicate is not None
            assert "current_setting('app.tenant_id'" in predicate, table.relname
            narrowed = "current_setting('app.workspace_id'" in predicate
            assert narrowed is (table.relname not in _TENANT_WIDE), table.relname


async def test_every_unique_key_leads_with_tenant_and_workspace(catalog: AsyncConnection) -> None:
    rows = (
        await catalog.execute(
            sa.text(
                """
                SELECT ic.relname AS index, t.relname AS tbl,
                       (SELECT array_agg(a.attname ORDER BY k.ord)
                        FROM unnest(i.indkey::int2[]) WITH ORDINALITY AS k(attnum, ord)
                        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
                       ) AS columns
                FROM pg_index i
                JOIN pg_class ic ON ic.oid = i.indexrelid
                JOIN pg_class t ON t.oid = i.indrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE n.nspname = 'sales' AND i.indisunique AND NOT i.indisprimary
                  AND NOT t.relispartition
                """
            )
        )
    ).all()
    assert len(rows) >= 10
    assert [
        r.index
        for r in rows
        if list(r.columns[:2]) != ["tenant_id", "workspace_id"]
        and not (r.tbl in _TENANT_WIDE and r.columns[0] == "tenant_id")
    ] == []


async def test_times_are_timestamptz_and_updated_at_is_kept_by_the_yielding_trigger(
    catalog: AsyncConnection,
) -> None:
    naive = (
        await catalog.execute(
            sa.text(
                "SELECT table_name, column_name FROM information_schema.columns"
                " WHERE table_schema = 'sales' AND data_type = 'timestamp without time zone'"
            )
        )
    ).all()
    assert naive == []
    untriggered = (
        await catalog.execute(
            sa.text(
                """
                SELECT c.table_name FROM information_schema.columns c
                WHERE c.table_schema = 'sales' AND c.column_name = 'updated_at'
                  AND NOT EXISTS (
                      SELECT 1 FROM pg_trigger tg
                      JOIN pg_proc p ON p.oid = tg.tgfoid
                      WHERE tg.tgrelid = format('sales.%I', c.table_name)::regclass
                        AND p.proname = 'touch_updated_at'
                  )
                """
            )
        )
    ).all()
    assert untriggered == []


async def test_every_constraint_is_named_by_the_convention(catalog: AsyncConnection) -> None:
    rows = (
        await catalog.execute(
            sa.text(
                "SELECT c.conname, c.contype::text AS contype, t.relname FROM pg_constraint c"
                " JOIN pg_class t ON t.oid = c.conrelid"
                " JOIN pg_namespace n ON n.oid = c.connamespace"
                " WHERE n.nspname = 'sales' AND NOT t.relispartition"
            )
        )
    ).all()
    prefix = {"p": "pk_", "f": "fk_", "u": "uq_", "c": "ck_"}
    wrong = [r.conname for r in rows if not r.conname.startswith(f"{prefix[r.contype]}{r.relname}")]
    assert wrong == []
