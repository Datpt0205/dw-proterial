"""A model reading that may look things up first: one bounded agent turn.

`InterpretationPort` is one call with a fixed input and no tool. Some readings
need what the input does not carry (an earlier message of the thread, the case a
number names), and the platform already has the pieces for that: an agent
assembled by `agent_factory.build_agent`, every tool call through `ToolExecutor`
(authorized, validated, executed, its output validated, audited). dw_sales ADR
0012 lets a context use them for a reading, under the same rules as a one-call
reading (dw_sales ADR 0005): the answer is validated into a schema, code
verifies it, and a person confirms what it proposes.

`AgentTurnPort` is that question, asked the same way as `InterpretationPort`:
"interpret these inputs into this schema, for this run". What it adds is a
ceiling (`TurnCeiling`): model calls, input tokens and seconds for the turn.
Over any of them the turn stops and says which (`TurnCeilingReachedError`); a
step falls back to its one-call reading, never to a guess. A turn that gives no
usable answer is `ModelUnavailableError`, as a one-call reading is. The run's
own spend ceiling is not the turn's: reaching it is `BudgetExceededError`, which
stops the run like any other step's.

The tools a turn offers are the worker's toolset, fixed when the turn is built;
the turn reads them through the run it is given (`RunContext`), and a context's
tool binds what it reads to that run, never to an argument the model passes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.interpretation import PromptRef

# Which ceiling stopped a turn.
TurnCeilingKind = Literal["calls", "spend", "time"]


@dataclass(frozen=True, slots=True)
class TurnCeiling:
    """What one turn may use: model calls (the final answer is one of them),
    input tokens over all its calls, and wall-clock seconds."""

    max_model_calls: int
    max_input_tokens: int
    max_seconds: float

    def __post_init__(self) -> None:
        if self.max_model_calls < 1 or self.max_input_tokens < 1 or self.max_seconds <= 0:
            raise ValueError("a turn ceiling allows at least one call, one token and some time")


class TurnCeilingReachedError(Exception):
    """The turn reached one of its ceilings before it gave an answer."""

    def __init__(self, ceiling: TurnCeilingKind) -> None:
        super().__init__(f"the turn reached its {ceiling} ceiling")
        self.ceiling: TurnCeilingKind = ceiling


class AgentTurnPort(Protocol):
    """Interpret ``inputs`` into ``schema`` for ``run``, with the tools the turn
    was built with, under its ceiling.

    ``inputs`` are untrusted: the prompt registry contains each one in an
    escaped block. The answer is validated into ``schema`` before it is
    returned. Raises `TurnCeilingReachedError` over a ceiling and
    `ModelUnavailableError` for no usable answer; a run's budget refusal
    (`BudgetExceededError`) propagates as itself.
    """

    @property
    def prompt(self) -> PromptRef:
        """The versioned prompt every turn renders: what a reading is stamped with."""
        ...

    @property
    def model_profile(self) -> str: ...

    @property
    def route(self) -> str:
        """The profile's route the turn talks through (``chat``)."""
        ...

    @property
    def ceiling(self) -> TurnCeiling: ...

    async def read[OutputT: BaseModel](
        self, inputs: Mapping[str, str], schema: type[OutputT], *, run: RunContext
    ) -> OutputT: ...
