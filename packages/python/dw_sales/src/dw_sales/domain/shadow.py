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
from typing import Final, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, model_validator

from dw_sales.domain.catalog import CustomerCode
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.labelled_cases import LabelledCase, NewId
from dw_sales.domain.order_checks import SHADOW_STEPS, MappedLine, ModelStep

__all__ = ["ShadowReading", "description_shadows", "item_key", "shadow_label"]

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
_VERSION = r"^[a-z][a-z0-9_.-]*@\d+\.\d+\.\d+$"
# The longest item key: a message id is at most 512, an attachment id 128.
ITEM_KEY_MAX: Final = 700


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
