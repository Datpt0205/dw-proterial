"""sales actor ids are principal uuids

Revision ID: 075dca5a6168
Revises: 68305ebe4a83
Create Date: 2026-10-05 04:15:52.320401+00:00

One actor id type across the Sales context (ticket 05). A quote's pricer and
approver were already `uuid` (`quote_cases.priced_by`, `approved_by`); an
order's preparer, Bravo recorder and cross-checker were `text` holding a
principal subject. The two sides of a maker/checker comparison must be the
same kind of id, and the one the platform's verified `AccessContext` carries
is `principal_id`, a uuid. So every column naming a person becomes `uuid`:

- `order_cases`: `prepared_by`, `bravo_recorded_by`, `cross_checked_by`,
  `returned_by`, `confirmed_by`, `closed_by`, `assigned_to`, and `makers`
  (`uuid[]`), with the `accumulate_order_makers` trigger function retyped;
- `order_lines.mapping_confirmed_by`, `order_lines.pc_confirmed_by`;
- `order_findings.disposition_by`;
- `quote_cases.assigned_to`;
- `artifacts.created_by`, `source_served.principal_id`,
  `worker_state.changed_by`;
- `case_events.initiated_by` (the person whose request started DW1's
  action).

`case_events.actor_id` stays `text`: it names a person (their uuid) or DW1's
own service id, and `actor_kind` says which.

The `~ '^[!-~]{1,254}$'` checks on these columns are dropped rather than
kept: the type is the check now. Constraints that held such a test beside
other conditions are re-created with the other conditions only.

No sales row exists outside a test database yet (no route wrote one before
this revision), so the casts cannot meet a subject that is not a uuid. If one
did, the upgrade fails on it rather than inventing an id.
"""

from __future__ import annotations

from alembic import op

revision = "075dca5a6168"
down_revision = "68305ebe4a83"
branch_labels = None
depends_on = None

_ACTOR = r"'^[!-~]{1,254}$'"

_ORDER_ACTORS = (
    "prepared_by",
    "bravo_recorded_by",
    "cross_checked_by",
    "returned_by",
    "confirmed_by",
    "closed_by",
    "assigned_to",
)

_MAKERS_FUNCTION = """
CREATE OR REPLACE FUNCTION sales.accumulate_order_makers() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
    NEW.makers := ARRAY(
        SELECT DISTINCT maker
        FROM unnest(
            CASE WHEN TG_OP = 'UPDATE' THEN OLD.makers ELSE '{}'::{array} END
            || ARRAY[NEW.prepared_by, NEW.bravo_recorded_by]
        ) AS maker
        WHERE maker IS NOT NULL
        ORDER BY maker
    );
    RETURN NEW;
END;
$fn$
"""

_CHECKER_NOT_MAKER = """
ALTER TABLE sales.order_cases ADD CONSTRAINT ck_order_cases_checker_not_maker CHECK (
    cross_checked_by IS NULL
    OR (cross_checked_by IS DISTINCT FROM prepared_by
        AND cross_checked_by IS DISTINCT FROM bravo_recorded_by
        AND cross_checked_by <> ALL (makers))
)
"""


def _retype(table: str, columns: tuple[str, ...], to: str) -> None:
    """Every column in one statement, so a CHECK comparing two of them never
    sees one converted and the other not."""
    clauses = ", ".join(f"ALTER COLUMN {c} TYPE {to} USING {c}::{to}" for c in columns)
    op.execute(f"ALTER TABLE sales.{table} {clauses}")


