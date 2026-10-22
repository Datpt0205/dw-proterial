"""The DW1 process as its configuration page draws it (2026-10-22, slice 1):
each lane's statuses and the moves between them, each surveyed step with the
rule fields it reads, and the fields that belong to a lane or to the whole
process.

Nothing about the process is copied here:

- **Nodes** are the status enums, in their order (`pipeline.CASE_STATUSES`),
  each with the steps a case is at in it (`pipeline.steps_at`, from
  `WIV_STEPS`) and whose turn it is (`STATUS_BUCKETS`; none means done).
- **Edges** are the domain's own move tables (`orders.order_moves`,
  `quotes.quote_moves`); a status moving to itself is left out.
- **Steps with no status** (O4, O5, O11, Q8, Q12) are listed per lane, not
  hung on an invented node.

What is new, and owned here, is the placement: which step reads which field
(`STEP_SETTINGS`, keyed by every `StepId`), the lane-wide and process-wide
groups, the fields this page shows but does not edit (`LOCKED`, each with a
`LockReason` the page words), and the fields it leaves out on purpose
(`NOT_ON_PAGE`). A placement names a key and a
path in the key's schema, never a value: the page reads values, and proposes
a whole version, through the rules routes it already has. Locking is
presentation only; a locked field is still proposed and approved on
`/sales/rules`, where the head's approval remains the authority.

A path is a document path, dot-separated; an entry of a map whose keys are a
closed set is named by its key (``findings.price_mismatch``,
``manual_baseline_minutes.O6``). A path names its whole subtree. `test_process
_settings.py` holds every placement to the key's schema, and every leaf of
every schema to a placement or to `NOT_ON_PAGE`, so a field added to a rule
fails until someone decides where it is shown.

A price-bearing key (`rules.PRICE_BEARING`) is absent, not empty, for a caller
without `sales.price.read`, as the rules list leaves it out (`rules.readable`).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes
from dw_sales.application.overview_ports import Bucket
from dw_sales.application.overview_service import PROCEDURE_KIND, STATUS_BUCKETS
from dw_sales.application.pipeline import CASE_STATUSES, steps_at
from dw_sales.application.rules import RuleKey, readable
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import order_moves
from dw_sales.domain.process import WIV_STEPS, Coverage, StepId
from dw_sales.domain.quotes import quote_moves

_VIEW = ConfigDict(frozen=True)
_RESOURCE: Final = "sales_rules_process"

# Each lane's moves, read from the domain's own tables.
_MOVES: Final[Mapping[CaseKind, Callable[[], Mapping[Any, frozenset[Any]]]]] = MappingProxyType(
    {CaseKind.ORDER: order_moves, CaseKind.QUOTE: quote_moves}
)


@dataclass(frozen=True, slots=True)
class Placement:
    """One field of one key's documents, shown where it is placed."""

    key: RuleKey
    path: str


_ORDER, _KPI, _QUOTE, _PRICING, _FOLLOWUPS = (
    RuleKey.ORDER_RULES,
    RuleKey.KPI,
    RuleKey.QUOTE_RULES,
    RuleKey.PRICING,
    RuleKey.FOLLOWUPS,
)


def _in(key: RuleKey, *paths: str) -> tuple[Placement, ...]:
    return tuple(Placement(key, path) for path in paths)


def _severities(*codes: str) -> tuple[Placement, ...]:
    """The severity of each order finding code, on the step that raises it."""
    return _in(_ORDER, *(f"findings.{code}" for code in codes))


def _step(step: StepId, *placed: tuple[Placement, ...]) -> tuple[StepId, tuple[Placement, ...]]:
    """A step's fields, ending with its own manual baseline in the KPI
    policy (the minutes the step took by hand, keyed by `StepId`)."""
    own = Placement(_KPI, f"manual_baseline_minutes.{step.value}")
    return step, (*(p for group in placed for p in group), own)


