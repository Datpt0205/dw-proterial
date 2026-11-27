"""The checks of WIV-03-012 steps 1, 2, 4 and 6, and the versioned rules they read.

Each function decides from what it is given: a PO, the master data the
application fetched for it, and `OrderRules`, the policy
`configs/policies/sales_order_rules@<version>.yaml`. Nothing here reads a
message body or a remark: the values that decide come from the PO's cells and
the master data, so text that reads like an instruction changes nothing.

Every finding is made by `OrderRules.finding`, which stamps the severity and
the rules' version on it, and every line checked carries its `LineBasis`: what
it was compared against, stamped when the check ran (spec decision 11).
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Final, Literal, NamedTuple, Self, assert_never

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dw_platform.domain.messages import MailAuthentication, is_domain, is_email_address
from dw_sales.domain.anchors import SourceAnchor
from dw_sales.domain.catalog import (
    BravoOrder,
    ConvertEntry,
    Customer,
    CustomerCode,
    Item,
    LmeBand,
    LmeMonth,
    Quotation,
    fiscal_year,
    known_uom,
    month_key,
)
from dw_sales.domain.description_reading import DescriptionReading, Verified
from dw_sales.domain.descriptions import StatedAttributes, candidates, read_description
from dw_sales.domain.orders import (
    AMOUNT_FIELDS,
    TOTAL_FIELD,
    CheckName,
    ExportControlMode,
    Finding,
    FindingCode,
    ImpliedTerm,
    ItemBasis,
    LeadTimeSource,
    LineBasis,
    LineCheck,
    LineMapping,
    LmeBasis,
    MappingStatus,
    OrderCase,
    OrderLine,
    PoDocument,
    PoLine,
    PrintDifference,
    QuotationBasis,
    Severity,
    diff_lines,
)
from dw_sales.domain.revision_hints import REVISION_MARKS, is_revision_mark

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class PriceRule(BaseModel):
    model_config = _FROZEN

    # A PO price passes within this fraction of the quoted price; 0 = equal.
    relative_tolerance: Decimal = Field(ge=0, lt=1)


class LmeBandRule(BaseModel):
    model_config = _FROZEN

    # The month whose LME price a band is held to, counted back from the month
    # of the PO date: 0 = that month, 1 = the month before.
    months_before_po_date: int = Field(ge=0, le=12)


class ShortLeadTimeRule(BaseModel):
    model_config = _FROZEN

    # The day the lead time is counted from: the day the PO was received (in
    # the Sales office's time zone), or the date the PO prints.
    start: Literal["received_date", "po_date"] = Field(alias="from")
    # item_standard: the item's standard lead time. quotation: the lead time
    # quoted to the customer, or the item's when the line has no quotation.
    lead_time: LeadTimeSource
    # Calendar days only: a working-day count needs a holiday calendar nobody
    # has supplied, so no other value is accepted until one is.
    day_basis: Literal["calendar"]


class ExportControlRule(BaseModel):
    model_config = _FROZEN

    # A denial-list check older than this, on the day the PO is received, is
    # no check (`missing_noc_esf`).
    denial_list_max_age_days: int = Field(ge=1, le=3650)


class IntakeCaps(BaseModel):
    """How much of a sender's file a reader opens before refusing it (decision 13)."""

    model_config = _FROZEN

    max_attachment_bytes: int = Field(ge=1)
    # What an .xlsx may unpack to: a zip bomb is refused before it is expanded.
    max_unpacked_bytes: int = Field(ge=1)
    max_sheets: int = Field(ge=1)
    max_pages: int = Field(ge=1)
    max_cells: int = Field(ge=1)


class ModelStep(StrEnum):
    """The DW1 steps a model may take part in: each a switch of `ModelAssist`
    by the same name (a test holds the two together), and each with the bar
    its live eval must meet before the switch does anything
    (`application.model_readiness.BARS`)."""

    DESCRIPTION_ATTRIBUTES = "description_attributes"
    SALESORDER_SKILL = "salesorder_skill"
    MESSAGE_INTENT = "message_intent"
    RFQ_EXTRACTION = "rfq_extraction"
    REPLY_INTENT = "reply_intent"
    REQUEST_HANDOFF = "request_handoff"
    LAYOUT_PROPOSAL = "layout_proposal"
    PO_BODY_EXTRACTION = "po_body_extraction"
    CHANGE_REQUEST = "change_request"
    THREAD_AGENT = "thread_agent"
    REPLY_DRAFT = "reply_draft"
    SKILL_INTENTS = "skill_intents"
    SKILL_MAIL_KINDS = "skill_mail_kinds"
    SKILL_DOCUMENT_FORMS = "skill_document_forms"
    SKILL_HANDOFFS = "skill_handoffs"
    SKILL_REPLY_DRAFTS = "skill_reply_drafts"
    TRIAGE_CARD = "triage_card"
    INTERNAL_CHANGE = "internal_change"
    # The case chat's reading of what the PIC states there (ticket 56/57).
    CASE_CHAT = "case_chat"
    # PC's mail read by DW1 while an order waits on PC (ticket 77).
    PC_REPLY = "pc_reply"


# The steps whose reading can run in shadow (ticket 67): each has the two
# places a shadow needs, where it reads and where a person decides. A step
# joins here with them, never before (failure-modes #1).
SHADOW_STEPS: Final[frozenset[ModelStep]] = frozenset(
    {
        ModelStep.DESCRIPTION_ATTRIBUTES,
        # A customer's reply on a case, by both readers side by side: the one
        # call and DW1's agent with skills, labelled by the move the PIC
        # takes next on the case.
        ModelStep.REPLY_INTENT,
        ModelStep.SKILL_INTENTS,
        # A mail no reader understood, labelled by the kind the person picks
        # as they mark it handled.
        ModelStep.MESSAGE_INTENT,
        # A PO written in a mail going to a person, labelled value by value
        # when an order case of the same customer and PO number is prepared.
        ModelStep.PO_BODY_EXTRACTION,
    }
)


