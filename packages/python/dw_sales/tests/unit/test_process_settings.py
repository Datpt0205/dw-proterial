"""The process page's data (2026-10-22, slice 1): the graph is the domain's,
and every rule field has a home.

The graph is read from its owners, so these tests hold the served view to
them: every status a node, every move an edge, every step on a node or listed
as stateless. The placement is new data, so these tests hold it to the
schemas: every placed path exists, every leaf of every overridable schema is
placed or left out with a reason, and a locked field is served locked.
"""

from __future__ import annotations

import itertools
import uuid
from collections.abc import Iterator, Mapping
from typing import Any

import pytest

from dw_kernel.errors import ConflictError, PermissionDeniedError
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_sales.application.access import Gate, SalesScopes
from dw_sales.application.overview_service import PROCEDURE_KIND
from dw_sales.application.process_settings import (
    BASELINE_ONLY,
    LANE_SETTINGS,
    LOCKED,
    NOT_ON_PAGE,
    PROCESS_SETTINGS,
    STEP_SETTINGS,
    LockReason,
    Placement,
    ProcessSettingsService,
    ProcessSettingsView,
    lock,
    within,
)
from dw_sales.application.rules import OVERRIDABLE, PRICE_BEARING, RuleKey
from dw_sales.domain import orders, quotes
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.process import WIV_STEPS, Coverage, StepId
from dw_sales.evals.graders import AN, READER
from dw_sales.evals.world import Caller

pytestmark = pytest.mark.unit

# Tenant IT (`sales_rules_editor`): proposes rules, reads no price.
IT = Caller(
    uuid.UUID(int=0x7A),
    "Ngô Minh Tâm",
    "tam.ngo@alpha.local",
    frozenset({"platform.members.write", SalesScopes.RULES_PROPOSE}),
)
_SERVICE = ProcessSettingsService(Gate(ScopeAuthorizationService()))


async def _view(caller: Caller = AN) -> ProcessSettingsView:
    return await _SERVICE.view(caller.context())


def _placed() -> list[Placement]:
    """Every placement: on a step, on a lane, on the whole process."""
    return [
        *(p for placed in STEP_SETTINGS.values() for p in placed),
        *(p for placed in LANE_SETTINGS.values() for p in placed),
        *PROCESS_SETTINGS,
    ]


# ------------------------------------------------------------- the graph --

_DOMAIN: Mapping[CaseKind, tuple[Any, Any, Any]] = {
    CaseKind.ORDER: (orders.OrderStatus, orders.order_moves(), orders.transition),
    CaseKind.QUOTE: (quotes.QuoteStatus, quotes.quote_moves(), quotes.transition),
}


async def test_every_status_is_a_node_in_the_enums_order() -> None:
    lanes = {lane.kind: lane for lane in (await _view()).lanes}
    assert set(lanes) == set(CaseKind)
    for kind, (enum, _, _) in _DOMAIN.items():
        assert [node.status for node in lanes[kind].nodes] == [s.value for s in enum]


async def test_the_edges_are_the_moves_the_domain_allows_less_staying_put() -> None:
    """Read against `transition`, the function that refuses a move, not only
    against the table the view was built from: the accessor is the table the
    domain enforces."""
    lanes = {lane.kind: lane for lane in (await _view()).lanes}
    for kind, (enum, moves, transition) in _DOMAIN.items():
        served = {(edge.source, edge.to) for edge in lanes[kind].edges}
        allowed = set()
        for source, target in itertools.product(enum, enum):
            try:
                transition(source, target)
            except ConflictError:
                continue
            if source is not target:
                allowed.add((source.value, target.value))
        assert served == allowed
        assert served == {(s.value, t.value) for s, ts in moves.items() for t in ts if s is not t}
        assert len(served) >= 10  # the lane was read, not an empty table


async def test_an_edge_is_served_as_from_and_to() -> None:
    lane = (await _view()).lanes[0]
    dumped = lane.model_dump(mode="json")
    assert set(dumped["edges"][0]) == {"from", "to"}


def test_the_move_tables_are_read_only() -> None:
    for moves in (orders.order_moves(), quotes.quote_moves()):
        with pytest.raises(TypeError):
            moves[next(iter(moves))] = frozenset()  # type: ignore[index]


