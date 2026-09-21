#!/usr/bin/env python
"""Scaffold a bounded context, wired into every seam the platform declares.

    scripts/new_context.py --name sales_chat

## Why this is a script and not a checklist

A context joins the platform at FOURTEEN places across eight files, and twelve
of them are configuration:

    packages/python/dw_<name>/            the package, five layers
    pyproject.toml                        uv.sources
    pyproject.toml                        ruff known-first-party
    pyproject.toml                        mypy mypy_path
    pyproject.toml                        coverage source
    pyproject.toml                        import-linter root_packages
    pyproject.toml                        the independence contract
    apps/api/.../bootstrap/wiring.py      build from the RuntimeSeam
    apps/api/.../main.py                  mount the router
    apps/api/pyproject.toml               declare the dependency
    apps/worker/.../main.py               register the consumer
    infra/docker/api.Dockerfile           two COPY lines
    infra/docker/worker.Dockerfile        two COPY lines
    scripts/verify_architecture.py        IMPORT_TO_DIST

`CLAUDE.md` has listed these for as long as the repo has existed and nobody had
ever walked them, because this repo deliberately ships no bounded context. The
list was nearly right: walking it turned up one missing entry,
`apps/api/pyproject.toml`, which `verify_architecture.py` caught the moment the
router was mounted. A list nobody executes is the failure mode this codebase
keeps finding in itself, so the list is executable now and CI walks it on every
push.

## What it generates

A context that RUNS, not a placeholder: a domain entity with a rule, a command
handler behind a port, a graph, a router that answers, and a test for the slice.
It has no database table — a real context adds migrations, and generating a
revision into the live chain is a worse default than leaving the one step a
human should think about.

The worker lane is written COMMENTED, alone among the seams. A generated context
owns no queue, so a registered lane would be a consumer with nothing to consume;
and `test_worker.py` asserts the exact set of lanes the process hosts, so a
context's lane arriving must be a deliberate change rather than one a scaffold
slipped in.

Deliberately NOT generated: prompts, tool specs, an eval dataset. Each is a
judgement about the product, and a generated one would be a plausible-looking
artifact nobody decided on — the same failure as a policy file nothing reads.
`CLAUDE.md` says what to add and the eval gate refuses a context without
security coverage, which is where that belongs.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

_NAME = re.compile(r"^[a-z][a-z0-9_]{2,30}$")


class ScaffoldError(RuntimeError):
    """Something the caller can fix, reported without a traceback."""


@dataclass(frozen=True)
class Context:
    """One context's names, derived once so nothing re-derives them wrongly."""

    name: str

    @property
    def package(self) -> str:
        return f"dw_{self.name}"

    @property
    def dist(self) -> str:
        return f"dw-{self.name.replace('_', '-')}"

    @property
    def title(self) -> str:
        return self.name.replace("_", " ").title()

    @property
    def cls(self) -> str:
        """The PascalCase prefix every generated type shares.

        Derived once. The first draft recomputed it at twenty call sites, which
        is the shape that drifts the first time the rule changes — and it pushed
        half the templates past the line limit.
        """
        return self.name.title().replace("_", "")

    @property
    def root(self) -> Path:
        return REPO_ROOT / "packages" / "python" / self.package


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _insert_after(text: str, anchor: str, addition: str, *, what: str) -> str:
    """Put `addition` on the line after `anchor`, refusing a duplicate.

    Refusing rather than skipping: a second run that silently did nothing would
    hide a half-applied first run, which is the state a scaffold must never
    leave behind.

    The duplicate test asks whether the addition already follows THIS anchor,
    not whether it appears anywhere in the file. Those are different questions
    and the first draft asked the wrong one: `mypy_path` and `coverage source`
    legitimately carry the identical line, so writing the first made the second
    look already-done and the scaffold refused itself halfway through.
    """
    if anchor not in text:
        raise ScaffoldError(f"{what}: anchor not found ({anchor!r}); the file has moved on")
    if text[text.index(anchor) + len(anchor) :].startswith(addition):
        raise ScaffoldError(f"{what} already lists this context — is it half-created?")
    return text.replace(anchor, anchor + addition, 1)


# --------------------------------------------------------------- the package --


