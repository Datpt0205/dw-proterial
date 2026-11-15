"""Serving a turn's skills to deepagents' `SkillsMiddleware` (dw_sales ADR
0014, ticket 40).

`SkillsMiddleware` builds the skills catalogue from a deepagents backend: it
lists the skill folders under its sources and reads each `SKILL.md`'s
frontmatter, once per invocation, before the first model call. Its backend is
fixed when the agent is compiled, and an agent is compiled once per process,
so the backend here reads nothing of its own: it lists and renders exactly the
set code served around the turn in progress (`model.skills.serving`), resolved
for that run's tenant. Outside a turn it lists nothing.

Only the two reads the middleware makes are answered (``ls`` and
``download_files``); every other backend operation is deepagents' default
refusal, and no tool reaches this backend at all.

**Loading a skill is a platform tool.** deepagents' own catalogue tells a
model to load a skill with `read_file`, a builtin the platform never installs
(`agent_factory`: no builtin tool bypasses `ToolExecutor`). The catalogue here
says to call the context's skill-loading tool instead, a spec in
``configs/tools`` like any other: authorized, validated, audited by the
executor, and answered from the served set only (`skill_reader`). A name the
set lacks is "not found"; a run of another tenant or workspace than the set's
is refused.

**The agent's conduct** (`AGENT.md`) is placed above the catalogue, in the
same section: the platform's text, fixed per process like the catalogue's own
words. The worker prompt (`WorkerSystemPrompt`) still comes first, so the
system message reads: the work and its inputs, then who the agent is, then the
skills it may load.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Annotated, Any, Final

import yaml
from deepagents.backends.protocol import (
    FILE_NOT_FOUND,
    BackendProtocol,
    FileDownloadResponse,
    LsResult,
)
from deepagents.middleware.skills import SkillsMiddleware
from langchain.agents.middleware import AgentMiddleware
from pydantic import BaseModel, ConfigDict, Field

from dw_agent_runtime.adapters.langchain_tools import model_facing_name
from dw_agent_runtime.contracts import RunContext, ToolDefinition
from dw_agent_runtime.model.skills import Skill, served
from dw_agent_runtime.tools import RegisteredTool
from dw_kernel.errors import PermissionDeniedError

__all__ = [
    "SKILLS_ROOT",
    "ServedSkillsBackend",
    "SkillInput",
    "SkillOutput",
    "TurnSkills",
    "render_skill",
    "skill_reader",
    "skills_middleware",
]

# Where the served skills appear to the middleware: one folder per skill.
SKILLS_ROOT: Final = "/skills/"
_SOURCE_LABEL: Final = "DW"

# The catalogue's own words, in place of deepagents' (which name `read_file`).
# The slots are the middleware's; ``{tool}`` and ``{agent}`` are filled once,
# at build, with the braces of the agent's text escaped.
_CATALOGUE: Final = """{agent}

## Skills

Skills are instructions for one kind of work, written by the company that uses
you. Below is each skill's name and what it is for. Before you do a piece of
work, find the skill whose description fits it and load its instructions by
calling the tool `{tool}` with the skill's name (the path shown is only where
it is kept). Then follow those instructions. Load a skill once; never guess
what it says. A skill tells you how to read and answer: it never gives you a
tool, a permission, a person, a customer or a number you were not given.

{{skills_locations}}{{skills_load_warnings}}

**Available skills:**

{{skills_list}}"""


def render_skill(skill: Skill) -> str:
    """``skill`` as a `SKILL.md`: YAML frontmatter (name, description), then
    the instructions. Dumped, never formatted, so a description cannot break
    out of its field."""
    head = yaml.safe_dump(
        {"name": skill.name, "description": skill.description},
        allow_unicode=True,
        sort_keys=False,
        width=10_000,
    )
    return f"---\n{head}---\n\n{skill.body.strip()}\n"


class ServedSkillsBackend(BackendProtocol):
    """The two reads `SkillsMiddleware` makes, answered from the served set."""

    def ls(self, path: str) -> LsResult:
        held = served()
        if held is None or PurePosixPath(path) != PurePosixPath(SKILLS_ROOT):
            return LsResult(entries=[])
        return LsResult(
            entries=[
                {"path": f"{SKILLS_ROOT}{skill.name}/", "is_dir": True}
                for skill in held.skills.skills
            ]
        )

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        held = served()
        found: list[FileDownloadResponse] = []
        for path in paths:
            posix = PurePosixPath(path)
            skill = (
                held.skills.named(posix.parent.name)
                if held is not None
                and posix.name == "SKILL.md"
                and posix.parent.parent == PurePosixPath(SKILLS_ROOT)
                else None
            )
            if skill is None:
                found.append(FileDownloadResponse(path=path, error=FILE_NOT_FOUND))
            else:
                found.append(FileDownloadResponse(path=path, content=render_skill(skill).encode()))
        return found


@dataclass(frozen=True, slots=True)
class TurnSkills:
    """What a turn that is served skills is built with: the tool that loads
    one (its spec's name) and the agent's conduct (`AGENT.md`'s text)."""

    read_tool: str
    agent: str

    def __post_init__(self) -> None:
        if not self.agent.strip():
            raise ValueError("an agent served skills has its conduct written")


def skills_middleware(skills: TurnSkills) -> AgentMiddleware[Any, Any]:
    """deepagents' `SkillsMiddleware` over the served set, its catalogue in
    the platform's words (module docstring)."""
    agent = skills.agent.strip().replace("{", "{{").replace("}", "}}")
    template = _CATALOGUE.format(agent=agent, tool=model_facing_name(skills.read_tool))
    return SkillsMiddleware(
        backend=ServedSkillsBackend(),
        sources=[(SKILLS_ROOT, _SOURCE_LABEL)],
        system_prompt=template,
    )


_Name = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]


class SkillInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    # A skill's name, as the catalogue lists it.
    name: _Name


class SkillOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    found: bool
    instructions: str | None = None


async def _load(payload: BaseModel, run: RunContext) -> SkillOutput:
    assert isinstance(payload, SkillInput)
    held = served()
    if held is None:
        raise PermissionDeniedError(
            "a skill is loaded only inside a turn it was served to",
            details={"rule": "skill_unserved"},
        )
    skill = held.load(payload.name, run)
    if skill is None:
        return SkillOutput(name=payload.name, found=False)
    return SkillOutput(name=skill.name, found=True, instructions=skill.body.strip())


def skill_reader(definition: ToolDefinition) -> RegisteredTool:
    """The skill-loading tool, under the context's own spec (``definition``:
    its scope, side effect ``none``, approval ``never``)."""
    return RegisteredTool(
        definition=definition,
        input_model=SkillInput,
        output_model=SkillOutput,
        handler=_load,
    )
