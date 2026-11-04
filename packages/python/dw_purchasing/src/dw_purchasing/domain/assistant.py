"""Status questions DW2 answers from live data (DW02 function 6).

The design DW1 ships (dw_sales ADR 0007), in DW2's words: a catalog, not a
chat. Three kinds of question and `out_of_scope` for everything else. The
model only reads a question into a `QuestionIntent`; code finds the case
among those the asker may see and words the answer itself. An answer names
no amount, whoever asks.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

# A question as a person types it; the API refuses a longer one.
QUESTION_CHARS: Final = 500
# The turns of a session the intent call is shown, newest last.
HISTORY_TURNS: Final = 6
# A session is kept this long after its last turn (`prune_assistant_sessions`).
SESSION_DAYS: Final = 30


class AssistantQuestionKind(StrEnum):
    """What DW2 answers, and everything else."""

    # Where a purchase request stands, by its PR number.
    REQUEST_STATUS = "request_status"
    # What waits on the asker: approvals, reviews, orders to follow.
    MY_WORK = "my_work"
    # Order lines past their date with less arrived than ordered.
    LATE_ORDERS = "late_orders"
    OUT_OF_SCOPE = "out_of_scope"


class QuestionIntent(BaseModel):
    """What the model reads a question as. Never an id: a number the person
    wrote, which code looks up, and whether the question is about the case
    the conversation was on."""

    model_config = _FROZEN

    kind: AssistantQuestionKind
    # The PR number as written, when the question names one.
    reference: str | None = Field(default=None, min_length=1, max_length=64)
    about_previous: bool = False


@dataclass(frozen=True, slots=True)
class CaseRef:
    """A case an answer rests on: its id and its PR number."""

    case_id: uuid.UUID
    label: str


@dataclass(frozen=True, slots=True)
class Turn:
    session_id: uuid.UUID
    seq: int
    asked_at: datetime
    question: str
    kind: AssistantQuestionKind
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


def same_reference(written: str, stored: str) -> bool:
    """Whether a number a person wrote names ``stored``: case, spaces and
    separators aside (`pr 2611 004` is `PR-2611-004`). Never a part:
    `004` alone names nothing."""
    return _SEPARATORS.sub("", written).casefold() == _SEPARATORS.sub("", stored).casefold()


def written_in(reference: str, question: str) -> bool:
    """Whether ``question`` writes ``reference`` (separators and case aside):
    the model may only copy a number, never invent one."""
    squeezed = _SEPARATORS.sub("", question).casefold()
    return bool(reference.strip()) and _SEPARATORS.sub("", reference).casefold() in squeezed


def title_of(question: str) -> str:
    """A session's title: its first question, on one line, at most 80."""
    line = " ".join(question.split())
    return line if len(line) <= 80 else line[:79] + "…"


# ----------------------------------------------------------- the words --

# The case states as the pages say them (`apps/web/.../labels.ts`
# `CASE_STATUS`); `test_purchasing_assistant.py` holds the two equal.
CASE_STATE: Final[dict[str, str]] = {
    "received": "Đã nhận",
    "awaiting_approval": "Chờ duyệt",
    "approved": "Đã duyệt",
    "rejected": "Từ chối",
    "rfq_drafted": "Đang hỏi giá",
    "awaiting_reapproval": "Chờ duyệt lại",
    "supplier_selected": "Đã chọn nhà cung cấp",
    "po_drafted": "Đã soạn PO",
}

CATALOG: Final = (
    "DW2 trả lời: một yêu cầu mua hàng đang ở bước nào (theo số PR), việc"
    " đang chờ bạn, và các dòng đơn đặt hàng trễ hạn. Câu trả lời không có số tiền."
)
