"""sales approvals on the platform required_scope column

Revision ID: ac31ff0f2087
Revises: 9c8b75ac5f91
Create Date: 2026-10-06 18:45:38.621926+00:00

Sales ticket 10 stamped who decides a DW1 approval in the approval's payload
(`decide_scope`) and let that scope stand in for `approvals.decide`. The
platform's model (its ADR 0004, `docs/adr/0011` here) stamps it in the
`required_scope` column and asks for BOTH. This revision moves the product
onto that model:

- **The stamp moves to the column.** Every approval whose payload names a
  well-formed `decide_scope` gets it as `required_scope`, and the payload key
  is renamed to `required_scope`, as `DecisionAsked` now writes it. All
  statuses, not only pending ones: a decided request's stamp also decides who
  may read it (ADR 0004 amendment, 2026-10-07). A row already stamped is left
  alone. A `decide_scope` that is not a scope name stops the upgrade instead
  of leaving a Sales request unstamped, which would show it to every member.
  Runs paused before this revision keep `decide_scope` in their checkpoint;
  `DecisionAsked` reads that name too.
- **Its deciders gain `approvals.decide`:** roles `sales_pic` and
  `sales_head` (cross-check, quote approval) and permission set
  `sales_quote_approver`. Without it no Sales decider passes the platform's
  first check. A consequence, accepted: they can also decide UNSTAMPED
  approvals in their workspace, as any approver can. No separation-of-duty
  rule names `approvals.decide` today; the upgrade asserts no membership of
  these roles breaks one that does.
"""

from __future__ import annotations

from alembic import op

revision = "ac31ff0f2087"
down_revision = "9c8b75ac5f91"
branch_labels = None
depends_on = None

# The shape `ck_approval_requests_required_scope` (36dabf47619c) enforces.
_SCOPE_SHAPE = r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$"
_ROLES = ("sales_pic", "sales_head")
_PERMISSION_SETS = ("sales_quote_approver",)


def _keys(keys: tuple[str, ...]) -> str:
    return ", ".join(f"'{key}'" for key in keys)


def upgrade() -> None:
    # Runs as the migrator, which bypasses RLS: every tenant's approvals.
    op.execute(
        rf"""
        DO $$
        DECLARE
            unreadable integer;
        BEGIN
            SELECT count(*) INTO unreadable
            FROM platform.approval_requests
            WHERE payload ? 'decide_scope'
              AND required_scope IS NULL
              AND coalesce(payload->>'decide_scope', '') !~ '{_SCOPE_SHAPE}';
            IF unreadable > 0 THEN
                RAISE EXCEPTION
                    '% approval(s) name a decide_scope that is not a scope name', unreadable;
            END IF;
        END
        $$
        """
    )
    op.execute(
        """
        UPDATE platform.approval_requests
        SET required_scope = payload->>'decide_scope',
            payload = (payload - 'decide_scope')
                || jsonb_build_object('required_scope', payload->>'decide_scope')
        WHERE payload ? 'decide_scope' AND required_scope IS NULL
        """
    )
    op.execute(
        "UPDATE platform.roles SET scopes = scopes || '[\"approvals.decide\"]'::jsonb"
        f" WHERE key IN ({_keys(_ROLES)}) AND NOT scopes ? 'approvals.decide'"
    )
    op.execute(
        "UPDATE platform.permission_sets SET scopes = scopes || '[\"approvals.decide\"]'::jsonb"
        f" WHERE key IN ({_keys(_PERMISSION_SETS)}) AND NOT scopes ? 'approvals.decide'"
    )
    # The trigger judges a membership only when it is written, so one this
    # change put in breach would sit unnoticed until its next edit failed.
    op.execute(
        """
        DO $$
        DECLARE
            breaking integer;
        BEGIN
            SELECT count(*) INTO breaking
            FROM platform.memberships m
            CROSS JOIN platform.sod_rules r
            WHERE (r.left_scopes ? 'approvals.decide' OR r.right_scopes ? 'approvals.decide')
              AND platform.sod_rule_broken(r.key, m.role_keys, m.permission_set_keys);
            IF breaking > 0 THEN
                RAISE EXCEPTION
                    '% membership(s) break a rule on approvals.decide', breaking;
            END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute(
        "UPDATE platform.permission_sets SET scopes = scopes - 'approvals.decide'"
        f" WHERE key IN ({_keys(_PERMISSION_SETS)})"
    )
    op.execute(
        f"UPDATE platform.roles SET scopes = scopes - 'approvals.decide' WHERE key IN ({_keys(_ROLES)})"
    )
    # The column stays as the platform's revision left it; only the payload
    # name goes back, so ticket 10's reader finds its stamp again.
    op.execute(
        """
        UPDATE platform.approval_requests
        SET payload = (payload - 'required_scope')
            || jsonb_build_object('decide_scope', payload->>'required_scope')
        WHERE payload ? 'required_scope' AND approval_type LIKE 'sales.%'
        """
    )