class ModelAssist(BaseModel):
    """Which DW1 steps a model takes part in for the tenant (dw_sales ADR 0005).

    Each is a switch the platform ships off; a tenant turns one on in its own
    version of these rules. The case stamps the version it was checked under,
    so what a case was read with never changes after.
    """

    model_config = _FROZEN

    # A local model reads an item description DW1's own vocabulary does not,
    # for a line the convert list does not map (ticket 28). Its labels are
    # flagged; Sales confirms the PRV code.
    description_attributes: bool
    # A local model gives the kind of a message no reader accepted, in place
    # of the keyword tables; code maps the kind to the route (ticket 31).
    message_intent: bool
    # A local model reads a request for quotation the fixed-label reader does
    # not, from the body, a PDF's text or a customer's Excel; every value it
    # read is flagged for Sales to confirm (ticket 29).
    rfq_extraction: bool
    # How long a message whose intent the model could not give stays not yet
    # processed, to be tried again, before it is routed `other` (ticket 31).
    unread_retry_hours: int = Field(ge=0, le=168)
    # A local model reads what a customer's reply in a case's thread says and
    # quotes where; code proposes the next step, Sales confirms (ticket 32).
    reply_intent: bool
    # A local model copies the spans of a delivery-change, complaint or
    # sample-request mail into a hand-off code writes (ticket 33).
    request_handoff: bool
    # A local model proposes which label on a new PO form names which field,
    # for the layout-onboarding screen a person completes (ticket 30).
    layout_proposal: bool
    # A local model fills a customer's SalesOrder file with the customer's
    # skill and read-only look-ups, naming each cell's source; code traces
    # every cell, writes only what it traced and flags the rest for the PIC
    # (ticket 41). Off, or below its bar: the customer's learned rules fill
    # it (ADR 0013). Off where a version does not say.
    salesorder_skill: bool = False
    # A local model reads a PO written in the mail body, with no file (AI
    # item 4); every value it read is flagged for Sales to confirm. Off when
    # a version written before 1.8.0 does not say.
    po_body_extraction: bool = False
    # A local model reads the changes a customer asks for in a reply's own
    # words (ticket 27): each a line, a field and the value's words, which
    # code finds and parses; Sales confirms each line. Off where a version
    # does not say: the platform's versions do not, so it ships off.
    change_request: bool = False
    # A local model reads a thread message's intents as `reply_intent` does,
    # and may first look up the thread's earlier messages, its cases, the
    # conversion list, a lead time or PC's answer with read-only tools bound
    # to the thread's customer (dw_sales ADR 0012, tickets 30 and 31). Over
    # its ceiling, or with no usable answer, the one-call reading reads it.
    # Off where a version does not say: the platform's versions do not.
    thread_agent: bool = False
    # A local model words the mail to a customer, offered beside the
    # template's draft: an answer to a customer's question, PC's answer to
    # their change, the confirmation (ticket 32). Code gives every fact,
    # drops a draft with a figure no fact holds or any amount, and chooses
    # the recipients; a person sends it. Off where a version does not say.
    reply_draft: bool = False
    # DW1's agent reads a thread message's intents with its skills (dw_sales
    # ADR 0014, ticket 40): one scored call picks the skill that fits from the
    # company's own skills (ADR 0015 decision 5), then one turn reads the
    # message as that skill says, with the same read-only tools, checked as
    # the one-call reading is. Without a reading, the thread agent reads it
    # where that is on, else the one call, else a person. Off where a version
    # does not say: the platform's versions do not.
    skill_intents: bool = False
    # How sure the model must be of the skill it picked before that skill
    # reads the message; less sure, the message is read as if the step were
    # off.
    skill_pick_confidence: float = Field(default=0.9, ge=0.5, le=1.0)
    # A local model classifies a message no reader accepted by the kinds the
    # company's mail-classifying skill names (ticket 42): the company's
    # approved version, else the platform's. Each kind goes where the skill
    # maps it, one of the platform's routes. With no kind read, the message
    # is classified as if this were off. Off where a version does not say.
    skill_mail_kinds: bool = False
    # A local model reads a customer's own request form the fixed reader
    # does not, by the forms the company's document-forms skill names for
    # that customer (ticket 42); code finds every value at its cell and
    # flags it for Sales to confirm. A file it reads makes the mail a
    # quotation request. Nothing read: as if this were off. Off where a
    # version does not say.
    skill_document_forms: bool = False
    # A routed message's hand-off to PC or QA is pre-filled by the kinds the
    # company's hand-off skill names (ticket 42 family 5): the company's
    # approved version, else the platform's. Each kind's fields and team are
    # the platform's, as the skill maps them. With no kind of the skill for
    # the message, or no usable answer, the hand-off is read as if this were
    # off. Off where a version does not say.
    skill_handoffs: bool = False
    # A mail to a customer is worded by the kinds the company's reply-drafts
    # skill names, each as one of the platform's drafts (ticket 42 family 5):
    # when it is offered, its facts, its check and its recipients stay the
    # draft's. Off: worded as `reply_draft` words it. Off where a version
    # does not say.
    skill_reply_drafts: bool = False
    # A message still routed "other" gets a card in the inbox (ticket 33):
    # a local model says which of the company's kinds of mail it seems to
    # be; code resolves the case it seems to concern from the numbers it
    # quotes (the sender's customer's only) and suggests one step from the
    # platform's routes. Advice: the routing stays until Sales takes or
    # dismisses it. Off where a version does not say.
    triage_card: bool = False
    # A local model reads PC's mail Sales pastes into "Thay đổi nội bộ"
    # (ticket 10): per line, the words naming it and each delivery's
    # quantity and date, which code finds, resolves and parses; Sales applies
    # the lines. Off: Sales types them. Off where a version does not say.
    internal_change: bool = False
    # The case chat states, for the PIC to confirm, a flag's decision or an
    # SO line's write the PIC asked for in the case's conversation (tickets
    # 56 and 57). ON where a version does not say, unlike every other step:
    # it is what the chat has done since it shipped, every statement waits
    # on the PIC's confirmation (its effects are T2, `STEP_TIERS`), and the
    # head turns it off with a version (Đạt, 2026-11-22). Turning it on again
    # is refused until its live eval passed (`ModelReadiness.unready`). Off:
    # the chat states nothing and points to the case page's controls.
    case_chat: bool = True
    # A local model reads the mail PC writes from the tenant's `pc_mailboxes`
    # while an order waits on PC, with no person pressing (ticket 77), as
    # `pc_dates` reads a mail Sales picks; code keeps a date only where the
    # mail writes it whole on a line asked, and proposes it. The PIC confirms
    # each line or corrects it: nothing is recorded by the reading. Off where
    # a version does not say (Đạt, 2026-11-26, by recommendation).
    pc_reply: bool = False
    # Every step with a shadow consumer (`SHADOW_STEPS`) reads in shadow
    # while it is not on and passing (ticket 67, dw_sales ADR 0015 decision
    # 4): the model reads where one is configured, its result is stored and
    # applied nowhere, and the decision a person then takes labels it. On
    # where a version does not say (decided 2026-11-24: one switch, not a list).
    shadow: bool = True
    # The most model calls shadow readings may make in an hour, for the whole
    # tenant: they never take the model from work that is on. Past it, a step
    # reads as when it is off until the hour turns. 0: none.
    shadow_calls_per_hour: int = Field(default=120, ge=0, le=100_000)

    def on(self, step: ModelStep) -> bool:
        """Whether the tenant's rules turn ``step`` on. On is not enough to use
        the model: its live eval must have met the bar too (ADR 0005, addendum
        of 2026-10-23, `application.model_readiness`)."""
        switch: bool = getattr(self, step.value)
        return switch


