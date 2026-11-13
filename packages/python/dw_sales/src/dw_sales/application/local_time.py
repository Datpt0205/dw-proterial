"""Which calendar day it is where the tenant works (audit 14).

The tenant's time zone has one owner, `working_hours.time_zone` in its
`sales_followups` policy, read through `LocalZonePort` (`TenantRuleBook.time_zone`).
The function here takes the zone as an argument, so nothing in it holds one.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from dw_sales.application.ports import SalesScope


class LocalZonePort(Protocol):
    """The time zone a scope's tenant counts its days in."""

    async def time_zone(self, scope: SalesScope) -> ZoneInfo: ...


def local_day(at: datetime, zone: ZoneInfo) -> date:
    """The calendar day ``at`` falls on in ``zone``."""
    return at.astimezone(zone).date()
