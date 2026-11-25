"""A model step's reading made in shadow, and the labelled case a person's
decision makes of it (ticket 67, dw_sales ADR 0015 decision 4).

A step the tenant lists in `ModelAssist.shadow` reads while it is not on and
passing: the reading is kept as a `ShadowReading` and applied nowhere, shown
nowhere. When a person makes the decision the step would have proposed, the
step's own service takes the reading for that item and `shadow_label` makes
the labelled case: what the model proposed beside what the person kept,
gated ``shadow`` (logged, not applied), so it counts toward the step's
threshold and the head's view as a gated result's label does.

A reading names its item by `item_key`, the key the step's gate already
uses for the same item (``<message>:<attachment or ->:<line or 0>:<step>``),
so the reading kept when the mail is processed and the decision taken later
on the case find each other without the case existing when the model read.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, model_validator

from dw_sales.domain.catalog import CustomerCode
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.labelled_cases import LabelledCase, NewId, value_text
from dw_sales.domain.message_intent import IntentKind, IntentReading
from dw_sales.domain.order_checks import SHADOW_STEPS, MappedLine, ModelStep
from dw_sales.domain.orders import OrderCase, PoDocument
from dw_sales.domain.reply_intent import ProposedStep, ReplyReading, proposed_step

__all__ = [
    "NO_STEP",
    "REPLY_MOVES",
    "REPLY_SHADOW_STEPS",
    "ShadowReading",
    "description_shadows",
    "item_key",
    "kind_shadow",
    "po_body_labels",
    "po_body_shadow",
    "po_match_key",
    "reply_shadow",
    "shadow_label",
]

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
_VERSION = r"^[a-z][a-z0-9_.-]*@\d+\.\d+\.\d+$"
# The longest item key: a message id is at most 512, an attachment id 128.
ITEM_KEY_MAX: Final = 700
# The longest match key: a customer code and a printed PO number.
MATCH_KEY_MAX: Final = 300


def item_key(
    message_id: str, attachment_id: str | None, line_no: int | None, step: ModelStep
) -> str:
    """The item a reading is of, as the step's gate names it."""
    return f"{message_id}:{attachment_id or '-'}:{line_no or 0}:{step.value}"


class ShadowReading(BaseModel):
    """What a step proposed for one item while it read in shadow: the
    proposal in the form the step's labelled case takes, and the versions
    and confidence it was read with."""

    model_config = _FROZEN

    reading_id: uuid.UUID
    step: ModelStep
    item_key: str = Field(min_length=1, max_length=ITEM_KEY_MAX)
    message_id: str = Field(pattern=r"^[!-~]{1,512}$")
    attachment_id: str | None = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    line_no: int | None = Field(ge=1, le=99_999)
    field: str = Field(pattern=r"^[a-z_]{1,40}$")
    proposed: JsonValue
    prompt: str = Field(pattern=_VERSION)
    model_profile: str | None = Field(min_length=1, max_length=64)
    rules: str | None = Field(pattern=_VERSION)
    confidence: float | None = Field(ge=0.0, le=1.0)
    read_at: AwareDatetime
    # The case the item belongs to, where the decision that labels it is
    # taken on the case and not on the item (a reply's next move).
    case_id: uuid.UUID | None = None
    # What a later record is found by, where the decision that labels it is
    # taken on another record (a PO in the mail: the customer and the PO
    # number its order case is opened under when the PO arrives as a file).
    match_key: str | None = Field(default=None, min_length=1, max_length=MATCH_KEY_MAX)

    @model_validator(mode="after")
    def _a_shadow_step(self) -> Self:
        if self.step not in SHADOW_STEPS:
            raise ValueError(f"{self.step.value} has no shadow reading")
        if self.proposed is None:
            raise ValueError("a shadow reading holds what the model proposed")
        if self.item_key != item_key(self.message_id, self.attachment_id, self.line_no, self.step):
            raise ValueError("the item key names another item")
        return self


