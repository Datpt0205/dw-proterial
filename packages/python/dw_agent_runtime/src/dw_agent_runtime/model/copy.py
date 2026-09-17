"""Words the runtime says, loaded from ``configs/copy``."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dw_agent_runtime.registry import ConfigError

_SEMVER_PATTERN = r"^\d+\.\d+\.\d+$"


class RuntimeCopy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(pattern=r"^1\.0$")
    copy_id: str
    version: str = Field(pattern=_SEMVER_PATTERN)
    description: str = ""
    tool_description_template: str
    approval_reason_template: str
    tool_rejected_template: str
    rejection_reason_template: str
    tool_failed_template: str
    tool_unavailable_template: str
    # Optional so every copy released before it still loads. A host that wires
    # `OneApprovalPerStepMiddleware` must load a copy that has it - the
    # middleware refuses to start otherwise - because the only other sentence
    # available tells the model not to call the tool again.
    approval_deferred_template: str | None = None
    mock_reply: str

    def tool_description(
        self, *, summary: str, when_to_use: str, when_not_to_use: str, returns: str
    ) -> str:
        return self.tool_description_template.format(
            summary=summary,
            when_to_use=when_to_use,
            when_not_to_use=when_not_to_use,
            returns=returns,
        )

    def approval_reason(self, tool: str) -> str:
        return self.approval_reason_template.format(tool=tool)

    def tool_rejected(self, tool: str, comment: str) -> str:
        reason = self.rejection_reason_template.format(comment=comment) if comment.strip() else ""
        return self.tool_rejected_template.format(tool=tool, reason=reason)

    def tool_failed(self, tool: str, code: str, message: str) -> str:
        """``code`` and ``message`` only - ``DWError.details`` is never safe to pass on."""
        return self.tool_failed_template.format(tool=tool, code=code, message=message)

    def tool_unavailable(self, tool: str, code: str) -> str:
        """The other kind of failure: the tool did not answer at all.

        ``code`` and no message, unlike the one above. That one reports a typed
        refusal whose wording we wrote; this one reports a timeout, a dead
        dependency or a plain bug, and an untyped failure's message carries the
        library's own words - a path, a query, an internal hostname. This
        string goes straight into the model's context and from there onto
        somebody's screen.
        """
        return self.tool_unavailable_template.format(tool=tool, code=code)

    def approval_deferred(self, tool: str, pending: str) -> str:
        """A gated call held back because another one in the same step is pending.

        Nothing ran and nothing failed. Kept apart from `tool_failed` on purpose:
        that sentence tells the model not to call again with the same arguments,
        and following it here would drop the second action without a word.
        """
        if self.approval_deferred_template is None:
            raise ConfigError(f"runtime copy {self.version} has no approval_deferred_template")
        return self.approval_deferred_template.format(tool=tool, pending=pending)


def load_runtime_copy(path: Path) -> RuntimeCopy:
    raw = path.read_bytes()
    try:
        return RuntimeCopy.model_validate(yaml.safe_load(raw))
    except (yaml.YAMLError, ValidationError) as exc:
        raise ConfigError(f"runtime copy {path.name} invalid: {exc}") from exc
