"""DW2's morning brief (DW02 function 6's other half, Đạt 2026-11-04: a
few counts each working morning, so nobody has to know what to ask).

Once per working day, from the tenant's time in the plant's day, each
person is told the counts of what waits on them, and only them:

- the buyers (`purchasing.rfq.prepare`, `purchasing.po.prepare`): requests
  approved and not yet asked of suppliers, being asked, with suppliers
  chosen and no order yet, orders still followed, and late lines;
- whoever looks over what DW2 read (`purchasing.request.intake`): the cases
  DW2 opened that wait for that look;
- each approver: the requests sent to the scope stamped on them
  (`ApprovalAsked.required_scope`), so a tier is told its own.

Counts only: never an amount, a supplier or a requester (a notification is
a side door, ui-quality §6). A person with nothing waiting is told nothing.
The time and the days are the tenant's rules (`PurchasingRules.brief`); a
version written before them reads the platform's (`read_over`).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Annotated, Final, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from dw_purchasing.domain.cases import CaseStatus, PurchaseCase

Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_WEEK: Final[tuple[Weekday, ...]] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
# The plant's day: the brief's time and its days are read in it.
PLANT: Final = ZoneInfo("Asia/Ho_Chi_Minh")


class BriefRules(BaseModel):
    """When the brief is sent: a time (HH:MM, the plant's) and the days."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    at: Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
    days: frozenset[Weekday] = Field(min_length=1)


def brief_day(rules: BriefRules, now: datetime) -> date | None:
    """Today's brief, if it is due at ``now``: a working day at the plant
    and its time has come. Late is still today's (a worker that was down
    sends it when it is back); tomorrow it is tomorrow's."""
    local = now.astimezone(PLANT)
    if _WEEK[local.weekday()] not in rules.days:
        return None
    hour, minute = (int(part) for part in rules.at.split(":"))
    return local.date() if local.time() >= time(hour, minute) else None


@dataclass(frozen=True, slots=True)
class Brief:
    """One audience's brief: who, by scope, and the counts in words."""

    audience: str
    scopes: frozenset[str]
    parts: tuple[str, ...]


# The buyer's states, in the order a case moves through them.
_BUYER: Final = (
    (CaseStatus.APPROVED, "cần soạn hỏi giá"),
    (CaseStatus.RFQ_DRAFTED, "đang hỏi giá"),
    (CaseStatus.SUPPLIER_SELECTED, "cần soạn PO"),
    (CaseStatus.PO_DRAFTED, "đơn đang theo dõi"),
)


def briefs(cases: Sequence[PurchaseCase], *, late: int) -> list[Brief]:
    """The briefs for one workspace's open ``cases`` and its ``late`` lines,
    each with something in it."""
    status = Counter(case.status for case in cases)
    buyer = [f"{status[s]} {words}" for s, words in _BUYER if status[s]]
    if late:
        buyer.append(f"{late} dòng hàng trễ hạn")
    found = []
    if buyer:
        found.append(
            Brief(
                "buyer",
                frozenset({"purchasing.rfq.prepare", "purchasing.po.prepare"}),
                tuple(buyer),
            )
        )
    review = sum(
        1
        for case in cases
        if case.status is CaseStatus.RECEIVED and case.review is not None and case.review.pending
    )
    if review:
        found.append(
            Brief(
                "review",
                frozenset({"purchasing.request.intake"}),
                (f"{review} yêu cầu DW2 đọc chờ xem lại",),
            )
        )
    asked: Counter[str] = Counter()
    for case in cases:
        if case.status is CaseStatus.AWAITING_APPROVAL and case.approval is not None:
            asked[case.approval.required_scope] += 1
        elif case.status is CaseStatus.AWAITING_REAPPROVAL and case.reapproval is not None:
            asked[case.reapproval.approval.required_scope] += 1
    for scope, count in sorted(asked.items()):
        found.append(
            Brief(f"approve:{scope}", frozenset({scope}), (f"{count} yêu cầu chờ bạn duyệt",))
        )
    return found