def shadow_label(
    reading: ShadowReading,
    kept: JsonValue | None,
    *,
    lane: CaseKind,
    case_id: uuid.UUID | None,
    customer_code: CustomerCode | None,
    at: AwareDatetime,
    by: uuid.UUID,
    new_id: NewId,
) -> LabelledCase:
    """The labelled case a person's decision makes of ``reading``: its
    proposal beside what they kept (None: kept nothing), gated ``shadow``."""
    return LabelledCase(
        label_id=new_id(),
        decided_at=at,
        step=reading.step,
        lane=lane,
        case_id=case_id,
        customer_code=customer_code,
        message_id=reading.message_id,
        attachment_id=reading.attachment_id,
        line_no=reading.line_no,
        field=reading.field,
        proposed=reading.proposed,
        kept=kept,
        prompt=reading.prompt,
        model_profile=reading.model_profile,
        rules=reading.rules,
        decided_by=by,
        confidence=reading.confidence,
        gate="shadow",
    )


def description_shadows(
    read: Mapping[int, MappedLine],
    *,
    message_id: str,
    attachment_id: str | None,
    rules: str | None,
    at: AwareDatetime,
    new_id: NewId,
) -> list[ShadowReading]:
    """The lines a description reading read in shadow (`description_attributes`),
    each proposing its candidates in their order, as `mapping_label` labels
    them when the step is on. A line with no usable reading proposes nothing."""
    step = ModelStep.DESCRIPTION_ATTRIBUTES
    readings = []
    for line_no, mapped in sorted(read.items()):
        reading = mapped.reading
        if reading is None or reading.outcome != "read":
            continue
        readings.append(
            ShadowReading(
                reading_id=new_id(),
                step=step,
                item_key=item_key(message_id, attachment_id, line_no, step),
                message_id=message_id,
                attachment_id=attachment_id,
                line_no=line_no,
                field="prv_code",
                proposed=list(mapped.mapping.candidates),
                prompt=reading.prompt,
                model_profile=reading.model_profile,
                rules=rules,
                confidence=reading.confidence,
                read_at=at,
            )
        )
    return readings


# ------------------------------------------------------------ a reply's move --

# The readers of a customer's reply that read it in shadow side by side.
REPLY_SHADOW_STEPS: Final = (ModelStep.REPLY_INTENT, ModelStep.SKILL_INTENTS)
# A reading that proposes no move: the PIC taking one is a correction of it.
NO_STEP: Final = "none"
# The move a PIC takes on a case, by the case's kind and its status before
# and after, as each `ProposedStep` is that move (`reply_intent.ProposedStep`
# says which method; a test holds the two together). `await_revised_po`
# moves nothing, so nothing here labels it.
REPLY_MOVES: Final[Mapping[tuple[CaseKind, str, str], ProposedStep]] = MappingProxyType(
    {
        (CaseKind.ORDER, "correction_requested", "in_review"): "resume_review",
        (CaseKind.ORDER, "in_review", "correction_requested"): "request_correction",
        (CaseKind.ORDER, "confirmation_sent", "confirmed"): "record_accepted",
        (CaseKind.ORDER, "confirmation_sent", "change_review"): "record_declined",
        (CaseKind.QUOTE, "spec_discussion", "design_replied"): "settle_spec",
        (CaseKind.QUOTE, "design_replied", "spec_discussion"): "discuss_spec",
        (CaseKind.QUOTE, "spec_discussion", "declined"): "decline_customer_rejected_spec",
    }
)


def reply_shadow(
    step: ModelStep,
    reading: ReplyReading,
    *,
    message_id: str,
    case_kind: CaseKind,
    case_id: uuid.UUID,
    status: str,
    at: AwareDatetime,
    new_id: NewId,
) -> ShadowReading | None:
    """A customer's reply read in shadow by ``step``: the move its reading
    proposes for the case in ``status`` (`proposed_step`), or `NO_STEP`.
    None for a reading that read nothing."""
    if reading.outcome != "read":
        return None
    proposed = proposed_step("customer", case_kind.value, status, reading)
    return ShadowReading(
        reading_id=new_id(),
        step=step,
        item_key=item_key(message_id, None, None, step),
        message_id=message_id,
        attachment_id=None,
        line_no=None,
        field="next_step",
        proposed=proposed or NO_STEP,
        prompt=reading.prompt,
        model_profile=reading.model_profile,
        rules=reading.rules,
        confidence=None,
        read_at=at,
        case_id=case_id,
    )


# ----------------------------------------------------------- a mail's kind --


