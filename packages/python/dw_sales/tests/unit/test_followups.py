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
from dw_sales.application.followups import LOADED, reminder_text
from dw_sales.application.overview_service import WHOSE_TURN
from dw_sales.application.rules import OVERRIDABLE, RuleKey
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.followups import (
    WATCHED,
    Followup,
    SalesFollowups,
    Stage,
    WaitingCase,
    brief_slot,
    due_soon,
    owed,
    pc_reminder_at,
)
from dw_sales.testing.followups import platform_reminder_copy

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
POLICY_FILE = REPO / "configs" / "policies" / "sales_followups@1.1.0.yaml"
# 1.1.0 predates the wait on PC (ticket 07): its section is 1.3.0's, as a
# tenant's version written before it reads it (`read_over`).
PC_FILE = REPO / "configs" / "policies" / "sales_followups@1.3.0.yaml"
# And the implied acceptance's (ticket 28), 1.4.0's.
IMPLIED_FILE = REPO / "configs" / "policies" / "sales_followups@1.4.0.yaml"
# And the waits on Design's new code and on a linked quote (tickets 06, 09).
WAITS_FILE = REPO / "configs" / "policies" / "sales_followups@1.6.0.yaml"
# Monday 19 October 2026, 08:00 in Ho Chi Minh City (UTC+7).
MONDAY_8 = datetime(2026, 10, 19, 1, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)
MINUTE = timedelta(minutes=1)


def _document() -> dict[str, Any]:
    loaded = yaml.safe_load(POLICY_FILE.read_bytes())
    assert isinstance(loaded, dict)
    loaded.setdefault("waiting_pc", yaml.safe_load(PC_FILE.read_bytes())["waiting_pc"])
    implied = yaml.safe_load(IMPLIED_FILE.read_bytes())["implied_acceptance"]
    loaded.setdefault("implied_acceptance", implied)
    waits = yaml.safe_load(WAITS_FILE.read_bytes())
    for name in ("waiting_design_code", "waiting_quote"):
        loaded.setdefault(name, waits[name])
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


def test_the_shipped_default_is_open_every_day_at_any_hour() -> None:
    """Đạt, 2026-11-13: DW runs 24/7 by default; a tenant narrows the hours
    as a rule version. Sunday 25 October 2026, 03:00 local is open."""
    policy = load_sales_policies(REPO / "configs" / "policies", REPO / "configs" / "copy").followups
    hours = policy.working_hours
    assert set(hours.days) == {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
    sunday_3am = datetime(2026, 10, 24, 20, 0, tzinfo=UTC)  # 03:00 UTC+7, Sunday
    assert hours.is_open(sunday_3am)
    assert all(hours.is_open(MONDAY_8 + day * 24 * HOUR - 8 * HOUR) for day in range(7))


def test_the_shipped_policy_holds_the_proposals_numbers() -> None:
    policy = load_sales_policies(REPO / "configs" / "policies", REPO / "configs" / "copy").followups
    assert policy.ref == "sales_followups@1.6.0"
    # 1.6.0 (tickets 06 and 09): one reminder to the PIC after a day of
    # waiting on Design's new code, or on a quote opened from the order.
    for wait in (policy.waiting_design_code, policy.waiting_quote):
        assert wait.enabled
        assert wait.remind.after_hours == 24
        assert wait.remind.notify == ("pic",)
    # 1.5.0 (ticket 48): a push names the case number unless the tenant
    # turns it off.
    assert policy.push.case_number
    assert policy.implied_acceptance.enabled
    assert policy.waiting_pc.enabled
    assert policy.waiting_pc.remind.after_hours == 24
    assert policy.waiting_pc.remind.notify == ("pic",)
    assert policy.order_unconfirmed.remind.after_hours == 4
    assert policy.order_unconfirmed.remind.notify == ("pic",)
    assert policy.order_unconfirmed.escalate.after_hours == 24
    assert policy.order_unconfirmed.escalate.notify == ("head",)
    assert policy.quote_deadline.warn.hours_before_due == 48
    assert policy.waiting_customer.remind.after_hours == 24
    assert policy.morning_brief.at == "07:30"
    assert policy.working_hours.time_zone == "Asia/Ho_Chi_Minh"
    assert policy.working_hours.days == ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


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


@pytest.mark.parametrize(
    "status", ["confirmation_sent", "confirmed", "closed", "correction_requested"]
)
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
        "waiting_pc",
        "your_turn",
        "implied_acceptance",
        "waiting_design_code",
        "waiting_quote",
    }


# ------------------------------------------------ waiting on PC (ticket 07) --


def _asked_pc(at: datetime | None, status: str = "in_review") -> WaitingCase:
    return replace(_case(status=status), pc_asked_at=at)


def test_an_order_waiting_on_pc_reminds_the_pic_a_day_after_pc_was_asked() -> None:
    asked = MONDAY_8 + 2 * HOUR
    case = _asked_pc(asked)
    assert ("waiting_pc", "remind") not in _owed(case, asked + 24 * HOUR - MINUTE)
    found = [
        d for d in owed(PLATFORM, [case], asked + 24 * HOUR) if d.followup.value == "waiting_pc"
    ]
    assert [(d.since, d.notify) for d in found] == [(asked, ("pic",))]
    title, body = reminder_text(platform_reminder_copy(), PLATFORM, found[0], asked + 24 * HOUR)
    assert "PC" in title and "VLX" in body


