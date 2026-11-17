"""Ticket 05's wait: a quote case marked pcs waits for the GM/BC Manager's
price, and its PIC is reminded a day later (`waiting_pcs_price`, on at 24 h,
PIC only), from when the case was marked pcs, until Sales records the price
or the case goes back to mass. DW1 never mails the GM: the PIC chases.

The rule (`owed`) first, then the lane over the in-memory world, whose
follow-up store reads the wait as `SqlFollowupStore` does.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_sales.adapters.policy_files import rule_book
from dw_sales.application.followups import FollowupLane
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.followups import Followup, SalesFollowups, WaitingCase, owed
from dw_sales.domain.quotes import PcsPriceLine, QuoteStatus
from dw_sales.evals.graders import CALLERS, DIEU
from dw_sales.evals.world import ALPHA, SampleSet, World, open_world
from dw_sales.evals.world import Directory as Holders
from dw_sales.testing.followups import platform_followups

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
HOUR = timedelta(hours=1)
MINUTE = timedelta(minutes=1)
T0 = datetime(2026, 11, 16, 1, 0, tzinfo=UTC)


def _quote(status: QuoteStatus = QuoteStatus.DESIGN_REPLIED, **waits: Any) -> WaitingCase:
    return WaitingCase(
        kind=CaseKind.QUOTE,
        case_id=uuid.UUID(int=5),
        status=status.value,
        reference="RFQ-1",
        customer_code="C-1",
        received_at=T0,
        status_since=T0,
        assigned_to=uuid.UUID(int=1),
        due=None,
        **waits,
    )


def _waits(case: WaitingCase, at: datetime, policy: SalesFollowups | None = None) -> list[Any]:
    return [
        (d.since, d.notify)
        for d in owed(policy or platform_followups(), [case], at)
        if d.followup is Followup.WAITING_PCS_PRICE
    ]


def test_a_pcs_case_without_the_gms_price_reminds_the_pic_a_day_after_it_was_marked() -> None:
    case = _quote(pcs_price_asked_at=T0)
    assert _waits(case, T0 + 24 * HOUR - MINUTE) == []
    assert _waits(case, T0 + 24 * HOUR) == [(T0, ("pic",))]


@pytest.mark.parametrize(
    "case",
    [
        # Mass, or pcs with the GM's price recorded: the store reads no wait.
        _quote(pcs_price_asked_at=None),
        # Sent or declined: nothing is priced any more.
        _quote(QuoteStatus.SENT, pcs_price_asked_at=T0),
        _quote(QuoteStatus.DECLINED, pcs_price_asked_at=T0),
    ],
)
def test_a_case_that_waits_on_no_gm_price_is_not_reminded_of_one(case: WaitingCase) -> None:
    assert _waits(case, T0 + 99 * HOUR) == []


def test_the_wait_switched_off_reminds_nobody() -> None:
    document = platform_followups().model_dump(mode="json")
    document["waiting_pcs_price"] = {**document["waiting_pcs_price"], "enabled": False}
    off = SalesFollowups.model_validate(document)
    assert _waits(_quote(pcs_price_asked_at=T0), T0 + 99 * HOUR, off) == []


# --------------------------------------------- the lane over the world --


class _Sender:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, tuple[uuid.UUID, ...]]] = []

    async def deliver(self, context: Any, **sent: Any) -> None:
        from dw_sales.application.followups import parse_source_key

        key = parse_source_key(sent["source_key"])
        assert key is not None
        self.calls.append((key.followup, sent["title"], sent["body"], tuple(sent["recipients"])))

    def of(self, followup: Followup) -> list[tuple[str, str, tuple[uuid.UUID, ...]]]:
        return [(t, b, r) for f, t, b, r in self.calls if f == followup.value]


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS)


async def _tick(world: World, at: datetime) -> _Sender:
    sender = _Sender()
    lane = FollowupLane(
        uow=world.store,
        policies=rule_book(world.policies, world.store.rule_versions),
        holders=Holders(CALLERS),
        notifications=sender,
        clock=FixedClock(at),
        ids=Uuid4Generator(),
    )
    await lane.tick(ALPHA)
    return sender


async def _m10_marked_pcs(world: World) -> tuple[uuid.UUID, datetime]:
    seen = await world.process_each(DIEU, ["M10"])
    case_id = seen["M10"][0].case_id
    assert case_id is not None
    await world.services.quote_commands.production_type(
        DIEU.context(), case_id, case_version=world.quote(case_id).case_version, kind="pcs"
    )
    marked = world.quote(case_id).production_type_set
    assert marked is not None
    return case_id, marked.at


async def test_the_pic_is_reminded_while_the_gm_has_not_priced_the_pcs_case() -> None:
    world = _world()
    _, marked = await _m10_marked_pcs(world)
    assert (await _tick(world, marked + 24 * HOUR - MINUTE)).of(Followup.WAITING_PCS_PRICE) == []

    ((title, body, recipients),) = (await _tick(world, marked + 24 * HOUR)).of(
        Followup.WAITING_PCS_PRICE
    )

    assert recipients == (DIEU.user_id,)
    assert "giá GM" in title
    assert "hơn 24 giờ" in body and "DW1 không gửi thư cho GM" in body


@pytest.mark.parametrize("ends", ["gm_price", "back_to_mass"])
async def test_the_reminder_stops_once_the_price_is_recorded_or_the_case_is_mass(
    ends: str,
) -> None:
    world = _world()
    case_id, marked = await _m10_marked_pcs(world)
    commands = world.services.quote_commands
    version = world.quote(case_id).case_version
    if ends == "gm_price":
        await commands.pcs_price(
            DIEU.context(),
            case_id,
            case_version=version,
            lines=[
                PcsPriceLine(line_no=n, unit_price=Decimal("12.40"))
                for n in sorted(world.quote(case_id).request.document.line_numbers())
            ],
        )
    else:
        await commands.production_type(DIEU.context(), case_id, case_version=version, kind="mass")

    assert (await _tick(world, marked + 99 * HOUR)).of(Followup.WAITING_PCS_PRICE) == []


def test_the_wait_starts_when_the_case_was_marked() -> None:
    """Marked again later (mass, then pcs), the wait is timed from the last mark."""
    later = T0 + 10 * HOUR
    case = replace(_quote(), pcs_price_asked_at=later)
    assert _waits(case, T0 + 24 * HOUR) == []
    assert _waits(case, later + 24 * HOUR) == [(later, ("pic",))]
