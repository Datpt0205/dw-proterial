"""The kinds of mail to a customer a tenant's ``reply-drafts`` skill names,
each worded as one of the platform's drafts (ticket 42 family 5, dw_sales
ADR 0014).

The model words a mail to a customer about an order beside the template's
draft (ticket 32, `application.reply_drafts`): an answer to the customer's
question, PC's answer to a change (6-DW4, 6-DW3), the confirmation. Which
KINDS a tenant offers, Sales' label for each and the words that say how each
is written are the tenant's: they live in its version of the ``reply-drafts``
skill. What a kind DOES stays code's: each names exactly one of the
platform's drafts (``drafts``, `ReplyKind`), and from it takes everything
that is not words:

- **when it is offered**: the platform draft's own gate (`ORDER_GATES`, the
  order's state, the customer's channel, the caller's scope);
- **the facts** the mail may state (`reply_facts`, never an amount) and the
  check every figure passes (`check_reply`);
- **the recipients**: the customer's contacts in master data. Nothing is sent.

So a skill cannot add a recipient, a send, a price, an amount or a tool: it
has no line for any. Each block::

    - kind: short_confirmation
      drafts: confirmation_draft
      label: Xác nhận ngắn
      means: confirm the order in three lines ...

`reply_kinds_of` reads the blocks (`skill_blocks.blocks_of`) and refuses
anything else; it is asked when a version is proposed and again whenever it
is served (a version that no longer reads is not used: the draft is worded
as with the step off).
"""

from __future__ import annotations

from typing import Final, Literal, Self, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dw_sales.domain.message_intent import KindName
from dw_sales.domain.skill_blocks import blocks_of

__all__ = [
    "REPLY_DRAFTS",
    "REPLY_KINDS",
    "ReplyKind",
    "ReplyKindSpec",
    "ReplyKinds",
    "reply_kinds_of",
]

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

# The skill whose kinds word a mail to a customer.
REPLY_DRAFTS: Final = "reply-drafts"
# The platform's drafts, each the legal moves of ticket 32.
ReplyKind = Literal[
    "question_answer", "change_can_do_draft", "change_options_draft", "confirmation_draft"
]
REPLY_KINDS: Final[tuple[ReplyKind, ...]] = get_args(ReplyKind)
MAX_KINDS: Final = 20

_FIELDS: Final = frozenset({"drafts", "label", "means"})


class ReplyKindSpec(BaseModel):
    """One kind of mail as the skill names it."""

    model_config = _FROZEN

    name: KindName
    drafts: ReplyKind
    label: str | None = Field(default=None, min_length=1, max_length=60)
    means: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def _named_for_sales(self) -> Self:
        if self.name in REPLY_KINDS and self.name != self.drafts:
            raise ValueError(f"the kind {self.name} is the platform's draft of that name")
        if self.label is None and self.name not in REPLY_KINDS:
            raise ValueError(f"the kind {self.name} needs a label: Sales sees it by one")
        return self


class ReplyKinds(BaseModel):
    """Every kind a version of the skill names, in its order."""

    model_config = _FROZEN

    kinds: tuple[ReplyKindSpec, ...] = Field(min_length=1, max_length=MAX_KINDS)

    @model_validator(mode="after")
    def _each_once(self) -> Self:
        names = [kind.name for kind in self.kinds]
        if len(set(names)) != len(names):
            raise ValueError("the skill names a kind twice")
        return self

    def named(self, name: str) -> ReplyKindSpec | None:
        return next((kind for kind in self.kinds if kind.name == name), None)

    def drafting(self, drafts: str) -> tuple[ReplyKindSpec, ...]:
        """The kinds worded as the platform's draft ``drafts``, in order."""
        return tuple(kind for kind in self.kinds if kind.drafts == drafts)


def reply_kinds_of(instructions: str) -> ReplyKinds:
    """The kinds ``instructions`` name (module docstring). Raises ValueError,
    saying what is wrong in words, for a block that does not read or a set
    that does not hold."""
    blocks = [
        {"name": block.pop("kind"), **block} for block in blocks_of(instructions, "kind", _FIELDS)
    ]
    if not blocks:
        raise ValueError('the skill names no kind: each starts with a line "- kind: <name>"')
    for block in blocks:
        drafts = block.get("drafts")
        if drafts is None:
            raise ValueError(f"the kind {block['name']} names no draft it is worded as")
        if drafts not in REPLY_KINDS:
            raise ValueError(
                f"the kind {block['name']} drafts {drafts}, which is not one of "
                + ", ".join(sorted(REPLY_KINDS))
            )
    return ReplyKinds.model_validate({"kinds": blocks})
