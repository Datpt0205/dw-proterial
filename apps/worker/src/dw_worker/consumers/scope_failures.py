"""A lane that visits many scopes says so once all of them were visited.

Each per-workspace loop catches one scope's failure so the other scopes still
get their tick. Swallowed for good, though, the lane's tick reads as clean,
and the worker's lane health (`dw_lane_last_ok_timestamp_seconds`, Sales
ticket 84) would call a lane healthy whose every tick fails in one workspace.
So the loop counts what it caught and calls `raise_if_failed` after the last
scope: the others were served, and `run_worker`'s loop logs the raise and
records no clean tick.

A lane that hands out a batch of items (the Zalo lanes' updates) has the same
shape: one item's failure must not drop the rest, and must not read as clean.
It says `what` failed, so the log names the right thing.
"""

from __future__ import annotations


class ScopesFailedError(Exception):
    """Raised after a lane visited every scope (or item) and at least one failed."""

    def __init__(self, lane: str, failed: int, what: str = "scope") -> None:
        super().__init__(f"{lane}: {failed} {what}(s) failed this tick")
        self.lane = lane
        self.failed = failed


def raise_if_failed(lane: str, failed: int, what: str = "scope") -> None:
    if failed:
        raise ScopesFailedError(lane, failed, what)
