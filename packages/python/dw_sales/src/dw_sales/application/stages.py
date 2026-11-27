"""A case finishes on the stage versions it was opened with (ticket 61, step 2).

DW1's work is five stages (ticket 61 step 1). A stage changes by a new
version beside the old one, never by editing the one open cases run on, so a
case opened on version N finishes on N after N+1 ships. Step 2 proves the
mechanism on one stage first, **write Bravo** (Đạt, 2026-11-23): the stage
with the hardest consequences and the fewest modules.

- **The stamp**: `CaseOrigin.stage_versions`, written once when a case is
  opened from `STAGE_DEFAULTS` and never looked up again; the database refuses
  an UPDATE that changes it (migration `7add0d23936a`'s trigger). Every reader
  takes the case's stamp, never today's default (one owner per fact: a stamp
  beats a fresh lookup).
- **The dispatch**: `StageHandlers`, one per stage, built at the composition
  root: version -> the code that does the stage's work. For write Bravo that
  is the gateway's command set (`BravoCommandsPort`): which command kinds a
  change becomes and how their content is hashed. A case pinned to a version
  with no handler is refused loudly, never run on the newest.
- **Removing a version**: refused at start-up while an open case is pinned to
  it (`refuse_orphans`, from `sales.open_cases_by_stage()`, counts only).

Not yet (step 2's next slices): rollout per PIC and shadow runs
(`sales.stage_rollouts`); the release manifest's `stages/<stage>@<semver>`.
Until then a new version reaches new cases by moving `STAGE_DEFAULTS`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from dw_kernel.errors import ConflictError


class Stage(StrEnum):
    """The stages versioned per case so far."""

    WRITE_BRAVO = "write_bravo"


# The version each new case is stamped with. Moving one is how a new version
# reaches new cases until per-PIC rollouts exist; the open ones keep theirs.
STAGE_DEFAULTS: Final[Mapping[Stage, str]] = MappingProxyType({Stage.WRITE_BRAVO: "1.0.0"})

_SEMVER: Final = re.compile(r"\d+\.\d+\.\d+")


def current_stages() -> dict[str, str]:
    """What a case opened now is stamped with."""
    return {stage.value: version for stage, version in STAGE_DEFAULTS.items()}


class StageConfigError(RuntimeError):
    """The handlers cannot serve the cases that exist: refuse to start."""


@dataclass(frozen=True)
class StageHandlers[H]:
    """The code for each version of one stage, and the refusals around it."""

    stage: Stage
    handlers: Mapping[str, H]

    def __post_init__(self) -> None:
        bad = sorted(v for v in self.handlers if not _SEMVER.fullmatch(v))
        if bad:
            raise StageConfigError(f"{self.stage.value}: not a version: {bad}")
        default = STAGE_DEFAULTS[self.stage]
        if default not in self.handlers:
            raise StageConfigError(
                f"{self.stage.value}@{default} is what new cases are stamped with,"
                " and no handler serves it"
            )

    def at(self, version: str) -> H:
        """The handler of ``version``; a version no handler serves is refused."""
        handler = self.handlers.get(version)
        if handler is None:
            raise ConflictError(
                "this case runs on a stage version this deployment no longer serves",
                details={
                    "stage": self.stage.value,
                    "version": version,
                    "rule": "stage_version_unavailable",
                },
            )
        return handler

    def pinned(self, stage_versions: Mapping[str, str]) -> str:
        """The version the case was stamped with. A case with no stamp for
        this stage is refused: it was never meant to run here."""
        version = stage_versions.get(self.stage.value)
        if version is None:
            raise ConflictError(
                "this case was opened with no version of this stage",
                details={"stage": self.stage.value, "rule": "stage_not_pinned"},
            )
        return version

    def for_case(self, stage_versions: Mapping[str, str]) -> tuple[str, H]:
        """The case's pinned version and its handler."""
        version = self.pinned(stage_versions)
        return version, self.at(version)

    def refuse_orphans(self, open_cases: Mapping[tuple[str, str], int]) -> None:
        """Refuse to start while an open case is pinned to a version of this
        stage no handler serves: removing a handler waits for its last case.
        ``open_cases`` counts open cases per (stage, version)."""
        orphaned = sorted(
            f"{version} ({count} open)"
            for (stage, version), count in open_cases.items()
            if stage == self.stage.value and count > 0 and version not in self.handlers
        )
        if orphaned:
            raise StageConfigError(
                f"{self.stage.value}: open cases are pinned to versions with no handler: "
                + ", ".join(orphaned)
            )
