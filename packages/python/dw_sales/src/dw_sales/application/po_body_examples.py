"""Decided values of a PO in a mail, shown as examples (ticket 43's second
step, dw_sales ADR 0015 decision 5).

`po_body_extraction` reads a whole mail, and what a customer's mails share is
how that customer writes a value, not which mail is most like this one: the
examples are the sender's customer's newest decided values, not the nearest
by meaning, so no index is asked. Each is cut from the stored mail by its
anchors (`domain.po_body_reading.written`), never from what a person typed:

- a value Sales confirmed: in a line like this, the field is these words;
- a value Sales corrected: these words are not the field (where the right
  words are, the person did not say, and DW does not guess).

A value the mail never wrote is no example. Every failure to find them is a
reading without them, never a refusal of the mail.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from typing import Any, Final, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from dw_sales.application.ports import SalesScope
from dw_sales.domain.catalog import CustomerCode

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

# The most decided values one reading is shown: each a line of the mail's
# prompt, which the mail's own room pays for (`po_body_reading.PoBodyReader`).
MAX_SHOWN: Final = 6


class PoBodyExample(BaseModel):
    """One decided value: the text line it is on, the field and its words,
    and whether the person kept them (``right``) or corrected them."""

    model_config = _FROZEN

    label_id: uuid.UUID
    case_id: uuid.UUID
    customer_code: CustomerCode | None
    decided_at: AwareDatetime
    field: str = Field(min_length=1, max_length=64)
    line: str = Field(min_length=1, max_length=400)
    words: str = Field(min_length=1, max_length=300)
    right: bool


class PoBodyExamplesPort(Protocol):
    """The decided values of one customer's mail POs, under the scope's RLS."""

    async def latest(
        self, scope: SalesScope, customer_code: str, limit: int
    ) -> Sequence[PoBodyExample]:
        """The newest decided values of ``customer_code`` this scope holds,
        newest first, at most ``limit``; a value decided again counts by its
        newest decision only."""
        ...


def shown(examples: Sequence[PoBodyExample]) -> str:
    """The examples as the prompt's `examples` variable (JSON), at most
    `MAX_SHOWN`, one per line and field: the field by the answer's own name
    (``quantity_span``), its words under ``right`` or ``wrong``."""
    seen: set[tuple[str, str]] = set()
    found: list[dict[str, Any]] = []
    for example in examples:
        key = (example.line, example.field)
        if key in seen:
            continue
        seen.add(key)
        found.append(
            {
                "line": example.line,
                "field": f"{example.field}_span",
                "right" if example.right else "wrong": example.words,
            }
        )
        if len(found) == MAX_SHOWN:
            break
    return json.dumps(found, ensure_ascii=False)
