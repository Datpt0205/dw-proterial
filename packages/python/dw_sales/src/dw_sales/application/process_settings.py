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

Ticket 35 (2026-11-16) adds three facts, each read from its owner:

- **The BA's step codes** on each status and each step of a flow beside the
  statuses (`process.BA_STEPS`, the one owner of the code and its words).
- **The flows beside the statuses** (`SUBFLOWS`): the talk before the PO
  (ticket 24), the wait on PC before the order is in Bravo (07), a change the
  customer asks by mail (27) and the update loop on an order in Bravo (29),
  each step with the statuses a case is in meanwhile and, for the loop, its
  moves, all read from the domain (`orders.update_loop_moves`, ...).
- **The head's short list** (`HEAD_SETTINGS`): the few settings a Sales head
  changes, each with one plain sentence; every other placement is the
  admin's, under "Nâng cao" (`audience`, which fails closed). Grouping only:
  what a field means, who may propose it and who approves it are unchanged.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Final, Literal, Protocol, get_args

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
from dw_sales.domain.orders import (
    CONFIRMATION_LEFT,
    OrderStatus,
    UpdateStep,
    changeable_statuses,
    design_wait_statuses,
    order_moves,
    quote_wait_statuses,
    update_loop_moves,
    update_loop_statuses,
)
from dw_sales.domain.process import BA_STEPS, WIV_STEPS, BaStep, Coverage, Procedure, StepId
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
            # Receive the PO: intake caps, the mail domains no customer is
            # known by, the marks of a revised file's name, the model steps
            # reading a message, and what the intake raises.
            _step(
                StepId.O1,
                _in(
                    _ORDER,
                    "intake",
                    "shared_mail_domains",
                    "revision_marks",
                    "model_assist.message_intent",
                    "model_assist.unread_retry_hours",
                    "model_assist.reply_intent",
                    "model_assist.thread_agent",
                    "model_assist.skill_intents",
                    "model_assist.skill_pick_confidence",
                    "model_assist.skill_mail_kinds",
                    "model_assist.triage_card",
                    "model_assist.request_handoff",
                    "model_assist.skill_handoffs",
                    "model_assist.change_request",
                ),
                _severities(
                    "duplicate_po",
                    "revised_po",
                    "revision_without_base",
                    "customer_unknown",
                    "customer_temporary",
                    "sender_unverified",
                    "legacy_encoding",
                    "delivery_term_mismatch",
                ),
            ),
            # The PRV code from the convert list, and how long DW1 waits on
            # Design's new code before reminding the PIC (ticket 06).
            _step(
                StepId.O2,
                _in(
                    _ORDER,
                    "model_assist.description_attributes",
                    "model_assist.shadow",
                    "model_assist.shadow_calls_per_hour",
                ),
                _severities("code_unmapped", "code_ambiguous"),
                _in(_FOLLOWUPS, "waiting_design_code"),
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
                _severities("value_uncertain", "line_total_mismatch", "files_disagree"),
            ),
            # The delivery date DW1 suggests, and how long DW1 waits on PC's
            # answer before reminding the PIC (ticket 07); the model reading
            # PC's own change of a confirmed order (ticket 10); the mailboxes PC
            # answers from (2026-11-23).
            _step(
                StepId.O4,
                _in(_ORDER, "short_lead_time", "model_assist.internal_change", "pc_mailboxes"),
                _severities("requested_date_short_lt", "requested_date_missing"),
                _in(_FOLLOWUPS, "waiting_pc"),
            ),
            _step(StepId.O5),
            # The check against the quotation, and how long an order waits on
            # a quote opened from it before DW1 reminds the PIC (ticket 09).
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
                    "reel_length_mismatch",
                    "spec_mismatch",
                ),
                _in(_FOLLOWUPS, "waiting_quote"),
            ),
            # The upload file: filled by the customer's SalesOrder skill where
            # that step is on and meets its bar, by the learned rules
            # otherwise (ticket 41).
            _step(StepId.O7, _in(_ORDER, "model_assist.salesorder_skill")),
            # Asking the customer to correct, and how long DW1 waits on them.
            # The case chat stating a flag's decision for the PIC to
            # confirm (tickets 56 and 57).
            _step(
                StepId.O8,
                _in(_ORDER, "model_assist.case_chat"),
                _in(_FOLLOWUPS, "waiting_customer"),
            ),
            # Whether a second person cross-checks the Bravo entry.
            _step(StepId.O9, _in(_ORDER, "cross_check_required")),
            # Confirmation and the export-control hold; then each customer's
            # days of silence that count as agreement, and telling the PIC
            # when they pass (ticket 28); the model's wording of the mails to
            # the customer beside the template's drafts (ticket 32).
            _step(
                StepId.O10,
                _in(
                    _ORDER,
                    "export_control_mode",
                    "export_control.denial_list_max_age_days",
                    "fiscal_year_start_month",
                    "implied_acceptance",
                    "model_assist.reply_draft",
                    "model_assist.skill_reply_drafts",
                ),
                _severities("missing_noc_esf"),
                _in(_FOLLOWUPS, "implied_acceptance"),
            ),
            _step(StepId.O11),
            # Reading the RFQ (a quote step whose switch lives in the order rules).
            _step(
                StepId.Q1,
                _in(_ORDER, "model_assist.rfq_extraction", "model_assist.skill_document_forms"),
            ),
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
            # The price and its evidence, and how long a pcs case waits on
            # the GM's price before DW1 reminds the PIC (ticket 05).
            _step(
                StepId.Q7,
                _in(
                    _QUOTE,
                    "reference_price.band_below_percent",
                    "reference_price.band_above_percent",
                    "copper_basis",
                ),
                _in(_PRICING, "copper_adders", "floor_margin", "freight"),
                _in(_FOLLOWUPS, "waiting_pcs_price"),
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
    # A person records the customer's agreement to the confirmation, in
    # words or by silence past their days, or that they declined it (ticket 28).
    RECORD_AGREEMENT = "record_agreement"
    RECORD_DECLINE = "record_decline"
    # An agreement by silence taken back (ticket 82).
    UNDO_IMPLIED = "undo_implied"
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
    # Straight to the confirmation only when the rules stamped on the case
    # need no cross-check.
    CROSS_CHECK_NOT_REQUIRED = "cross_check_not_required"
    # `missing_noc_esf` acknowledged, and absent under `block_confirmation`.
    EXPORT_CONTROL_HOLD = "export_control_hold"
    # A short lead time has a date production control confirmed.
    PC_CONFIRMED_DATE = "pc_confirmed_date"
    # The request's own findings are answered.
    REQUEST_FINDINGS = "request_findings"
    # Agreement by silence only for a customer with days in the order rules,
    # once they have passed (ticket 28).
    IMPLIED_DAYS = "implied_days"


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
    (_O.UPLOADED_TO_BRAVO, _O.CONFIRMATION_SENT): _edge(
        _A.CONFIRM,
        "sales",
        _G.CROSS_CHECK_NOT_REQUIRED,
        _G.EXPORT_CONTROL_HOLD,
        _G.PC_CONFIRMED_DATE,
    ),
    (_O.UPLOADED_TO_BRAVO, _O.IN_REVIEW): _edge(_A.RETURN, "sales", _G.APPROVAL, _G.MAKER_CHECKER),
    (_O.UPLOADED_TO_BRAVO, _O.CHANGE_REVIEW): _edge(_A.REVISE, "customer"),
    (_O.CROSS_CHECKED, _O.CONFIRMATION_SENT): _edge(
        _A.CONFIRM, "sales", _G.EXPORT_CONTROL_HOLD, _G.PC_CONFIRMED_DATE
    ),
    (_O.CROSS_CHECKED, _O.CHANGE_REVIEW): _edge(_A.REVISE, "customer"),
    (_O.CONFIRMATION_SENT, _O.CONFIRMED): _edge(_A.RECORD_AGREEMENT, "sales", _G.IMPLIED_DAYS),
    # A revision there moves the same way (`revise`); the decline is the
    # move this status adds.
    (_O.CONFIRMATION_SENT, _O.CHANGE_REVIEW): _edge(_A.RECORD_DECLINE, "sales"),
    (_O.CONFIRMED, _O.CHANGE_REVIEW): _edge(_A.REVISE, "customer"),
    (_O.CONFIRMED, _O.CONFIRMATION_SENT): _edge(_A.UNDO_IMPLIED, "sales"),
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
    # What a push to a phone may show (ticket 48).
    "push",
) + _in(
    # How much error what applies itself may make, and the audit share
    # (ticket 44): every model step's, so the whole process's.
    _ORDER,
    "autonomy.applies_itself_error",
    "autonomy.hand_off_error",
    "autonomy.audit_share",
    # How the readings learn from decided lines (ticket 43): the examples a
    # reading is shown, and when a better prompt is tried; every reading's.
    "learning.examples_per_line",
    "learning.new_cases_to_retrain",
    # How long a customer's worked pairs are kept (ticket 41).
    "learning.salesorder_pairs_kept_days",
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
    # Two owners: every server reader takes the tenant's zone from this field
    # (audit 14), but the web shows every time in Asia/Ho_Chi_Minh
    # (`apps/web/lib/dates.ts`, ui-quality §8), so a zone changed here would
    # put the screens and the files on two clocks.
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
_BRAVO_WRITES = (
    "which Bravo writes DW1 performs: switched on per kind with its UAT proof on"
    " /sales/rules, never from a step of the process (ticket 63)"
)
_LEARNED = (
    "each customer's own rules: learned from a worked example on the customer's row of"
    " the master data and approved there, never edited on a page (ticket 38)"
)

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
            Placement(key, path): _VERSION
            for key in (RuleKey.HANDOFFS, RuleKey.REMINDERS, RuleKey.ASSISTANT)
            for path in ("schema_version", "copy_id", "version")
        },
        Placement(RuleKey.EMAILS, "sender"): _COPY,
        Placement(RuleKey.EMAILS, "emails"): _COPY,
        Placement(RuleKey.DOCUMENTS, "documents"): _COPY,
        Placement(RuleKey.BRAVO_UPLOAD, "sheet_name"): _COPY,
        Placement(RuleKey.BRAVO_UPLOAD, "banner"): _COPY,
        Placement(RuleKey.BRAVO_UPLOAD, "columns"): _COPY,
        Placement(RuleKey.HANDOFFS, "unknown"): _COPY,
        Placement(RuleKey.HANDOFFS, "line"): _COPY,
        Placement(RuleKey.HANDOFFS, "quote"): _COPY,
        Placement(RuleKey.HANDOFFS, "templates"): _COPY,
        Placement(RuleKey.HANDOFFS, "pc_request"): _COPY,
        Placement(RuleKey.HANDOFFS, "design_request"): _COPY,
        Placement(RuleKey.REMINDERS, "reminders"): _COPY,
        Placement(RuleKey.REMINDERS, "next_steps"): _COPY,
        Placement(RuleKey.REMINDERS, "brief"): _COPY,
        Placement(RuleKey.REMINDERS, "push"): _COPY,
        Placement(RuleKey.ASSISTANT, "words"): _COPY,
        **{
            Placement(RuleKey.SALESORDER_RULES, path): _VERSION
            for path in ("schema_version", "policy_id", "policy_version", "mock", "description")
        },
        Placement(RuleKey.SALESORDER_RULES, "customers"): _LEARNED,
        **{
            Placement(RuleKey.BRAVO_WRITES, path): _VERSION
            for path in ("schema_version", "policy_id", "policy_version")
        },
        Placement(RuleKey.BRAVO_WRITES, "kinds"): _BRAVO_WRITES,
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


