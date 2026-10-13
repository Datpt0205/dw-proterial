"""A model reads what a customer's reply in a case's thread says; code checks it.

Ticket 32, dw_sales ADR 0005 (the rules: `domain.reply_intent`). Asked only for
a message the thread headers already linked to a case (`application.threads`),
where the tenant's rules turn it on and a DW1 run is processing.
`ReplyReader.read` sends the reply's subject and newest part
(`mail_parts.newest_part`, history cut by structure) and the question Sales
last asked on the case, built by code, under prompt `sales.reply_intent`, and
returns the reading code accepts: the kind, and the quotes it located exactly
once in the newest part; ``unclear`` when none was. No usable answer (the
model down, too slow or outside the schema) is an ``unavailable`` reading: the
reply stays on its case with no proposal. A budget or quota refusal is not
that: it propagates, and the run stops.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from dw_agent_runtime.contracts import RunContext
from dw_sales.application.model_reading import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
    cut_to_tokens,
)
from dw_sales.application.threads import ThreadedCase
from dw_sales.domain.mail_parts import MessagePart
from dw_sales.domain.reply_intent import (
    ModelReplyIntent,
    ReplyReading,
    located_quotes,
    verified_kind,
)

# The prompt a reply is read with. Its file is
# `configs/prompts/sales/reply_intent@1.0.0.yaml`; a test holds the two
# together, and a new wording is a new version here and a new file there.
REPLY_INTENT: Final = PromptRef("sales.reply_intent", "1.0.0")
# A kind and up to three sentences: about 150 tokens measured.
_OUTPUT_TOKENS: Final = 500
# What the prompt itself costs with the case's question, held above its
# rendered size by a test, so the body is cut where the route's bound says.
PROMPT_TOKENS: Final = 1500


@dataclass(frozen=True)
class ReplyReader:
    """Reads a reply's intent through a model and locates what it quotes."""

    model: InterpretationPort

    async def read(
        self, part: MessagePart, case: ThreadedCase, *, rules_version: str, run: RunContext
    ) -> ReplyReading:
        """The reply's reading as code accepts it (module docstring)."""
        inputs = {
            "subject": part.subject,
            "body": cut_to_tokens(part.body, self.model.max_input_tokens - PROMPT_TOKENS),
            "question": case.question,
        }
        try:
            answer = await self.model.interpret(
                REPLY_INTENT,
                inputs,
                ModelReplyIntent,
                run=run,
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except ModelUnavailableError:
            return self._stamp(rules_version, "unavailable")
        quotes = located_quotes(part.text, answer.quote_spans)
        return ReplyReading(
            **self._fields(rules_version),
            outcome="read",
            kind=verified_kind(answer.kind, quotes),
            quotes=quotes,
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
