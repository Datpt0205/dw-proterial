"""Skills a turn is served: words that say how to do one kind of work
(dw_sales ADR 0014, ticket 40).

A skill is a name, a one-line description and instructions, in the shape
deepagents' `SkillsMiddleware` reads (`SKILL.md`: frontmatter, then the text).
The model sees every skill's name and description in its catalogue and loads
the one whose description fits the work, through a tool code offers; it is
never handed a skill code chose for it (ADR 0014 decision 3: code guards, it
does not route).

**Words, never power.** A skill adds no tool, no scope, no recipient and no
number: the tools a turn may call are the worker's toolset, each bound by code
and run through `ToolExecutor`, whatever a skill says. A skill that asks for
another tool, another customer or another tenant asks a model that can reach
none of them.

**Served by code, for the run's tenant.** Code resolves the set for a run
(its tenant's approved version of each skill, else the platform's, never
another tenant's) and serves it around one turn (`serving`), as a context's
tools are bound around one. The catalogue and the loading tool read only what
is served; a turn with none served is offered no skill at all, and a load
from a run of another tenant or workspace than the set's is refused.

**What a reading used** is what it loaded (`ServedSkills.loaded`): the refs a
reading stamps, so a case says which version of which words read it.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Final

from dw_agent_runtime.contracts import RunContext
from dw_kernel.errors import PermissionDeniedError

__all__ = ["NAME", "ServedSkills", "Skill", "SkillSet", "served", "serving"]

# A skill's name as deepagents validates it (the Agent Skills specification):
# lowercase letters and digits in words joined by single hyphens, at most 64.
NAME: Final = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_NAME_LENGTH: Final = 64
_DESCRIPTION_LENGTH: Final = 1024


@dataclass(frozen=True, slots=True)
class Skill:
    """One skill as a turn is served it."""

    name: str
    description: str
    body: str
    # The version a reading stamps: ``<id>@<semver>``, the platform's or the
    # tenant's own.
    ref: str

    def __post_init__(self) -> None:
        if len(self.name) > _NAME_LENGTH or not NAME.match(self.name):
            raise ValueError("a skill's name is lowercase words joined by hyphens")
        if not self.description.strip() or len(self.description) > _DESCRIPTION_LENGTH:
            raise ValueError("a skill has a description of at most 1024 characters")
        if not self.body.strip():
            raise ValueError("a skill has instructions")


@dataclass(frozen=True, slots=True)
class SkillSet:
    """The skills resolved for one run's tenant and workspace."""

    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    skills: tuple[Skill, ...]

    def __post_init__(self) -> None:
        if len({s.name for s in self.skills}) != len(self.skills):
            raise ValueError("a skill set names each skill once")

    def named(self, name: str) -> Skill | None:
        return next((s for s in self.skills if s.name == name), None)


@dataclass
class ServedSkills:
    """A set served around one turn, and the refs the turn loaded, in order."""

    skills: SkillSet
    loaded: list[str] = field(default_factory=list)

    def load(self, name: str, run: RunContext) -> Skill | None:
        """The skill named ``name`` for ``run``: refused for a run of another
        tenant or workspace than the set's; None for a name the set lacks."""
        if (self.skills.tenant_id, self.skills.workspace_id) != (run.tenant_id, run.workspace_id):
            raise PermissionDeniedError(
                "a skill is loaded only for the run it was resolved for",
                details={"rule": "skill_scope"},
            )
        skill = self.skills.named(name)
        if skill is not None and skill.ref not in self.loaded:
            self.loaded.append(skill.ref)
        return skill


_SERVED: ContextVar[ServedSkills | None] = ContextVar("dw_served_skills", default=None)


@contextmanager
def serving(skills: SkillSet) -> Iterator[ServedSkills]:
    """``skills`` are the catalogue and what may be loaded inside the block,
    and nothing outside it."""
    held = ServedSkills(skills)
    token = _SERVED.set(held)
    try:
        yield held
    finally:
        _SERVED.reset(token)


def served() -> ServedSkills | None:
    """What the turn in progress is served; None outside `serving`."""
    return _SERVED.get()
