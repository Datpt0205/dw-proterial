"""A line split over several delivery dates, read the way both readers read it (ticket 21).

A PO prints a split line in one of two shapes the readers know: rows under the
line, each with a quantity and a date and nothing else (Excel); or a list in
the line's date cell, ``16/11/2026: 3.050; 30/11/2026: 3.050`` (Excel and
PDF). Each reader reads a date and a number its own way; what a list entry is,
and how the schedules become the line's, is said once here.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from datetime import date
from decimal import Decimal

from dw_sales.domain.anchors import SourceAnchor
from dw_sales.domain.orders import DeliverySchedule

# Entries apart by ";" or a line break, each "date: quantity".
_ENTRIES = re.compile(r"[;\n]")
_ENTRY = re.compile(r"\s*(?P<day>[^:]+?)\s*:\s*(?P<quantity>[^:]+?)\s*")


def listed_schedules(
    text: str,
    anchor: SourceAnchor,
    day: Callable[[str], date],
    number: Callable[[str], Decimal],
) -> tuple[DeliverySchedule, ...] | None:
    """The schedules a "date: quantity" list in one cell prints, each with
    the cell's anchor; None when the text is no such list (it has no colon).

    Raises ValueError naming what was expected, never the text, when it is a
    list and an entry is not a date and a quantity.
    """
    if ":" not in text:
        return None
    schedules: list[DeliverySchedule] = []
    for entry in (e for e in _ENTRIES.split(text) if e.strip()):
        match = _ENTRY.fullmatch(entry)
        if match is None:
            raise ValueError("is not a list of 'date: quantity'")
        try:
            schedules.append(
                DeliverySchedule(
                    quantity=number(match["quantity"]),
                    requested_date=day(match["day"]),
                    anchor=anchor,
                )
            )
        except ValueError as exc:
            raise ValueError("is not a list of 'date: quantity'") from exc
    return tuple(schedules)


def in_date_order(schedules: Sequence[DeliverySchedule]) -> tuple[DeliverySchedule, ...]:
    """Earliest first, as a line holds them; two on one date keep their order."""
    return tuple(sorted(schedules, key=lambda s: s.requested_date))