def _package_files(ctx: Context) -> dict[str, str]:
    p, title, cls = ctx.package, ctx.title, ctx.cls
    return {
        "pyproject.toml": f'''[project]
name = "{ctx.dist}"
version = "0.1.0"
description = "{title} bounded context"
requires-python = ">=3.12"
dependencies = [
    "dw-kernel",
    "dw-platform",
    "dw-agent-runtime",
    # Pinned to match the packages that already own these: `apps/api` for
    # FastAPI and `dw_agent_runtime` for LangGraph. A context that picked its own
    # range would be a second opinion about one fact, and uv would refuse the
    # workspace the first time the two disagreed.
    "fastapi>=0.115,<1",
    "langgraph>=0.6,<2",
    "pydantic>=2.10,<3",
    "sqlalchemy[asyncio]>=2.0.36,<2.1",
]

[build-system]
requires = ["hatchling>=1.26"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/{p}"]
''',
        f"src/{p}/__init__.py": f'"""The {title} bounded context."""\n',
        f"src/{p}/py.typed": "",
        f"src/{p}/domain/__init__.py": "",
        f"src/{p}/domain/entities.py": (
            f'''"""What this context is about. No framework anywhere near it.

Replace `{title}Request` with the real thing. What must NOT change is the
shape: a frozen model that refuses an invalid state in its constructor, so
nothing downstream has to ask whether it is valid.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class {cls}Request(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: uuid.UUID
    tenant_id: uuid.UUID
    subject: str = Field(min_length=1, max_length=200)

    def summary(self) -> str:
        """A domain rule, here so the layer is not an empty folder."""
        return self.subject.strip()
'''
        ),
        f"src/{p}/application/__init__.py": "",
        f"src/{p}/application/ports.py": f'''"""Ports this context needs, declared BY the consumer.

The composition root satisfies them. Declaring them here rather than importing a
concrete adapter is what keeps the handler testable without infrastructure.
"""

from __future__ import annotations

from typing import Protocol

from {p}.domain.entities import {cls}Request


class {cls}SinkPort(Protocol):
    """Where a handled request goes. A real context names its repository here."""

    async def record(self, request: {cls}Request) -> None: ...
''',
        f"src/{p}/application/handlers.py": (
            f'''"""Handlers: the only place this context decides anything."""

from __future__ import annotations

from dataclasses import dataclass

from {p}.application.ports import {cls}SinkPort
from {p}.domain.entities import {cls}Request


@dataclass(frozen=True)
class Handle{cls}:
    sink: {cls}SinkPort

    async def __call__(self, request: {cls}Request) -> str:
        await self.sink.record(request)
        return request.summary()
'''
        ),
        f"src/{p}/workflows/__init__.py": "",
        f"src/{p}/workflows/graph.py": f'''"""The versioned graph, registered on the runtime seam.

Typed state and a version in the registry key, because a run records the graph
version it started on and a resume replays that exact one.
"""

from __future__ import annotations

from typing import Any, TypedDict

GRAPH_ID = "{ctx.name}"
GRAPH_VERSION = "1.0.0"


class {cls}State(TypedDict, total=False):
    subject: str
    summary: str


def build_graph() -> Any:
    """Built lazily so importing this module needs no LangGraph at test time."""
    from langgraph.graph import END, START, StateGraph

    def summarise(state: {cls}State) -> {cls}State:
        return {{"summary": state.get("subject", "").strip()}}

    graph: StateGraph[{cls}State, None, {cls}State, {cls}State] = StateGraph(
        {cls}State
    )
    graph.add_node("summarise", summarise)
    graph.add_edge(START, "summarise")
    graph.add_edge("summarise", END)
    return graph.compile()
''',
        f"src/{p}/adapters/__init__.py": "",
        f"src/{p}/adapters/sink.py": (
            f'''"""Adapters: the only layer allowed to know a database or an SDK.

This one keeps requests in memory, which is a real implementation of the port
and not a placeholder — a context with a table replaces it with a SQL repository
and a migration.
"""

from __future__ import annotations

from {p}.domain.entities import {cls}Request


class InMemory{cls}Sink:
    """Implements this context's `{cls}SinkPort`."""

    def __init__(self) -> None:
        self.recorded: list[{cls}Request] = []

    async def record(self, request: {cls}Request) -> None:
        self.recorded.append(request)
'''
        ),
        f"src/{p}/presentation/__init__.py": "",
        f"src/{p}/presentation/routes.py": (
            f'''"""HTTP surface. Authorization belongs where the mutation is."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from {p}.application.handlers import Handle{cls}
from {p}.domain.entities import {cls}Request

router = APIRouter(prefix="/api/v1/{ctx.name.replace("_", "-")}", tags=["{ctx.name}"])


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=200)


def build_router(handler: Handle{cls}) -> APIRouter:
    """Injected, never resolved from a global: the app owns the wiring."""

    @router.post("/requests")
    async def create(body: _Body) -> dict[str, str]:
        # Tenancy comes from the verified access context in a real context, never
        # from the body. Fixed here so the generated slice cannot look like a
        # place where a client supplies its own tenant.
        request = {cls}Request(
            request_id=uuid.uuid4(), tenant_id=uuid.UUID(int=0), subject=body.subject
        )
        return {{"summary": await handler(request)}}

    return router
'''
        ),
        "tests/unit/__init__.py": "",
        f"tests/unit/test_{ctx.name}_slice.py": (
            f'''"""The generated slice, end to end, no infrastructure.

Kept because a scaffold that shipped untested code would be teaching the wrong
habit on the first file a new context ever has.
"""

from __future__ import annotations

import uuid

import pytest

from {p}.adapters.sink import InMemory{cls}Sink
from {p}.application.handlers import Handle{cls}
from {p}.domain.entities import {cls}Request

pytestmark = pytest.mark.unit


async def test_a_handled_request_reaches_the_sink_and_comes_back_summarised() -> None:
    sink = InMemory{cls}Sink()
    request = {cls}Request(
        request_id=uuid.uuid4(), tenant_id=uuid.uuid4(), subject="  báo giá quý 4  "
    )

    summary = await Handle{cls}(sink)(request)

    assert summary == "báo giá quý 4"
    assert sink.recorded == [request]


def test_an_empty_subject_is_refused_by_the_entity() -> None:
    """In the constructor, so nothing downstream has to ask whether it is valid."""
    # One id for both fields, so this line stays inside the line limit whatever
    # the context is named — the generated code has to pass `ruff format --check`
    # for every legal name, not just a short one.
    an_id = uuid.uuid4()
    with pytest.raises(ValueError):
        {cls}Request(request_id=an_id, tenant_id=an_id, subject="")
'''
        ),
    }