class SubflowKey(StrEnum):
    """A flow beside a lane's statuses: a case waits or loops in it while its
    status stays where it is (ticket 35)."""

    # The customer's mails before the PO, read as its thread (ticket 24):
    # before any case exists.
    THREAD = "thread"
    # Sales asked PC for delivery dates before the order is in Bravo (07).
    PC_REQUEST = "pc_request"
    # A change the customer asked by mail, confirmed line by line (27).
    CHANGE_REQUEST = "change_request"
    # The update loop on an order whose confirmation has left (29).
    UPDATE = "update"
    # Sales asked Design for a new PRV code for a line (06).
    DESIGN_CODE = "design_code"
    # A quote case opened from the order, not yet approved or declined (09).
    QUOTE = "quote"


@dataclass(frozen=True, slots=True)
class Subflow:
    """A flow's steps in order, the statuses a case is in at each (none:
    before any case), and where each step may go next."""

    steps: tuple[str, ...]
    statuses: Mapping[str, frozenset[OrderStatus]]
    moves: Mapping[str, frozenset[str]]


_UPDATE_STEPS: Final[tuple[str, ...]] = get_args(UpdateStep)

# Each lane's flows beside its statuses, read from the domain: nothing about
# where a flow runs or how it moves is written here.
SUBFLOWS: Final[Mapping[CaseKind, Mapping[SubflowKey, Subflow]]] = MappingProxyType(
    {
        CaseKind.ORDER: MappingProxyType(
            {
                SubflowKey.THREAD: Subflow(
                    steps=("before_po",), statuses={"before_po": frozenset()}, moves={}
                ),
                SubflowKey.PC_REQUEST: Subflow(
                    steps=("waiting_pc",),
                    statuses={"waiting_pc": changeable_statuses()},
                    moves={},
                ),
                # Taken at once before the order is in Bravo; once its
                # confirmation has left, a confirmed line joins the update loop.
                SubflowKey.CHANGE_REQUEST: Subflow(
                    steps=("confirm_lines",),
                    statuses={"confirm_lines": changeable_statuses() | CONFIRMATION_LEFT},
                    moves={},
                ),
                SubflowKey.UPDATE: Subflow(
                    steps=_UPDATE_STEPS,
                    statuses=update_loop_statuses(),
                    moves=update_loop_moves(),
                ),
                SubflowKey.DESIGN_CODE: Subflow(
                    steps=("waiting_design",),
                    statuses={"waiting_design": design_wait_statuses()},
                    moves={},
                ),
                SubflowKey.QUOTE: Subflow(
                    steps=("waiting_quote",),
                    statuses={"waiting_quote": quote_wait_statuses()},
                    moves={},
                ),
            }
        ),
        CaseKind.QUOTE: MappingProxyType({}),
    }
)