class Autonomy(BaseModel):
    """How much error a step that applies its result by itself may make
    (dw_sales ADR 0015, decided 2026-11-16; ticket 44). The tier of each step
    is code's (`dw_sales.domain.autonomy.STEP_TIERS`); these are the
    tenant's numbers for each tier that may apply itself. A tenant may only
    tighten them: the upper bounds are the platform's defaults, so loosening
    one is a platform change."""

    model_config = _FROZEN

    # The highest share of wrong results among those a reading, classifying
    # or linking step applied by itself (T0).
    applies_itself_error: float = Field(default=0.05, gt=0.0, le=0.05)
    # The same for an internal hand-off or a move into someone's queue (T1).
    hand_off_error: float = Field(default=0.02, gt=0.0, le=0.02)
    # The share of what applied itself that goes to the case's PIC instead,
    # unannounced, to confirm: never below the platform's 3%, since the
    # audit is what keeps the measured rate honest.
    audit_share: float = Field(default=0.03, ge=0.03, le=1.0)


class Learning(BaseModel):
    """How DW1's readings learn from what people decided (dw_sales ADR 0015
    decision 5, ticket 43). Numbers only: what is shown and what is proposed
    is code's to choose, and a proposed prompt version is the head's to
    approve."""

    model_config = _FROZEN

    # How many lines people already decided a reading of item descriptions is
    # shown for each line it reads, the same customer's first. 0 shows none.
    examples_per_line: int = Field(default=3, ge=0, le=5)
    # How many newly decided lines a step needs before DW1 tries a better
    # version of its prompt on all of them, for the head to approve.
    new_cases_to_retrain: int = Field(default=50, ge=20, le=5000)
    # How many days a customer's worked pair (a PO and the SalesOrder file
    # the PIC made from it, ticket 41) is kept to replay the customer's
    # SalesOrder skill on; the worker drops an older one
    # (`salesorder_pairs.WorkedPairRetention`). A year where a version does
    # not say, as none of the platform's versions does: the pairs carry
    # prices, and a year still holds every season's PO shapes.
    salesorder_pairs_kept_days: int = Field(default=365, ge=30, le=1095)


class LayoutOnboarding(BaseModel):
    """How a newly approved PO layout earns trust (ticket 30)."""

    model_config = _FROZEN

    # The first this-many POs read through a new or changed layout keep every
    # value `value_uncertain`: an approved but wrong mapping must not repeat
    # silently on every later PO.
    uncertain_first_pos: int = Field(ge=0, le=100)


PasswordFileValues = Literal["every_value", "failed_checks_only"]