# Which fields each surveyed step reads, keyed by every `StepId` (the tunables
# inventory of 2026-10-22). O5 and O11 are outside this slice (DW2) and carry
# only their baseline; every other step names what it reads, or says in
# `BASELINE_ONLY` why it reads nothing more.
STEP_SETTINGS: Final[Mapping[StepId, tuple[Placement, ...]]] = MappingProxyType(
    dict(
        (
            # Receive the PO: intake caps, the model steps reading a message,
            # and what the intake raises.
            _step(
                StepId.O1,
                _in(
                    _ORDER,
                    "intake",
                    "model_assist.message_intent",
                    "model_assist.unread_retry_hours",
                    "model_assist.reply_intent",
                    "model_assist.request_handoff",
                ),
                _severities(
                    "duplicate_po",
                    "revised_po",
                    "revision_without_base",
                    "customer_unknown",
                    "customer_temporary",
                    "sender_unverified",
                    "legacy_encoding",
                ),
            ),
            # The PRV code from the convert list.
            _step(
                StepId.O2,
                _in(_ORDER, "model_assist.description_attributes"),
                _severities("code_unmapped", "code_ambiguous"),
            ),
            # Enter the PO: a new layout's first POs, read value by value.
            _step(
                StepId.O3,
                _in(
                    _ORDER, "layout_onboarding.uncertain_first_pos", "model_assist.layout_proposal"
                ),
                _severities("value_uncertain", "line_total_mismatch"),
            ),
            # The delivery date DW1 suggests.
            _step(
                StepId.O4,
                _in(_ORDER, "short_lead_time"),
                _severities("requested_date_short_lt", "requested_date_missing"),
            ),
            _step(StepId.O5),
            # The check against the quotation.
            _step(
                StepId.O6,
                _in(_ORDER, "price.relative_tolerance", "lme_band.months_before_po_date"),
                _severities(
                    "quotation_missing",
                    "price_mismatch",
                    "currency_mismatch",
                    "uom_mismatch",
                    "lme_band_mismatch",
                    "moq_violation",
                    "pack_multiple",
                ),
            ),
            _step(StepId.O7),
            # Asking the customer to correct, and how long DW1 waits on them.
            _step(StepId.O8, _in(_FOLLOWUPS, "waiting_customer")),
            # Whether a second person cross-checks the Bravo entry.
            _step(StepId.O9, _in(_ORDER, "cross_check_required")),
            # Confirmation and the export-control hold.
            _step(
                StepId.O10,
                _in(
                    _ORDER,
                    "export_control_mode",
                    "export_control.denial_list_max_age_days",
                    "fiscal_year_start_month",
                ),
                _severities("missing_noc_esf"),
            ),
            _step(StepId.O11),
            # Reading the RFQ (a quote step whose switch lives in the order rules).
            _step(StepId.Q1, _in(_ORDER, "model_assist.rfq_extraction")),
            _step(StepId.Q2),
            # The request to Design: whose mail counts as Design's, and how long
            # DW1 waits for the reply.
            _step(
                StepId.Q3,
                _in(_QUOTE, "design_mailboxes"),
                _in(_FOLLOWUPS, "quote_waiting_design"),
            ),
            _step(StepId.Q4),
            _step(StepId.Q5),
            _step(StepId.Q6, _in(_FOLLOWUPS, "waiting_customer")),
            # The price and its evidence.
            _step(
                StepId.Q7,
                _in(
                    _QUOTE,
                    "reference_price.band_below_percent",
                    "reference_price.band_above_percent",
                    "copper_basis",
                ),
                _in(_PRICING, "copper_adders", "floor_margin", "freight"),
            ),
            _step(StepId.Q8),
            # Approval: how long the approved quotation is valid.
            _step(StepId.Q9, _in(_QUOTE, "validity_days")),
            _step(StepId.Q10),
            _step(StepId.Q11),
            _step(StepId.Q12),
        )
    )
)

