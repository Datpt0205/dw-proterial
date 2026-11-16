"""The platform's follow-up policy and its words, and `LocalZonePort`
answering its zone, for tests and evals with no rule book.

Read through `load_sales_policies`, the one place that names which version
DW1 runs, so a test's zone and its "due soon" have one owner too:
`working_hours.time_zone` and `morning_brief.due_within_days`.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo

from dw_sales.application.ports import SalesScope
from dw_sales.application.reminder_copy import ReminderCopy
from dw_sales.domain.followups import SalesFollowups

_CONFIGS: Final = Path(__file__).resolve().parents[6] / "configs"


@dataclass(frozen=True, slots=True)
class FixedZone:
    """Implements `LocalZonePort` with one zone for every scope."""

    zone: ZoneInfo

    async def time_zone(self, scope: SalesScope) -> ZoneInfo:
        return self.zone


@cache
def platform_followups() -> SalesFollowups:
    """The follow-up policy the platform ships."""
    from dw_sales.adapters.policy_files import load_sales_policies

    return load_sales_policies(_CONFIGS / "policies", _CONFIGS / "copy").followups


@cache
def platform_reminder_copy() -> ReminderCopy:
    """The words of the follow-ups the platform ships (ticket 42 family 6)."""
    from dw_sales.adapters.policy_files import load_sales_policies

    return load_sales_policies(_CONFIGS / "policies", _CONFIGS / "copy").reminders


def platform_zone() -> FixedZone:
    """The zone the platform's follow-up policy ships."""
    return FixedZone(platform_followups().working_hours.zone)
