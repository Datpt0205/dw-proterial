"""The kinds of hand-off a tenant's ``handoffs`` skill names, and the closed
sets each maps onto (ticket 42 family 5, dw_sales ADR 0014).

A message routed to Sales as a delivery change, a complaint or a sample
request gets a hand-off to PC or QA pre-filled from the customer's words
(ticket 33). Which KINDS of hand-off a tenant writes, the words that tell the
model what each is about and what to copy, and Sales' label for each, are the
tenant's: they live in its version of the ``handoffs`` skill. What a kind DOES
stays code's, from two closed sets:

- **``asks``**: the fields it is copied into, one of the three typed shapes
  ticket 33 built (`ASKS`): the order's lines and their new quantities and
  dates, the lot and the customer's sentences about a problem, or the sample
  items and their quantity. Code locates, parses and resolves each value as
  it does for the platform's kinds; a skill adds no field.
- **``to``**: the team it goes to, one of `HandoffTeam` (PC or QA). A team,
  never an address, a person or a send: Sales picks the recipients and sends
  it from their own mailbox. A skill cannot add a recipient.

A kind is the name of the mail kind it is for: the kind the message's reading
stamped (the tenant's ``mail-kinds`` skill, or the one call's), so a
company's new kind of mail gets its hand-off by a skill version, no code. A
name of a platform route that is no hand-off (an order, a quotation request,
a reply, a portal notice, ``other``) is refused: those go where code sends
them, with no hand-off. Each block::

    - kind: certificate_request
      asks: lot_and_problem
      to: qa
      label: Xin chứng chỉ chất lượng
      means: the customer asks for a quality certificate ...

`handoff_kinds_of` reads the blocks (`skill_blocks.blocks_of`) and refuses
anything else; it is asked when a version is proposed and again whenever it
is served (a version that no longer reads is not used: the hand-off is read
as with the step off).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, Literal, Self, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dw_sales.domain.handoffs import HandoffKind, HandoffTeam
from dw_sales.domain.message_intent import IntentKind, KindName
from dw_sales.domain.skill_blocks import blocks_of

__all__ = [
    "ASKS",
    "HANDOFFS",
    "PLATFORM_KINDS",
    "TEAMS",
    "HandoffKindSpec",
    "HandoffKinds",
    "handoff_kinds_of",
]

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

# The skill whose kinds pre-fill a routed message's hand-off.
HANDOFFS: Final = "handoffs"
# The fields a kind asks for, by the words a skill writes: each one of the
# three typed shapes of ticket 33 (`handoffs.MODEL_SCHEMAS`).
Asks = Literal["order_lines", "lot_and_problem", "sample_items"]
ASKS: Final[Mapping[Asks, HandoffKind]] = MappingProxyType(
    {
        "order_lines": "delivery_change",
        "lot_and_problem": "complaint",
        "sample_items": "sample_request",
    }
)
TEAMS: Final[frozenset[str]] = frozenset(get_args(HandoffTeam))
# The platform's kinds of hand-off: each a routing reason ticket 33 reads.
PLATFORM_KINDS: Final[frozenset[str]] = frozenset(get_args(HandoffKind))
# Platform routes that take no hand-off: a kind of that name is refused.
_NOT_A_HANDOFF: Final = frozenset(get_args(IntentKind)) - PLATFORM_KINDS
MAX_KINDS: Final = 20

_FIELDS: Final = frozenset({"asks", "to", "label", "means"})


class HandoffKindSpec(BaseModel):
    """One kind of hand-off as the skill names it."""

    model_config = _FROZEN

    name: KindName
    asks: Asks
    to: HandoffTeam
    label: str | None = Field(default=None, min_length=1, max_length=60)
    means: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def _a_handoff(self) -> Self:
        if self.name in _NOT_A_HANDOFF:
            raise ValueError(f"{self.name} is a route that takes no hand-off")
        if self.label is None and self.name not in PLATFORM_KINDS:
            raise ValueError(f"the kind {self.name} needs a label: Sales sees it by one")
        return self

    @property
    def shape(self) -> HandoffKind:
        """The typed fields it is copied into."""
        return ASKS[self.asks]


class HandoffKinds(BaseModel):
    """Every kind a version of the skill names, in its order."""

    model_config = _FROZEN

    kinds: tuple[HandoffKindSpec, ...] = Field(min_length=1, max_length=MAX_KINDS)

    @model_validator(mode="after")
    def _each_once(self) -> Self:
        names = [kind.name for kind in self.kinds]
        if len(set(names)) != len(names):
            raise ValueError("the skill names a kind twice")
        return self

    def named(self, name: str) -> HandoffKindSpec | None:
        return next((kind for kind in self.kinds if kind.name == name), None)


def handoff_kinds_of(instructions: str) -> HandoffKinds:
    """The kinds ``instructions`` name (module docstring). Raises ValueError,
    saying what is wrong in words, for a block that does not read or a set
    that does not hold."""
    blocks = [
        {"name": block.pop("kind"), **block} for block in blocks_of(instructions, "kind", _FIELDS)
    ]
    if not blocks:
        raise ValueError('the skill names no kind: each starts with a line "- kind: <name>"')
    for block in blocks:
        for key, allowed in (("asks", ASKS), ("to", TEAMS)):
            value = block.get(key)
            if value is None:
                raise ValueError(f"the kind {block['name']} names no {key}")
            if value not in allowed:
                raise ValueError(
                    f"the kind {block['name']} names {key} {value}, which is not one of "
                    + ", ".join(sorted(allowed))
                )
    return HandoffKinds.model_validate({"kinds": blocks})