# Surveyed steps this slice covers that read no rule field besides their
# baseline, with why: a step added later fails the test until it names its
# fields or says here why it has none. An OUT step (O5, O11) needs no reason.
BASELINE_ONLY: Final[Mapping[StepId, str]] = MappingProxyType(
    {
        StepId.O7: "the self-check reads O3's and O6's findings; the upload file is copy",
        StepId.Q2: "the YCBG draft is copy (slice 2)",
        StepId.Q4: "Design's reply is mock data; how long DW1 waits for it is Q3's",
        StepId.Q5: "declining reads the decline copy (slice 2) and fixed reasons",
        StepId.Q8: "the quotation document is copy (slice 2); its validity is Q9's",
        StepId.Q10: "sending reads the send copy (slice 2)",
        StepId.Q11: "the master-list row is written on mock data",
        StepId.Q12: "screening runs on mock data; its 12-month window is code (slice 3)",
    }
)

# Fields that govern a whole lane: its follow-up and its KPI target.
LANE_SETTINGS: Final[Mapping[CaseKind, tuple[Placement, ...]]] = MappingProxyType(
    {
        CaseKind.ORDER: (
            *_in(_FOLLOWUPS, "order_unconfirmed"),
            *_in(_KPI, "order_confirmation_target_hours"),
        ),
        CaseKind.QUOTE: (
            *_in(_FOLLOWUPS, "quote_deadline"),
            *_in(_KPI, "quotation_target_days"),
        ),
    }
)

# Fields that govern the whole process. Working hours field by field: a
# placement never holds a locked field inside it, so the lock is served.
PROCESS_SETTINGS: Final[tuple[Placement, ...]] = _in(
    _FOLLOWUPS,
    "working_hours.time_zone",
    "working_hours.days",
    "working_hours.start",
    "working_hours.end",
    "morning_brief",
)


class LockReason(StrEnum):
    """Why the page shows a field without editing it: served with the field,
    worded by the web (`rule-labels.ts`, keyed by these values, so a reason
    added here fails its typecheck until it has words)."""

    # Model steps: ADR 0005 turns one on once its live eval meets the bar, and
    # no code checks that bar (sales_order_rules@1.6.0).
    MODEL_BAR_UNCHECKED = "model_bar_unchecked"
    # The readers bind the platform file's intake caps when they are built
    # (adapters/assembly.py), so a tenant's version may not reach them.
    BOUND_AT_BUILD = "bound_at_build"
    # Trust configuration: whose mail is Design's.
    TRUST = "trust"
    # Two owners: the received date and the files fix Asia/Ho_Chi_Minh
    # (domain/order_checks.py SALES_TIME_ZONE).
    TWO_OWNERS = "two_owners"


# Shown, not edited here, with why. Each names its subtree, and is placed as
# itself or inside a placement of its own (`test_process_settings.py`).
LOCKED: Final[Mapping[Placement, LockReason]] = MappingProxyType(
    {
        Placement(_ORDER, "model_assist"): LockReason.MODEL_BAR_UNCHECKED,
        Placement(_ORDER, "intake"): LockReason.BOUND_AT_BUILD,
        Placement(_QUOTE, "design_mailboxes"): LockReason.TRUST,
        Placement(_FOLLOWUPS, "working_hours.time_zone"): LockReason.TWO_OWNERS,
    }
)

_VERSION = "the version's own fields: the editor asks for them with every proposal"
_COPY = "copy and templates: placed on steps in slice 2, edited on /sales/rules"

# Fields of an overridable key this page leaves out on purpose, with why.
NOT_ON_PAGE: Final[Mapping[Placement, str]] = MappingProxyType(
    {
        **{
            Placement(key, path): _VERSION
            for key in (_ORDER, _KPI, _QUOTE, _PRICING, _FOLLOWUPS)
            for path in ("schema_version", "policy_id", "policy_version")
        },
        **{
            Placement(RuleKey.BRAVO_UPLOAD, path): _VERSION
            for path in ("schema_version", "policy_id", "policy_version", "mock", "description")
        },
        **{
            Placement(key, path): _VERSION
            for key in (RuleKey.EMAILS, RuleKey.DOCUMENTS)
            for path in ("schema_version", "copy_id", "version", "mock", "description")
        },
        **{
            Placement(RuleKey.HANDOFFS, path): _VERSION
            for path in ("schema_version", "copy_id", "version")
        },
        Placement(RuleKey.EMAILS, "sender"): _COPY,
        Placement(RuleKey.EMAILS, "emails"): _COPY,
        Placement(RuleKey.DOCUMENTS, "documents"): _COPY,
        Placement(RuleKey.BRAVO_UPLOAD, "sheet_name"): _COPY,
        Placement(RuleKey.BRAVO_UPLOAD, "columns"): _COPY,
        Placement(RuleKey.HANDOFFS, "unknown"): _COPY,
        Placement(RuleKey.HANDOFFS, "line"): _COPY,
        Placement(RuleKey.HANDOFFS, "quote"): _COPY,
        Placement(RuleKey.HANDOFFS, "templates"): _COPY,
    }
)


