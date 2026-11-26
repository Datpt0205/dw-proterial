"""Status questions DW1 answers from live data (dw_sales ADR 0007; the
contract's DW01 criterion 6).

A catalog, not a chat: four kinds of question, three steps of a case a
person may ask for (ticket 46), a decision on one of the case's flags stated
for the PIC to confirm (ticket 56), and `out_of_scope` for everything else.
The model only reads a question into a `QuestionIntent`; code finds the
case among those the caller may see and builds the facts. An answer carries
no amount, whoever asks and whatever the channel.

The labels below are the glossary's (`CONTEXT.md`, "Order case states",
"Quote case states") and the work list's own words (`labels.ts`'s `ACTION`);
`test_assistant.py` reads both files, so a label changed on either side turns
it red instead of drifting (failure-modes #2).
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

from dw_sales.domain.dispositions import CaseKind

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

# A question as a person types it; the API refuses a longer one.
QUESTION_CHARS: Final = 500
# The turns of a session the intent call is shown, newest last.
HISTORY_TURNS: Final = 6


class QuestionKind(StrEnum):
    """What DW1 answers (the agreed list), and everything else."""

    ORDER_STATUS = "order_status"
    QUOTE_STATUS = "quote_status"
    MY_WORK = "my_work"
    OVERDUE = "overdue"
    # A step of a case the person asks DW1 for (ticket 46): answered with
    # the case page's own button, in that case's conversation; DW1 itself
    # does nothing from the chat.
    DRAFT_REPLY = "draft_reply"
    REMIND_CUSTOMER = "remind_customer"
    EXPLAIN_THREAD = "explain_thread"
    # The PIC states a decision on one of the case's open flags (ticket 56):
    # DW1 says back exactly what it would record, and records it only when
    # the PIC confirms that statement (`ProposedDecision.content_hash`).
    DECIDE_FINDING = "decide_finding"
    # The PIC asks for an SO line's confirmed date or quantity to be written
    # into Bravo (ticket 56 over ticket 53): DW1 says back exactly what it
    # would propose, and proposes it for approval only when the PIC confirms.
    PROPOSE_BRAVO_WRITE = "propose_bravo_write"
    # The head gives the case to a person named in the chat (ticket 79): DW1
    # finds exactly one of the people the case may be given to and says it
    # back; the case is given only when the head confirms that statement.
    ASSIGN_CASE = "assign_case"
    OUT_OF_SCOPE = "out_of_scope"


# What a PIC may decide on a flag from the chat: the finding dispositions
# that need no typed value (`orders.DispositionKind`), in the API's words.
ChatDecision = Literal["accepted", "ask_customer"]
REASON_CHARS: Final = 200
# What a PIC may ask the chat to write into Bravo: ticket 53's confirmed
# date and quantity, and ticket 71's cancel, in `bravo_line_writes.LineChange`'s
# words.
WriteField = Literal["confirmed_date", "quantity", "cancel"]


class QuestionIntent(BaseModel):
    """What the model reads a question as. Never an id: a number the person
    wrote, which code looks up, and whether the question is about the case
    the conversation was on."""

    model_config = _FROZEN

    kind: QuestionKind
    # The PO or request number as written, when the question names one.
    reference: str | None = Field(default=None, min_length=1, max_length=64)
    about_previous: bool = False
    # `decide_finding`: the flag's code as the case lists it to the model,
    # which code then looks for among the case's open flags; the decision;
    # and the reason as the person gave it. A cancel (`propose_bravo_write`,
    # field "cancel") carries its reason here too.
    finding_code: str | None = Field(default=None, pattern=r"^[a-z_]{1,64}$")
    decision: ChatDecision | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=REASON_CHARS)
    # `propose_bravo_write` only: the PO line the person names, the field,
    # and the new value as the model writes it (an ISO date or a plain
    # number), which code parses strictly and says back before anything.
    line_no: int | None = Field(default=None, ge=1, le=99_999)
    field: WriteField | None = None
    new_value: str | None = Field(default=None, min_length=1, max_length=32)
    # `assign_case` only: the person as the question names them (a name, a
    # given name, an address), which code looks for among the case's
    # candidates; never an id.
    assignee: str | None = Field(default=None, min_length=1, max_length=64)


@dataclass(frozen=True, slots=True)
class ProposedDecision:
    """A flag's decision DW1 states in a case's conversation (ticket 56).

    Bound to the case, its version and the exact words: the PIC confirms
    `content_hash`, and code records only a decision whose content still
    hashes to it on a case still at ``case_version``. Nothing a model wrote
    names the case or the flag: the case is the conversation's, the flag one
    of its open findings.
    """

    case_kind: CaseKind
    case_id: uuid.UUID
    case_version: int
    finding_key: str
    decision: ChatDecision
    reason: str | None
    # The prompt that read the PIC's sentence (`name@version`), stamped when
    # the statement is made, for its labelled case (ticket 57). Not part of
    # what the PIC confirms: the hash binds what they were shown. None on a
    # statement stored before the stamp.
    prompt: str | None = None

    @property
    def content_hash(self) -> str:
        content = {
            "case_kind": self.case_kind.value,
            "case_id": str(self.case_id),
            "case_version": self.case_version,
            "finding_key": self.finding_key,
            "decision": self.decision,
            "reason": self.reason,
        }
        canonical = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def stored(self) -> dict[str, object]:
        return {
            "case_kind": self.case_kind.value,
            "case_id": str(self.case_id),
            "case_version": self.case_version,
            "finding_key": self.finding_key,
            "decision": self.decision,
            "reason": self.reason,
            **({} if self.prompt is None else {"prompt": self.prompt}),
        }

    @classmethod
    def from_stored(cls, row: Mapping[str, object]) -> ProposedDecision:
        decision = str(row["decision"])
        if decision not in ("accepted", "ask_customer"):
            raise ValueError(f"unknown decision {decision!r}")
        version = row["case_version"]
        if not isinstance(version, int):
            raise ValueError("case_version is not an integer")
        reason, prompt = row.get("reason"), row.get("prompt")
        return cls(
            case_kind=CaseKind(str(row["case_kind"])),
            case_id=uuid.UUID(str(row["case_id"])),
            case_version=version,
            finding_key=str(row["finding_key"]),
            decision=decision,  # type: ignore[arg-type]
            reason=None if reason is None else str(reason),
            prompt=None if prompt is None else str(prompt),
        )


@dataclass(frozen=True, slots=True)
class ProposedBravoWrite:
    """An SO line's value DW1 states it would propose writing into Bravo
    (ticket 56 over ticket 53), bound like `ProposedDecision`: the PIC
    confirms `content_hash`, and code opens the write's approval only for
    content that still hashes to it on a case still at ``case_version``.
    ``value`` is canonical: an ISO date, a quantity with no exponent, or a
    cancel's reason as `bravo_line_writes.cancel_reason` collapses it."""

    case_kind: CaseKind
    case_id: uuid.UUID
    case_version: int
    line_no: int
    field: WriteField
    value: str
    # As `ProposedDecision.prompt`: stamped, stored, outside the hash.
    prompt: str | None = None

    def _content(self) -> dict[str, object]:
        return {
            "action": "bravo_write",
            "case_kind": self.case_kind.value,
            "case_id": str(self.case_id),
            "case_version": self.case_version,
            "line_no": self.line_no,
            "field": self.field,
            "value": self.value,
        }

    def stored(self) -> dict[str, object]:
        return {
            **self._content(),
            **({} if self.prompt is None else {"prompt": self.prompt}),
        }

    @property
    def content_hash(self) -> str:
        canonical = json.dumps(
            self._content(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def from_stored(cls, row: Mapping[str, object]) -> ProposedBravoWrite:
        field_name = str(row["field"])
        if field_name not in get_args(WriteField):
            raise ValueError(f"unknown field {field_name!r}")
        version, line_no = row["case_version"], row["line_no"]
        if not isinstance(version, int) or not isinstance(line_no, int):
            raise ValueError("case_version and line_no are integers")
        return cls(
            case_kind=CaseKind(str(row["case_kind"])),
            case_id=uuid.UUID(str(row["case_id"])),
            case_version=version,
            line_no=line_no,
            field=field_name,  # type: ignore[arg-type]
            value=str(row["value"]),
            prompt=None if row.get("prompt") is None else str(row["prompt"]),
        )


@dataclass(frozen=True, slots=True)
class ProposedAssignment:
    """The case given to one person, as DW1 states it in the case's
    conversation (ticket 79), bound like `ProposedDecision`: the head confirms
    `content_hash` (the person and the name they were shown), and code gives
    the case only on a case still at ``case_version``, through the assignment
    service, which checks the right again."""

    case_kind: CaseKind
    case_id: uuid.UUID
    case_version: int
    assignee: uuid.UUID
    name: str
    prompt: str | None = None

    def _content(self) -> dict[str, object]:
        return {
            "action": "assign",
            "case_kind": self.case_kind.value,
            "case_id": str(self.case_id),
            "case_version": self.case_version,
            "assignee": str(self.assignee),
            "name": self.name,
        }

    def stored(self) -> dict[str, object]:
        return {**self._content(), **({} if self.prompt is None else {"prompt": self.prompt})}

    @property
    def content_hash(self) -> str:
        canonical = json.dumps(
            self._content(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def from_stored(cls, row: Mapping[str, object]) -> ProposedAssignment:
        version = row["case_version"]
        if not isinstance(version, int):
            raise ValueError("case_version is not an integer")
        return cls(
            case_kind=CaseKind(str(row["case_kind"])),
            case_id=uuid.UUID(str(row["case_id"])),
            case_version=version,
            assignee=uuid.UUID(str(row["assignee"])),
            name=str(row["name"]),
            prompt=None if row.get("prompt") is None else str(row["prompt"]),
        )


Proposal = ProposedDecision | ProposedBravoWrite | ProposedAssignment


def proposal_from_stored(row: Mapping[str, object]) -> Proposal:
    """A turn's stored statement: a Bravo write and an assignment name their
    action; a flag's decision, stored before there was a second kind, none."""
    if row.get("action") == "bravo_write":
        return ProposedBravoWrite.from_stored(row)
    if row.get("action") == "assign":
        return ProposedAssignment.from_stored(row)
    return ProposedDecision.from_stored(row)


# The case page's own control a case conversation offers for a step asked
# of it (ticket 46): the page draws it, with its own gate and API, where
# it has one; the chat starts nothing.
CaseOffer = Literal["reply_draft", "customer_reminder", "thread_summary"]
OFFERS: Final[Mapping[QuestionKind, CaseOffer]] = MappingProxyType(
    {
        QuestionKind.DRAFT_REPLY: "reply_draft",
        QuestionKind.REMIND_CUSTOMER: "customer_reminder",
        QuestionKind.EXPLAIN_THREAD: "thread_summary",
    }
)


@dataclass(frozen=True, slots=True)
class CaseKey:
    """The case a conversation is bound to, as the case page's route names
    it (ticket 46): code checks the caller may read it before anything else."""

    kind: CaseKind
    case_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class CaseRef:
    """A case an answer rests on: the page it links to, and what it is called."""

    kind: CaseKind
    case_id: uuid.UUID
    label: str


@dataclass(frozen=True, slots=True)
class Turn:
    """One question and its answer, as a session keeps it."""

    session_id: uuid.UUID
    seq: int
    asked_at: datetime
    question: str
    kind: QuestionKind
    reference: str | None
    answer: str
    cites: tuple[CaseRef, ...]
    # The case the conversation is on after this turn, if any.
    focus: CaseRef | None
    answered_by: Literal["model", "code"]
    # A decision or a Bravo write stated for the PIC to confirm (ticket 56);
    # None otherwise.
    proposal: Proposal | None = None


@dataclass(frozen=True, slots=True)
class Session:
    """A person's conversation: on one case (``case``, bound by code from the
    case page's route, ticket 46), or their one general conversation (None).
    Code finds it by the case, never by an id a client sends."""

    session_id: uuid.UUID
    user_id: uuid.UUID
    title: str
    created_at: datetime
    last_turn_at: datetime
    case: CaseRef | None = None
    # When the person last saw the conversation; an answer kept after it is
    # unread (the mark on the case lists). None: never seen.
    last_read_at: datetime | None = None

    @property
    def unread(self) -> bool:
        return self.last_read_at is None or self.last_turn_at > self.last_read_at


_SEPARATORS: Final = re.compile(r"[\s\-_/.]+")


def same_reference(written: str, stored: str | None) -> bool:
    """Whether a number a person wrote names ``stored``: case, spaces and
    separators aside (`nrv po 26 0457` is `NRV-PO-26-0457`). Never a prefix
    or a part: `0457` alone names nothing."""
    if stored is None:
        return False
    return _SEPARATORS.sub("", written).casefold() == _SEPARATORS.sub("", stored).casefold()


# ----------------------------------------------------------- the words --

ORDER_STATE: Final[dict[str, str]] = {
    "received": "Đã nhận",
    "checked": "Đã kiểm tra",
    "in_review": "Chờ PIC tự kiểm",
    "correction_requested": "Chờ khách sửa PO",
    "prepared": "PIC đã tự kiểm",
    "uploaded_to_bravo": "Đã nhập Bravo",
    "cross_checked": "Đã kiểm chéo",
    "confirmation_sent": "Đã gửi xác nhận, chờ khách",
    "confirmed": "Khách đã đồng ý",
    "change_review": "Xem thay đổi PO",
    "closed": "Đã đóng",
}

QUOTE_STATE: Final[dict[str, str]] = {
    "received": "Đã nhận",
    "ycbg_drafted": "Đã soạn YCBG",
    "ycbg_recorded": "Đã lập YCBG trên Bravo",
    "sent_to_design": "Chờ Design",
    "design_replied": "Design đã phản hồi",
    "spec_discussion": "Thảo luận spec với khách",
    "priced": "Đã định giá",
    "pending_approval": "Chờ duyệt",
    "returned": "Bị trả lại định giá",
    "approved": "Đã duyệt",
    "sent": "Đã gửi khách",
    "master_list_recorded": "Đã ghi master list",
    "declined": "Từ chối báo giá",
}

ACTION: Final[dict[str, str]] = {
    "self_check": "Tự kiểm và quyết định từng cờ",
    "bravo_entry": "Nhập Bravo và ghi số đơn",
    "cross_check": "Kiểm chéo với Bravo",
    "confirm": "Gửi xác nhận cho khách",
    "apply_change": "Áp dụng thay đổi PO trên Bravo",
    "resend_cross_check": "Gửi kiểm chéo lại",
    "draft_ycbg": "Soạn YCBG",
    "record_ycbg": "Ghi số YCBG trên Bravo",
    "send_to_design": "Gửi Design",
    "price": "Định giá",
    "settle_spec": "Chốt spec với khách",
    "submit": "Trình duyệt báo giá",
    "approve": "Duyệt báo giá",
    "reprice": "Định giá lại",
    "send": "Gửi báo giá cho khách",
    "record_master_list": "Xác nhận master list",
}

# What DW1 answers and every sentence code says are the tenant's copy
# (`application.assistant_copy`, `configs/copy/sales_assistant@<v>.yaml`).


def day(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def label(table: dict[str, str], code: str) -> str:
    """A code's words; a code the table lacks shows as itself, never as
    another code's words."""
    return table.get(code, code)