# The procedure whose BA steps a lane draws.
_PROCEDURE: Final[Mapping[CaseKind, Procedure]] = MappingProxyType(
    {kind: procedure for procedure, kind in PROCEDURE_KIND.items()}
)


def ba_steps(kind: CaseKind, place: str) -> tuple[BaStep, ...]:
    """The BA's steps at ``place`` of ``kind``'s lane: a status, or
    ``<flow>.<step>``; none where the BA's flow has none."""
    return BA_STEPS[_PROCEDURE[kind]].get(place, ())


class Audience(StrEnum):
    """Who a setting is shown to first. Presentation only: who may propose or
    approve it is the rules' own (`sales.rules.propose`, the head's approval)."""

    # The Sales head's short list: on one screen, each with one sentence.
    HEAD = "head"
    # Everything else, under "Nâng cao": the admin's, or the platform's.
    ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class HeadSetting:
    """A setting on the head's short list, with the one plain sentence that
    says what it does."""

    placement: Placement
    sentence: str


# The head's short list for DW1 (ticket 35; Đạt, 11-13: "không được quá nhiều
# dẫn tới rối loạn"): numbers a head decides without reading a rule's schema,
# in the order the work meets them. Each is a field placed on the page (its
# step's, lane's or the process's) and edited there; none is locked. Why
# these and not the rest is in the ticket's "## Done".
HEAD_SETTINGS: Final[tuple[HeadSetting, ...]] = (
    HeadSetting(
        Placement(_ORDER, "price.relative_tolerance"),
        "Đơn giá trên PO được lệch bao nhiêu so với báo giá mà DW1 vẫn coi là khớp"
        " (0 là phải bằng đúng).",
    ),
    HeadSetting(
        Placement(_ORDER, "cross_check_required"),
        "Bật thì mỗi đơn đã nhập Bravo cần người thứ hai kiểm chéo trước khi gửi xác nhận"
        " cho khách.",
    ),
    HeadSetting(
        Placement(_FOLLOWUPS, "waiting_pc.remind.after_hours"),
        "PC chưa trả ngày giao sau bấy nhiêu giờ thì DW1 nhắc Sales phụ trách.",
    ),
    HeadSetting(
        Placement(_FOLLOWUPS, "waiting_customer.remind.after_hours"),
        "Khách chưa trả lời sau bấy nhiêu giờ thì DW1 nhắc Sales phụ trách.",
    ),
    HeadSetting(
        Placement(_FOLLOWUPS, "order_unconfirmed.remind.after_hours"),
        "PO chưa được xác nhận sau bấy nhiêu giờ thì DW1 nhắc Sales phụ trách.",
    ),
    HeadSetting(
        Placement(_FOLLOWUPS, "order_unconfirmed.escalate.after_hours"),
        "PO chưa được xác nhận sau bấy nhiêu giờ thì DW1 báo Trưởng bộ phận.",
    ),
    HeadSetting(
        Placement(_FOLLOWUPS, "quote_waiting_design.remind.after_hours"),
        "Design chưa trả lời yêu cầu báo giá sau bấy nhiêu giờ thì DW1 nhắc Sales phụ trách.",
    ),
    HeadSetting(
        Placement(_FOLLOWUPS, "quote_deadline.warn.hours_before_due"),
        "Còn bấy nhiêu giờ đến hạn báo giá thì DW1 báo Sales phụ trách.",
    ),
    HeadSetting(
        Placement(_QUOTE, "validity_days"),
        "Báo giá đã duyệt có hiệu lực bấy nhiêu ngày, tính cả ngày phát hành.",
    ),
    HeadSetting(
        Placement(_FOLLOWUPS, "morning_brief.at"),
        "Giờ DW1 gửi bản tin buổi sáng mỗi ngày làm việc.",
    ),
    # What applies itself (ticket 44): a tenant may only lower the two rates
    # and raise the share, as the rule's bounds hold.
    HeadSetting(
        Placement(_ORDER, "autonomy.applies_itself_error"),
        "DW1 chỉ tự làm việc đọc, phân loại, ghép mã khi đo được tỷ lệ sai không quá mức"
        " này (tối đa 0,05 là 5%).",
    ),
    HeadSetting(
        Placement(_ORDER, "autonomy.hand_off_error"),
        "DW1 chỉ tự chuyển việc cho PC, QA, Design khi đo được tỷ lệ sai không quá mức"
        " này (tối đa 0,02 là 2%).",
    ),
    HeadSetting(
        Placement(_ORDER, "autonomy.audit_share"),
        "Trong những việc DW1 tự làm, phần này được gửi người phụ trách kiểm lại mà không"
        " báo trước (ít nhất 0,03 là 3%).",
    ),
)
# One screen: a head reads the whole list without scrolling past it. Thirteen
# since ticket 44 added the three that bound what applies itself.
HEAD_SETTINGS_MAX: Final = 13


