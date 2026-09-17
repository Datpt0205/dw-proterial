"""How long a run may sit at ``running`` before it is presumed dead.

Its own policy file rather than a worker's guardrails: ``worker_runs`` is a
platform table that every host writes to, so a per-worker number would leave
whichever host loaded a different one disagreeing about the same rows.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dw_agent_runtime.registry import ConfigError

_SEMVER_PATTERN = r"^\d+\.\d+\.\d+$"

# An hour is the documented floor of what is safe; anything shorter risks
# reaping a run that is merely slow. See the policy file for the arithmetic.
MIN_STALE_SECONDS = 3600


class WorkerRunPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(pattern=r"^1\.0$")
    policy_id: str
    policy_version: str = Field(pattern=_SEMVER_PATTERN)
    stale_run_after_seconds: int = Field(ge=MIN_STALE_SECONDS)


def load_worker_run_policy(path: Path) -> WorkerRunPolicy:
    raw = path.read_bytes()
    try:
        return WorkerRunPolicy.model_validate(yaml.safe_load(raw))
    except (yaml.YAMLError, ValidationError) as exc:
        raise ConfigError(f"worker run policy {path.name} invalid: {exc}") from exc