class OrderRules(BaseModel):
    """`sales_order_rules`: the fine print of the order checks, versioned.

    Every finding code has a severity, and a policy that leaves one out is
    refused: a code with no severity would be a check whose result blocks
    nothing, which reads as a safeguard and is not one.
    """

    model_config = _FROZEN

    schema_version: str = Field(pattern=r"^1\.0$")
    policy_id: Literal["sales_order_rules"]
    policy_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    price: PriceRule
    lme_band: LmeBandRule
    short_lead_time: ShortLeadTimeRule
    # WIV-03-012 step 9. False lets an order go from uploaded_to_bravo to
    # confirmed without a second person; stamped on each case when checked.
    cross_check_required: bool
    export_control_mode: ExportControlMode
    export_control: ExportControlRule
    intake: IntakeCaps
    # The month the fiscal year starts in; the ESF is renewed per fiscal year.
    fiscal_year_start_month: int = Field(ge=1, le=12)
    model_assist: ModelAssist
    layout_onboarding: LayoutOnboarding
    findings: Mapping[FindingCode, Severity]
    # Mail domains several companies write from, such as one a group of
    # companies shares: a sender there is known by their own address only,
    # never by the domain (dw_sales ADR 0009 decision 5, ticket 20). Empty
    # where a version written before 1.13.0 does not say.
    shared_mail_domains: tuple[str, ...] = Field(default=(), max_length=200)
    # Per customer, the days of silence after a confirmation that count as
    # their agreement (dw_sales ADR 0011, ticket 28): a person records it once
    # they pass, never DW1. A customer not listed never agrees by silence;
    # empty where a version written before 1.14.0 does not say.
    implied_acceptance: Mapping[CustomerCode, ImpliedTerm] = Field(
        default_factory=dict, max_length=2000
    )
    # The error a step that applies itself may make, per tier, and the audit
    # share (dw_sales ADR 0015, ticket 44). The defaults above where a version
    # does not say, as none of the platform's versions does.
    autonomy: Autonomy = Field(default_factory=Autonomy)
    # How readings learn from decided cases (ticket 43). The defaults where a
    # version does not say, as none of the platform's versions does.
    learning: Learning = Field(default_factory=Learning)
    # The letters this company's customers write after a PO number in a
    # file's name to mark it revised (``-R1``, ``_REV2``; ticket 22,
    # `revision_hints`): a hint shown beside what decides, never a decision.
    # Today's four where a version does not say, as none of the platform's
    # versions does (ticket 42 family 6).
    revision_marks: tuple[str, ...] = Field(default=REVISION_MARKS, max_length=20)
    # The addresses production control (PC) answers from (decided 2026-11-23):
    # once named, only a verified mail from one of them is offered as PC's
    # answer on an order's dates (`pc_dates.PcDateReplies.mails`). Empty, as
    # a version before 1.16.0 reads, offers any verified mail naming the order
    # that is not the customer's, with its sender shown: a person still picks
    # it, and nothing is recorded until they confirm each line.
    pc_mailboxes: tuple[str, ...] = Field(default=(), max_length=20)
    # A PO read from a file the reader sandbox opened with a password its mail
    # carries (ticket 17): ``every_value`` waits for a person on each value
    # read (Đạt, 11-13), as every version before 1.17.0 reads;
    # ``failed_checks_only`` reads it as any other file of its layout, each
    # value waiting only on a check it failed, the file still named as opened
    # with a password (ticket 80; off until Đạt says the unscanned bytes may).
    password_file: PasswordFileValues = "every_value"

    @model_validator(mode="before")
    @classmethod
    def _no_sender_left_out(cls, data: object) -> object:
        """`ignored_sender_domains` (1.7.0, 1.8.0, and any tenant version
        written then) is dropped on reading: no mail is left out any more
        (Đạt, 2026-11-02), and a version that holds it must still read."""
        if isinstance(data, Mapping) and "ignored_sender_domains" in data:
            return {k: v for k, v in data.items() if k != "ignored_sender_domains"}
        return data

    @field_validator("shared_mail_domains")
    @classmethod
    def _domains_are_keys(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for index, domain in enumerate(value):
            if not is_domain(domain):
                raise ValueError(f"shared_mail_domains[{index}] is not a lowercase domain")
        if len(set(value)) != len(value):
            raise ValueError("shared_mail_domains repeat")
        return value

    @field_validator("pc_mailboxes")
    @classmethod
    def _pc_mailboxes_are_addresses(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for index, address in enumerate(value):
            if not is_email_address(address):
                raise ValueError(f"pc_mailboxes[{index}] is not an email address")
        if len({address.lower() for address in value}) != len(value):
            raise ValueError("pc_mailboxes repeat")
        return value

    @field_validator("revision_marks")
    @classmethod
    def _marks_are_letters(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for index, mark in enumerate(value):
            if not is_revision_mark(mark):
                raise ValueError(f"revision_marks[{index}] is not 1-5 capital letters")
        if len(set(value)) != len(value):
            raise ValueError("revision_marks repeat")
        return value

    @model_validator(mode="after")
    def _every_finding_has_a_severity(self) -> Self:
        if missing := sorted(set(FindingCode) - self.findings.keys()):
            raise ValueError(f"no severity for {[code.value for code in missing]}")
        return self

    @property
    def version(self) -> str:
        """What a finding is stamped with: ``sales_order_rules@1.6.0``."""
        return f"{self.policy_id}@{self.policy_version}"

    @property
    def ref(self) -> str:
        """``key@x.y.z``, as a tenant's version of it is named (ticket 36)."""
        return self.version

    def finding(
        self,
        code: FindingCode,
        *,
        line_no: int | None = None,
        expected: str | None = None,
        actual: str | None = None,
    ) -> Finding:
        return Finding(
            code=code,
            severity=self.findings[code],
            line_no=line_no,
            expected=expected,
            actual=actual,
            rule_version=self.version,
        )

    def lme_month(self, po_date: date) -> str:
        """The month (``YYYY-MM``) whose LME price a banded line is checked against."""
        months = po_date.year * 12 + po_date.month - 1 - self.lme_band.months_before_po_date
        return month_key(date(months // 12, months % 12 + 1, 1))

    def lead_time_start(self, *, po_date: date, received_on: date) -> date:
        """The day a line's lead time is counted from. ``received_on`` is the
        day the message arrived where the tenant works: its caller counts it
        in the tenant's zone (`local_time`), the one owner of that fact."""
        match self.short_lead_time.start:
            case "received_date":
                return received_on
            case "po_date":
                return po_date
            case other:
                assert_never(other)


# ----------------------------------------------------------------- mapping --


class MappedLine(NamedTuple):
    mapping: LineMapping
    # The item the line's checks run against: the exact one, or the single
    # candidate (which Sales must still confirm). None otherwise.
    item: Item | None
    # The convert list's code for the customer's code, when it had one.
    convert_prv_code: str | None = None
    # A model's reading of the description, when one was asked for
    # (`map_read_line`); stamped on the line's basis.
    reading: DescriptionReading | None = None
    # The attributes the candidates were computed from; stamped on the basis.
    stated: StatedAttributes | None = None


def map_line(po_line: PoLine, *, entry: ConvertEntry | None, items: Sequence[Item]) -> MappedLine:
    """The PRV code a line names: the convert list's, else candidates the description fits.

    A convert entry decides on its own. When its item is not in the item master
    the line is unmapped, not matched by description instead: the convert list
    has said which item this is, and a different item that happens to fit the
    words would be a guess against it.

    A description typed in a TCVN3 or VNI font is not matched at all: its
    letters are not what the customer sees (`legacy_encoding`, ticket 20).
    """
    if entry is not None:
        item = next((i for i in items if i.prv_code == entry.prv_code), None)
        if item is None:
            return MappedLine(LineMapping(status=MappingStatus.UNMAPPED), None, entry.prv_code)
        return MappedLine(
            LineMapping(status=MappingStatus.EXACT, prv_code=item.prv_code), item, entry.prv_code
        )
    typed_legacy = "description" in po_line.legacy_fields
    stated = None if typed_legacy else read_description(po_line.description)
    return _by_description(stated, items, None)


def wants_reading(po_line: PoLine, *, entry: ConvertEntry | None) -> bool:
    """Whether a model may read the line's description (dw_sales ADR 0005):
    the convert list has no code for it, DW1's own vocabulary does not read
    it, and it is not text typed in a legacy font. A deterministic reading is
    never replaced by a model's, and a convert entry decides on its own."""
    return (
        entry is None
        and bool(po_line.description.strip())
        and "description" not in po_line.legacy_fields
        and read_description(po_line.description) is None
    )


def map_read_line(
    verified: Verified | None, reading: DescriptionReading, items: Sequence[Item]
) -> MappedLine:
    """The candidates a model reading code verified fits, as `map_line` maps a
    description it reads itself: one fit is a candidate Sales confirms,
    several are ambiguous, none is unmapped. Never exact. ``verified`` is
    None for a reading that was refused or never came (``reading`` says
    which); the line is then unmapped, as without a model."""
    stated = verified.stated if verified is not None else None
    return _by_description(stated, items, reading)


def _by_description(
    stated: StatedAttributes | None, items: Sequence[Item], reading: DescriptionReading | None
) -> MappedLine:
    fitting = candidates(stated, items) if stated is not None else ()
    if not fitting:
        return MappedLine(
            LineMapping(status=MappingStatus.UNMAPPED), None, reading=reading, stated=stated
        )
    codes = tuple(i.prv_code for i in fitting)
    if len(fitting) == 1:
        return MappedLine(
            LineMapping(status=MappingStatus.CANDIDATE, candidates=codes),
            fitting[0],
            reading=reading,
            stated=stated,
        )
    return MappedLine(
        LineMapping(status=MappingStatus.AMBIGUOUS, candidates=codes),
        None,
        reading=reading,
        stated=stated,
    )


def current_quotation(
    quotations: Sequence[Quotation], *, customer_code: str, prv_code: str, day: date
) -> Quotation | None:
    """The customer's quotation for the item that applies on ``day``.

    Of two valid ones the later issue applies: a new quotation replaces the one
    before it. The fixtures never hold two, so this rule is the tie-break, not
    a path any golden case depends on.
    """
    valid = [
        q
        for q in quotations
        if q.customer_code == customer_code and q.prv_code == prv_code and q.is_valid_on(day)
    ]
    return max(valid, key=lambda q: (q.valid_from, q.quote_no), default=None)


# ------------------------------------------------------------- line checks --


def check_line(
    po_line: PoLine,
    mapped: MappedLine,
    *,
    currency: str,
    po_date: date,
    received_on: date,
    quotation: Quotation | None,
    lme: LmeMonth | None,
    rules: OrderRules,
) -> LineCheck:
    """Every finding about one line, with the basis each check compared against.

    ``quotation`` is the customer's quotation for ``mapped.item`` that applies
    on the PO date (`current_quotation`), and ``lme`` the price of
    `OrderRules.lme_month`, or None when there is none on record.
    """
    number = po_line.line_no
    mapping = mapped.mapping
    found: list[Finding] = []
    run: list[CheckName] = ["read", "mapping"]

    if mapping.status is MappingStatus.UNMAPPED:
        found.append(
            _on(rules, FindingCode.CODE_UNMAPPED, number, None, po_line.customer_item_code)
        )
    elif mapping.status is MappingStatus.AMBIGUOUS:
        found.append(
            _on(rules, FindingCode.CODE_AMBIGUOUS, number, None, po_line.customer_item_code)
        )
    if flags := sorted({flag.flag.value for flag in po_line.flags}):
        found.append(_on(rules, FindingCode.VALUE_UNCERTAIN, number, None, ",".join(flags)))
    if po_line.requested_date is None:
        # "Date to follow" (ticket 34): the line reads, and Sales asks for the
        # date or goes ahead without it.
        found.append(_on(rules, FindingCode.REQUESTED_DATE_MISSING, number, "a date", None))

    item = mapped.item
    uom = known_uom(po_line.uom)
    run.append("uom")
    unit_differs = uom is None or (
        item is not None and (uom != item.uom or (quotation is not None and uom != quotation.uom))
    )
    if unit_differs:
        expected_unit = item.uom if item is not None else None
        found.append(
            _on(
                rules,
                FindingCode.UOM_MISMATCH,
                number,
                expected_unit or "a known unit",
                po_line.uom,
            )
        )

    basis = LineBasis(
        convert_prv_code=mapped.convert_prv_code,
        candidates=mapping.candidates,
        checks_run=tuple(run),
        description_reading=mapped.reading,
        stated_attributes=mapped.stated,
    )
    if item is None:
        return LineCheck(
            line=OrderLine(po_line=po_line, mapping=mapping, basis=basis), findings=tuple(found)
        )
    if quotation is not None and (
        quotation.prv_code != item.prv_code or not quotation.is_valid_on(po_date)
    ):
        raise ValueError(f"line {number} is checked against a quotation for its item and date")

    run.append("quotation")
    lme_basis: LmeBasis | None = None
    if quotation is None:
        found.append(
            _on(
                rules,
                FindingCode.QUOTATION_MISSING,
                number,
                f"valid on {po_date.isoformat()}",
                None,
            )
        )
    else:
        run.append("currency")
        if currency != quotation.currency:
            # Never converted: the exchange-rate rule is owed by the company.
            found.append(
                _on(rules, FindingCode.CURRENCY_MISMATCH, number, quotation.currency, currency)
            )
        elif not unit_differs:
            run.append("price")
            if price := _price_finding(po_line, quotation, rules):
                found.append(price)
        if isinstance(quotation.copper_basis, LmeBand):
            run.append("lme_band")
            lme_basis, band = _lme_check(number, quotation.copper_basis, lme, po_date, rules)
            if band is not None:
                found.append(band)

    moq = quotation.moq if quotation is not None else item.moq
    if not unit_differs:
        # A quantity in another unit is not comparable with a MOQ or a pack.
        # One the item master does not hold (Bravo's has neither, B06) is not
        # checked, and the coverage says so: never a MOQ or a pack of zero.
        if moq is not None:
            run.append("moq")
            if po_line.quantity < moq:
                found.append(
                    _on(rules, FindingCode.MOQ_VIOLATION, number, str(moq), str(po_line.quantity))
                )
        if item.pack_multiple is not None:
            run.append("pack")
            if po_line.quantity % item.pack_multiple:
                found.append(
                    _on(
                        rules,
                        FindingCode.PACK_MULTIPLE,
                        number,
                        str(item.pack_multiple),
                        str(po_line.quantity),
                    )
                )

    found += _stated_checks(po_line, mapped, item, run, rules)

    known = _lead_time(item, quotation, rules)
    lead_time, source = known if known is not None else (None, None)
    earliest: date | None = None
    if lead_time is not None:
        run.append("lead_time")
        earliest = rules.lead_time_start(po_date=po_date, received_on=received_on) + timedelta(
            days=lead_time
        )
    # Per schedule (ticket 21): one finding on the line, naming each date
    # requested sooner than the lead time allows.
    if earliest is not None and (
        short := [s.requested_date for s in po_line.schedules if s.requested_date < earliest]
    ):
        found.append(
            _on(
                rules,
                FindingCode.REQUESTED_DATE_SHORT_LT,
                number,
                earliest.isoformat(),
                ", ".join(day.isoformat() for day in short),
            )
        )
    basis = LineBasis(
        convert_prv_code=mapped.convert_prv_code,
        candidates=mapping.candidates,
        item=ItemBasis(
            prv_code=item.prv_code,
            uom=item.uom,
            moq=item.moq,
            pack_multiple=item.pack_multiple,
            standard_lead_time_days=item.standard_lead_time_days,
        ),
        quotation=_quotation_basis(quotation),
        lme=lme_basis,
        lead_time_days=lead_time,
        lead_time_source=source,
        checks_run=tuple(run),
        description_reading=mapped.reading,
        stated_attributes=mapped.stated,
    )
    line = OrderLine(
        po_line=po_line,
        mapping=mapping,
        basis=basis,
        # DW1's proposal, labelled as one: the requested date when the lead
        # time allows it, else the first day it does, which is also the
        # proposal for a line printed with no date. With no lead time known,
        # the requested date, or none for Sales to choose.
        suggested_delivery_date=_suggested(po_line.requested_date, earliest),
    )
    return LineCheck(line=line, findings=tuple(found))


def _stated_checks(
    po_line: PoLine, mapped: MappedLine, item: Item, run: list[CheckName], rules: OrderRules
) -> list[Finding]:
    """What the line's description states against the item ("hk & cable",
    ticket 38): its length per reel against the item's standard length
    (`reel_length_mismatch`), its spec number against the item's
    (`spec_mismatch`). Each runs only where both sides are known, and
    ``run`` says which ran: a description DW1's vocabulary does not read,
    or an item with no standard length or spec, is not checked."""
    stated = mapped.stated
    if stated is None and "description" not in po_line.legacy_fields:
        stated = read_description(po_line.description)
    if stated is None:
        return []
    number = po_line.line_no
    found: list[Finding] = []
    if stated.pack_length_m is not None and item.pack_multiple is not None:
        run.append("reel_length")
        if stated.pack_length_m != item.pack_multiple:
            found.append(
                _on(
                    rules,
                    FindingCode.REEL_LENGTH_MISMATCH,
                    number,
                    str(item.pack_multiple),
                    str(stated.pack_length_m),
                )
            )
    specs = item_specs(item)
    if stated.spec_no is not None and specs:
        run.append("spec")
        if _spec_key(stated.spec_no) not in {_spec_key(s) for s in specs}:
            found.append(
                _on(rules, FindingCode.SPEC_MISMATCH, number, ", ".join(specs), stated.spec_no)
            )
    return found


def item_specs(item: Item) -> tuple[str, ...]:
    """The spec numbers the item master holds for ``item``: DW1's own
    attribute and the numbers Bravo's specification column lists (split on
    commas, semicolons and spaces), each once, in that order."""
    listed = [item.attributes.spec_no] if item.attributes.spec_no else []
    if item.specification:
        listed += [part for part in re.split(r"[\s,;]+", item.specification) if part]
    return tuple(dict.fromkeys(listed))


def _spec_key(text: str) -> str:
    return unicodedata.normalize("NFKC", text).strip().casefold()


def _on(
    rules: OrderRules, code: FindingCode, line_no: int, expected: str | None, actual: str | None
) -> Finding:
    return rules.finding(code, line_no=line_no, expected=expected, actual=actual)


def _price_finding(po_line: PoLine, quotation: Quotation, rules: OrderRules) -> Finding | None:
    quoted = quotation.unit_price
    if abs(po_line.unit_price - quoted) <= quoted * rules.price.relative_tolerance:
        return None
    return rules.finding(
        FindingCode.PRICE_MISMATCH,
        line_no=po_line.line_no,
        expected=f"{quoted} {quotation.currency}",
        actual=f"{po_line.unit_price} {quotation.currency}",
    )


def _lme_check(
    line_no: int, band: LmeBand, lme: LmeMonth | None, po_date: date, rules: OrderRules
) -> tuple[LmeBasis, Finding | None]:
    month = rules.lme_month(po_date)
    if lme is not None and lme.month != month:
        raise ValueError(f"line {line_no} is checked against LME {month}, given {lme.month}")
    basis = LmeBasis(month=month, usd_per_tonne=lme.usd_per_tonne if lme is not None else None)
    expected = f"{band.low_usd_per_tonne}-{band.high_usd_per_tonne} USD/t"
    if lme is None:
        # A band nobody can check is not a band that holds.
        return basis, _on(
            rules, FindingCode.LME_BAND_MISMATCH, line_no, expected, f"no LME price for {month}"
        )
    if band.contains(lme.usd_per_tonne):
        return basis, None
    return basis, _on(
        rules,
        FindingCode.LME_BAND_MISMATCH,
        line_no,
        expected,
        f"{lme.usd_per_tonne} USD/t ({month})",
    )


def _suggested(requested: date | None, earliest: date | None) -> date | None:
    if earliest is None:
        return requested
    return earliest if requested is None else max(requested, earliest)


def _lead_time(
    item: Item, quotation: Quotation | None, rules: OrderRules
) -> tuple[int, LeadTimeSource] | None:
    """The lead time a line is held to and where it came from; None where
    neither the rule's source nor the item master holds one."""
    source = rules.short_lead_time.lead_time
    standard: tuple[int, LeadTimeSource] | None = (
        None
        if item.standard_lead_time_days is None
        else (item.standard_lead_time_days, "item_standard")
    )
    match source:
        case "item_standard":
            return standard
        case "quotation":
            if quotation is None:
                return standard
            return quotation.lead_time_days, "quotation"
        case _:
            assert_never(source)


def _quotation_basis(quotation: Quotation | None) -> QuotationBasis | None:
    if quotation is None:
        return None
    return QuotationBasis(
        quote_no=quotation.quote_no,
        unit_price=quotation.unit_price,
        currency=quotation.currency,
        uom=quotation.uom,
        moq=quotation.moq,
        lead_time_days=quotation.lead_time_days,
        copper_basis=quotation.copper_basis,
        valid_from=quotation.valid_from,
        valid_to=quotation.valid_to,
    )


# ---------------------------------------------------------- the PO as read --


# The codes each PO-level check raises: what running it again replaces on a
# case (`OrderCase.correct_value`), which refuses a finding outside them.
DOCUMENT_CHECK_CODES: Final = frozenset(
    {
        FindingCode.LINE_TOTAL_MISMATCH,
        FindingCode.VALUE_UNCERTAIN,
        FindingCode.LEGACY_ENCODING,
        FindingCode.FILES_DISAGREE,
    }
)
# What `check_history` can raise.
HISTORY_CHECK_CODES: Final = frozenset(
    {FindingCode.DUPLICATE_PO, FindingCode.REVISED_PO, FindingCode.REVISION_WITHOUT_BASE}
)
CUSTOMER_CHECK_CODES: Final = frozenset(
    {
        FindingCode.CUSTOMER_UNKNOWN,
        FindingCode.CUSTOMER_TEMPORARY,
        FindingCode.MISSING_NOC_ESF,
        FindingCode.SENDER_UNVERIFIED,
        FindingCode.DELIVERY_TERM_MISMATCH,
    }
)


def check_document(document: PoDocument, rules: OrderRules) -> tuple[Finding, ...]:
    """Whether every line printed was read, and read from a place a person sees.

    `line_total_mismatch`: the line numbers are not 1..N in reading order, a
    numbered row was not read, the line amounts do not add up to the printed
    total, or a line's schedules do not add up to its quantity (ticket 21).
    `value_uncertain` (PO level): a header value or the total read from a
    flagged region, or a sheet nothing reads. A line's own flags are its
    line's finding (`check_line`). `legacy_encoding`: a value was read from
    text typed in a TCVN3 or VNI font; the document says where the first one
    is (`PoDocument.first_legacy_text`). `files_disagree`: the PO's second
    file (`PoDocument.print_copy`, ticket 22) prints values differently; it
    names both files and, per value, where each prints it and what (an
    amount by its field and place only: this finding is shown to a reader
    who may not see prices).
    """
    found: list[Finding] = []
    numbers = [line.line_no for line in document.lines]
    expected: list[str] = []
    actual: list[str] = []
    if numbers != list(range(1, len(numbers) + 1)) or document.rows_printed != len(numbers):
        expected.append(f"lines 1-{document.rows_printed}")
        actual.append(f"lines {_ranges(numbers)}")
    if document.total is not None:
        added = sum((line.amount for line in document.lines), Decimal(0))
        if added != document.total.amount:
            expected.append(f"total {document.total.amount}")
            actual.append(f"sum of lines {added}")
    for line in document.lines:
        if line.prints_schedules and line.scheduled_quantity != line.quantity:
            expected.append(f"line {line.line_no} quantity {line.quantity}")
            actual.append(f"line {line.line_no} schedules {line.scheduled_quantity}")
    if expected:
        found.append(
            rules.finding(
                FindingCode.LINE_TOTAL_MISMATCH,
                expected="; ".join(expected),
                actual="; ".join(actual),
            )
        )
    flags = {flag.flag.value for flag in document.header.flags}
    if document.total is not None:
        flags |= {flag.flag.value for flag in document.total.flags}
    if document.unchecked_regions:
        flags.add("unchecked_region")
    if flags:
        found.append(rules.finding(FindingCode.VALUE_UNCERTAIN, actual=",".join(sorted(flags))))
    if (legacy := document.first_legacy_text()) is not None:
        _, encoding = legacy
        found.append(
            rules.finding(
                FindingCode.LEGACY_ENCODING, expected="Unicode", actual=encoding.value.upper()
            )
        )
    copy = document.print_copy
    if copy is not None and copy.differences:
        ours = [(d, _read_at(document, d), d.ours) for d in copy.differences]
        theirs = [(d, d.anchor, d.theirs) for d in copy.differences]
        found.append(
            rules.finding(
                FindingCode.FILES_DISAGREE,
                expected=_cited(document.attachment_id or "", ours),
                actual=_cited(copy.attachment_id, theirs),
            )
        )
    return tuple(found)


def _read_at(document: PoDocument, difference: PrintDifference) -> SourceAnchor:
    """Where the case's own file prints the value ``difference`` names."""
    if difference.line_no is None:
        if difference.field == TOTAL_FIELD and document.total is not None:
            return document.total.anchor
        anchor: SourceAnchor = getattr(document.header.anchors, difference.field)
        return anchor
    line = next(x for x in document.lines if x.line_no == difference.line_no)
    at: SourceAnchor = getattr(line.anchors, difference.field)
    return at


def _cited(
    attachment_id: str, values: Sequence[tuple[PrintDifference, SourceAnchor, str | None]]
) -> str:
    """``PO123.xlsx: line 2 requested_date 2026-12-01 [Sheet1!F12]; …``, cut
    to what a finding holds. An amount is named by its field and place."""
    cited = []
    for difference, anchor, value in values:
        where = f"line {difference.line_no} " if difference.line_no else ""
        shown = "" if difference.field in AMOUNT_FIELDS or value is None else f" {value}"
        place = anchor.cell_ref or (f"p{anchor.page}" if anchor.page else "")
        cited.append(f"{where}{difference.field}{shown}" + (f" [{place}]" if place else ""))
    text = f"{attachment_id}: {'; '.join(cited)}"
    return text if len(text) <= 200 else text[:199] + "…"


def _ranges(numbers: Iterable[int]) -> str:
    """``1-4, 6-8`` for 1, 2, 3, 4, 6, 7, 8, in the order read."""
    runs: list[list[int]] = []
    for number in numbers:
        if runs and number == runs[-1][-1] + 1:
            runs[-1].append(number)
        else:
            runs.append([number])
    return ", ".join(f"{r[0]}-{r[-1]}" if len(r) > 1 else str(r[0]) for r in runs)


# --------------------------------------------------- who sent it, and to whom --


def check_customer(
    customer: Customer,
    *,
    attributed_by_document: bool,
    authentication: MailAuthentication,
    po_date: date,
    received_on: date,
    delivery_term: str | None,
    rules: OrderRules,
) -> tuple[Finding, ...]:
    """Findings about the customer and the sender, in the order shown.

    `customer_unknown` when the customer was taken from the buyer the document
    names rather than the sender's domain; `customer_temporary`;
    `missing_noc_esf`, which holds the order's confirmation until the
    export-control PIC accepts it (DW1 decides nothing about export control);
    `sender_unverified` when the mail system's results are not all ``pass``;
    `delivery_term_mismatch` when the PO's ``delivery_term`` is not the
    customer's (`same_delivery_term`). A PO stating none, or a customer whose
    record holds none, is not a mismatch: there is nothing to compare.
    """
    found: list[Finding] = []
    if attributed_by_document:
        found.append(
            rules.finding(
                FindingCode.CUSTOMER_UNKNOWN,
                expected="customer confirmed by Sales",
                actual=f"buyer named on the document: {customer.code}",
            )
        )
    if customer.status == "temporary":
        found.append(
            rules.finding(FindingCode.CUSTOMER_TEMPORARY, expected="official", actual="temporary")
        )
    if compliance := _compliance_finding(customer, po_date, received_on, rules):
        found.append(compliance)
    if not authentication.verified:
        results = (authentication.spf, authentication.dkim, authentication.dmarc)
        found.append(
            rules.finding(
                FindingCode.SENDER_UNVERIFIED,
                expected="spf=pass, dkim=pass, dmarc=pass",
                actual="spf={}, dkim={}, dmarc={}".format(*results),
            )
        )
    held = customer.delivery_term
    stated = delivery_term
    if stated is not None and held is not None and not same_delivery_term(stated, held):
        found.append(
            rules.finding(FindingCode.DELIVERY_TERM_MISMATCH, expected=held, actual=stated)
        )
    return tuple(found)


# Incoterms 2020: the closed set a delivery term is compared in (ticket 02).
# The term on every sales order seen is one (B41: DAP, FCA, CIP, one per
# customer), and a PO prints it with its place and edition ("DAP Hanoi",
# "FCA Haiphong, Incoterms 2020"), which the customer's record does not hold.
INCOTERMS: Final = frozenset(
    {"EXW", "FCA", "CPT", "CIP", "DAP", "DPU", "DDP", "FAS", "FOB", "CFR", "CIF"}
)


def incoterm(text: str) -> str | None:
    """The one Incoterms rule ``text`` names as a word of its own, or None
    when it names none, or two (then nothing says which one was meant)."""
    named = {word for word in re.split(r"[^0-9A-Z]+", text.upper()) if word} & INCOTERMS
    return next(iter(named)) if len(named) == 1 else None


def same_delivery_term(stated: str, held: str) -> bool:
    """Whether the term a PO states is the customer's: the same Incoterms
    rule, whatever place follows it; or, for a term outside Incoterms that a
    customer's record holds as Bravo spells it, the same words. Anything else
    is a person's to decide, never a guess."""
    rule = incoterm(stated)
    if rule is not None:
        return rule == incoterm(held)
    return _words(stated) == _words(held)


def _words(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _compliance_finding(
    customer: Customer, po_date: date, received: date, rules: OrderRules
) -> Finding | None:
    year = fiscal_year(po_date, start_month=rules.fiscal_year_start_month)
    compliance = customer.compliance
    max_age = rules.export_control.denial_list_max_age_days
    checked_on = compliance.denial_list_checked_on
    screened = checked_on is not None and (received - checked_on).days <= max_age
    if compliance.noc_confirmed and compliance.esf_fiscal_year == year and screened:
        return None
    noc = "NOC confirmed" if compliance.noc_confirmed else "no NOC"
    esf = f"ESF FY{compliance.esf_fiscal_year}" if compliance.esf_fiscal_year else "no ESF"
    denial = (
        f"denial-list check {checked_on.isoformat()}"
        if checked_on is not None
        else "no denial-list check"
    )
    return rules.finding(
        FindingCode.MISSING_NOC_ESF,
        expected=f"NOC confirmed, ESF FY{year}, denial-list check within {max_age} days",
        actual=f"{noc}, {esf}, {denial}",
    )


# ------------------------------------------------------------------ history --

SAME_REVISION_CHANGED: Final = "nội dung đổi mà không tăng revision"


class History(NamedTuple):
    """What the PO number already has, and what this revision is to it."""

    finding: Finding | None
    # The DW1 case this revision joins and supersedes.
    base: OrderCase | None = None
    duplicate_of_case: uuid.UUID | None = None
    duplicate_of_so: str | None = None
    # A revision whose base is a sales order Bravo holds and no DW1 case does.
    base_so_no: str | None = None
    # An earlier revision than the case already holds, arriving late: not a
    # duplicate (its lines differ), not something to supersede the case with.
    stale: bool = False


def check_history(
    customer_code: str,
    document: PoDocument,
    prv_codes: Mapping[int, str | None],
    earlier: Sequence[OrderCase],
    bravo_orders: Sequence[BravoOrder],
    *,
    rules: OrderRules,
) -> History:
    """Whether this PO number was seen before, in a DW1 case or in Bravo.

    Keyed by revision. The same revision with identical lines is
    `duplicate_po`. The same revision with other lines, or a higher revision,
    is `revised_po`: it joins the case that holds the PO, or names the Bravo
    order when only Bravo has it. A revision above 0 with no base in either
    source is `revision_without_base`, handled as a new PO. ``prv_codes`` maps
    each line to the code it was checked against, for the comparison with the
    Bravo entry, which holds PRV codes rather than the customer's.
    """
    header = document.header
    cases = [
        case
        for case in earlier
        if case.customer_code == customer_code and case.header.po_no == header.po_no
    ]
    orders = [
        order
        for order in bravo_orders
        if order.customer_code == customer_code and order.po_no == header.po_no
    ]
    if not cases and not orders:
        if header.revision == 0:
            return History(None)
        return History(
            rules.finding(
                FindingCode.REVISION_WITHOUT_BASE,
                expected=f"revision {header.revision - 1} seen first",
                actual=str(header.revision),
            )
        )

    same_case = next(
        (
            case
            for case in cases
            for revision in (case.document, *(old.document for old in case.superseded))
            if revision.header.revision == header.revision
            and not diff_lines(revision.lines, document.lines)
        ),
        None,
    )
    same_order = next(
        (
            order
            for order in orders
            if order.po_revision == header.revision and _same_entry(order, document, prv_codes)
        ),
        None,
    )
    known = [case.header.revision for case in cases] + [order.po_revision for order in orders]
    if same_case is not None or same_order is not None:
        return History(
            rules.finding(
                FindingCode.DUPLICATE_PO,
                expected=f"a revision after {max(known)}",
                actual=str(header.revision),
            ),
            duplicate_of_case=same_case.case_id if same_case is not None else None,
            duplicate_of_so=same_order.so_no if same_case is None and same_order else None,
        )

    originals = [c for c in cases if FindingCode.DUPLICATE_PO not in {f.code for f in c.findings}]
    base = max(originals or cases, key=lambda case: case.header.revision, default=None)
    latest_so = max(orders, key=lambda order: order.po_revision, default=None)
    held = max(known)
    if header.revision < held:
        return History(None, stale=True)
    if header.revision == held:
        expected, actual = str(header.revision), SAME_REVISION_CHANGED
    else:
        expected, actual = str(held), str(header.revision)
    finding = rules.finding(FindingCode.REVISED_PO, expected=expected, actual=actual)
    if base is not None:
        return History(finding, base=base)
    assert latest_so is not None  # no case for the PO, so Bravo holds it
    return History(finding, base_so_no=latest_so.so_no)


def _deliveries(line: PoLine) -> list[tuple[Decimal, date | None]]:
    """A line's quantity per requested date; one with no date when it prints none."""
    if not line.schedules:
        return [(line.quantity, None)]
    return [(s.quantity, s.requested_date) for s in line.schedules]


def _same_entry(
    order: BravoOrder, document: PoDocument, prv_codes: Mapping[int, str | None]
) -> bool:
    """The Bravo order holds this PO's lines: number, PRV code, quantity, price,
    date; a line split over several dates as one entry per schedule, and a line
    printed with no date as one entry with none, which no Bravo line matches."""
    entered: set[tuple[int, str | None, Decimal, Decimal, date | None]] = {
        (line.line_no, line.prv_code, line.quantity, line.unit_price, line.delivery_date)
        for line in order.lines
    }
    printed = {
        (
            line.line_no,
            prv_codes.get(line.line_no),
            quantity,
            line.unit_price,
            day,
        )
        for line in document.lines
        for quantity, day in _deliveries(line)
    }
    return order.currency == document.header.currency and entered == printed
