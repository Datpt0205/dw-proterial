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

Per step, three more facts, each read from its owner (2026-10-23):

- **models**: the model steps the step's placed `model_assist.<step>` fields
  name, each with the tenant's switch, the bar (`model_readiness.BARS`), the
  latest measurement for the model and prompt it runs on now, whether it is
  in effect (on AND passing), and its live share over the last 7 days (what
  the step handled in this workspace and how much of it DW1 carried,
  `activity_ports.automatic_share_last_7_days`). Read-only; absent with the
  key that holds the switches, for a caller who may not read it, and the
  share with it: it is not read at all for that caller.
- **uses**: the master-data lists and whether PO layouts are read by the step
  (`STEP_USES`, declared here: no other owner says it; held total by a test).
- **actors**: the roles and permission sets whose scopes perform or approve
  the step's actions (`STEP_SCOPES`), read from the platform's catalog
  (`RoleCatalogPort`), never a list of role names typed here.

Each edge carries its action, who takes it and what guards it (`EDGES`),
checked against the domain's move tables by a test, so a move added to the
domain fails until it says what it is.

A price-bearing key (`rules.PRICE_BEARING`) is absent, not empty, for a caller
without `sales.price.read`, as the rules list leaves it out (`rules.readable`).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from dw_kernel.ports import UtcClock
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.activity_ports import (
    WEEK,
    StepActivityReadPort,
    automatic_share_last_7_days,
)
from dw_sales.application.model_readiness import BARS, ModelReadiness
from dw_sales.application.order_ports import OrderRulesPort
from dw_sales.application.overview_ports import Bucket
from dw_sales.application.overview_service import PROCEDURE_KIND, STATUS_BUCKETS
from dw_sales.application.pipeline import CASE_STATUSES, steps_at
from dw_sales.application.rules import RuleKey, readable
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.master_data import CatalogList
from dw_sales.domain.order_checks import ModelStep
from dw_sales.domain.orders import OrderStatus, order_moves
from dw_sales.domain.process import WIV_STEPS, Coverage, StepId
from dw_sales.domain.quotes import QuoteStatus, quote_moves

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
            # Receive the PO: which senders' mail is taken at all, intake
            # caps, the model steps reading a message, and what the intake
            # raises.
            _step(
                StepId.O1,
                _in(
                    _ORDER,
                    "ignored_sender_domains",
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
            # Enter the PO: a new layout's first POs and a PO written in the
            # mail, read value by value.
            _step(
                StepId.O3,
                _in(
                    _ORDER,
                    "layout_onboarding.uncertain_first_pos",
                    "model_assist.layout_proposal",
                    "model_assist.po_body_extraction",
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


@dataclass(frozen=True, slots=True)
class Uses:
    """What a step reads besides its rules: master-data lists, PO layouts."""

    lists: frozenset[CatalogList] = frozenset()
    layouts: bool = False


_L = CatalogList

# What each surveyed step reads, keyed by every `StepId` (2026-10-23, read
# from the code that does each step): no other owner says it, so it is
# declared here beside the fields, and a test holds it total. A list written
# but not read (the master list Q11 records) is not one the step uses.
STEP_USES: Final[Mapping[StepId, Uses]] = MappingProxyType(
    {
        # The sender's customer, and the PO read with the customer's layout.
        StepId.O1: Uses(frozenset({_L.CUSTOMERS}), layouts=True),
        StepId.O2: Uses(frozenset({_L.CONVERT_LIST, _L.ITEMS})),
        # A new layout's first POs, read value by value.
        StepId.O3: Uses(layouts=True),
        # The item's standard lead time, else the quotation's.
        StepId.O4: Uses(frozenset({_L.ITEMS, _L.QUOTATIONS})),
        StepId.O5: Uses(),
        StepId.O6: Uses(frozenset({_L.ITEMS, _L.QUOTATIONS, _L.LME})),
        StepId.O7: Uses(),
        StepId.O8: Uses(),
        StepId.O9: Uses(),
        StepId.O10: Uses(),
        StepId.O11: Uses(),
        StepId.Q1: Uses(frozenset({_L.CUSTOMERS, _L.ITEMS, _L.CONVERT_LIST})),
        StepId.Q2: Uses(frozenset({_L.CUSTOMERS, _L.ITEMS, _L.CONVERT_LIST})),
        StepId.Q3: Uses(),
        StepId.Q4: Uses(),
        StepId.Q5: Uses(),
        StepId.Q6: Uses(),
        StepId.Q7: Uses(frozenset({_L.QUOTATIONS, _L.LME})),
        StepId.Q8: Uses(frozenset({_L.CUSTOMERS})),
        StepId.Q9: Uses(),
        StepId.Q10: Uses(),
        StepId.Q11: Uses(),
        StepId.Q12: Uses(frozenset({_L.QUOTATIONS})),
    }
)

_S = SalesScopes

# The scopes that perform or approve each step's actions, keyed by every
# `StepId`; who holds them is the platform's catalog (`RoleCatalogPort`). An
# OUT step (another worker's) has none here.
STEP_SCOPES: Final[Mapping[StepId, frozenset[SalesScopes]]] = MappingProxyType(
    {
        StepId.O1: frozenset({_S.INBOX_PROCESS}),
        StepId.O2: frozenset({_S.ORDER_PREPARE}),
        StepId.O3: frozenset({_S.ORDER_PREPARE, _S.LAYOUT_APPROVE}),
        StepId.O4: frozenset({_S.ORDER_PREPARE}),
        StepId.O5: frozenset(),
        StepId.O6: frozenset({_S.ORDER_PREPARE}),
        StepId.O7: frozenset({_S.ORDER_PREPARE}),
        StepId.O8: frozenset({_S.ORDER_PREPARE}),
        StepId.O9: frozenset({_S.ORDER_CROSS_CHECK}),
        StepId.O10: frozenset({_S.ORDER_PREPARE, _S.COMPLIANCE_ACK}),
        StepId.O11: frozenset(),
        StepId.Q1: frozenset({_S.INBOX_PROCESS, _S.QUOTE_PREPARE}),
        StepId.Q2: frozenset({_S.QUOTE_PREPARE}),
        StepId.Q3: frozenset({_S.QUOTE_PREPARE}),
        StepId.Q4: frozenset({_S.QUOTE_PREPARE}),
        StepId.Q5: frozenset({_S.QUOTE_PREPARE}),
        StepId.Q6: frozenset({_S.QUOTE_PREPARE}),
        StepId.Q7: frozenset({_S.QUOTE_PREPARE}),
        StepId.Q8: frozenset({_S.QUOTE_PREPARE}),
        StepId.Q9: frozenset({_S.QUOTE_PREPARE, _S.QUOTE_APPROVE}),
        StepId.Q10: frozenset({_S.QUOTE_PREPARE}),
        StepId.Q11: frozenset({_S.QUOTE_PREPARE}),
        # The screening report is read, not acted on.
        StepId.Q12: frozenset({_S.CASE_READ}),
    }
)


class EdgeAction(StrEnum):
    """What makes a case move: the domain method that moves it."""

    CHECK = "check"
    CLOSE = "close"
    START_REVIEW = "start_review"
    PREPARE = "prepare"
    REQUEST_CORRECTION = "request_correction"
    # The customer's next revision of the PO joins the case.
    REVISE = "revise"
    RESUME_REVIEW = "resume_review"
    RECORD_BRAVO_ENTRY = "record_bravo_entry"
    # A change to a prepared case reopens its self-check.
    EDIT = "edit"
    CROSS_CHECK = "cross_check"
    # The checker or the approver sends the case back.
    RETURN = "return"
    CONFIRM = "confirm"
    APPLY_CHANGE = "apply_change"
    DRAFT_YCBG = "draft_ycbg"
    RECORD_YCBG = "record_ycbg"
    SEND_TO_DESIGN = "send_to_design"
    RECORD_DESIGN_REPLY = "record_design_reply"
    DISCUSS_SPEC = "discuss_spec"
    SETTLE_SPEC = "settle_spec"
    # Sales decides the price, the first time or again.
    PRICE = "price"
    SUBMIT = "submit"
    APPROVE = "approve"
    SEND = "send"
    RECORD_MASTER_LIST = "record_master_list"
    DECLINE = "decline"


class EdgeGuard(StrEnum):
    """What the domain refuses a move without."""

    # No open finding but `missing_noc_esf`, none sent back to the customer,
    # every line mapped (an order); each blocking price finding accepted with
    # a reason (a quotation's approval).
    BLOCKING_FINDINGS = "blocking_findings"
    # A finding is sent back to the customer.
    ASK_CUSTOMER = "ask_customer"
    # The PIC states the Bravo entry was compared with the PO.
    ENTRY_COMPARED = "entry_compared"
    # Decided on a platform approval (strict: a second person, a comment).
    APPROVAL = "approval"
    # Nobody who made the case decides it.
    MAKER_CHECKER = "maker_checker"
    # Straight to confirmed only when the rules stamped on the case need no
    # cross-check.
    CROSS_CHECK_NOT_REQUIRED = "cross_check_not_required"
    # `missing_noc_esf` acknowledged, and absent under `block_confirmation`.
    EXPORT_CONTROL_HOLD = "export_control_hold"
    # A short lead time has a date production control confirmed.
    PC_CONFIRMED_DATE = "pc_confirmed_date"
    # The request's own findings are answered.
    REQUEST_FINDINGS = "request_findings"


@dataclass(frozen=True, slots=True)
class Edge:
    action: EdgeAction
    # Who takes it: Sales in the portal, DW1, or someone outside whose message
    # DW1 processes (the customer, Design).
    actor: Bucket
    guards: tuple[EdgeGuard, ...] = ()


_A, _G, _O, _Q = EdgeAction, EdgeGuard, OrderStatus, QuoteStatus


def _edge(action: EdgeAction, actor: Bucket, *guards: EdgeGuard) -> Edge:
    return Edge(action, actor, guards)


_DECLINE = _edge(_A.DECLINE, "sales")
_PRICE = _edge(_A.PRICE, "sales")

_ORDER_EDGES: Final[Mapping[tuple[OrderStatus, OrderStatus], Edge]] = {
    (_O.RECEIVED, _O.CHECKED): _edge(_A.CHECK, "dw"),
    (_O.RECEIVED, _O.CLOSED): _edge(_A.CLOSE, "sales"),
    (_O.CHECKED, _O.IN_REVIEW): _edge(_A.START_REVIEW, "sales"),
    (_O.CHECKED, _O.CLOSED): _edge(_A.CLOSE, "sales"),
    (_O.IN_REVIEW, _O.PREPARED): _edge(_A.PREPARE, "sales", _G.BLOCKING_FINDINGS),
    (_O.IN_REVIEW, _O.CORRECTION_REQUESTED): _edge(_A.REQUEST_CORRECTION, "sales", _G.ASK_CUSTOMER),
    (_O.IN_REVIEW, _O.CHECKED): _edge(_A.REVISE, "customer"),
    (_O.IN_REVIEW, _O.CLOSED): _edge(_A.CLOSE, "sales"),
    (_O.CORRECTION_REQUESTED, _O.CHECKED): _edge(_A.REVISE, "customer"),
    (_O.CORRECTION_REQUESTED, _O.IN_REVIEW): _edge(_A.RESUME_REVIEW, "sales"),
    (_O.CORRECTION_REQUESTED, _O.CLOSED): _edge(_A.CLOSE, "sales"),
    (_O.PREPARED, _O.UPLOADED_TO_BRAVO): _edge(_A.RECORD_BRAVO_ENTRY, "sales", _G.ENTRY_COMPARED),
    (_O.PREPARED, _O.IN_REVIEW): _edge(_A.EDIT, "sales"),
    (_O.PREPARED, _O.CHECKED): _edge(_A.REVISE, "customer"),
    (_O.PREPARED, _O.CLOSED): _edge(_A.CLOSE, "sales"),
    (_O.UPLOADED_TO_BRAVO, _O.CROSS_CHECKED): _edge(
        _A.CROSS_CHECK, "sales", _G.APPROVAL, _G.MAKER_CHECKER
    ),
    (_O.UPLOADED_TO_BRAVO, _O.CONFIRMED): _edge(
        _A.CONFIRM,
        "sales",
        _G.CROSS_CHECK_NOT_REQUIRED,
        _G.EXPORT_CONTROL_HOLD,
        _G.PC_CONFIRMED_DATE,
    ),
    (_O.UPLOADED_TO_BRAVO, _O.IN_REVIEW): _edge(_A.RETURN, "sales", _G.APPROVAL, _G.MAKER_CHECKER),
    (_O.UPLOADED_TO_BRAVO, _O.CHANGE_REVIEW): _edge(_A.REVISE, "customer"),
    (_O.CROSS_CHECKED, _O.CONFIRMED): _edge(
        _A.CONFIRM, "sales", _G.EXPORT_CONTROL_HOLD, _G.PC_CONFIRMED_DATE
    ),
    (_O.CROSS_CHECKED, _O.CHANGE_REVIEW): _edge(_A.REVISE, "customer"),
    (_O.CONFIRMED, _O.CHANGE_REVIEW): _edge(_A.REVISE, "customer"),
    (_O.CHANGE_REVIEW, _O.UPLOADED_TO_BRAVO): _edge(
        _A.APPLY_CHANGE, "sales", _G.BLOCKING_FINDINGS, _G.ENTRY_COMPARED
    ),
}
_QUOTE_EDGES: Final[Mapping[tuple[QuoteStatus, QuoteStatus], Edge]] = {
    (_Q.RECEIVED, _Q.YCBG_DRAFTED): _edge(_A.DRAFT_YCBG, "sales", _G.REQUEST_FINDINGS),
    (_Q.RECEIVED, _Q.DECLINED): _DECLINE,
    (_Q.YCBG_DRAFTED, _Q.YCBG_RECORDED): _edge(_A.RECORD_YCBG, "sales"),
    (_Q.YCBG_DRAFTED, _Q.DECLINED): _DECLINE,
    (_Q.YCBG_RECORDED, _Q.SENT_TO_DESIGN): _edge(_A.SEND_TO_DESIGN, "sales"),
    (_Q.YCBG_RECORDED, _Q.DECLINED): _DECLINE,
    (_Q.SENT_TO_DESIGN, _Q.DESIGN_REPLIED): _edge(_A.RECORD_DESIGN_REPLY, "design"),
    (_Q.SENT_TO_DESIGN, _Q.DECLINED): _DECLINE,
    (_Q.DESIGN_REPLIED, _Q.SPEC_DISCUSSION): _edge(_A.DISCUSS_SPEC, "sales"),
    (_Q.DESIGN_REPLIED, _Q.PRICED): _PRICE,
    (_Q.DESIGN_REPLIED, _Q.DECLINED): _DECLINE,
    (_Q.SPEC_DISCUSSION, _Q.DESIGN_REPLIED): _edge(_A.SETTLE_SPEC, "sales"),
    (_Q.SPEC_DISCUSSION, _Q.SENT_TO_DESIGN): _edge(_A.SEND_TO_DESIGN, "sales"),
    (_Q.SPEC_DISCUSSION, _Q.DECLINED): _DECLINE,
    (_Q.PRICED, _Q.PENDING_APPROVAL): _edge(_A.SUBMIT, "sales"),
    (_Q.PRICED, _Q.DECLINED): _DECLINE,
    (_Q.PENDING_APPROVAL, _Q.APPROVED): _edge(
        _A.APPROVE, "approver", _G.APPROVAL, _G.MAKER_CHECKER, _G.BLOCKING_FINDINGS
    ),
    (_Q.PENDING_APPROVAL, _Q.RETURNED): _edge(_A.RETURN, "approver", _G.APPROVAL, _G.MAKER_CHECKER),
    (_Q.PENDING_APPROVAL, _Q.PRICED): _PRICE,
    (_Q.PENDING_APPROVAL, _Q.DECLINED): _DECLINE,
    (_Q.RETURNED, _Q.PRICED): _PRICE,
    (_Q.RETURNED, _Q.DECLINED): _DECLINE,
    (_Q.APPROVED, _Q.SENT): _edge(_A.SEND, "sales"),
    (_Q.APPROVED, _Q.PRICED): _PRICE,
    (_Q.APPROVED, _Q.DECLINED): _DECLINE,
    (_Q.SENT, _Q.MASTER_LIST_RECORDED): _edge(_A.RECORD_MASTER_LIST, "sales"),
}

# Every move each lane's domain allows, less staying put, with what it is,
# by status value. `test_process_settings.py` holds each to its domain's move
# table (`order_moves`, `quote_moves`), so neither changes without the other.
EDGES: Final[Mapping[CaseKind, Mapping[tuple[str, str], Edge]]] = MappingProxyType(
    {
        kind: MappingProxyType({(s.value, t.value): edge for (s, t), edge in table.items()})
        for kind, table in (
            (CaseKind.ORDER, _ORDER_EDGES),
            (CaseKind.QUOTE, _QUOTE_EDGES),
        )
    }
)


def model_steps(step: StepId) -> tuple[ModelStep, ...]:
    """The model steps a process step takes part in: the `model_assist`
    switches placed on it (`STEP_SETTINGS`), so the two cannot disagree."""
    prefix = "model_assist."
    names = {s.value for s in ModelStep}
    return tuple(
        ModelStep(p.path.removeprefix(prefix))
        for p in STEP_SETTINGS[step]
        if p.key is RuleKey.ORDER_RULES
        and p.path.startswith(prefix)
        and p.path.removeprefix(prefix) in names
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
    "your_turn",
)


class LockReason(StrEnum):
    """Why the page shows a field without editing it: served with the field,
    worded by the web (`rule-labels.ts`, keyed by these values, so a reason
    added here fails its typecheck until it has words)."""

    # Model steps: a version that turns one on is refused unless its live eval
    # met the bar (ADR 0005, addendum of 2026-10-23). Proposed on /sales/rules;
    # each step's measurement is served beside it (`ProcessStepView.models`).
    MODEL_BAR = "model_bar"
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
        Placement(_ORDER, "model_assist"): LockReason.MODEL_BAR,
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
    action: EdgeAction
    # Who takes the move.
    actor: Bucket
    guards: list[EdgeGuard]


class ProcessLaneView(BaseModel):
    model_config = _VIEW

    kind: CaseKind
    nodes: list[ProcessNodeView]
    edges: list[ProcessEdgeView]
    # The lane's steps no status stands for (a suggestion, a document, DW2's).
    stateless_steps: list[str]


class MeasurementView(BaseModel):
    model_config = _VIEW

    value: float
    passed: bool
    model: str
    prompt: str
    measured_at: datetime


class LiveShareView(BaseModel):
    """What the step handled in the workspace over the last ``window_days``
    days, and how much of it DW1 carried (`StepTally`)."""

    model_config = _VIEW

    handled: int
    automatic: int
    # Automatic over handled; None when the step handled nothing.
    share: float | None
    # `activity_ports.WEEK`, in days.
    window_days: int


class StepModelView(BaseModel):
    """One model step of a process step, read-only."""

    model_config = _VIEW

    step: ModelStep
    # The tenant's switch, in its order rules in force.
    enabled: bool
    bar: float
    metric: str
    # The model and the prompt the step runs on now; model None: unresolved.
    model: str | None
    prompt: str
    # The newest measurement on that model and prompt; None: never measured.
    latest: MeasurementView | None
    # Enabled AND that measurement passes at today's bar: the model is used.
    effective: bool
    live_share: LiveShareView


class UsesView(BaseModel):
    model_config = _VIEW

    lists: list[CatalogList]
    layouts: bool


class ActorView(BaseModel):
    """A role or a permission set holding scopes the step's actions need."""

    model_config = _VIEW

    kind: Literal["role", "permission_set"]
    key: str
    name: str
    # The step's scopes it holds.
    scopes: list[str]


class ProcessStepView(BaseModel):
    model_config = _VIEW

    step_id: str
    coverage: Coverage
    settings: list[SettingView]
    # Empty for a caller who may not read the order rules, which hold the switches.
    models: list[StepModelView]
    uses: UsesView
    actors: list[ActorView]


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
            _edge_view(kind, source.value, target.value)
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


def _edge_view(kind: CaseKind, source: str, target: str) -> ProcessEdgeView:
    edge = EDGES[kind][(source, target)]
    return ProcessEdgeView(
        source=source, to=target, action=edge.action, actor=edge.actor, guards=list(edge.guards)
    )


class CatalogEntry(Protocol):
    """A role or a permission set as the platform's catalog holds it."""

    @property
    def key(self) -> str: ...

    @property
    def name(self) -> str: ...

    @property
    def scopes(self) -> tuple[str, ...]: ...


class RoleCatalogPort(Protocol):
    """The platform's role and permission-set catalog (`platform.roles`,
    `platform.permission_sets`), read as its admin console reads it: the
    composition root hands in the platform's own repository."""

    async def list_roles(self) -> Sequence[CatalogEntry]: ...

    async def list_permission_sets(self) -> Sequence[CatalogEntry]: ...


def _actors(
    scopes: frozenset[SalesScopes],
    roles: Sequence[CatalogEntry],
    sets: Sequence[CatalogEntry],
) -> list[ActorView]:
    """The roles, then the permission sets, holding any of ``scopes``."""
    wanted = {scope.value for scope in scopes}
    found: list[ActorView] = []
    for kind, entries in (("role", roles), ("permission_set", sets)):
        found.extend(
            ActorView(
                kind="role" if kind == "role" else "permission_set",
                key=entry.key,
                name=entry.name,
                scopes=held,
            )
            for entry in entries
            if (held := sorted(wanted & set(entry.scopes)))
        )
    return found


@dataclass(frozen=True)
class ProcessSettingsService:
    """The process page's one read, to whoever may propose a rule version."""

    gate: Gate
    # The tenant's order rules in force: where its model switches are.
    rules: OrderRulesPort
    readiness: ModelReadiness
    roles: RoleCatalogPort
    # What the model steps did, for each one's share over the last week.
    activity: StepActivityReadPort
    clock: UtcClock

    async def view(self, context: AccessContext) -> ProcessSettingsView:
        await self.gate.require(context, SalesScopes.RULES_PROPOSE, resource_type=_RESOURCE)

        def shown(placed: tuple[Placement, ...]) -> list[SettingView]:
            return [
                SettingView(key=p.key, path=p.path, lock=lock(p))
                for p in placed
                if readable(self.gate, context, p.key)
            ]

        roles = await self.roles.list_roles()
        sets = await self.roles.list_permission_sets()
        models = await self._models(context)
        steps: list[ProcessStepView] = []
        for step in WIV_STEPS:
            step_id = StepId(step.step_id)
            uses = STEP_USES[step_id]
            steps.append(
                ProcessStepView(
                    step_id=step.step_id,
                    coverage=step.coverage,
                    settings=shown(STEP_SETTINGS[step_id]),
                    models=[models[m] for m in model_steps(step_id) if m in models],
                    uses=UsesView(lists=sorted(uses.lists), layouts=uses.layouts),
                    actors=_actors(STEP_SCOPES[step_id], roles, sets),
                )
            )
        return ProcessSettingsView(
            lanes=[_lane(kind) for kind in CASE_STATUSES],
            steps=steps,
            lane_settings={kind: shown(placed) for kind, placed in LANE_SETTINGS.items()},
            process_settings=shown(PROCESS_SETTINGS),
        )

    async def _models(self, context: AccessContext) -> dict[ModelStep, StepModelView]:
        """Every model step as the tenant has it now; none for a caller who
        may not read the order rules, which hold the switches."""
        if not readable(self.gate, context, RuleKey.ORDER_RULES):
            return {}
        scope = sales_scope(context)
        rules = await self.rules.rules(scope)
        shares = await automatic_share_last_7_days(self.activity, scope, now=self.clock.now())
        found: dict[ModelStep, StepModelView] = {}
        for step in ModelStep:
            share = shares[step]
            readiness = await self.readiness.check(scope, step)
            latest = readiness.latest
            enabled = rules.model_assist.on(step)
            found[step] = StepModelView(
                step=step,
                enabled=enabled,
                bar=readiness.bar,
                metric=BARS[step].metric,
                model=readiness.model,
                prompt=readiness.prompt,
                latest=None
                if latest is None
                else MeasurementView(
                    value=latest.value,
                    passed=latest.passed,
                    model=latest.model,
                    prompt=latest.prompt,
                    measured_at=latest.measured_at,
                ),
                effective=enabled and readiness.ready,
                live_share=LiveShareView(
                    handled=share.handled,
                    automatic=share.automatic,
                    share=share.share,
                    window_days=WEEK.days,
                ),
            )
        return found
