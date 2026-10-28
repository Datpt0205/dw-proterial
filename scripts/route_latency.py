"""p50/p95/p99 per API route, from the API's `request_timing` log lines.

    docker compose ... logs --no-log-prefix api | uv run python scripts/route_latency.py
    make latency-report            # the same, on the compose stack

Reads whatever traffic the log holds: an e2e run, a person clicking through
the demo, or a week at the customer's. Slowest p95 first, so the route to
look at is on top. `--min-count` leaves out routes seen too few times for a
percentile to mean anything; they are counted in the footer, not hidden.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from collections import defaultdict

LINE = re.compile(r"request_timing (\w+) (\S+) (\d{3}) ([\d.]+)ms")


def percentile(sorted_ms: list[float], p: float) -> float:
    """Nearest rank: the smallest value at or above p percent of the sample."""
    rank = max(1, math.ceil(p / 100 * len(sorted_ms)))
    return sorted_ms[rank - 1]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--min-count", type=int, default=3)
    args = ap.parse_args()

    samples: dict[tuple[str, str], list[float]] = defaultdict(list)
    errors: dict[tuple[str, str], int] = defaultdict(int)
    for line in sys.stdin:
        m = LINE.search(line)
        if not m:
            continue
        key = (m.group(1), m.group(2))
        samples[key].append(float(m.group(4)))
        if m.group(3).startswith("5"):
            errors[key] += 1
    if not samples:
        sys.exit("no request_timing lines on stdin")

    rows = []
    few = 0
    for key, ms in samples.items():
        if len(ms) < args.min_count:
            few += 1
            continue
        ms.sort()
        rows.append(
            (
                percentile(ms, 95),
                key,
                len(ms),
                percentile(ms, 50),
                percentile(ms, 99),
                ms[-1],
                errors[key],
            )
        )
    rows.sort(reverse=True)
    print(f"{'p50':>8} {'p95':>8} {'p99':>8} {'max':>8} {'n':>5} {'5xx':>4}  route")
    for p95, (method, route), n, p50, p99, top, err in rows:
        print(f"{p50:8.0f} {p95:8.0f} {p99:8.0f} {top:8.0f} {n:5d} {err:4d}  {method} {route}")
    total = sum(len(ms) for ms in samples.values())
    shown = f"{len(rows)} routes shown (ms)"
    print(f"\n{total} requests, {shown}; {few} with fewer than {args.min_count}.")


if __name__ == "__main__":
    main()