# ------------------------------------------------------------- the root wiring --


def _patch_root_pyproject(ctx: Context) -> None:
    path = REPO_ROOT / "pyproject.toml"
    text = _read(path)
    text = _insert_after(
        text,
        "dw-evals = { workspace = true }\n",
        f"{ctx.dist} = {{ workspace = true }}\n",
        what="uv.sources",
    )
    text = _insert_after(
        text,
        '    "dw_evals",\n    "dw_api",\n',
        f'    "{ctx.package}",\n',
        what="ruff known-first-party",
    )
    text = _insert_after(
        text,
        '    "packages/python/dw_evals/src",\n',
        f'    "packages/python/{ctx.package}/src",\n',
        what="mypy_path",
    )
    # The coverage denominator. A context absent from here is a context whose
    # untested modules never lower the number — the coverage gate unable to see
    # what it is gating.
    #
    # Anchored on two lines, not one: `packages/python/dw_platform/src` appears
    # in `mypy_path` as well, and a single-line anchor would quietly insert this
    # into the wrong list.
    text = _insert_after(
        text,
        '    "packages/python/dw_platform/src",\n    "apps/api/src",\n',
        f'    "packages/python/{ctx.package}/src",\n',
        what="coverage source",
    )
    before = text
    text = text.replace(
        '    "dw_observability",\n    "dw_evals",\n]\n\n[[tool.importlinter.contracts]]',
        f'    "dw_observability",\n    "dw_evals",\n    "{ctx.package}",\n]\n\n'
        f"""[[tool.importlinter.contracts]]
# Contexts are independent: one importing another is a super-agent forming, and
# the second one is always where it starts. The platform may not import a
# context either — that direction is what keeps the skeleton reusable.
name = "{ctx.title} is independent"
type = "forbidden"
source_modules = ["{ctx.package}"]
forbidden_modules = ["dw_api", "dw_worker", "dw_docgen"]

[[tool.importlinter.contracts]]""",
        1,
    )
    if text == before:
        raise ScaffoldError("import-linter root_packages: anchor not found")
    _write(path, text)


