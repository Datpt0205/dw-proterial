"""`InterpretationPort` over the platform's model gateway (dw_sales ADR 0005).

The gateway renders the versioned prompt with the run's tenant (each input in
an escaped ``<input>`` block), routes it to the profile DW1's worker names,
checks the run's budget before the call, records usage against the run, and
validates the answer into the schema. What this adapter adds is the one
translation DW1 needs: every way of getting no usable answer becomes
`ModelUnavailableError`, which a step turns into a person's work. A budget or
quota refusal is not translated: it stops the run.

No tool is offered: `generate_structured` takes none, so a turn that reads a
document cannot call one (ADR 0007).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import BaseModel

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.ports import ModelGateway, ModelOutputInvalidError, ModelRequest
from dw_kernel.errors import InfrastructureError, NotFoundError
from dw_sales.application.model_reading import ModelUnavailableError, PromptRef

_LOG = logging.getLogger("dw_sales.model")
# The route every DW1 reading runs on: structured output, no tools.
_TASK = "structured_extraction"


@dataclass(frozen=True)
class GatewayInterpretation:
    """Implements `InterpretationPort` with a `ModelGateway`.

    ``model_profile`` is the one DW1's worker config names
    (`configs/workers/sales.yaml`, ``default_model_profile``), read by the
    composition root, so the profile has one owner.
    """

    gateway: ModelGateway
    model_profile: str
    # The route's own declaration (`configs/models/<profile>.yaml`,
    # ``structured_extraction.max_input_tokens``), read by the composition
    # root so the bound has one owner.
    max_input_tokens: int

    @property
    def route(self) -> str:
        return _TASK

    async def interpret[OutputT: BaseModel](
        self,
        prompt: PromptRef,
        inputs: Mapping[str, str],
        schema: type[OutputT],
        *,
        run: RunContext,
        max_output_tokens: int,
    ) -> OutputT:
        request = ModelRequest(
            task=_TASK,
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.version,
            variables=dict(inputs),
            model_profile=self.model_profile,
            max_output_tokens=max_output_tokens,
        )
        try:
            return await self.gateway.generate_structured(request, schema, run_context=run)
        except (InfrastructureError, ModelOutputInvalidError, NotFoundError) as exc:
            # Ids and the error's kind only: never an input or an answer,
            # which are a customer's words.
            _LOG.warning(
                "model reading unavailable for run %s (%s, %s): %s",
                run.run_id,
                prompt,
                self.model_profile,
                type(exc).__name__,
            )
            raise ModelUnavailableError(type(exc).__name__) from exc
