"""The worker's own prompt, placed in front of what the harness wrote.

`deepagents` builds part of the system message itself. `SkillsMiddleware`
appends the skills catalogue - the only channel that tells a model which skills
exist - and `FilesystemMiddleware` appends the host-path routing for a
composite backend. Both are pinned OUTSIDE anything a caller passes in
`middleware=`, and outer middleware runs first, so by the time a caller's own
prompt middleware is reached those sections are already in `request`.

`dynamic_prompt` REPLACES the system message. Used for a worker prompt it
therefore deletes them on every model call, silently: nothing errors, the
prompt is complete on its own terms, and the only symptom is a model that never
uses a skill it was never told about. That is how `sales_chat` shipped a
drawing tool the assistant answered around for a week - `ui.present` was
offered and `generative-ui` was unreachable, so every answer came back as
prose.

Prepending is also the order `create_deep_agent` produces for its own
`system_prompt` parameter: the caller's text first, the harness sections
appended below it. That parameter is not usable for a prompt that names today's
date and the screen in view, because it is resolved once at build time and
these agents are compiled once per process - hence a middleware that renders
per call and keeps the same shape.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, cast

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage

__all__ = ["WorkerSystemPrompt"]


class WorkerSystemPrompt(AgentMiddleware[Any, Any]):
    """Renders the worker prompt per model call and puts it above the rest."""

    def __init__(self, render: Callable[[ModelRequest[Any]], str]) -> None:
        super().__init__()
        self._render = render

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        appended = list(request.system_message.content_blocks) if request.system_message else []
        message = SystemMessage(
            content_blocks=[cast(Any, {"type": "text", "text": self._render(request)}), *appended]
        )
        return await handler(request.override(system_message=message))