def _patch_api(ctx: Context) -> None:
    p, cls = ctx.package, ctx.cls

    path = REPO_ROOT / "apps" / "api" / "src" / "dw_api" / "bootstrap" / "wiring.py"
    text = _read(path)
    text = _insert_after(
        text,
        "    # ---- BOUNDED CONTEXTS PLUG IN HERE -----------------------------------\n",
        f"""    # {ctx.title}: built from the seam, never from a global. `container.runtime`
    # carries the session factory, clock, ids, registries and gateways; anything
    # this context needs beyond them is its own adapter.
    from {p}.adapters.sink import InMemory{cls}Sink
    from {p}.application.handlers import Handle{cls}

    container.{ctx.name}_handler = Handle{cls}(InMemory{cls}Sink())

""",
        what="wiring seam",
    )
    _write(path, text)

    path = REPO_ROOT / "apps" / "api" / "src" / "dw_api" / "bootstrap" / "container.py"
    text = _read(path)
    text = _insert_after(
        text,
        "    run_store: SqlWorkerRunStore | None = None\n",
        f"    {ctx.name}_handler: object | None = None\n",
        what="ApiContainer",
    )
    _write(path, text)

    path = REPO_ROOT / "apps" / "api" / "src" / "dw_api" / "main.py"
    text = _read(path)
    text = _insert_after(
        text,
        "    # ---- BOUNDED CONTEXT ROUTERS MOUNT HERE ------------------------------\n",
        f"""    # Guarded on the dependency it needs: a context whose wiring is absent
    # mounts nothing rather than mounting a route that 500s on every call.
    if container.{ctx.name}_handler is not None:
        from {p}.application.handlers import Handle{cls}
        from {p}.presentation.routes import build_router as build_{ctx.name}_router

        assert isinstance(container.{ctx.name}_handler, Handle{cls})
        app.include_router(build_{ctx.name}_router(container.{ctx.name}_handler))

""",
        what="router mount",
    )
    _write(path, text)


def _patch_worker(ctx: Context) -> None:
    path = REPO_ROOT / "apps" / "worker" / "src" / "dw_worker" / "main.py"
    text = _read(path)
    text = _insert_after(
        text,
        "    # ---- BOUNDED CONTEXT LANES REGISTER HERE -----------------------------\n",
        f"""    # {ctx.title} registers here. Left COMMENTED on purpose, twice over:
    #
    #   - a generated context owns no queue, so a lane would be a consumer with
    #     nothing to consume — a placeholder, which this repo does not ship;
    #   - `apps/worker/tests/unit/test_worker.py` asserts the exact set of lanes
    #     this process hosts, so a context's lane arriving is a deliberate,
    #     visible change and not something a scaffold slips in.
    #
    # Uncomment when the context has real work, add `{ctx.dist}` to
    # `apps/worker/pyproject.toml`, name the lane in that test, and append a
    # `ReapTarget` for every job queue it owns so abandoned rows are settled by
    # the one reaper rather than by a second sweeper.
    #
    #     from {ctx.package}.adapters import ...
    #     registry.register("{ctx.name}", <its consumer>)

""",
        what="worker lane",
    )
    _write(path, text)


def _patch_api_pyproject(ctx: Context) -> None:
    """The API declares what it imports.

    `verify_architecture.py` found this one: mounting the router makes
    `apps/api` an importer of the context, and an undeclared import is a package
    that builds locally and fails in the container, where only declared
    dependencies are installed.
    """
    path = REPO_ROOT / "apps" / "api" / "pyproject.toml"
    text = _read(path)
    text = _insert_after(
        text,
        '    "dw-memory",\n',
        f'    "{ctx.dist}",\n',
        what="apps/api dependencies",
    )
    _write(path, text)


