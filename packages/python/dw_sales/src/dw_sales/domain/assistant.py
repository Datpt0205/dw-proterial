"""Status questions DW1 answers from live data (dw_sales ADR 0007; the
contract's DW01 criterion 6).

A catalog, not a chat: four kinds of question, and `out_of_scope` for
everything else. The model only reads a question into a `QuestionIntent`;
code finds the case among those the caller may see and builds the facts. An
answer carries no amount, whoever asks and whatever the channel.

The labels below are the glossary's (`CONTEXT.md`, "Order case states",
"Quote case states") and the work list's own words (`labels.ts`'s `ACTION`);
`test_assistant.py` reads both files, so a label changed on either side turns
it red instead of drifting (failure-modes #2).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Final, Literal

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
    OUT_OF_SCOPE = "out_of_scope"


class QuestionIntent(BaseModel):
    """What the model reads a question as. Never an id: a number the person
    wrote, which code looks up, and whether the question is about the case
    the conversation was on."""

    model_config = _FROZEN

    kind: QuestionKind
    # The PO or request number as written, when the question names one.
    reference: str | None = Field(default=None, min_length=1, max_length=64)
    about_previous: bool = False


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


@dataclass(frozen=True, slots=True)
class Session:
    session_id: uuid.UUID
    user_id: uuid.UUID
    title: str
    created_at: datetime
    last_turn_at: datetime


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
    "confirmed": "Đã xác nhận",
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

# What DW1 answers, said whenever a question is outside it.
CATALOG: Final = (
    "DW1 trả lời được: trạng thái một PO (ghi số PO), trạng thái một yêu cầu báo giá "
    "(ghi số yêu cầu), việc đang chờ bạn, và việc đã quá hạn."
)


def day(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def label(table: dict[str, str], code: str) -> str:
    """A code's words; a code the table lacks shows as itself, never as
    another code's words."""
    return table.get(code, code)
