"""The one-call door to a model a context reads and writes through.

Lifted from Sales by docs/adr/0013 (dw_sales ADR 0005 made the rule): a model
may turn a sender's words into a typed reading, or code's facts into prose;
code verifies what it returns, resolves every identifier and decides.

`InterpretationPort` is the narrowest thing a context asks of a model:
"interpret these inputs into this schema", under a versioned prompt,
attributed to the run that asked (`RunContext`: tenant, worker, release), with
no tool offered (ADR 0007-document-content-turns-cannot-call-outbound-tools).
The composition root satisfies it with the platform's gateway
(`dw_agent_runtime.adapters.model_interpretation`). A model that is down, too
slow or answers outside the schema is `ModelUnavailableError`, which a step
turns into "not understood" for a person. A budget or quota refusal is not that
error: it stops the run, and is reported as a stop.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel

from dw_agent_runtime.contracts import RunContext


@dataclass(frozen=True, slots=True)
class PromptRef:
    """A versioned prompt in ``configs/prompts``, pinned by the release manifest."""

    prompt_id: str
    version: str

    def __str__(self) -> str:
        return f"{self.prompt_id}@{self.version}"


def estimated_tokens(text: str) -> int:
    """An upper estimate of the tokens ``text`` costs a local model: a wide
    character (CJK, kana) or any other non-ASCII letter as one token, ASCII
    as one per three characters. Generous on purpose: a step that sends less
    than it could costs one more call; one that sends more than fits is
    refused by the server."""
    wide = sum(1 for char in text if not char.isascii())
    return wide + (len(text) - wide + 2) // 3


def cut_to_tokens(text: str, room: int) -> str:
    """``text`` cut from its end until `estimated_tokens` says it fits in
    ``room``: what a step reads is in a message's first lines, and the rest is
    not sent rather than refused by the server."""
    cut = text
    while cut and estimated_tokens(cut) > room:
        cut = cut[: len(cut) * 3 // 4]
    return cut


class ModelUnavailableError(Exception):
    """No usable answer: the model is down or timed out, its output did not
    validate against the schema, or no model is configured for the profile.
    The step degrades to a person; it never guesses."""


class InterpretationPort(Protocol):
    """Interpret ``inputs`` into ``schema`` under ``prompt``, for ``run``.

    ``inputs`` are untrusted: the prompt registry contains each one in an
    escaped block. The answer is validated into ``schema`` before it is
    returned. Raises `ModelUnavailableError` when there is no usable answer;
    a budget or quota refusal propagates as itself.
    """

    @property
    def model_profile(self) -> str:
        """The profile every call runs on: what a reading is stamped with."""
        ...

    @property
    def route(self) -> str:
        """The profile's route every call runs on."""
        ...

    @property
    def max_input_tokens(self) -> int:
        """The most input one call on the route is sent, as the route declares
        it (`ModelRoute.max_input_tokens`). A step cuts or splits what it sends
        under this: an input the server refuses as too long is not retried
        into success, it only costs the retries."""
        ...

    async def interpret[OutputT: BaseModel](
        self,
        prompt: PromptRef,
        inputs: Mapping[str, str],
        schema: type[OutputT],
        *,
        run: RunContext,
        max_output_tokens: int,
    ) -> OutputT: ...
