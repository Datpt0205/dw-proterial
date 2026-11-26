"""Every `dw_*` metric an alert rule reads is one some code emits (Sales
ticket 84; failure-modes #1).

A rule over a metric nobody writes evaluates to nothing and never fires, and
reads in review like a safeguard. Membership in `ALL_METRICS` is not enough:
that tuple is a declaration, and it holds names no code emits. So each name a
rule reads must be a constant of `dw_observability.metrics` that some source
file outside it hands to `add_metric` or `set_gauge`.

What this cannot see: a metric emitted under a literal string rather than its
constant, and whether the emitting line runs in a deployment at all. The
second is what `DwLaneStale` and the compose smoke are for.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from dw_observability import metrics

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
ALERTS = REPO / "infra" / "prometheus" / "alerts.yml"
_SUFFIXES = ("_bucket", "_sum", "_count")


def _names_rules_read() -> set[str]:
    rules = yaml.safe_load(ALERTS.read_text(encoding="utf-8"))
    names: set[str] = set()
    for group in rules["groups"]:
        for rule in group["rules"]:
            for name in re.findall(r"\bdw_[a-z0-9_]+", rule["expr"]):
                for suffix in _SUFFIXES:
                    name = name.removesuffix(suffix)
                names.add(name)
    return names


def _constants() -> dict[str, str]:
    return {
        value: key
        for key, value in vars(metrics).items()
        if key.startswith("DW_") and isinstance(value, str)
    }


def _sources() -> list[str]:
    roots = [*REPO.glob("apps/*/src"), *REPO.glob("packages/python/*/src")]
    own = Path(metrics.__file__).resolve()
    return [
        path.read_text(encoding="utf-8")
        for root in roots
        for path in root.rglob("*.py")
        if path.resolve() != own
    ]


def test_the_rules_read_some_dw_metric() -> None:
    """Guards the parse: a YAML shape change must not make the check vacuous."""
    assert {"dw_lane_last_ok_timestamp_seconds", "dw_outbox_backlog_size"} <= _names_rules_read()


def test_every_dw_metric_a_rule_reads_is_emitted_by_some_code() -> None:
    constants = _constants()
    sources = _sources()
    undeclared = sorted(n for n in _names_rules_read() if n not in constants)
    assert not undeclared, f"rules read metrics no constant names: {undeclared}"
    silent = sorted(
        name
        for name in _names_rules_read()
        if not any(
            re.search(rf"\b(?:add_metric|set_gauge)\(\s*{constants[name]}\b", text)
            for text in sources
        )
    )
    assert not silent, f"rules read metrics nothing emits: {silent}"