def audience(placement: Placement) -> Audience:
    """The head's for a field on their short list; the admin's for anything
    else, a field added later included, until someone puts it on the list."""
    if any(h.placement == placement for h in HEAD_SETTINGS):
        return Audience.HEAD
    return Audience.ADMIN


# ------------------------------------------------------------------ views --


class SettingView(BaseModel):
    model_config = _VIEW

    key: RuleKey
    path: str
    # Why it is shown and not edited on this page; None: the page edits it.
    lock: LockReason | None


class BaStepView(BaseModel):
    model_config = _VIEW

    code: str
    label: str


class ProcessNodeView(BaseModel):
    model_config = _VIEW

    status: str
    steps: list[str]
    # Whose turn a case in this status is; None: it waits on nobody (done).
    holder: Bucket | None
    # The BA's steps a case is at in this status; empty where the BA's flow has none.
    ba_steps: list[BaStepView]


class ProcessEdgeView(BaseModel):
    model_config = ConfigDict(frozen=True, validate_by_name=True, serialize_by_alias=True)

    source: str = Field(alias="from")
    to: str
    action: EdgeAction
    # Who takes the move.
    actor: Bucket
    guards: list[EdgeGuard]


class SubflowStepView(BaseModel):
    model_config = _VIEW

    step: str
    # The statuses a case is in at this step, in the lane's order; empty:
    # before any case exists.
    statuses: list[str]
    # The flow's steps it may go to next, in the flow's order; itself left out.
    next: list[str]
    ba_steps: list[BaStepView]


