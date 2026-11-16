"""A routed message's hand-off pre-filled by the kinds the tenant's
``handoffs`` skill names (ticket 42 family 5, dw_sales ADR 0014).

Ticket 33's hand-off is pre-filled for three routing reasons, each a kind
code knows (`order_intake.HANDOFF_KINDS`, `handoffs.MODEL_SCHEMAS`): a
tenant's new kind of hand-off (a certificate request to QA, say) cost
Python. Here the kinds are the tenant's ``handoffs`` skill
(`domain.handoff_kinds`): the platform's version names today's three with
today's fields and teams, and a tenant adds or rewords one with a skill
version its head approves, after a replay (`HandoffKindReplay`).

- **Which kind**: the kind the message's reading stamped (the tenant's mail
  kind, or the one call's), else the platform kind of its routing reason;
  never the model's choice. A version naming neither is not asked, and the
  hand-off is read as with the step off.
- **What it does** is code's, as the skill maps it onto the platform's closed
  sets: the fields it is copied into (`ASKS`) and the team it goes to
  (`TEAMS`). Every value is located, parsed and resolved by
  `HandoffReader`, exactly as for the platform's kinds; the skill's words
  only tell the model what the mail is about and what to copy.
- **No usable answer** (the model down, a mail too long, a version whose
  kinds no longer read): `HandoffKindReader.read` returns None and the
  message's hand-off is read as with the step off: ticket 33's reading where
  that is on, else none. A budget or quota refusal propagates, as everywhere.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.skills import Skill
from dw_platform.domain.mail_parts import MessagePart, newest_part
from dw_platform.domain.messages import InboundMessage
from dw_sales.application.handoffs import Copied, HandoffReader, ServedKind
from dw_sales.application.mail_kinds import SkillPort
from dw_sales.application.ports import SalesScope
from dw_sales.domain.catalog import Customer
from dw_sales.domain.handoff_kinds import HANDOFFS, HandoffKinds, handoff_kinds_of
from dw_sales.domain.handoffs import Handoff

__all__ = [
    "HandoffKindExample",
    "HandoffKindExamplesPort",
    "HandoffKindReader",
    "HandoffKindReplay",
    "served_handoff_kinds",
]

_LOG = logging.getLogger("dw_sales.model")


def served_handoff_kinds(skill: Skill) -> HandoffKinds | None:
    """The kinds ``skill``'s words name, or None for words that do not read:
    checked again whenever the skill is served, so a version no longer
    holding is not used (the hand-off is read as with the step off)."""
    try:
        return handoff_kinds_of(skill.body)
    except ValueError as exc:
        # Which version and why; never the words.
        _LOG.warning("hand-off kinds of %s not used: %s", skill.ref, type(exc).__name__)
        return None


@dataclass(frozen=True)
class HandoffKindReader:
    """Pre-fills a routed message's hand-off by the tenant's hand-off kinds
    (module docstring)."""

    reader: HandoffReader
    skills: SkillPort

    async def read(
        self,
        scope: SalesScope,
        part: MessagePart,
        customer: Customer,
        names: Sequence[str],
        *,
        received_on: date,
        rules_version: str,
        run: RunContext,
    ) -> Handoff | None:
        """The hand-off of the first of ``names`` the served version names
        (the reading's kind, then the routing reason's), or None for none
        named, words that do not read or no usable answer."""
        skill = await self.skills.skill(run, HANDOFFS)
        kinds = served_handoff_kinds(skill)
        if kinds is None:
            return None
        kind = next((found for name in names if (found := kinds.named(name)) is not None), None)
        if kind is None:
            return None
        handoff = await self.reader.read(
            scope,
            part,
            customer,
            kind.shape,
            received_on=received_on,
            rules_version=rules_version,
            run=run,
            served=ServedKind(skill, kind),
        )
        return None if handoff.outcome == "unavailable" else handoff


# ------------------------------------------------------------- replay --


@dataclass(frozen=True, slots=True)
class HandoffKindExample:
    """One example mail a proposed version is replayed on: the kind it is
    routed as and what a person copies from it."""

    example_id: str
    message: InboundMessage
    kind: str
    # The sender's own PO the mail names (None: none, or another customer's,
    # which a replay cannot tell apart and so does not grade), the lot as
    # written, the phrases of its sentences or items (casefolded) and how
    # many lines it asks to change.
    po_no: str | None
    lot: str | None
    phrases: tuple[str, ...]
    lines: int


class HandoffKindExamplesPort(Protocol):
    """The platform's example mails a hand-off proposal is replayed on."""

    def examples(self) -> Sequence[HandoffKindExample]: ...


# (messages, right with the proposal, right with the version in force,
# readings with no usable answer, the security cases the proposal failed).
ReplayCounts = tuple[int, int, int, int, tuple[str, ...]]


@dataclass(frozen=True)
class HandoffKindReplay:
    """A proposed version of the ``handoffs`` skill read on the platform's
    example mails beside the version in force (`skill_replay.SkillReplayer`
    asks it for that skill). Each mail is read as the model call reads it,
    located by code with no order resolved (a replay holds none of the
    tenant's orders, `HandoffReader.located`): right where the lot, every
    sentence or item and as many lines as the mail states are located, and
    the sender's own PO where it names one. A version naming no kind for a
    mail copies nothing of it. Nothing is stored or shown but the counts."""

    reader: HandoffReader
    examples: HandoffKindExamplesPort

    async def counts(
        self,
        proposed: Skill,
        in_force: Skill,
        *,
        new_run: Callable[[], RunContext],
        forget_run: Callable[[uuid.UUID], object],
    ) -> ReplayCounts:
        """Every example read with ``proposed`` and with ``in_force``; each
        reading a run of its own (``new_run``), freed from the spend ledger
        after (``forget_run``)."""
        sides = (
            (proposed, served_handoff_kinds(proposed)),
            (in_force, served_handoff_kinds(in_force)),
        )
        messages = unanswered = 0
        right = [0, 0]
        for example in self.examples.examples():
            messages += 1
            for side, (skill, kinds) in enumerate(sides):
                copied = await self._copied(skill, kinds, example, new_run, forget_run)
                if copied is False:
                    continue
                if copied is None:
                    unanswered += 1
                    continue
                right[side] += _right(example, copied)
        return messages, right[0], right[1], unanswered, ()

    async def _copied(
        self,
        skill: Skill,
        kinds: HandoffKinds | None,
        example: HandoffKindExample,
        new_run: Callable[[], RunContext],
        forget_run: Callable[[uuid.UUID], object],
    ) -> Copied | Literal[False] | None:
        """What ``skill`` copies of ``example``: False where it names no kind
        for it (nothing copied, wrong but answered), None for no usable
        answer."""
        kind = None if kinds is None else kinds.named(example.kind)
        if kind is None:
            return False
        run = new_run()
        try:
            return await self.reader.located(
                newest_part(example.message), ServedKind(skill, kind), run=run
            )
        finally:
            forget_run(run.run_id)


def _right(example: HandoffKindExample, copied: Copied) -> int:
    """1 where ``copied`` is what a person copies of ``example``."""
    phrases = all(any(p in quote for quote in copied.quotes) for p in example.phrases)
    po = example.po_no is None or copied.po_no == example.po_no
    return int(po and phrases and copied.lot == example.lot and copied.lines == example.lines)