async def test_every_step_is_on_a_node_or_listed_as_stateless_exactly_once() -> None:
    """Fails when a step is added to `WIV_STEPS` and the graph leaves it out."""
    view = await _view()
    for lane in view.lanes:
        on_nodes = {step for node in lane.nodes for step in node.steps}
        assert on_nodes.isdisjoint(lane.stateless_steps)
        expected = {s.step_id for s in WIV_STEPS if PROCEDURE_KIND[s.procedure] is lane.kind}
        assert on_nodes | set(lane.stateless_steps) == expected
    assert {s for lane in view.lanes for s in lane.stateless_steps} == {
        "O4",
        "O5",
        "O11",
        "Q8",
        "Q12",
    }


async def test_a_done_status_waits_on_nobody() -> None:
    nodes = {(lane.kind, n.status): n for lane in (await _view()).lanes for n in lane.nodes}
    assert nodes[(CaseKind.ORDER, "confirmed")].holder is None
    assert nodes[(CaseKind.QUOTE, "pending_approval")].holder == "approver"


# ------------------------------------------------------ the placement map --


def test_the_map_is_keyed_by_every_step() -> None:
    assert set(STEP_SETTINGS) == set(StepId)
    assert [s.step_id for s in WIV_STEPS] == [s.value for s in StepId]


def test_each_covered_step_names_its_fields_or_says_why_it_has_none() -> None:
    for step in WIV_STEPS:
        step_id = StepId(step.step_id)
        baseline = Placement(RuleKey.KPI, f"manual_baseline_minutes.{step.step_id}")
        own = [p for p in STEP_SETTINGS[step_id] if p != baseline]
        assert baseline in STEP_SETTINGS[step_id], step_id
        if step.coverage is Coverage.OUT:
            assert not own and step_id not in BASELINE_ONLY, step_id
        else:
            assert bool(own) != (step_id in BASELINE_ONLY), step_id


def _resolved(node: dict[str, Any], defs: Mapping[str, Any]) -> dict[str, Any]:
    while "$ref" in node:
        node = defs[node["$ref"].rsplit("/", 1)[-1]]
    if "anyOf" in node:
        present = [n for n in node["anyOf"] if n.get("type") != "null"]
        if len(present) == 1:
            return _resolved(present[0], defs)
    return node


def _paths(key: RuleKey) -> Iterator[tuple[str, bool]]:
    """Every path in ``key``'s schema, and whether it is a leaf: an object's
    fields are walked, a closed-key map's entries by key; an open map, a
    list or a value is a leaf."""
    schema = OVERRIDABLE[key].model_json_schema(by_alias=True)
    defs = schema.get("$defs", {})

    def walk(node: dict[str, Any], prefix: str) -> Iterator[tuple[str, bool]]:
        node = _resolved(node, defs)
        if node.get("type") == "object" and "properties" in node:
            if prefix:
                yield prefix, False
            for name, child in node["properties"].items():
                yield from walk(child, f"{prefix}.{name}" if prefix else name)
            return
        names = node.get("propertyNames")
        closed = _resolved(names, defs).get("enum") if names else None
        if node.get("type") == "object" and closed:
            yield prefix, False
            for entry in closed:
                yield f"{prefix}.{entry}", True
            return
        yield prefix, True

    yield from walk(schema, "")


_SCHEMA_PATHS = {key: dict(_paths(key)) for key in RuleKey}


def test_the_schema_walk_sees_closed_maps_and_nested_fields() -> None:
    """The walk the next tests trust can see what they check (failure-modes #0)."""
    order = _SCHEMA_PATHS[RuleKey.ORDER_RULES]
    assert order["findings.price_mismatch"] and order["model_assist.message_intent"]
    assert not order["findings"] and not order["intake"]
    assert _SCHEMA_PATHS[RuleKey.KPI]["manual_baseline_minutes.Q12"]
    assert _SCHEMA_PATHS[RuleKey.PRICING]["copper_adders"]  # a list is one leaf
    assert sum(len(paths) for paths in _SCHEMA_PATHS.values()) > 100


