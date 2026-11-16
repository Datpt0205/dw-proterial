"""The kinds of mail a tenant's mail-classifying skill names, and the one
legal route each takes (ticket 42 family 1, dw_sales ADR 0014).

A message no reader accepted is classified by its words (ticket 31). Which
KINDS of mail a tenant tells apart, and the words that say what each is, are
the tenant's: they live in its version of the ``mail-kinds`` skill, a text a
person proposes and the head approves, never code. What a kind DOES stays
code's: each kind names exactly one route from the closed set of legal routes
(`ROUTES`, today's kinds of `message_intent.IntentKind`, each a row of
`order_intake.INTENT_ROUTES`), so a tenant's new kind of mail goes where an
existing one goes. A skill invents no route, no owner, no recipient and no
send.

**How a skill names its kinds.** In its instructions, one block per kind, at
the start of a line::

    - kind: invoice_question
      route: other
      label: Hỏi hoá đơn
      means: the customer asks about an invoice or a payment ...
        (a longer meaning goes on, indented)

``kind`` is its name (lowercase words joined by ``_``), ``route`` one of
`ROUTES`, ``label`` the words Sales sees (needed for a kind the platform does
not ship; a platform kind without one shows the platform's word), ``means``
what the model reads it by. `mail_kinds_of` reads the blocks and refuses
anything else in them: an unknown route, a second kind of one name, a key it
does not know. It is asked when a version is proposed (an unknown route
refuses the proposal) and again whenever the skill is served (a version that
no longer reads is not used, and the mail is read as with the step off).
"""

from __future__ import annotations

import re
from typing import Final, Literal, Self, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dw_sales.domain.message_intent import IntentKind, KindName

__all__ = [
    "MAIL_KINDS",
    "MAX_KINDS",
    "NO_KIND",
    "ROUTES",
    "MailKind",
    "MailKinds",
    "ReadRoute",
    "mail_kinds_of",
]

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

# The skill whose kinds classify a mail no reader accepted.
MAIL_KINDS: Final = "mail-kinds"
# The legal routes a kind may take: the platform's own kinds, each a row of
# `order_intake.INTENT_ROUTES` (a test holds the two together).
ROUTES: Final[frozenset[str]] = frozenset(get_args(IntentKind))
# What the model answers when no kind the skill names fits.
NO_KIND: Final = "none"
# Where a mail is read into: a legal route, or ``none`` for no kind read.
ReadRoute = IntentKind | Literal["none"]
# A company tells apart a few dozen kinds of mail at most; every one is in the
# schema of every call.
MAX_KINDS: Final = 40

_START: Final = re.compile(r"^- kind:[ \t]*(.*)$")
_FIELD: Final = re.compile(r"^[ \t]+(route|label|means):[ \t]*(.*)$")
_KEY: Final = re.compile(r"^[ \t]+([A-Za-z_]+):")


class MailKind(BaseModel):
    """One kind of mail as the skill names it."""

    model_config = _FROZEN

    name: KindName
    route: IntentKind
    label: str | None = Field(default=None, min_length=1, max_length=60)
    means: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def _named_for_sales(self) -> Self:
        if self.name == NO_KIND:
            raise ValueError(f'"{NO_KIND}" is the answer that names no kind, not a kind')
        if self.label is None and self.name not in ROUTES:
            raise ValueError(f"the kind {self.name} needs a label: Sales sees it by one")
        return self


class MailKinds(BaseModel):
    """Every kind a version of the skill names, in its order."""

    model_config = _FROZEN

    kinds: tuple[MailKind, ...] = Field(min_length=1, max_length=MAX_KINDS)

    @model_validator(mode="after")
    def _each_once(self) -> Self:
        names = [kind.name for kind in self.kinds]
        if len(set(names)) != len(names):
            raise ValueError("the skill names a kind twice")
        return self

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(kind.name for kind in self.kinds)

    def named(self, name: str) -> MailKind | None:
        return next((kind for kind in self.kinds if kind.name == name), None)


def mail_kinds_of(instructions: str) -> MailKinds:
    """The kinds ``instructions`` name (module docstring). Raises ValueError,
    saying what is wrong in words, for a block that does not read or a set
    that does not hold."""
    blocks: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    last: str | None = None
    for raw in instructions.replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        if start := _START.match(line):
            current = {"name": start.group(1).strip()}
            blocks.append(current)
            last = None
            continue
        if current is None:
            continue
        if not line.strip() or not line[0].isspace():
            # A blank line or the next paragraph ends the block.
            current, last = None, None
            continue
        if field := _FIELD.match(line):
            key = field.group(1)
            if key in current:
                raise ValueError(f"the kind {current['name']} says {key} twice")
            current[key] = field.group(2).strip()
            last = key
        elif key_like := _KEY.match(line):
            raise ValueError(f"the kind {current['name']} has an unknown line {key_like.group(1)}")
        elif last is not None:
            current[last] = f"{current[last]} {line.strip()}".strip()
        else:
            raise ValueError(f"the kind {current['name']} has a line that belongs to nothing")
    if not blocks:
        raise ValueError('the skill names no kind: each starts with a line "- kind: <name>"')
    for block in blocks:
        route = block.get("route")
        if route is None:
            raise ValueError(f"the kind {block['name']} names no route")
        if route not in ROUTES:
            raise ValueError(
                f"the kind {block['name']} names the route {route}, which is not one of "
                + ", ".join(sorted(ROUTES))
            )
    return MailKinds.model_validate({"kinds": blocks})
