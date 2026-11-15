"""DW1's platform skills, read from ``configs/skills/dw1`` (dw_sales ADR 0014,
ticket 40): `AGENT.md`, DW1's conduct, and one folder per skill holding its
`SKILL.md` in deepagents' format (YAML frontmatter with ``name``,
``description`` and ``metadata.version``, then the instructions).

A skill's folder is its name, as deepagents requires; its version is the
frontmatter's, which the release manifest pins with the file's checksum. A
file that does not hold to this fails here, at startup, not on the first
mail.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final

import yaml

from dw_sales.application.skills import (
    Dw1Skills,
    SkillDocument,
    platform_skills,
    skill_key,
)

__all__ = ["load_dw1_skills"]

_FRONTMATTER: Final = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
_SEMVER: Final = re.compile(r"^\d+\.\d+\.\d+$")


def _parts(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    match = _FRONTMATTER.match(text)
    if match is None:
        raise ValueError(f"{path}: no YAML frontmatter")
    head = yaml.safe_load(match.group(1))
    if not isinstance(head, dict):
        raise ValueError(f"{path}: the frontmatter is not a mapping")
    version = str((head.get("metadata") or {}).get("version", ""))
    if not _SEMVER.match(version):
        raise ValueError(f"{path}: metadata.version is not a version")
    return head, match.group(2).strip()


def _skill(path: Path) -> SkillDocument:
    head, body = _parts(path)
    if head.get("name") != path.parent.name:
        raise ValueError(f"{path}: a skill's name is its folder's")
    return SkillDocument(
        policy_id=skill_key(path.parent.name),
        policy_version=str(head["metadata"]["version"]),
        description=str(head.get("description", "")),
        instructions=body,
    )


def load_dw1_skills(directory: Path) -> Dw1Skills:
    """``directory`` (``configs/skills/dw1``) as the platform layer."""
    head, agent = _parts(directory / "AGENT.md")
    skills = [_skill(path) for path in sorted(directory.glob("*/SKILL.md"))]
    return Dw1Skills(
        agent=agent,
        agent_ref=f"{head['name']}@{head['metadata']['version']}",
        skills=platform_skills(skills),
    )
