"""A model reads a PO the customer wrote in the mail itself (AI item 4).

The rules are `domain.po_body_reading`'s. Asked by order intake only for a
message that names an order and carries no document, from a sender whose
domain is a customer's, where the tenant's rules turn the step on, its live
eval met the bar (`ModelStep.PO_BODY_EXTRACTION`), and a DW1 run is
processing the message. `PoBodyReader.read` shows the model the message's
newest part, under prompt `sales.po_body_extraction`, and returns the PO code
accepted, every value flagged `model_read`, or why there is none; intake then
routes the message to Sales as before, with that reason. A budget or quota
refusal is not a reason: it stops the run. What the mail leaves open of its
notation, the customer's notation record settles (ticket 37,
`NotationRecordPort`). It is shown, as untrusted input like the mail, the
customer's newest decided values (ticket 43, `application.po_body_examples`).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Final

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.interpretation import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
    ScoredInterpretationPort,
    estimated_tokens,
)
from dw_platform.domain.mail_parts import newest_part
from dw_platform.domain.messages import InboundMessage
from dw_sales.application.customer_notations import NotationRecordPort, record_for
from dw_sales.application.po_body_examples import MAX_SHOWN, PoBodyExamplesPort, shown
from dw_sales.application.ports import SalesScope
from dw_sales.domain.orders import PoDocument
from dw_sales.domain.po_body_reading import ModelPoBody, read_po_body
from dw_sales.domain.rfq_reading import normalised

logger = logging.getLogger(__name__)

# The prompt a PO in the mail is read with, and the reader the PO is stamped
# with (`PoDocument.parser_version`). Its file is
# `configs/prompts/sales/po_body_extraction@1.2.0.yaml`; a test holds the two
# together, and holds the prompt's rendered size under `PROMPT_TOKENS`.
# 1.2.0 (ticket 43): `examples`, the customer's decided values.
PO_BODY_EXTRACTION: Final = PromptRef("sales.po_body_extraction", "1.2.0")
PROMPT_TOKENS: Final = 1800
# Room for `MAX_LINES` lines (about 120 tokens each) and the PO's own values.
_OUTPUT_TOKENS: Final = 2000


@dataclass(frozen=True)
class PoBodyReader:
    model: InterpretationPort
    # The sender's customer's notation record (ticket 37).
    records: NotationRecordPort
    # The customer's decided values (ticket 43); None: none shown.
    examples: PoBodyExamplesPort | None = None

    async def read(
        self,
        message: InboundMessage,
        *,
        scope: SalesScope,
        customer_code: str,
        received_on: date,
        run: RunContext,
    ) -> PoDocument | str:
        """The PO written in ``message``, or why none was read: ``too_long``
        (a mail no call holds is a person's to read, never read in part),
        ``unavailable``, or `read_po_body`'s reason. ``received_on``: the day
        it arrived where the tenant works, which a date without a year reads
        by; ``customer_code`` the sender's customer, whose record is read."""
        text = normalised(newest_part(message).text)
        room = self.model.max_input_tokens - PROMPT_TOKENS
        if estimated_tokens(text) > room:
            return "too_long"
        examples = await self._examples(scope, customer_code)
        if estimated_tokens(text) + estimated_tokens(examples) > room:
            # The mail is read whole, or not at all; examples are not owed.
            examples = "[]"
        inputs = {"mail": text, "examples": examples}
        scores: Mapping[str, float] | None = None
        try:
            # Scored where the door can score (ticket 44): the same call, with
            # each value's probability from its tokens, which the threshold
            # of a value applying itself is measured on.
            if isinstance(self.model, ScoredInterpretationPort):
                scored = await self.model.interpret_scored(
                    PO_BODY_EXTRACTION,
                    inputs,
                    ModelPoBody,
                    run=run,
                    max_output_tokens=_OUTPUT_TOKENS,
                )
                answer = scored.answer
                scores = scored.confidences
            else:
                answer = await self.model.interpret(
                    PO_BODY_EXTRACTION,
                    inputs,
                    ModelPoBody,
                    run=run,
                    max_output_tokens=_OUTPUT_TOKENS,
                )
        except ModelUnavailableError:
            return "unavailable"
        verdict = read_po_body(
            text,
            answer,
            received_on,
            parser_version=str(PO_BODY_EXTRACTION),
            record=await record_for(self.records, scope, customer_code),
            confidences=scores,
            model_profile=self.model.model_profile,
        )
        if verdict.refused:
            # Counts by reason only: a refusal names no customer word.
            logger.info(
                "po_body_extraction refused spans",
                extra={"message_id": message.message_id, "refused": dict(verdict.refused)},
            )
        if verdict.document is None:
            assert verdict.not_read is not None  # a verdict holds one or the other
            return verdict.not_read
        return verdict.document

    async def _examples(self, scope: SalesScope, customer_code: str) -> str:
        """The customer's decided values as the prompt shows them, or none
        on any failure: the mail is read as it was before examples existed."""
        if self.examples is None:
            return "[]"
        try:
            return shown(await self.examples.latest(scope, customer_code, MAX_SHOWN * 2))
        except Exception as exc:
            # Broad on purpose; the type only, a message can quote text.
            logger.warning(
                "po_body examples unavailable; reading without",
                extra={"error": type(exc).__name__},
            )
            return "[]"
