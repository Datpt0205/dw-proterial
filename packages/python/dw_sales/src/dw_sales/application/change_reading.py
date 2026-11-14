"""A model reads the changes a customer asks for in a reply's own words;
code keeps what it can find and parse (ticket 27, dw_sales ADR 0010 decision
2 and ADR 0005; the rules: `domain.change_requests.model_changes`).

Asked only where the tenant's rules turn `model_assist.change_request` on and
its live eval met the bar (`ModelStepGatePort`), when a person records a
change request from a reply ("Ghi yêu cầu thay đổi"): through the one-call
door, as the asker. The model is shown the mail's newest part and nothing
else (no item code, no line of the order: the words naming a line are the
mail's, and code resolves them against the case).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Final

from dw_agent_runtime.context import caller_run
from dw_agent_runtime.model.interpretation import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
    estimated_tokens,
)
from dw_platform.application.access_context import AccessContext
from dw_sales.domain.change_requests import (
    ChangeReading,
    ModelChanges,
    ReadChanges,
    model_changes,
)
from dw_sales.domain.orders import OrderCase

logger = logging.getLogger(__name__)

# The prompt a change asked in a mail's words is read with. Its file is
# `configs/prompts/sales/change_request@1.0.0.yaml`; a test holds the two
# together, and the rendered prompt under `PROMPT_TOKENS`.
CHANGE_REQUEST: Final = PromptRef("sales.change_request", "1.0.0")
PROMPT_TOKENS: Final = 1400
# Up to ten changes, about 60 tokens each.
_OUTPUT_TOKENS: Final = 900
_ORDER: Final = "sales_order_case"


@dataclass(frozen=True)
class ChangeReader:
    """Reads the changes a mail asks in its own words through a model, and
    keeps what code accepts of the answer (`model_changes`)."""

    model: InterpretationPort

    async def read(
        self,
        case: OrderCase,
        text: str,
        *,
        received_on: date,
        rules_version: str,
        run_for: AccessContext,
        run_id: uuid.UUID,
        worker: tuple[str, str],
    ) -> tuple[ReadChanges, ChangeReading]:
        """``text`` is the mail's newest part, NFKC-normalised. A mail no call
        holds, or no usable answer, reads nothing and says ``unavailable``: the
        lines are code's and the person's. A budget or quota refusal is not
        that, and propagates."""
        stamp = {
            "prompt": str(CHANGE_REQUEST),
            "model_profile": self.model.model_profile,
            "route": self.model.route,
            "rules": rules_version,
        }
        if estimated_tokens(text) > self.model.max_input_tokens - PROMPT_TOKENS:
            return ReadChanges(), ChangeReading(**stamp, outcome="unavailable")
        try:
            answer = await self.model.interpret(
                CHANGE_REQUEST,
                {"mail": text},
                ModelChanges,
                run=caller_run(
                    run_for,
                    run_id=run_id,
                    worker_id=worker[0],
                    worker_version=worker[1],
                    trace="sales-change-request",
                    subject_ref=f"{_ORDER}:{case.case_id}",
                ),
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except ModelUnavailableError:
            return ReadChanges(), ChangeReading(**stamp, outcome="unavailable")
        read = model_changes(case, text, answer, received_on)
        if read.unread:
            # Counts only: a refusal names no customer word.
            logger.info(
                "change_request dropped spans",
                extra={"case_id": str(case.case_id), "unread": read.unread},
            )
        return read, ChangeReading(**stamp, outcome="read")