class ProcessSubflowView(BaseModel):
    model_config = _VIEW

    key: SubflowKey
    steps: list[SubflowStepView]


class ProcessLaneView(BaseModel):
    model_config = _VIEW

    kind: CaseKind
    nodes: list[ProcessNodeView]
    edges: list[ProcessEdgeView]
    # The lane's steps no status stands for (a suggestion, a document, DW2's).
    stateless_steps: list[str]
    # The flows beside the statuses, in `SubflowKey` order.
    subflows: list[ProcessSubflowView]


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


class HeadSettingView(BaseModel):
    """A setting of the head's short list: where it is, and its sentence."""

    model_config = _VIEW

    key: RuleKey
    path: str
    sentence: str


class ProcessSettingsView(BaseModel):
    model_config = _VIEW

    lanes: list[ProcessLaneView]
    # The head's short list, in its order; a key the caller may not read is left out.
    head_settings: list[HeadSettingView]
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
                ba_steps=_ba_views(kind, status.value),
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
        subflows=[_subflow_view(kind, key, flow, statuses) for key, flow in SUBFLOWS[kind].items()],
    )


def _ba_views(kind: CaseKind, place: str) -> list[BaStepView]:
    return [BaStepView(code=b.code, label=b.label) for b in ba_steps(kind, place)]


def _subflow_view(
    kind: CaseKind, key: SubflowKey, flow: Subflow, statuses: Sequence[StrEnum]
) -> ProcessSubflowView:
    return ProcessSubflowView(
        key=key,
        steps=[
            SubflowStepView(
                step=step,
                statuses=[s.value for s in statuses if s in flow.statuses[step]],
                next=[t for t in flow.steps if t != step and t in flow.moves.get(step, ())],
                ba_steps=_ba_views(kind, f"{key.value}.{step}"),
            )
            for step in flow.steps
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
            head_settings=[
                HeadSettingView(key=h.placement.key, path=h.placement.path, sentence=h.sentence)
                for h in HEAD_SETTINGS
                if readable(self.gate, context, h.placement.key)
            ],
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
