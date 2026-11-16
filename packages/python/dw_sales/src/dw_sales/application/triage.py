"""The triage card a message routed ``other`` carries (ticket 33; the card's
rules are `dw_sales.domain.triage`).

Asked by intake for a message it routes ``other`` (`OrderIntake.process`),
where the tenant's rules turn the step on and it meets its bar, inside the
DW1 run processing the message. `TriageReader.read` asks ONE structured call
under the tenant's served ``mail-kinds`` skill (the prompt
``sales.triage_card``, the inputs and schema the mail kinds' own: the
kinds the version names, plus ``none``), and code makes the card of it:

- the kind, read as code reads a mail kind (a name the version does not hold
  is no kind), and the route the skill maps it onto;
- the numbers code locates in the newest part, resolved by the one
  resolution intake has (`IntentReader.resolve`): against the sender's own
  customer's records only, so a number of another customer, or of no
  customer, names no case;
- the step: the kind's route where a person can take it (`card_step`).

None, and no card, for a skill whose words no longer read or no usable
answer: the message stays routed as it is, exactly as with the step off. A
budget or quota refusal propagates, as everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.interpretation import PromptRef
from dw_platform.domain.mail_parts import MessagePart
from dw_sales.application.mail_kinds import MailKindReader, served_kinds
from dw_sales.application.ports import SalesScope
from dw_sales.domain.catalog import Customer
from dw_sales.domain.mail_kinds import MAIL_KINDS
from dw_sales.domain.message_intent import located_numbers
from dw_sales.domain.triage import TriageCard, card_case, card_step

__all__ = ["TRIAGE_CARD_PROMPT", "TriageReader"]

# The prompt a card is read with (`configs/prompts/sales/triage_card@1.0.0
# .yaml`); a test holds the two together.
TRIAGE_CARD_PROMPT: Final = PromptRef("sales.triage_card", "1.0.0")


@dataclass(frozen=True)
class TriageReader:
    """Reads a triage card for a message routed ``other`` (module docstring)."""

    # The mail kinds' reader: the served skill, the one call, and the one
    # resolution of the numbers named.
    kinds: MailKindReader

    async def read(
        self,
        scope: SalesScope,
        part: MessagePart,
        customer: Customer | None,
        *,
        rules_version: str,
        run: RunContext,
    ) -> TriageCard | None:
        """The card, or None for no card (module docstring). ``customer`` is
        the sender's, as intake found it: the only customer a number is
        resolved against."""
        skill = await self.kinds.skills.skill(run, MAIL_KINDS)
        kinds = served_kinds(skill)
        if kinds is None:
            return None
        answer = await self.kinds.answer(skill, kinds, part, run=run, prompt=TRIAGE_CARD_PROMPT)
        if answer is None:
            return None
        numbers = located_numbers(part.text, answer.spans)
        references = await self.kinds.references.resolve(scope, customer, numbers)
        kind = answer.kind
        return TriageCard(
            prompt=str(TRIAGE_CARD_PROMPT),
            model_profile=self.kinds.model.model_profile,
            route=self.kinds.model.route,
            rules=rules_version,
            skill=skill.ref,
            kind=None if kind is None else kind.name,
            kind_label=None if kind is None else kind.label,
            routed_as=None if kind is None else kind.route,
            references=references,
            case_id=card_case(references),
            step=card_step(None if kind is None else kind.route),
        )
