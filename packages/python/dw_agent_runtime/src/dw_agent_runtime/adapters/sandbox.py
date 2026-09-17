"""A `deepagents` sandbox backend that runs commands in the docgen container.

`BaseSandbox` derives `ls`, `read`, `write`, `edit`, `glob` and `grep` from four
primitives, so this class implements those four and inherits the rest. The model
therefore sees the tool set it already knows — `execute`, `read_file`,
`write_file`, `edit_file`, `glob`, `grep` — and nothing here has to reimplement
any of it.

ONE INSTANCE, MANY RUNS. The agent is compiled once and reused, so this backend
cannot hold a tenant or a session in instance state: two runs would share one
workdir and one of them would read the other's draft. The session is resolved
per call from LangGraph's run context, which is the same mechanism deepagents'
own `StoreBackend` uses to namespace the memory store.

The session is keyed on the CONVERSATION, not the turn. A follow-up ("shorten
the context section") then finds the files the previous turn wrote, which is
what makes editing a document feel like editing rather than regenerating. Files
still do not survive a container restart - the sandbox is a tmpfs - so a tool
that reloads an artifact remains necessary rather than merely convenient.

The synchronous half of the protocol refuses. Every host runs this agent on its
async path, the audit wrapper around this class cannot write its row
synchronously either, and an untested sync HTTP client kept only to satisfy an
abstract method is worse than a sentence saying which path to use.
"""

from __future__ import annotations

from typing import Final, NoReturn

from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox
from langgraph.runtime import get_runtime

from dw_agent_runtime.adapters.docgen_client import DocgenClient, FileResult
from dw_agent_runtime.contracts import RunContext
from dw_kernel.errors import InfrastructureError

# What the service reports when a path resolves outside the session. Replaced
# with a sentence naming the working directory, because a model that is told
# "invalid_path" retries the same path and one that is told where it may write
# does not.
_INVALID_PATH: Final = "invalid_path"

_ASYNC_ONLY: Final = (
    "the document sandbox has no synchronous path; run the agent with `ainvoke` "
    "or `astream`, which is what every host in this repo does"
)


class DocgenSandbox(BaseSandbox):
    """Talks to one docgen service; scopes every call to the caller's session."""

    def __init__(
        self,
        client: DocgenClient,
        *,
        root: str = "/work",
        run_context: RunContext | None = None,
    ) -> None:
        self._client = client
        self._root = root.rstrip("/")
        # Left unset in the agent, whose single instance serves every tenant and
        # must therefore read the run per call. Set by a caller that already
        # holds a `RunContext` and is not inside the graph's runtime - a test,
        # or a tool handler reloading an artifact.
        self._run_context = run_context

    # ------------------------------------------------------------ identity --

    @property
    def id(self) -> str:
        """The session this call belongs to, read from the run context."""
        return session_id_for(self._run_context or run_context_of_current_run())

    @property
    def root(self) -> str:
        """The directory the model works in."""
        return session_root_for(self._run_context or run_context_of_current_run(), self._root)

    # ------------------------------------------------------------- execute --

    def execute(self, command: str, *, timeout: int | None = None) -> NoReturn:
        raise InfrastructureError(_ASYNC_ONLY)

    async def aexecute(
        self,
        command: str,
        *,
        # Forwarded to the sandbox as a command deadline; it is not an
        # `asyncio.timeout()` contract on this call.
        timeout: int | None = None,
    ) -> ExecuteResponse:
        result = await self._client.execute(self.id, command, timeout=timeout)
        return ExecuteResponse(
            output=result.output, exit_code=result.exit_code, truncated=result.truncated
        )

    # --------------------------------------------------------------- files --

    def upload_files(self, files: list[tuple[str, bytes]]) -> NoReturn:
        raise InfrastructureError(_ASYNC_ONLY)

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        try:
            results = await self._client.upload(self.id, files)
        except InfrastructureError as exc:
            # Per-file, not raised: `deepagents` requires batch operations to
            # report failures the model can react to, and raising here kills the
            # turn instead.
            return [FileUploadResponse(path=path, error=str(exc)) for path, _ in files]
        return [FileUploadResponse(path=r.path, error=self._explain(r.error)) for r in results]

    def download_files(self, paths: list[str]) -> NoReturn:
        raise InfrastructureError(_ASYNC_ONLY)

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        try:
            results = await self._client.download(self.id, paths)
        except InfrastructureError as exc:
            return [FileDownloadResponse(path=path, error=str(exc)) for path in paths]
        return [self._downloaded(result) for result in results]

    # ------------------------------------------------------------ lifecycle --

    async def release(self) -> None:
        """Delete this session's directory. Idempotent."""
        await self._client.release(self.id)

    # -------------------------------------------------------------- private --

    def _downloaded(self, result: FileResult) -> FileDownloadResponse:
        return FileDownloadResponse(
            path=result.path, content=result.content, error=self._explain(result.error)
        )

    def _explain(self, error: str | None) -> str | None:
        if error == _INVALID_PATH:
            return f"{_INVALID_PATH}: paths must be inside {self.root}"
        return error


def session_id_for(context: RunContext) -> str:
    """The sandbox session a run belongs to.

    Keyed on the conversation rather than the turn, so a follow-up finds the
    files the previous turn wrote. The tenant is in the name as well, so a
    directory listing on the container says who a leftover workdir belongs to
    without a database lookup.
    """
    conversation = context.thread_id or context.run_id
    return f"t{context.tenant_id.hex[:8]}-{conversation.hex}"


def session_root_for(context: RunContext, root: str = "/work") -> str:
    """The absolute directory a run's files live in.

    A module function and not only a property, because the system prompt has to
    state this path - `write_file` requires absolute paths and the model has no
    other way to learn this one - and the prompt is rendered where no sandbox
    instance is in scope. One implementation, so the sentence the model reads
    can never name a different directory than the one its files land in.
    """
    return f"{root.rstrip('/')}/{session_id_for(context)}"


def run_context_of_current_run() -> RunContext:
    """The run this call belongs to.

    Raises rather than defaulting: a sandbox that cannot name its session would
    have to pick one, and any choice is another run's workdir.
    """
    try:
        runtime = get_runtime()
    except (RuntimeError, KeyError) as exc:
        raise InfrastructureError(
            "the document sandbox was used outside a LangGraph run, so it cannot "
            "tell which conversation it belongs to"
        ) from exc
    # Annotated `object` on purpose: `get_runtime()` leaves its context type
    # unsolved, so mypy would otherwise call the guard below unreachable and the
    # guard is the point - a graph compiled with someone else's context schema
    # must not silently share one tenant's workdir with another.
    context: object = runtime.context
    if not isinstance(context, RunContext):
        raise InfrastructureError(
            "the graph was compiled with a context that is not a RunContext, so the "
            "document sandbox cannot scope its session to a tenant"
        )
    return context
