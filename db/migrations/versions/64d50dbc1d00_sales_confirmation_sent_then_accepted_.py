"""sales confirmation sent then accepted or implied

Revision ID: 64d50dbc1d00
Revises: 0d1d0e4eb203
Create Date: 2026-11-14 22:40:02.785165+00:00

Sales ticket 28 (dw_sales ADR 0011): an order's confirmation leaves
(`confirmation_sent`, "Đã gửi xác nhận, chờ khách"), then the customer agrees
in words or by silence past their days (`confirmed`, "Khách đã đồng ý"), and a
person records which. Until now `confirmed` was entered when the PIC recorded
the confirmation sent ("Ghi đã gửi xác nhận", `OrderCase.confirm`, with each
line's confirmed dates), and ticket 29 used it as a stand-in for
`confirmation_sent`.

- **Existing rows**: an order in `confirmed` is a confirmation SENT, not a
  customer's agreement, since nothing recorded one: it moves to
  `confirmation_sent`, its `confirmation` the time the PIC recorded it
  (`confirmed_at`), with no sent copy and no term of silence (the rules it
  was checked under have none), so none is ever implied. Its version does
  not change (a name corrected, no decision taken), and `updated_at` keeps
  its value (`touch_updated_at` disabled for the UPDATE, as `6d0252a87a6c`
  did). Each order event into or out of `confirmed` is renamed the same way,
  so "when it entered its status" still reads from the log.
- **`sales.order_cases.confirmation`**: what left (`ConfirmationSent`: when,
  the sent copy it was recorded from, the customer's term and the instant
  silence counts as agreement), an object present exactly while the order is
  in `confirmation_sent` or `confirmed`; a term names a known day count and
  start, and comes with its instant.
- **`sales.order_cases.agreement`**: how the customer agreed
  (`CustomerAgreement`: `accepted` or `implied`, who recorded it and when),
  an object present exactly in `confirmed`.
- **`ck_order_cases_status`**, **`ck_case_events_status`** take
  `confirmation_sent` (`test_sales_schema.py` holds them equal to
  `OrderStatus`); **`ck_order_cases_update_loop`** admits a loop on either
  status of a confirmation that left (ticket 29's loop starts from both).
- **`ck_followup_deliveries_followup`** takes `implied_acceptance`.
- **`ix_order_cases_open_work`** is rebuilt on the predicate the work list
  writes (`SETTLED_ORDERS`): an order whose confirmation left waits on the
  customer and is no step of Sales', as `confirmed` was not.

The columns belong to a table that already holds its grants, RLS policy and
FORCE: nothing about who may read or write it changes.

Downgrade folds both statuses back into `confirmed` (the agreement is lost),
renames the events back, and restores every check and the index.
"""

from __future__ import annotations

from alembic import op

revision = "64d50dbc1d00"
down_revision = "0d1d0e4eb203"
branch_labels = None
depends_on = None

_ORDER_STATUSES_BEFORE = (
    "received",
    "checked",
    "in_review",
    "correction_requested",
    "prepared",
    "uploaded_to_bravo",
    "cross_checked",
    "confirmed",
    "change_review",
    "closed",
)
_ORDER_STATUSES = (*_ORDER_STATUSES_BEFORE, "confirmation_sent")
_QUOTE_STATUSES = (
    "received",
    "ycbg_drafted",
    "ycbg_recorded",
    "sent_to_design",
    "design_replied",
    "spec_discussion",
    "priced",
    "pending_approval",
    "returned",
    "approved",
    "sent",
    "master_list_recorded",
    "declined",
)
_STEPS = ("ask_pc", "waiting_pc", "answer_customer", "waiting_customer", "bravo_update")
_LOOP_ON_BEFORE = ("confirmed", "change_review", "uploaded_to_bravo", "cross_checked")
_LOOP_ON = (*_LOOP_ON_BEFORE, "confirmation_sent")
_FOLLOWUPS_BEFORE = (
    "order_unconfirmed",
    "quote_waiting_design",
    "quote_deadline",
    "waiting_customer",
    "morning_brief",
    "your_turn",
    "waiting_pc",
)
_FOLLOWUPS = (*_FOLLOWUPS_BEFORE, "implied_acceptance")
_LEFT = ("confirmation_sent", "confirmed")
_HOW = ("accepted", "implied")
_DAY_COUNTS = ("calendar", "business")
_COUNTED_FROM = ("confirmation_sent", "po_date")
_SETTLED_BEFORE = "('confirmed', 'closed')"
_SETTLED = "('confirmation_sent', 'confirmed', 'closed')"
_NO_DUE = "'9999-12-31'"