def test_every_placed_path_is_in_its_keys_schema() -> None:
    for placement in (*_placed(), *LOCKED, *NOT_ON_PAGE):
        assert placement.path in _SCHEMA_PATHS[placement.key], placement


def test_every_leaf_of_every_schema_is_placed_or_left_out_with_a_reason() -> None:
    """A field added to a rule fails here until someone decides where the
    page shows it, or that it does not."""
    placed, left_out = _placed(), list(NOT_ON_PAGE)
    for key, paths in _SCHEMA_PATHS.items():
        for path, leaf in paths.items():
            if not leaf:
                continue
            shown = [p for p in placed if p.key is key and within(path, p.path)]
            omitted = [p for p in left_out if p.key is key and within(path, p.path)]
            assert shown or omitted, f"{key.value}: {path} has no home"
            assert not (shown and omitted), f"{key.value}: {path} is both shown and left out"
    assert all(reason for reason in NOT_ON_PAGE.values())


def test_a_lock_is_placed_as_itself_or_inside_and_never_under_a_wider_placement() -> None:
    """A placement holding a locked field inside it would be served unlocked
    and hide the lock: the lock is placed as itself or as finer paths."""
    for held in LOCKED:
        assert any(p.key is held.key and within(p.path, held.path) for p in _placed()), held
        wider = [
            p
            for p in _placed()
            if p.key is held.key and p.path != held.path and within(held.path, p.path)
        ]
        assert wider == [], held


async def test_the_locked_paths_are_served_with_their_reason_and_nothing_else_is() -> None:
    view = await _view()
    served = [
        *(s for step in view.steps for s in step.settings),
        *(s for settings in view.lane_settings.values() for s in settings),
        *view.process_settings,
    ]
    reasons = {(s.key, s.path): s.lock for s in served if s.lock is not None}
    model = LockReason.MODEL_BAR_UNCHECKED
    assert reasons == {
        (RuleKey.ORDER_RULES, "intake"): LockReason.BOUND_AT_BUILD,
        (RuleKey.ORDER_RULES, "model_assist.message_intent"): model,
        (RuleKey.ORDER_RULES, "model_assist.unread_retry_hours"): model,
        (RuleKey.ORDER_RULES, "model_assist.reply_intent"): model,
        (RuleKey.ORDER_RULES, "model_assist.request_handoff"): model,
        (RuleKey.ORDER_RULES, "model_assist.description_attributes"): model,
        (RuleKey.ORDER_RULES, "model_assist.layout_proposal"): model,
        (RuleKey.ORDER_RULES, "model_assist.rfq_extraction"): model,
        (RuleKey.QUOTE_RULES, "design_mailboxes"): LockReason.TRUST,
        (RuleKey.FOLLOWUPS, "working_hours.time_zone"): LockReason.TWO_OWNERS,
    }
    locked = set(reasons)
    # Every field under `model_assist` is placed, so every one is served locked.
    assert {
        path
        for path, leaf in _SCHEMA_PATHS[RuleKey.ORDER_RULES].items()
        if leaf and within(path, "model_assist")
    } == {path for key, path in locked if within(path, "model_assist")}
    assert lock(Placement(RuleKey.ORDER_RULES, "cross_check_required")) is None


# ---------------------------------------------------------- who reads it --


async def test_a_caller_without_the_propose_scope_is_refused() -> None:
    with pytest.raises(PermissionDeniedError):
        await _view(READER)


async def test_a_caller_without_price_read_is_served_no_price_bearing_key() -> None:
    """Absent, not empty: the steps are all there, and no setting of a key
    holding prices; the dump names none of them."""
    hidden = await _view(IT)
    dumped = hidden.model_dump_json()
    for key in PRICE_BEARING:
        assert key.value not in dumped, key
    for path in ("price.relative_tolerance", "floor_margin", "copper_adders", "findings."):
        assert path not in dumped, path
    assert [s.step_id for s in hidden.steps] == [s.value for s in StepId]
    # The search can fail: a PIC, who reads prices, is served all three.
    shown = (await _view(AN)).model_dump_json()
    assert all(key.value in shown for key in PRICE_BEARING)
    assert "price.relative_tolerance" in shown
