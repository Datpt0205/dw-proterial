"""A model reads a PO the customer wrote in the mail itself (AI item 4).

The rules are `domain.po_body_reading`'s. Asked by order intake only for a
message that names an order and carries no document, from a sender whose
domain is a customer's, where the tenant's rules turn the step on, its live
eval met the bar (`ModelStep.PO_BODY_EXTRACTION`), and a DW1 run is
processing the message. `PoBodyReader.read` shows the model the message's
newest part, under prompt `sales.po_body_extraction`, and returns the PO code
accepted, every value flagged `model_read`, or why there is none; intake then
routes the message to Sales as before, with that reason. A budget or quota
refusal is not a reason: it stops the run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.interpretation import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
    estimated_tokens,
)
from dw_sales.domain.mail_parts import newest_part
from dw_sales.domain.messages import InboundMessage
from dw_sales.domain.order_checks import received_date
from dw_sales.domain.orders import PoDocument
from dw_sales.domain.po_body_reading import ModelPoBody, read_po_body
from dw_sales.domain.rfq_reading import normalised

logger = logging.getLogger(__name__)

# The prompt a PO in the mail is read with, and the reader the PO is stamped
# with (`PoDocument.parser_version`). Its file is
# `configs/prompts/sales/po_body_extraction@1.0.0.yaml`; a test holds the two
# together, and holds the prompt's rendered size under `PROMPT_TOKENS`.
PO_BODY_EXTRACTION: Final = PromptRef("sales.po_body_extraction", "1.0.0")
PROMPT_TOKENS: Final = 1800
# Room for `MAX_LINES` lines (about 120 tokens each) and the PO's own values.
_OUTPUT_TOKENS: Final = 2000


@dataclass(frozen=True)
class PoBodyReader:
    model: InterpretationPort

    async def read(self, message: InboundMessage, *, run: RunContext) -> PoDocument | str:
        """The PO written in ``message``, or why none was read: ``too_long``
        (a mail no call holds is a person's to read, never read in part),
        ``unavailable``, or `read_po_body`'s reason."""
        text = normalised(newest_part(message).text)
        if estimated_tokens(text) > self.model.max_input_tokens - PROMPT_TOKENS:
            return "too_long"
        try:
            answer = await self.model.interpret(
                PO_BODY_EXTRACTION,
                {"mail": text},
                ModelPoBody,
                run=run,
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except ModelUnavailableError:
            return "unavailable"
        verdict = read_po_body(
            text,
            answer,
            received_date(message.received_at),
            parser_version=str(PO_BODY_EXTRACTION),
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
