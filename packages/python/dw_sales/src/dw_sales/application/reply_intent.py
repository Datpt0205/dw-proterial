"""A model reads what a message in a case's thread does; code checks it.

Tickets 32 and 26, dw_sales ADR 0010 decision 1 (the rules:
`domain.reply_intent`). Asked for a customer's reply the thread headers
already linked to a case (`application.threads`), and for a message Sales
sent on a thread holding a case (ticket 25), where the tenant's rules turn it
on and a DW1 run is processing. `ReplyReader.read` sends the message's
subject and newest part (`mail_parts.newest_part`, history cut by structure)
and a context code wrote (who wrote it, what Sales last asked on the case),
under prompt `sales.reply_intent`, and returns the reading code accepts: the
intents, each with the quotes it located exactly once in the newest part,
``unclear`` where none was. No usable answer (the model down, too slow or
outside the schema) is an ``unavailable`` reading: the message proposes
nothing. A budget or quota refusal is not that: it propagates, and the run
stops.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.interpretation import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
    cut_to_tokens,
)
from dw_platform.domain.mail_parts import MessagePart
from dw_sales.domain.reply_intent import (
    Author,
    ModelThreadIntents,
    ReplyReading,
    verified_intents,
)

# The prompt a thread message is read with. Its file is
# `configs/prompts/sales/reply_intent@2.0.0.yaml`; a test holds the two
# together, and a new wording is a new version here and a new file there.
REPLY_INTENT: Final = PromptRef("sales.reply_intent", "2.0.0")
# Up to four intents with up to three sentences each: about 300 tokens.
_OUTPUT_TOKENS: Final = 800
# What the prompt itself costs with the context, held above its rendered
# size by a test, so the body is cut where the route's bound says.
PROMPT_TOKENS: Final = 1900

# Who wrote the message, in the context's first sentence: code's words.
_WRITER: Final[dict[Author, str]] = {
    "customer": "The customer wrote this message to the seller's Sales team.",
    "sales": "The seller's Sales team wrote this message to the customer.",
}


def reading_context(author: Author, about: str) -> str:
    """The context a message is read with: who wrote it, then ``about``
    (what Sales last asked on the case, `threads.question`), both code's."""
    return f"{_WRITER[author]} {about}"


@dataclass(frozen=True)
class ReplyReader:
    """Reads a thread message's intents through a model and locates what it
    quotes."""

    model: InterpretationPort

    async def read(
        self,
        part: MessagePart,
        *,
        author: Author,
        about: str,
        rules_version: str,
        run: RunContext,
    ) -> ReplyReading:
        """The message's reading as code accepts it (module docstring)."""
        inputs = {
            "context": reading_context(author, about),
            "subject": part.subject,
            "body": cut_to_tokens(part.body, self.model.max_input_tokens - PROMPT_TOKENS),
        }
        try:
            answer = await self.model.interpret(
                REPLY_INTENT,
                inputs,
                ModelThreadIntents,
                run=run,
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except ModelUnavailableError:
            return self._stamp(rules_version, "unavailable")
        return ReplyReading(
            **self._fields(rules_version),
            outcome="read",
            intents=verified_intents(part.text, answer),
        )

    def _stamp(self, rules_version: str, outcome: str) -> ReplyReading:
        return ReplyReading.model_validate({**self._fields(rules_version), "outcome": outcome})

    def _fields(self, rules_version: str) -> dict[str, str]:
        return {
            "prompt": str(REPLY_INTENT),
            "model_profile": self.model.model_profile,
            "route": self.model.route,
            "rules": rules_version,
        }
