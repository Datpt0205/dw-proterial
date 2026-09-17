"""Tool catalogue loaded from ``configs/tools``.

A tool's policy and the words the model reads to choose it are configuration,
not code. Splitting the description into fixed parts is what keeps a catalogue
consistent: a model picks the wrong tool mostly when a description says what a
tool does but never when to avoid it.

Per-argument documentation is NOT here — it belongs on the handler's Pydantic
input model, which is what the model actually receives as a JSON schema.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dw_agent_runtime.contracts import ApprovalPolicy, SideEffectLevel, ToolDefinition
from dw_agent_runtime.model.copy import RuntimeCopy
from dw_agent_runtime.registry import ConfigError
from dw_kernel.errors import NotFoundError

_SEMVER_PATTERN = r"^\d+\.\d+\.\d+$"


class ToolSpec(BaseModel):
    """Versioned tool contract as written by a bounded context."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(pattern=r"^1\.0$")
    name: str
    version: str = Field(pattern=_SEMVER_PATTERN)
    summary: str
    when_to_use: str
    when_not_to_use: str
    returns: str
    required_scopes: frozenset[str]
    side_effect_level: SideEffectLevel
    approval_policy: ApprovalPolicy
    timeout_seconds: int = Field(gt=0, le=600)
    max_retries: int = Field(ge=0, le=10)
    idempotent: bool
    data_classification: frozenset[str]

    def description(self, copy: RuntimeCopy) -> str:
        return copy.tool_description(
            summary=self.summary,
            when_to_use=self.when_to_use,
            when_not_to_use=self.when_not_to_use,
            returns=self.returns,
        )

    def to_definition(self, copy: RuntimeCopy) -> ToolDefinition:
        base = f"contracts/tools/{self.name}@{self.version}"
        return ToolDefinition(
            name=self.name,
            version=self.version,
            description=self.description(copy),
            input_schema_ref=f"{base}/input.json",
            output_schema_ref=f"{base}/output.json",
            required_scopes=self.required_scopes,
            side_effect_level=self.side_effect_level,
            approval_policy=self.approval_policy,
            timeout_seconds=self.timeout_seconds,
            max_retries=self.max_retries,
            idempotent=self.idempotent,
            data_classification=self.data_classification,
        )


@dataclass(frozen=True)
class LoadedToolSpec:
    spec: ToolSpec
    checksum: str
    source_path: Path


@dataclass
class ToolSpecRegistry:
    copy: RuntimeCopy
    _specs: dict[tuple[str, str], LoadedToolSpec] = field(default_factory=dict)

    def load_directory(self, directory: Path) -> list[LoadedToolSpec]:
        return [self.load_file(path) for path in sorted(directory.rglob("*.yaml"))]

    def load_file(self, path: Path) -> LoadedToolSpec:
        raw = path.read_bytes()
        try:
            spec = ToolSpec.model_validate(yaml.safe_load(raw))
        except (yaml.YAMLError, ValidationError) as exc:
            raise ConfigError(f"tool spec {path.name} invalid: {exc}") from exc
        loaded = LoadedToolSpec(
            spec=spec, checksum=hashlib.sha256(raw).hexdigest(), source_path=path
        )
        self.register(loaded)
        return loaded

    def register(self, loaded: LoadedToolSpec) -> None:
        key = (loaded.spec.name, loaded.spec.version)
        if key in self._specs:
            raise ConfigError(
                f"tool spec already registered: {key[0]}@{key[1]} "
                f"({self._specs[key].source_path.name} and {loaded.source_path.name})"
            )
        self._specs[key] = loaded

    def resolve(self, name: str, version: str) -> ToolSpec:
        loaded = self._specs.get((name, version))
        if loaded is None:
            raise NotFoundError(
                "tool spec not registered", details={"tool": name, "version": version}
            )
        return loaded.spec

    def definition(self, name: str, version: str) -> ToolDefinition:
        return self.resolve(name, version).to_definition(self.copy)
