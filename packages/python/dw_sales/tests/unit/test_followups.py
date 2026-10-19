"""The `sales_followups` policy and what it makes owed (ticket 42).

Pure: the policy as `configs/policies/sales_followups@1.0.0.yaml` ships it,
cases as the lane reads them, and a clock. The lane itself (delivery, the
record, the brief, tenants) is `test_followups_lane.py`.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from dw_sales.adapters.policy_files import load_sales_policies
from dw_sales.application.followups import LOADED
from dw_sales.application.rules import OVERRIDABLE, RuleKey
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.followups import (
    WATCHED,
    Followup,
    SalesFollowups,
    Stage,
    WaitingCase,
    brief_slot,
    owed,
)

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
POLICY_FILE = REPO / "configs" / "policies" / "sales_followups@1.0.0.yaml"
# Monday 19 October 2026, 08:00 in Ho Chi Minh City (UTC+7).
MONDAY_8 = datetime(2026, 10, 19, 1, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)
MINUTE = timedelta(minutes=1)


def _document() -> dict[str, Any]:
    loaded = yaml.safe_load(POLICY_FILE.read_bytes())
    assert isinstance(loaded, dict)
    return loaded


def _policy(**sections: dict[str, Any]) -> SalesFollowups:
    """The shipped policy with whole sections replaced or merged."""
    document = _document()
    for name, values in sections.items():
        document[name] = {**document[name], **values}
    return SalesFollowups.model_validate(document)


PLATFORM = _policy()


def _case(
    kind: CaseKind = CaseKind.ORDER,
    status: str = "in_review",
    *,
    received: datetime = MONDAY_8,
    since: datetime | None = None,
    due: date | None = None,
) -> WaitingCase:
    return WaitingCase(
        kind=kind,
        case_id=uuid.uuid4(),
        status=status,
        reference="PO-1",
        customer_code="VLX",
        received_at=received,
        status_since=since or received,
        assigned_to=uuid.uuid4(),
        due=due,
    )


def _owed(
    case: WaitingCase, now: datetime, policy: SalesFollowups = PLATFORM
) -> set[tuple[str, str]]:
    return {(d.followup.value, d.stage.value) for d in owed(policy, [case], now)}


# ------------------------------------------------------------ the policy --


def test_the_shipped_policy_holds_the_proposals_numbers() -> None:
    policy = load_sales_policies(REPO / "configs" / "policies", REPO / "configs" / "copy").followups
    assert policy.ref == "sales_followups@1.0.0"
    assert policy.order_unconfirmed.remind.after_hours == 4
    assert policy.order_unconfirmed.remind.notify == ("pic",)
    assert policy.order_unconfirmed.escalate.after_hours == 24
    assert policy.order_unconfirmed.escalate.notify == ("head",)
    assert policy.quote_deadline.warn.hours_before_due == 48
    assert policy.waiting_customer.remind.after_hours == 24
    assert policy.morning_brief.at == "07:30"
    assert policy.working_hours.time_zone == "Asia/Ho_Chi_Minh"
    assert policy.working_hours.days == ("mon", "tue", "wed", "thu", "fri", "sat")


def test_the_key_is_one_a_tenant_may_override() -> None:
    assert OVERRIDABLE[RuleKey.FOLLOWUPS] is SalesFollowups


def test_every_field_says_what_it_is_for_the_rules_form() -> None:
    """The rules page renders a form from the schema: every field a person
    edits has a description, at every depth."""

    def walk(schema: dict[str, Any], defs: dict[str, Any], path: str) -> list[str]:
        missing: list[str] = []
        for name, field in schema.get("properties", {}).items():
            if name in ("schema_version", "policy_id", "policy_version"):
                continue
            if "description" not in field:
                missing.append(f"{path}{name}")
            ref = field.get("$ref") or next(
                (a["$ref"] for a in field.get("allOf", []) if "$ref" in a), None
            )
            if ref:
                missing += walk(defs[ref.rsplit("/", 1)[1]], defs, f"{path}{name}.")
        return missing

    schema = SalesFollowups.model_json_schema()
    assert walk(schema, schema["$defs"], "") == []


@pytest.mark.parametrize(
    ("section", "values"),
    [
        # An escalation no later than the reminder it follows.
        ("order_unconfirmed", {"escalate": {"after_hours": 4, "notify": ["head"]}}),
        # A bare 07:30 in YAML is the number 450, not a time.
        ("morning_brief", {"at": 450}),
        ("morning_brief", {"at": "7:30"}),
        ("working_hours", {"time_zone": "Mars/Olympus_Mons"}),
        ("working_hours", {"days": ["mon", "mon"]}),
        ("working_hours", {"days": []}),
        ("working_hours", {"start": "18:00"}),
        ("order_unconfirmed", {"remind": {"after_hours": 0, "notify": ["pic"]}}),
        ("order_unconfirmed", {"remind": {"after_hours": 4, "notify": []}}),
        ("order_unconfirmed", {"remind": {"after_hours": 4, "notify": ["pic", "pic"]}}),
        ("order_unconfirmed", {"remind": {"after_hours": 4, "notify": ["customer"]}}),
        ("quote_deadline", {"warn": {"hours_before_due": -1, "notify": ["pic"]}}),
    ],
)
def test_a_document_that_would_fail_open_is_refused(section: str, values: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _policy(**{section: values})


@pytest.mark.parametrize("field", ["enabled", "remind", "escalate"])
def test_no_field_has_a_default(field: str) -> None:
    """A switch or a threshold left out is refused, never read as on, off or
    a number nobody chose (failure-modes #7)."""
    document = _document()
    del document["order_unconfirmed"][field]
    with pytest.raises(ValidationError):
        SalesFollowups.model_validate(document)


def test_every_status_a_followup_watches_is_one_the_lane_loads() -> None:
    """The lane loads the statuses a case waits on someone in (the
    overview's buckets); a follow-up watching any other would never fire."""
    for kind, statuses in WATCHED.items():
        assert statuses <= LOADED[kind], kind


# ------------------------------------------------------ order unconfirmed --


def test_an_order_is_reminded_to_its_pic_at_four_hours_not_a_minute_before() -> None:
    case = _case()
    assert _owed(case, MONDAY_8 + 4 * HOUR - MINUTE) == set()
    assert _owed(case, MONDAY_8 + 4 * HOUR) == {("order_unconfirmed", "remind")}
    (due,) = owed(PLATFORM, [case], MONDAY_8 + 4 * HOUR)
    assert due.notify == ("pic",)
    assert due.since == case.received_at


def test_an_order_unconfirmed_a_day_goes_to_the_head() -> None:
    case = _case()
    assert ("order_unconfirmed", "escalate") not in _owed(case, MONDAY_8 + 24 * HOUR - MINUTE)
    found = owed(PLATFORM, [case], MONDAY_8 + 24 * HOUR)
    escalated = [d for d in found if d.stage is Stage.ESCALATE]
    assert [d.notify for d in escalated] == [("head",)]


@pytest.mark.parametrize("status", ["confirmed", "closed", "correction_requested"])
def test_an_order_confirmed_closed_or_waiting_on_the_customer_is_not_unconfirmed(
    status: str,
) -> None:
    owed_now = _owed(_case(status=status), MONDAY_8 + 48 * HOUR)
    assert not {f for f, _ in owed_now} & {"order_unconfirmed"}


def test_a_switched_off_followup_is_owed_nothing() -> None:
    off = _policy(order_unconfirmed={"enabled": False})
    assert _owed(_case(), MONDAY_8 + 48 * HOUR, off) == set()


def test_a_tenants_own_threshold_moves_the_reminder() -> None:
    later = _policy(order_unconfirmed={"remind": {"after_hours": 8, "notify": ["pic", "head"]}})
    case = _case()
    assert _owed(case, MONDAY_8 + 4 * HOUR, later) == set()
    (due,) = owed(later, [case], MONDAY_8 + 8 * HOUR)
    assert due.notify == ("pic", "head")


# ------------------------------------------------------------- quotes --


def test_a_quote_waiting_on_design_is_counted_from_when_it_was_sent() -> None:
    sent = MONDAY_8 + 30 * HOUR
    case = _case(CaseKind.QUOTE, "sent_to_design", since=sent)
    assert _owed(case, sent + 24 * HOUR - MINUTE) == set()
    assert _owed(case, sent + 24 * HOUR) == {("quote_waiting_design", "remind")}
    assert _owed(_case(CaseKind.QUOTE, "design_replied", since=sent), sent + 48 * HOUR) == set()


def test_a_quote_deadline_is_told_two_days_before_the_end_of_its_day() -> None:
    # Due Wednesday 21 October: late from Thursday 00:00 local, told from
    # Tuesday 00:00 local (Monday 17:00 UTC).
    case = _case(CaseKind.QUOTE, "priced", due=date(2026, 10, 21))
    told = datetime(2026, 10, 19, 17, 0, tzinfo=UTC)
    assert _owed(case, told - MINUTE) == set()
    assert _owed(case, told) == {("quote_deadline", "warn")}
    (due,) = owed(PLATFORM, [case], told)
    assert due.since == datetime(2026, 10, 21, 17, 0, tzinfo=UTC)


def test_a_quote_sent_or_without_a_due_date_has_no_deadline_reminder() -> None:
    now = datetime(2026, 10, 21, 3, 0, tzinfo=UTC)
    assert _owed(_case(CaseKind.QUOTE, "sent", due=date(2026, 10, 21)), now) == set()
    assert _owed(_case(CaseKind.QUOTE, "priced"), now) == set()


# --------------------------------------------------- waiting on the customer --


@pytest.mark.parametrize(
    ("kind", "status"),
    [(CaseKind.ORDER, "correction_requested"), (CaseKind.QUOTE, "spec_discussion")],
)
def test_a_case_waiting_on_the_customer_a_day_reminds_the_pic(kind: CaseKind, status: str) -> None:
    asked = MONDAY_8 + 2 * HOUR
    case = _case(kind, status, since=asked)
    assert ("waiting_customer", "remind") not in _owed(case, asked + 24 * HOUR - MINUTE)
    assert ("waiting_customer", "remind") in _owed(case, asked + 24 * HOUR)


def test_a_second_wait_is_owed_again() -> None:
    """The stage is owed per wait: a case that comes back to the customer
    later is a new wait, with its own reminder."""
    first = _case(CaseKind.ORDER, "correction_requested", since=MONDAY_8)
    again = replace(first, status_since=first.status_since + 50 * HOUR)
    a = owed(PLATFORM, [first], MONDAY_8 + 100 * HOUR)
    b = owed(PLATFORM, [again], MONDAY_8 + 100 * HOUR)
    assert {d.since for d in a} != {d.since for d in b}


# -------------------------------------------------------- working hours --


@pytest.mark.parametrize(
    ("moment", "open_"),
    [
        (MONDAY_8 - MINUTE, False),  # 07:59 Monday
        (MONDAY_8, True),  # 08:00 Monday
        (MONDAY_8 + 9.5 * HOUR - MINUTE, True),  # 17:29
        (MONDAY_8 + 9.5 * HOUR, False),  # 17:30
        (MONDAY_8 + 5 * 24 * HOUR, True),  # Saturday 08:00
        (MONDAY_8 + 6 * 24 * HOUR, False),  # Sunday 08:00
    ],
)
def test_working_hours_are_monday_to_saturday_eight_to_half_past_five(
    moment: datetime, open_: bool
) -> None:
    assert PLATFORM.working_hours.is_open(moment) is open_


def test_a_tenant_may_work_on_sunday() -> None:
    every_day = _policy(working_hours={"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]})
    assert every_day.working_hours.is_open(MONDAY_8 + 6 * 24 * HOUR)


# ---------------------------------------------------------------- brief --


def test_the_brief_is_due_from_half_past_seven_on_a_working_day() -> None:
    half_past_seven = MONDAY_8 - 30 * MINUTE
    assert brief_slot(PLATFORM, half_past_seven - MINUTE) is None
    slot = brief_slot(PLATFORM, half_past_seven)
    assert slot is not None
    assert slot.day == date(2026, 10, 19)
    assert slot.at == half_past_seven
    # Monday's counts from Saturday's: Sunday is no working day.
    assert slot.since == half_past_seven - 2 * 24 * HOUR
    # Late is still today's.
    later = brief_slot(PLATFORM, MONDAY_8 + 10 * HOUR)
    assert later is not None and later.day == slot.day


def test_no_brief_on_sunday_or_switched_off() -> None:
    assert brief_slot(PLATFORM, MONDAY_8 + 6 * 24 * HOUR) is None
    assert brief_slot(_policy(morning_brief={"enabled": False}), MONDAY_8) is None


def test_a_tenants_own_brief_time_moves_it() -> None:
    nine = _policy(morning_brief={"at": "09:00"})
    assert brief_slot(nine, MONDAY_8 + 59 * MINUTE) is None
    assert brief_slot(nine, MONDAY_8 + HOUR) is not None


def test_followups_name_the_stage_they_are_owed_at() -> None:
    assert {f.value for f in Followup} == {
        "order_unconfirmed",
        "quote_waiting_design",
        "quote_deadline",
        "waiting_customer",
    }