def within(path: str, subtree: str) -> bool:
    """Whether ``path`` is ``subtree`` or lies under it."""
    return path == subtree or path.startswith(f"{subtree}.")


def lock(placement: Placement) -> LockReason | None:
    """Why a field under a `LOCKED` subtree of its key is not edited here;
    None for a field the page edits."""
    return next(
        (
            reason
            for locked, reason in LOCKED.items()
            if locked.key is placement.key and within(placement.path, locked.path)
        ),
        None,
    )


# ------------------------------------------------------------------ views --


class SettingView(BaseModel):
    model_config = _VIEW

    key: RuleKey
    path: str
    # Why it is shown and not edited on this page; None: the page edits it.
    lock: LockReason | None


class ProcessNodeView(BaseModel):
    model_config = _VIEW

    status: str
    steps: list[str]
    # Whose turn a case in this status is; None: it waits on nobody (done).
    holder: Bucket | None


class ProcessEdgeView(BaseModel):
    model_config = ConfigDict(frozen=True, validate_by_name=True, serialize_by_alias=True)

    source: str = Field(alias="from")
    to: str


class ProcessLaneView(BaseModel):
    model_config = _VIEW

    kind: CaseKind
    nodes: list[ProcessNodeView]
    edges: list[ProcessEdgeView]
    # The lane's steps no status stands for (a suggestion, a document, DW2's).
    stateless_steps: list[str]


class ProcessStepView(BaseModel):
    model_config = _VIEW

    step_id: str
    coverage: Coverage
    settings: list[SettingView]


class ProcessSettingsView(BaseModel):
    model_config = _VIEW

    lanes: list[ProcessLaneView]
    steps: list[ProcessStepView]
    lane_settings: dict[CaseKind, list[SettingView]]
    process_settings: list[SettingView]


def _lane(kind: CaseKind) -> ProcessLaneView:
    statuses = list(CASE_STATUSES[kind])
    moves = _MOVES[kind]()
    return ProcessLaneView(
        kind=kind,
        nodes=[
            ProcessNodeView(
                status=status.value,
                steps=steps_at(kind, status.value),
                holder=STATUS_BUCKETS[kind].get(status.value),
            )
            for status in statuses
        ],
        edges=[
            ProcessEdgeView(source=source.value, to=target.value)
            for source in statuses
            for target in statuses
            if target is not source and target in moves[source]
        ],
        stateless_steps=[
            step.step_id
            for step in WIV_STEPS
            if PROCEDURE_KIND[step.procedure] is kind and not step.states
        ],
    )


@dataclass(frozen=True)
class ProcessSettingsService:
    """The process page's one read, to whoever may propose a rule version."""

    gate: Gate

    async def view(self, context: AccessContext) -> ProcessSettingsView:
        await self.gate.require(context, SalesScopes.RULES_PROPOSE, resource_type=_RESOURCE)

        def shown(placed: tuple[Placement, ...]) -> list[SettingView]:
            return [
                SettingView(key=p.key, path=p.path, lock=lock(p))
                for p in placed
                if readable(self.gate, context, p.key)
            ]

        return ProcessSettingsView(
            lanes=[_lane(kind) for kind in CASE_STATUSES],
            steps=[
                ProcessStepView(
                    step_id=step.step_id,
                    coverage=step.coverage,
                    settings=shown(STEP_SETTINGS[StepId(step.step_id)]),
                )
                for step in WIV_STEPS
            ],
            lane_settings={kind: shown(placed) for kind, placed in LANE_SETTINGS.items()},
            process_settings=shown(PROCESS_SETTINGS),
        )