def _patch_verify_architecture(ctx: Context) -> None:
    """The twelfth seam, and the one this script did not know about.

    `verify_architecture.py` maps an import name to the distribution that must
    declare it, and refuses an import it has never heard of. A context absent
    from that map fails the check with "unknown third-party import" — which is
    the check doing its job, and is how the count went from eleven to twelve.
    """
    path = REPO_ROOT / "scripts" / "verify_architecture.py"
    text = _read(path)
    text = _insert_after(
        text,
        '    "dw_docgen": "dw-docgen",\n',
        f'    "{ctx.package}": "{ctx.dist}",\n',
        what="verify_architecture IMPORT_TO_DIST",
    )
    _write(path, text)


def _patch_dockerfiles(ctx: Context) -> None:
    for name in ("api.Dockerfile", "worker.Dockerfile"):
        path = REPO_ROOT / "infra" / "docker" / name
        text = _read(path)
        anchor = (
            "COPY packages/python/dw_evals/pyproject.toml packages/python/dw_evals/pyproject.toml\n"
        )
        text = _insert_after(
            text,
            anchor,
            f"COPY packages/python/{ctx.package}/pyproject.toml"
            f" packages/python/{ctx.package}/pyproject.toml\n",
            what=name,
        )
        _write(path, text)


def scaffold(ctx: Context) -> None:
    if ctx.root.exists():
        raise ScaffoldError(f"{ctx.root.relative_to(REPO_ROOT)} already exists")
    # Root files first: they are the ones that fail loudly if the repo has moved
    # on, and failing before any file is written leaves nothing half-made.
    _patch_root_pyproject(ctx)
    _patch_api(ctx)
    _patch_worker(ctx)
    _patch_api_pyproject(ctx)
    _patch_verify_architecture(ctx)
    _patch_dockerfiles(ctx)
    for relative, body in _package_files(ctx).items():
        _write(ctx.root / relative, body)


def _format(ctx: Context) -> bool:
    """Hand everything this script wrote to `ruff format`.

    Not a nicety. The templates interpolate a name of any legal length into
    lines whose width therefore depends on the name, so a template that fits for
    `sales_chat` spills for a longer one — measured, with a 29-character name:
    four files came out unformatted, two of them in `apps/api`. Chasing that per
    template is fixing the symptom at every site instead of the cause once.

    Returns False when ruff is not on PATH, which is a real state for someone
    running the script outside the workspace — the scaffold is still correct,
    it just needs `ruff format` run over it.
    """
    ruff = shutil.which("ruff")
    if ruff is None:
        return False
    # Fixed argv; every path comes from this script, none from the caller.
    subprocess.run(
        [ruff, "format", "--quiet", *(str(p) for p in _TOUCHED_PYTHON(ctx))],
        cwd=REPO_ROOT,
        check=True,
    )
    return True


def _TOUCHED_PYTHON(ctx: Context) -> list[Path]:  # noqa: N802 - reads as a constant
    return [
        ctx.root,
        REPO_ROOT / "apps" / "api" / "src" / "dw_api" / "main.py",
        REPO_ROOT / "apps" / "api" / "src" / "dw_api" / "bootstrap" / "wiring.py",
        REPO_ROOT / "apps" / "api" / "src" / "dw_api" / "bootstrap" / "container.py",
        REPO_ROOT / "apps" / "worker" / "src" / "dw_worker" / "main.py",
        REPO_ROOT / "scripts" / "verify_architecture.py",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Scaffold a bounded context.")
    parser.add_argument("--name", required=True, help="snake_case, e.g. sales_chat")
    args = parser.parse_args()

    if not _NAME.match(args.name):
        raise SystemExit(f"--name must be snake_case, 3-31 chars: {args.name!r}")

    ctx = Context(args.name)
    try:
        scaffold(ctx)
    except ScaffoldError as exc:
        raise SystemExit(f"scaffold refused: {exc}") from exc

    formatted = _format(ctx)
    print(f"created packages/python/{ctx.package} and wired 14 seams", file=sys.stderr)
    if not formatted:
        print("ruff not on PATH — run `ruff format` over the new files", file=sys.stderr)
    print(
        "next: uv sync --all-packages, then make lint typecheck test-unit test-architecture\n"
        "still yours to add: migrations, configs/workers/"
        f"{ctx.name}.yaml, prompts, tool specs, and an eval dataset with"
        " prompt_injection / cross_tenant_attack / missing_evidence coverage",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
