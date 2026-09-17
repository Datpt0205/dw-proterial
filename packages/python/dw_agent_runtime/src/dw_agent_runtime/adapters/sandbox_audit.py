"""Puts every sandbox command on the same audit trail as every tool call.

WHY THIS EXISTS. `execute` is a deepagents builtin. It never reaches
`ToolExecutor`, so it never passes through authorization, idempotency or audit —
the three things every other side-effecting call in this system goes through.
Two of those absences are fine and one is not:

- **Authorization** is not missed. The sandbox holds nothing tenant-scoped: no
  database, no object store, no credentials, no network. There is no privilege
  to check because there is nothing to reach.
- **Idempotency** is not missed either. Running a command twice inside a
  scratch directory is not a side effect; the effects that need a key are the
  tools that take a file *out* of the sandbox, and those do go through
  `ToolExecutor`.
- **Audit** is missed, and it is the one that matters. "Model-written code ran
  on our infrastructure" with no record of what ran is not something an
  incident review can work with.

So this wrapper writes one audit row per command, carrying the same run id,
tenant and workspace as the tool calls around it. Whether a run stayed inside
its lane becomes one query rather than two.

IT SUBCLASSES `BaseSandbox` RATHER THAN DELEGATING. Every file operation the
base class derives - `read`, `write`, `edit`, `glob`, `grep` - is a shell
command underneath, and routing them through this class means they are recorded
too. That is noisier than auditing only what the model typed, and it is the
stronger property: the trail says what executed in the container, not what
somebody meant to execute. It also avoids a `__getattr__` proxy, which would
pass every future deepagents method through unrecorded and unchecked.

File transfers are the exception: they move bytes without running anything, and
a file written into a tmpfs that dies with the request is not an effect anybody
can review. The moment a file leaves the sandbox it goes through a real tool,
audited by the executor like any other.

`policy_decision` is recorded as `no_policy` rather than `allow`, because no
policy was evaluated. Writing `allow` would claim a gate passed when there was
no gate; the containment here is the container, and the row should say so.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Final

from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
    SandboxBackendProtocol,
)
from deepagents.backends.sandbox import BaseSandbox

from dw_agent_runtime.adapters.sandbox import run_context_of_current_run
from dw_agent_runtime.context import access_context_from_run
from dw_agent_runtime.contracts import RunContext
from dw_kernel.errors import InfrastructureError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.ports import PlatformUnitOfWorkFactory
from dw_platform.domain.audit import AuditEvent

SANDBOX_EXECUTE_ACTION: Final = "sandbox.execute"

# Enough of the command to recognise it in a timeline; the hash identifies it
# exactly. The text is kept rather than only its digest - the opposite of what
# `ToolExecutor` does with tool input, and deliberately so: a tool's input is
# reconstructible from its name and schema, an arbitrary script is not.
COMMAND_PREVIEW_CHARS: Final = 1000


class AuditedSandbox(BaseSandbox):
    """Records what the sandbox was asked to run, then asks the sandbox to run it."""

    def __init__(
        self,
        inner: SandboxBackendProtocol,
        *,
        uow_factory: PlatformUnitOfWorkFactory,
        clock: UtcClock,
        id_generator: IdGenerator,
        run_context: RunContext | None = None,
    ) -> None:
        self._inner = inner
        self._uow_factory = uow_factory
        self._clock = clock
        self._id_generator = id_generator
        # Left unset in the agent, where it is read per call from the LangGraph
        # run. Tests pass one so they need no graph.
        self._run_context = run_context

    @property
    def id(self) -> str:
        return self._inner.id

    @property
    def root(self) -> str:
        """The run's working directory, from the backend that owns the session.

        Not `BaseSandbox`'s concern, so it is not inherited: it comes from the
        inner backend, which is the thing that knows where a session lives.
        """
        root = getattr(self._inner, "root", None)
        if not isinstance(root, str):
            raise InfrastructureError(
                "the wrapped sandbox does not say which directory a run works in"
            )
        return root

    # ------------------------------------------------------------- execute --

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        """Refused rather than run unaudited.

        The audit row is written through the async unit of work and there is no
        synchronous route to it. Quietly skipping the record on this path would
        leave exactly the gap this class exists to close, so it fails loudly.
        Every host runs this agent on its async path.
        """
        raise InfrastructureError(
            "the document sandbox refuses synchronous execution because the audit "
            "record cannot be written synchronously; run the agent on its async path"
        )

    async def aexecute(
        self,
        command: str,
        *,
        # Forwarded to the sandbox as a command deadline; it is not an
        # `asyncio.timeout()` contract on this call.
        timeout: int | None = None,
    ) -> ExecuteResponse:
        started = self._clock.now()
        response = await self._inner.aexecute(command, timeout=timeout)
        await self._record(command, response, started=started)
        return response

    # --------------------------------------------------------------- files --
    # Delegated without a record; see the module docstring.

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return self._inner.upload_files(files)

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return await self._inner.aupload_files(files)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return self._inner.download_files(paths)

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return await self._inner.adownload_files(paths)

    # -------------------------------------------------------------- private --

    async def _record(self, command: str, response: ExecuteResponse, *, started: datetime) -> None:
        context = self._run_context or run_context_of_current_run()
        finished = self._clock.now()
        event = AuditEvent(
            id=self._id_generator.new_uuid(),
            tenant_id=TenantId(context.tenant_id),
            workspace_id=WorkspaceId(context.workspace_id),
            actor_id=UserId(context.actor_id),
            action=SANDBOX_EXECUTE_ACTION,
            resource_type="sandbox",
            resource_id=self.id,
            run_id=context.run_id,
            policy_decision="no_policy",
            trace_id=context.trace_id,
            details={
                "command": command[:COMMAND_PREVIEW_CHARS],
                "command_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(),
                "command_chars": len(command),
                "exit_code": response.exit_code,
                "output_truncated": response.truncated,
                "duration_ms": int((finished - started).total_seconds() * 1000),
            },
            occurred_at=finished.astimezone(UTC),
        )
        async with self._uow_factory(access_context_from_run(context)) as uow:
            await uow.audit.append(event)
            await uow.commit()