def test_an_order_whose_pc_answer_is_recorded_is_owed_no_pc_reminder() -> None:
    """The case names no request once PC answered every line asked: nothing
    keeps firing after the answer (failure-modes #6)."""
    assert ("waiting_pc", "remind") not in _owed(_asked_pc(None), MONDAY_8 + 72 * HOUR)


def test_the_pc_reminder_is_the_tenants_number_and_switch() -> None:
    later = _policy(waiting_pc={"remind": {"after_hours": 48, "notify": ["pic", "head"]}})
    case = _asked_pc(MONDAY_8)
    assert ("waiting_pc", "remind") not in _owed(case, MONDAY_8 + 47 * HOUR, later)
    assert ("waiting_pc", "remind") in _owed(case, MONDAY_8 + 48 * HOUR, later)
    assert pc_reminder_at(later, MONDAY_8) == MONDAY_8 + 48 * HOUR
    off = _policy(waiting_pc={"enabled": False})
    assert ("waiting_pc", "remind") not in _owed(case, MONDAY_8 + 72 * HOUR, off)
    assert pc_reminder_at(off, MONDAY_8) is None


# ------------------------------------------- your turn (2026-10-28) --


def test_whose_turn_reads_the_buckets_and_the_next_steps() -> None:
    order, quote = WHOSE_TURN[CaseKind.ORDER], WHOSE_TURN[CaseKind.QUOTE]
    assert order["in_review"] == "pic"
    assert order["uploaded_to_bravo"] == "head"  # a cross-check, by someone else
    assert "received" not in order  # DW1's own
    assert "correction_requested" not in order  # the customer's
    assert quote["received"] == "pic"
    assert quote["design_replied"] == "pic"
    assert quote["pending_approval"] == "head"
    assert "sent_to_design" not in quote  # Design's


def test_a_case_waiting_on_a_person_is_owed_at_once_and_once_per_status() -> None:
    case = _case(status="in_review", since=MONDAY_8)
    (due,) = [
        d
        for d in owed(PLATFORM, [case], MONDAY_8, turns=WHOSE_TURN)
        if d.followup.value == "your_turn"
    ]
    assert (due.stage.value, due.since, due.notify) == ("notify", MONDAY_8, ("pic",))
    later = _case(status="prepared", since=MONDAY_8 + HOUR)
    (again,) = [
        d
        for d in owed(PLATFORM, [later], MONDAY_8 + HOUR, turns=WHOSE_TURN)
        if d.followup.value == "your_turn"
    ]
    assert again.since != due.since  # a new wait, a new notice
    assert not [
        d
        for d in owed(PLATFORM, [_case(status="received")], MONDAY_8, turns=WHOSE_TURN)
        if d.followup.value == "your_turn"
    ]


@pytest.mark.parametrize(
    ("status", "step"),
    [
        ("ycbg_drafted", "DW1 đã soạn YCBG: nhập vào Bravo rồi ghi số YCBG để gửi Design."),
        ("design_replied", "Design đã trả lời: quyết định giá, DW1 đã gợi ý giá kèm căn cứ."),
        ("received", "Mở hồ sơ để xem việc cần làm."),
    ],
)
def test_your_turn_on_a_quote_says_what_to_do_next(status: str, step: str) -> None:
    """Where DW1 did the step before, the notice names the next one, so the
    PIC need not open the case to learn it (2026-10-28)."""
    case = _case(CaseKind.QUOTE, status)
    (due,) = owed(PLATFORM, [case], MONDAY_8, turns=WHOSE_TURN)
    assert due.followup is Followup.YOUR_TURN
    title, body = reminder_text(platform_reminder_copy(), PLATFORM, due, MONDAY_8)
    assert title == "Đến lượt bạn: Báo giá PO-1"
    assert body.endswith(step)


@pytest.mark.parametrize(
    ("due", "within", "soon"),
    [
        (date(2026, 10, 5), 2, True),  # today
        (date(2026, 10, 7), 2, True),  # the last day the policy counts
        (date(2026, 10, 8), 2, False),
        (date(2026, 10, 8), 3, True),  # a tenant counting three days
        (date(2026, 10, 4), 2, False),  # past: overdue, not "due soon"
    ],
)
def test_due_soon_is_the_policys_days_and_nothing_else(due: date, within: int, soon: bool) -> None:
    """Audit finding 15: "sắp đến hạn" is `morning_brief.due_within_days`,
    decided here for the brief, the work list and the quote page alike; the
    web holds no threshold of its own."""
    platform = load_sales_policies(REPO / "configs" / "policies", REPO / "configs" / "copy")
    policy = platform.followups
    policy = policy.model_copy(
        update={
            "morning_brief": policy.morning_brief.model_copy(update={"due_within_days": within})
        }
    )

    assert due_soon(due, date(2026, 10, 5), policy) is soon