def upgrade() -> None:
    # ---- order_cases ------------------------------------------------------
    op.execute("ALTER TABLE sales.order_cases DROP CONSTRAINT ck_order_cases_actors")
    op.execute("ALTER TABLE sales.order_cases DROP CONSTRAINT ck_order_cases_checker_not_maker")
    op.execute("ALTER TABLE sales.order_cases ALTER COLUMN makers DROP DEFAULT")
    _retype("order_cases", _ORDER_ACTORS, "uuid")
    op.execute("ALTER TABLE sales.order_cases ALTER COLUMN makers TYPE uuid[] USING makers::uuid[]")
    op.execute("ALTER TABLE sales.order_cases ALTER COLUMN makers SET DEFAULT '{}'::uuid[]")
    op.execute(_MAKERS_FUNCTION.replace("{array}", "uuid[]"))
    op.execute(_CHECKER_NOT_MAKER)

    # ---- order_lines ------------------------------------------------------
    op.execute("ALTER TABLE sales.order_lines DROP CONSTRAINT ck_order_lines_mapping_confirmation")
    op.execute("ALTER TABLE sales.order_lines DROP CONSTRAINT ck_order_lines_pc_confirmation")
    _retype("order_lines", ("mapping_confirmed_by", "pc_confirmed_by"), "uuid")
    op.execute(
        """
        ALTER TABLE sales.order_lines ADD CONSTRAINT ck_order_lines_mapping_confirmation CHECK (
            (mapping_status = 'candidate_confirmed')
            = (mapping_confirmed_by IS NOT NULL AND mapping_confirmed_at IS NOT NULL)
            AND (mapping_confirmed_by IS NULL) = (mapping_confirmed_at IS NULL)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE sales.order_lines ADD CONSTRAINT ck_order_lines_pc_confirmation CHECK (
            (pc_confirmed_by IS NULL) = (pc_confirmed_at IS NULL)
        )
        """
    )

    # ---- order_findings ---------------------------------------------------
    op.execute(
        "ALTER TABLE sales.order_findings DROP CONSTRAINT ck_order_findings_disposition_text"
    )
    _retype("order_findings", ("disposition_by",), "uuid")
    op.execute(
        """
        ALTER TABLE sales.order_findings ADD CONSTRAINT ck_order_findings_disposition_text CHECK (
            char_length(disposition_reason) <= 500
            AND char_length(disposition_value) <= 200
            AND char_length(disposition_source) <= 500
        )
        """
    )

    # ---- the rest: a person's id each, with nothing else in their check ---
    for table, column, constraint in (
        ("quote_cases", "assigned_to", "ck_quote_cases_assigned_to"),
        ("artifacts", "created_by", "ck_artifacts_created_by"),
        ("source_served", "principal_id", "ck_source_served_principal_id"),
        ("worker_state", "changed_by", "ck_worker_state_changed_by"),
        ("case_events", "initiated_by", "ck_case_events_initiated_by"),
    ):
        op.execute(f"ALTER TABLE sales.{table} DROP CONSTRAINT {constraint}")
        _retype(table, (column,), "uuid")


def downgrade() -> None:
    for table, column, constraint in (
        ("quote_cases", "assigned_to", "ck_quote_cases_assigned_to"),
        ("artifacts", "created_by", "ck_artifacts_created_by"),
        ("source_served", "principal_id", "ck_source_served_principal_id"),
        ("worker_state", "changed_by", "ck_worker_state_changed_by"),
        ("case_events", "initiated_by", "ck_case_events_initiated_by"),
    ):
        _retype(table, (column,), "text")
        op.execute(
            f"ALTER TABLE sales.{table} ADD CONSTRAINT {constraint} CHECK ({column} ~ {_ACTOR})"
        )

    op.execute(
        "ALTER TABLE sales.order_findings DROP CONSTRAINT ck_order_findings_disposition_text"
    )
    _retype("order_findings", ("disposition_by",), "text")
    op.execute(
        f"""
        ALTER TABLE sales.order_findings ADD CONSTRAINT ck_order_findings_disposition_text CHECK (
            char_length(disposition_reason) <= 500
            AND char_length(disposition_value) <= 200
            AND char_length(disposition_source) <= 500
            AND disposition_by ~ {_ACTOR}
        )
        """
    )

    op.execute("ALTER TABLE sales.order_lines DROP CONSTRAINT ck_order_lines_mapping_confirmation")
    op.execute("ALTER TABLE sales.order_lines DROP CONSTRAINT ck_order_lines_pc_confirmation")
    _retype("order_lines", ("mapping_confirmed_by", "pc_confirmed_by"), "text")
    op.execute(
        f"""
        ALTER TABLE sales.order_lines ADD CONSTRAINT ck_order_lines_mapping_confirmation CHECK (
            (mapping_status = 'candidate_confirmed')
            = (mapping_confirmed_by IS NOT NULL AND mapping_confirmed_at IS NOT NULL)
            AND (mapping_confirmed_by IS NULL) = (mapping_confirmed_at IS NULL)
            AND mapping_confirmed_by ~ {_ACTOR}
        )
        """
    )
    op.execute(
        f"""
        ALTER TABLE sales.order_lines ADD CONSTRAINT ck_order_lines_pc_confirmation CHECK (
            (pc_confirmed_by IS NULL) = (pc_confirmed_at IS NULL)
            AND pc_confirmed_by ~ {_ACTOR}
        )
        """
    )

    op.execute("ALTER TABLE sales.order_cases DROP CONSTRAINT ck_order_cases_checker_not_maker")
    op.execute("ALTER TABLE sales.order_cases ALTER COLUMN makers DROP DEFAULT")
    _retype("order_cases", _ORDER_ACTORS, "text")
    op.execute("ALTER TABLE sales.order_cases ALTER COLUMN makers TYPE text[] USING makers::text[]")
    op.execute("ALTER TABLE sales.order_cases ALTER COLUMN makers SET DEFAULT '{}'::text[]")
    op.execute(_MAKERS_FUNCTION.replace("{array}", "text[]"))
    op.execute(_CHECKER_NOT_MAKER)
    actors = " AND ".join(f"{column} ~ {_ACTOR}" for column in _ORDER_ACTORS)
    op.execute(
        f"ALTER TABLE sales.order_cases ADD CONSTRAINT ck_order_cases_actors CHECK ({actors})"
    )
