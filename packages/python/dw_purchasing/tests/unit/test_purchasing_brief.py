"""DW2's morning brief (DW02 function 6's other half): once per working day,
at the tenant's time in the plant's day, each person told the counts of
what waits on them; never an amount, never a case's words."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from dw_purchasing.domain.brief import BriefRules, brief_day
from dw_purchasing.testing.flows import orders_drafted
from dw_purchasing.testing.lane import lane_of
from dw_purchasing.testing.world import ALPHA, RecordedNotices, World, caller, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
FIXTURES = REPO / "evals/fixtures/cases"
INTAKE = json.loads((FIXTURES / "purchasing_pr_intake.json").read_text(encoding="utf-8"))
SOURCING = json.loads((FIXTURES / "purchasing_sourcing.json").read_text(encoding="utf-8"))
RULES = BriefRules.model_validate(
    {"at": "07:30", "days": ["mon", "tue", "wed", "thu", "fri", "sat"]}
)


def _world() -> World:
    world = open_world(REPO, INTAKE["answers"])
    world.model.by_schema = {
        "ModelOffer": SOURCING["answers"],
        "RfqWording": {"PR-2611-004": SOURCING["rfq_words"]["good"]},
    }
    return world


@pytest.mark.parametrize(
    ("utc", "day"),
    [
        # Tuesday 07:00 at the plant: not yet.
        (datetime(2026, 11, 3, 0, 0, tzinfo=UTC), None),
        # Tuesday 07:30 at the plant: today's.
        (datetime(2026, 11, 3, 0, 30, tzinfo=UTC), "2026-11-03"),
        # 23:00 UTC on Monday is Tuesday 06:00 at the plant: not yet.
        (datetime(2026, 11, 2, 23, 0, tzinfo=UTC), None),
        # Sunday at the plant: no brief.
        (datetime(2026, 11, 8, 2, 0, tzinfo=UTC), None),
    ],
)
def test_the_brief_is_due_from_its_time_on_a_working_day_at_the_plant(
    utc: datetime, day: str | None
) -> None:
    found = brief_day(RULES, utc)
    assert (found.isoformat() if found else None) == day


def test_a_time_that_is_no_time_is_no_rule() -> None:
    with pytest.raises(ValueError):
        BriefRules.model_validate({"at": "7h30", "days": ["mon"]})
    with pytest.raises(ValueError):
        BriefRules.model_validate({"at": "07:30", "days": []})


async def _waiting_on_everyone(world: World) -> tuple[uuid.UUID, str]:
    """P01's orders followed, P02 sent to its approver: the approver's scope."""
    await orders_drafted(world)
    item = await world.service.read_mail(caller(), "P02")
    assert item.case_id is not None
    await world.approvals.submit(caller(), item.case_id, case_version=1)
    case = await world.service.case(caller(), item.case_id)
    assert case.approval is not None
    return item.case_id, case.approval.required_scope


async def test_each_person_is_told_once_a_day_what_waits_on_them_in_counts() -> None:
    world, notices = _world(), RecordedNotices()
    _, scope = await _waiting_on_everyone(world)
    lane = lane_of(world, notices)
    # Saturday 21/11, 09:00 at the plant; P01's lines were needed by 20/11.
    world.clock.advance_to(datetime(2026, 11, 21, 2, 0, tzinfo=UTC))

    await lane.tick(*ALPHA)
    await lane.tick(*ALPHA)

    briefs = {k: v for k, v in notices.told.items() if k.startswith("purchasing.brief:")}
    buyer = briefs["purchasing.brief:2026-11-21:buyer"]
    assert buyer[0] == frozenset({"purchasing.rfq.prepare", "purchasing.po.prepare"})
    assert "1 đơn đang theo dõi" in buyer[4] and "2 dòng hàng trễ hạn" in buyer[4]
    assert buyer[5] == "/purchasing"
    approver = briefs[f"purchasing.brief:2026-11-21:approve:{scope}"]
    assert approver[0] == frozenset({scope})
    assert "1 yêu cầu chờ bạn duyệt" in approver[4]
    # Counts only: no number in it but a count.
    for told in briefs.values():
        assert all(len(n) <= 3 for n in re.findall(r"\d+", told[4]))

    # Sunday: nothing new.
    world.clock.advance_to(datetime(2026, 11, 22, 2, 0, tzinfo=UTC))
    await lane.tick(*ALPHA)
    assert not [k for k in notices.told if k.startswith("purchasing.brief:2026-11-22")]


async def test_the_tenant_s_own_time_is_the_one_read() -> None:
    """A tenant whose rules send the brief at 10:00 is told nothing at 09:00
    at the plant, and is told at 10:00."""
    world, notices = _world(), RecordedNotices()
    await _waiting_on_everyone(world)
    own = yaml.safe_load(
        (REPO / "configs/policies/purchasing_rules@1.8.0.yaml").read_text(encoding="utf-8")
    )
    own.pop("schema_version", None)
    own.pop("policy_id", None)
    world.tenant_policies.documents[(ALPHA[0], "purchasing_rules")] = {
        **own,
        "version": "9.0.0",
        "brief": {"at": "10:00", "days": ["sat"]},
    }
    lane = lane_of(world, notices)
    world.clock.advance_to(datetime(2026, 11, 21, 2, 0, tzinfo=UTC))
    await lane.tick(*ALPHA)
    assert not [k for k in notices.told if k.startswith("purchasing.brief:")]
    world.clock.advance_to(datetime(2026, 11, 21, 3, 0, tzinfo=UTC))
    await lane.tick(*ALPHA)
    assert "purchasing.brief:2026-11-21:buyer" in notices.told