def kind_shadow(
    kind: IntentKind,
    reading: IntentReading,
    *,
    message_id: str,
    at: AwareDatetime,
    new_id: NewId,
) -> ShadowReading:
    """A mail no reader understood, read in shadow by `message_intent`: the
    kind it read (the platform's, the route it takes), for the kind the
    person picks as they mark the mail handled."""
    step = ModelStep.MESSAGE_INTENT
    return ShadowReading(
        reading_id=new_id(),
        step=step,
        item_key=item_key(message_id, None, None, step),
        message_id=message_id,
        attachment_id=None,
        line_no=None,
        field="kind",
        proposed=kind,
        prompt=reading.prompt,
        model_profile=reading.model_profile,
        rules=reading.rules,
        confidence=None,
        read_at=at,
    )


# ------------------------------------------------------ a PO in the mail --

# The values a PO in the mail is labelled on, of the PO and of each line: the
# ones an order is entered with. The PO number is the match key itself.
PO_HEADER_FIELDS: Final = ("po_date", "currency")
PO_LINE_FIELDS: Final = (
    "customer_item_code",
    "quantity",
    "uom",
    "unit_price",
    "requested_date",
)
# The move that settles an order's values: a person prepared it.
PO_SETTLED_MOVE: Final = ("in_review", "prepared")


def po_match_key(customer_code: str, po_no: str) -> str:
    """The order case a PO in the mail is found again by: its customer and
    its PO number, trimmed and case-folded as people retype one."""
    return f"{customer_code}:{' '.join(po_no.split()).casefold()}"


def _texts(holder: object, fields: tuple[str, ...]) -> dict[str, str]:
    values = {f: getattr(holder, f, None) for f in fields}
    return {f: value_text(v) for f, v in values.items() if v is not None}


def po_body_shadow(
    document: PoDocument,
    *,
    message_id: str,
    customer_code: str,
    at: AwareDatetime,
    new_id: NewId,
) -> ShadowReading:
    """A PO written in a mail going to a person, read in shadow by
    `po_body_extraction`: every value it read, by field and line, found
    again by its customer and PO number."""
    step = ModelStep.PO_BODY_EXTRACTION
    return ShadowReading(
        reading_id=new_id(),
        step=step,
        item_key=item_key(message_id, None, None, step),
        message_id=message_id,
        attachment_id=None,
        line_no=None,
        field="po",
        proposed={
            "header": _texts(document.header, PO_HEADER_FIELDS),
            "lines": {str(line.line_no): _texts(line, PO_LINE_FIELDS) for line in document.lines},
        },
        prompt=document.parser_version,
        model_profile=document.model_profile,
        rules=None,
        confidence=None,
        read_at=at,
        match_key=po_match_key(customer_code, document.header.po_no),
    )


def po_body_labels(
    reading: ShadowReading,
    case: OrderCase,
    *,
    at: AwareDatetime,
    by: uuid.UUID,
    new_id: NewId,
) -> list[LabelledCase]:
    """What a PO read in shadow is labelled with once its order case is
    prepared: each value read beside the value the case holds as entered
    (Sales' corrections included), one labelled case per value. A line the
    reading names that the case does not hold kept nothing (a rejection)."""
    proposed = reading.proposed
    assert isinstance(proposed, dict)
    header = case.effective_header
    lines = {line.line_no: line.effective for line in case.lines}
    pairs: list[tuple[int | None, str, JsonValue, JsonValue | None]] = []
    read_header = proposed.get("header") or {}
    assert isinstance(read_header, dict)
    kept_header = _texts(header, PO_HEADER_FIELDS)
    pairs += [(None, f, v, kept_header.get(f)) for f, v in sorted(read_header.items())]
    read_lines = proposed.get("lines") or {}
    assert isinstance(read_lines, dict)
    for number, values in sorted(read_lines.items(), key=lambda item: int(item[0])):
        assert isinstance(values, dict)
        line = lines.get(int(number))
        kept = {} if line is None else _texts(line, PO_LINE_FIELDS)
        pairs += [(int(number), f, v, kept.get(f)) for f, v in sorted(values.items())]
    return [
        LabelledCase(
            label_id=new_id(),
            decided_at=at,
            step=reading.step,
            lane=CaseKind.ORDER,
            case_id=case.case_id,
            customer_code=case.customer_code,
            message_id=reading.message_id,
            attachment_id=None,
            line_no=line_no,
            field=field,
            proposed=value,
            kept=kept,
            prompt=reading.prompt,
            model_profile=reading.model_profile,
            rules=case.rules_version,
            decided_by=by,
            confidence=None,
            gate="shadow",
        )
        for line_no, field, value, kept in pairs
        if value is not None
    ]
