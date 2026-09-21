"""Where a model call's usage goes, and the rule that bookkeeping never wins.

This used to sit beside `SqlUsageRecorder`, which wrote every call to
`platform.model_usage_ledger`. That ledger is gone: it existed to answer "what
did this tenant cost last month", nothing in this repo invoices anybody, and the
only readers were a per-tenant daily spend cap and an admin dashboard — both
removed with it. Cost still reaches telemetry, which is where one call is
inspected.

The fan-out stays even though only one recorder is wired today, because the
property it carries is not about the number of recorders:

- a recorder that raises must not take the run down. The model answer the caller
  is holding has already been paid for; losing the record of it is the smaller
  loss by a wide margin, and it is logged.
- no recorder at all is a legitimate state. A deployment with telemetry off
  records nothing, and the gateway must not need to know that.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.gateway import ModelUsage, UsageRecorderPort
from dw_agent_runtime.ports import ModelRequest

_LOG = logging.getLogger("dw_agent_runtime.usage")

__all__ = ["CompositeUsageRecorder"]


@dataclass(frozen=True)
class CompositeUsageRecorder:
    """Fans one call's usage out to every recorder, and lets none of them win."""

    recorders: Sequence[UsageRecorderPort]

    async def record(
        self, run_context: RunContext, request: ModelRequest, usage: ModelUsage
    ) -> None:
        for recorder in self.recorders:
            try:
                await recorder.record(run_context, request, usage)
            except Exception:
                _LOG.warning(
                    "usage recorder %s failed for run %s",
                    type(recorder).__name__,
                    run_context.run_id,
                    exc_info=True,
                )
