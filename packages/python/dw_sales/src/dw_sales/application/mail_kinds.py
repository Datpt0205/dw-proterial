"""A message no reader accepted, classified by the kinds the tenant's
mail-classifying skill names; code routes each kind where the skill maps it
(ticket 42 family 1, dw_sales ADR 0014).

The one-call reading of ticket 31 (`message_intent.IntentReader`) classifies
by a closed set of kinds written into its prompt: a new kind of mail at a
tenant cost Python, the API contract, the web and a deploy. Here the kinds and
their words are the tenant's ``mail-kinds`` skill (`domain.mail_kinds`): the
platform's version names today's kinds word for word, and a tenant adds or
rewords one with a skill version its head approves, after a replay
(`MailKindReplay`).

- **The model answers** one of the kinds the served version names, or
  ``none``: the answer's schema is built per call from those names, so a
  server decoding against it cannot write another word, and code reads a name
  the version does not hold as ``none`` whatever got through. Also the
  language and the document numbers it names, as the one call does.
- **Code routes**: the kind's route is the skill's mapping onto the closed set
  of legal routes (`mail_kinds.ROUTES`), read and checked by code from the
  version's words each time it is served; `order_intake.INTENT_ROUTES` then
  says where that route goes. The model never names a route.
- **No kind read** (``none``, the model down, a version whose kinds no longer
  read): `MailKindReader.read` returns None and the message is classified as
  if the step were off: the one-call reading where that is on, else a person.
  A budget or quota refusal propagates, as everywhere.
- **Numbers** are resolved by the one call's own resolution
  (`IntentReader.resolve`): one answer to "which record is this number", not
  two.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, create_model

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.interpretation import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
    cut_to_tokens,
    estimated_tokens,
)
from dw_agent_runtime.model.skills import Skill
from dw_platform.domain.mail_parts import MessagePart, newest_part
from dw_platform.domain.messages import InboundMessage
from dw_sales.application.message_intent import IntentRead, IntentReader
from dw_sales.application.ports import SalesScope
from dw_sales.domain.catalog import Customer
from dw_sales.domain.mail_kinds import (
    MAIL_KINDS,
    MAX_KINDS,
    NO_KIND,
    MailKind,
    MailKinds,
    ReadRoute,
    mail_kinds_of,
)
from dw_sales.domain.message_intent import (
    MAX_REFERENCES,
    IntentKind,
    IntentLanguage,
    IntentReading,
    located_numbers,
)

__all__ = [
    "MAIL_KINDS_PROMPT",
    "MailKindExample",
    "MailKindExamplesPort",
    "MailKindReader",
    "MailKindReplay",
    "SkillPort",
    "kinds_schema",
]

_LOG = logging.getLogger("dw_sales.model")

# The prompt the kinds are read with (`configs/prompts/sales/mail_kinds@1.0.0
# .yaml`); the skill's words are one of its contained inputs.
MAIL_KINDS_PROMPT: Final = PromptRef("sales.mail_kinds", "1.0.0")
# A kind's name, a language and up to five short spans.
_OUTPUT_TOKENS: Final = 200
# What the prompt costs without the skill's words, held above its rendered
# size by a test, as the one call's is.
PROMPT_TOKENS: Final = 600


class SkillPort(Protocol):
    """One skill as the run's tenant holds it now: its approved version, else
    the platform's, never another tenant's (`skills.SkillBook`)."""

    async def skill(self, run: RunContext, name: str) -> Skill: ...


def kinds_schema(names: Sequence[str]) -> type[BaseModel]:
    """The answer's schema for a version naming ``names``: the one call's
    fields, its kind one of ``names`` or `NO_KIND`. Built per call because the
    kinds are the tenant's; the gateway sends it as the server's JSON schema.
    The spans come before the kind, so the model reads before it labels."""
    if not 0 < len(names) <= MAX_KINDS:
        raise ValueError("a version names between one and forty kinds")
    allowed: Any = Literal.__getitem__((*names, NO_KIND))
    return create_model(
        "MailKindAnswer",
        __config__=ConfigDict(frozen=True, extra="forbid"),
        language=(IntentLanguage, ...),
        referenced_number_spans=(
            tuple[str, ...],
            Field(max_length=MAX_REFERENCES),
        ),
        kind=(allowed, ...),
    )


@dataclass(frozen=True, slots=True)
class KindAnswer:
    """What one call said, as code reads it: the kind (None for ``none``, or a
    name the version does not hold), the language and the spans."""

    kind: MailKind | None
    language: IntentLanguage
    spans: tuple[str, ...]


@dataclass(frozen=True)
class MailKindReader:
    """Classifies a message by the tenant's mail kinds (module docstring)."""

    model: InterpretationPort
    skills: SkillPort
    # The one call's reader, for its resolution of the numbers named.
    references: IntentReader

    async def read(
        self,
        scope: SalesScope,
        part: MessagePart,
        customer: Customer | None,
        *,
        rules_version: str,
        run: RunContext,
    ) -> IntentRead | None:
        """The kind read and its route, or None for no kind read."""
        skill = await self.skills.skill(run, MAIL_KINDS)
        kinds = served_kinds(skill)
        if kinds is None:
            return None
        answer = await self.answer(skill, kinds, part, run=run)
        if answer is None or answer.kind is None:
            return None
        kind = answer.kind
        numbers = located_numbers(part.text, answer.spans)
        references = await self.references.resolve(scope, customer, numbers)
        return IntentRead(
            route=kind.route,
            reading=IntentReading(
                prompt=str(MAIL_KINDS_PROMPT),
                model_profile=self.model.model_profile,
                route=self.model.route,
                rules=rules_version,
                outcome="read",
                kind=kind.name,
                language=answer.language,
                references=references,
                skill=skill.ref,
                routed_as=kind.route,
                kind_label=kind.label,
            ),
        )

    async def answer(
        self,
        skill: Skill,
        kinds: MailKinds,
        part: MessagePart,
        *,
        run: RunContext,
        prompt: PromptRef = MAIL_KINDS_PROMPT,
    ) -> KindAnswer | None:
        """One call under ``skill``'s words: None for no usable answer.
        ``prompt``: the mail kinds' own, or a triage card's (ticket 33), which
        asks the same question of a mail already routed ``other``, with the
        same inputs and the same schema."""
        inputs = {
            "skill": skill.body,
            "subject": part.subject,
            "body": self._bounded(skill, part.body),
        }
        try:
            answer = await self.model.interpret(
                prompt,
                inputs,
                kinds_schema(kinds.names),
                run=run,
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except ModelUnavailableError:
            return None
        name = str(getattr(answer, "kind"))  # noqa: B009 - a schema built per call
        language: IntentLanguage = getattr(answer, "language")  # noqa: B009
        spans: tuple[str, ...] = tuple(getattr(answer, "referenced_number_spans"))  # noqa: B009
        # Code's reading of the word: a name the version does not hold is no
        # kind, whatever the decoder let through.
        return KindAnswer(kinds.named(name) if name != NO_KIND else None, language, spans)

    def _bounded(self, skill: Skill, body: str) -> str:
        """The body cut to what fits the route beside the prompt and the
        skill's words: a mail's kind is in its first lines."""
        room = self.model.max_input_tokens - PROMPT_TOKENS - estimated_tokens(skill.body)
        return cut_to_tokens(body, max(room, 0))


def served_kinds(skill: Skill) -> MailKinds | None:
    """The kinds ``skill``'s words name, or None for words that do not read:
    checked again whenever the skill is served, so a version no longer
    holding is not used (the message is read as with the step off)."""
    try:
        return mail_kinds_of(skill.body)
    except ValueError as exc:
        # Which version and why; never the words.
        _LOG.warning("mail kinds of %s not used: %s", skill.ref, type(exc).__name__)
        return None


# ------------------------------------------------------------- replay --


@dataclass(frozen=True, slots=True)
class MailKindExample:
    """One example mail a proposed version is replayed on: the route it is
    expected to take, or, for a security case, the routes it must never take."""

    example_id: str
    message: InboundMessage
    # The route it is read as; None for a security case only.
    gold: IntentKind | None
    # The routes it must never be read into (a security case); empty for a
    # golden one.
    never: frozenset[str]


class MailKindExamplesPort(Protocol):
    """The platform's example mails a mail-kinds proposal is replayed on."""

    def examples(self) -> Sequence[MailKindExample]: ...


# (messages, right with the proposal, right with the version in force,
# readings with no usable answer, the security cases the proposal failed).
ReplayCounts = tuple[int, int, int, int, tuple[str, ...]]


@dataclass(frozen=True)
class MailKindReplay:
    """A proposed version of the ``mail-kinds`` skill read on the platform's
    example mails beside the version in force (`skill_replay.SkillReplayer`
    asks it for that skill). Graded by ROUTE, what code does with the mail:
    a tenant's new kind that goes where the expected one goes is right. A
    security case fails when the proposal reads it into a route it must never
    take."""

    reader: MailKindReader
    examples: MailKindExamplesPort

    async def counts(
        self,
        proposed: Skill,
        in_force: Skill,
        *,
        new_run: Callable[[], RunContext],
        forget_run: Callable[[uuid.UUID], object],
    ) -> ReplayCounts:
        """Every example read with ``proposed`` and, the golden ones, with
        ``in_force``; each reading a run of its own (``new_run``), freed from
        the spend ledger after (``forget_run``)."""
        with_kinds, without_kinds = served_kinds(proposed), served_kinds(in_force)
        messages = right_with = right_without = unanswered = 0
        failed: list[str] = []
        for example in self.examples.examples():
            with_it = await self._route(proposed, with_kinds, example, new_run, forget_run)
            unanswered += with_it is None
            if with_it in example.never:
                failed.append(example.example_id)
            if example.gold is None:
                continue
            without = await self._route(in_force, without_kinds, example, new_run, forget_run)
            messages += 1
            unanswered += without is None
            right_with += with_it == example.gold
            right_without += without == example.gold
        return messages, right_with, right_without, unanswered, tuple(failed)

    async def _route(
        self,
        skill: Skill,
        kinds: MailKinds | None,
        example: MailKindExample,
        new_run: Callable[[], RunContext],
        forget_run: Callable[[uuid.UUID], object],
    ) -> str | None:
        """The route ``example`` takes under ``skill``: ``none`` for no kind
        read (answered, but routed by no kind), None for no usable answer."""
        route, _ = await self.read(
            skill, kinds, example.message, new_run=new_run, forget_run=forget_run
        )
        return route

    async def read(
        self,
        skill: Skill,
        kinds: MailKinds | None,
        message: InboundMessage,
        *,
        new_run: Callable[[], RunContext],
        forget_run: Callable[[uuid.UUID], object],
    ) -> tuple[ReadRoute | None, MailKind | None]:
        """``message`` read under ``skill``, in a run of its own: the route
        and the kind (``none`` and no kind for no kind read, or for words
        that do not read; None and no kind for no usable answer). The mail a
        version was taught from is read this way (ticket 34)."""
        if kinds is None:
            return NO_KIND, None
        run = new_run()
        try:
            answer = await self.reader.answer(skill, kinds, newest_part(message), run=run)
        finally:
            forget_run(run.run_id)
        if answer is None:
            return None, None
        if answer.kind is None:
            return NO_KIND, None
        return answer.kind.route, answer.kind