def _in(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{value}'" for value in values) + ")"


def _statuses(orders: tuple[str, ...], loop_on: tuple[str, ...]) -> None:
    op.execute(
        f"""
        ALTER TABLE sales.order_cases
            DROP CONSTRAINT ck_order_cases_status,
            ADD CONSTRAINT ck_order_cases_status CHECK (status IN {_in(orders)}),
            DROP CONSTRAINT ck_order_cases_update_loop,
            ADD CONSTRAINT ck_order_cases_update_loop CHECK (
                update_loop IS NULL OR (
                    jsonb_typeof(update_loop) = 'object'
                    AND update_loop ->> 'step' IN {_in(_STEPS)}
                    AND status IN {_in(loop_on)}
                )
            )
        """
    )
    op.execute(
        f"""
        ALTER TABLE sales.case_events
            DROP CONSTRAINT ck_case_events_status,
            ADD CONSTRAINT ck_case_events_status CHECK (
                CASE case_kind
                    WHEN 'order' THEN to_status IN {_in(orders)}
                        AND (from_status IS NULL OR from_status IN {_in(orders)})
                    ELSE to_status IN {_in(_QUOTE_STATUSES)}
                        AND (from_status IS NULL OR from_status IN {_in(_QUOTE_STATUSES)})
                END
            )
        """
    )


def _followups(values: tuple[str, ...]) -> None:
    op.execute(
        f"""
        ALTER TABLE sales.followup_deliveries
            DROP CONSTRAINT ck_followup_deliveries_followup,
            ADD CONSTRAINT ck_followup_deliveries_followup CHECK (followup IN {_in(values)})
        """
    )


def _open_work(settled: str) -> None:
    op.execute("DROP INDEX sales.ix_order_cases_open_work")
    op.execute(
        "CREATE INDEX ix_order_cases_open_work ON sales.order_cases"
        f" (tenant_id, workspace_id, (coalesce(due, {_NO_DUE})), received_at, id)"
        f" WHERE status NOT IN {settled}"
    )


def _rename_events(old: str, new: str) -> None:
    for column in ("to_status", "from_status"):
        op.execute(
            f"UPDATE sales.case_events SET {column} = '{new}'"
            f" WHERE case_kind = 'order' AND {column} = '{old}'"
        )


def upgrade() -> None:
    _statuses(_ORDER_STATUSES, _LOOP_ON)
    op.execute("ALTER TABLE sales.order_cases ADD COLUMN confirmation jsonb")
    op.execute("ALTER TABLE sales.order_cases ADD COLUMN agreement jsonb")
    op.execute("ALTER TABLE sales.order_cases DISABLE TRIGGER touch_updated_at")
    op.execute(
        "UPDATE sales.order_cases"
        " SET status = 'confirmation_sent',"
        " confirmation = jsonb_build_object('sent_at', confirmed_at)"
        " WHERE status = 'confirmed'"
    )
    op.execute("ALTER TABLE sales.order_cases ENABLE TRIGGER touch_updated_at")
    _rename_events("confirmed", "confirmation_sent")
    op.execute(
        f"""
        ALTER TABLE sales.order_cases
            ADD CONSTRAINT ck_order_cases_confirmation CHECK (
                (status IN {_in(_LEFT)}) = (confirmation IS NOT NULL)
                AND (
                    confirmation IS NULL OR (
                        jsonb_typeof(confirmation) = 'object'
                        AND confirmation ->> 'sent_at' IS NOT NULL
                        AND coalesce(confirmation #>> '{{term,day_count}}', 'calendar')
                            IN {_in(_DAY_COUNTS)}
                        AND coalesce(confirmation #>> '{{term,counted_from}}', 'confirmation_sent')
                            IN {_in(_COUNTED_FROM)}
                        AND (confirmation #>> '{{term,days}}' IS NULL)
                            = (confirmation ->> 'implied_from' IS NULL)
                    )
                )
            ),
            ADD CONSTRAINT ck_order_cases_agreement CHECK (
                (status = 'confirmed') = (agreement IS NOT NULL)
                AND (
                    agreement IS NULL OR (
                        jsonb_typeof(agreement) = 'object'
                        AND agreement ->> 'how' IN {_in(_HOW)}
                    )
                )
            )
        """
    )
    _followups(_FOLLOWUPS)
    _open_work(_SETTLED)


def downgrade() -> None:
    _open_work(_SETTLED_BEFORE)
    op.execute("DELETE FROM sales.followup_deliveries WHERE followup = 'implied_acceptance'")
    _followups(_FOLLOWUPS_BEFORE)
    op.execute("ALTER TABLE sales.order_cases DROP CONSTRAINT ck_order_cases_agreement")
    op.execute("ALTER TABLE sales.order_cases DROP CONSTRAINT ck_order_cases_confirmation")
    _rename_events("confirmation_sent", "confirmed")
    op.execute("ALTER TABLE sales.order_cases DISABLE TRIGGER touch_updated_at")
    op.execute(
        "UPDATE sales.order_cases SET status = 'confirmed' WHERE status = 'confirmation_sent'"
    )
    op.execute("ALTER TABLE sales.order_cases ENABLE TRIGGER touch_updated_at")
    op.execute("ALTER TABLE sales.order_cases DROP COLUMN agreement")
    op.execute("ALTER TABLE sales.order_cases DROP COLUMN confirmation")
    _statuses(_ORDER_STATUSES_BEFORE, _LOOP_ON_BEFORE)
