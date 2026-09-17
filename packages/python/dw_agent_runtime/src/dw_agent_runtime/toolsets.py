"""Toolset catalogue loaded from ``configs/toolsets``.

``ToolSpecRegistry`` answers "what does this tool version look like"; this
module answers the different question of "which tool versions does this worker
offer". Nothing expressed that before, so the agent builders read the entire
registry and the duplicate-name check stood in for a resolution step: register
two versions of one tool and agent construction died, because both collapse to
the same model-facing name.

Resolution belongs in configuration rather than in Python — picking "the highest
version" in code would be a policy invented at the call site.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from dw_agent_runtime.registry import ConfigError
from dw_kernel.errors import NotFoundError
from dw_kernel.overlay import TenantOverlay

_SEMVER_PATTERN = r"^\d+\.\d+\.\d+$"


class ToolPin(BaseModel):
    """One tool at one version."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    version: str = Field(pattern=_SEMVER_PATTERN)


class Toolset(BaseModel):
    """The tools one worker version offers, pinned by version."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(pattern=r"^1\.0$")
    toolset_id: str
    version: str = Field(pattern=_SEMVER_PATTERN)
    tools: tuple[ToolPin, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def one_version_per_name(self) -> Toolset:
        """Two versions of one tool cannot both be offered in the same turn.

        They collapse to the same model-facing name once the namespace dot is
        replaced, so the model could not address them separately and the scope
        map would let one govern the other.
        """
        names = [pin.name for pin in self.tools]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"toolset pins two versions of: {', '.join(duplicates)}")
        return self

    @property
    def pins(self) -> tuple[tuple[str, str], ...]:
        return tuple((pin.name, pin.version) for pin in self.tools)


@dataclass(frozen=True)
class LoadedToolset:
    toolset: Toolset
    checksum: str
    source_path: Path


@dataclass
class ToolsetRegistry:
    """Fail-fast registry keyed by (toolset_id, version)."""

    # Platform toolsets plus per-tenant overrides: which tools a worker offers
    # is exactly the knob a customer's process turns.
    _toolsets: TenantOverlay[tuple[str, str], LoadedToolset] = field(default_factory=TenantOverlay)

    def load_directory(
        self, directory: Path, *, tenant_id: UUID | None = None
    ) -> list[LoadedToolset]:
        return [
            self.load_file(path, tenant_id=tenant_id) for path in sorted(directory.rglob("*.yaml"))
        ]

    def load_file(self, path: Path, *, tenant_id: UUID | None = None) -> LoadedToolset:
        raw = path.read_bytes()
        try:
            toolset = Toolset.model_validate(yaml.safe_load(raw))
        except (yaml.YAMLError, ValidationError) as exc:
            raise ConfigError(f"toolset {path.name} invalid: {exc}") from exc
        loaded = LoadedToolset(
            toolset=toolset, checksum=hashlib.sha256(raw).hexdigest(), source_path=path
        )
        self.register(loaded, tenant_id=tenant_id)
        return loaded

    def register(self, loaded: LoadedToolset, *, tenant_id: UUID | None = None) -> None:
        key = (loaded.toolset.toolset_id, loaded.toolset.version)
        existing = self._toolsets.existing(key, tenant_id=tenant_id)
        if existing is not None:
            raise ConfigError(
                f"toolset already registered: {key[0]}@{key[1]} "
                f"({existing.source_path.name} and {loaded.source_path.name})"
            )
        self._toolsets.put(key, loaded, tenant_id=tenant_id)

    def resolve(self, toolset_id: str, version: str, *, tenant_id: UUID | None = None) -> Toolset:
        loaded = self._toolsets.get((toolset_id, version), tenant_id=tenant_id)
        if loaded is None:
            raise NotFoundError(
                "toolset not registered",
                details={"toolset_id": toolset_id, "version": version},
            )
        return loaded.toolset
