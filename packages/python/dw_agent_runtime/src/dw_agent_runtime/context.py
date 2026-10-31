"""Bridging RunContext (per-run trusted context) to platform AccessContext."""

from __future__ import annotations

import uuid
from typing import Final

from dw_agent_runtime.contracts import RunContext
from dw_platform.application.access_context import AccessContext

# The channel a run is recorded under when a person started it from the
# portal: every run but a lane's that names its own.
WEB_CHANNEL: Final = "web"


def access_context_from_run(run_context: RunContext) -> AccessContext:
    """Derive the platform AccessContext for DB/audit work inside a run.

    The RunContext was built at the boundary from a verified AccessContext, so
    this is a projection, not an escalation.
    """
    return AccessContext(
        tenant_id=run_context.tenant_id,
        workspace_id=run_context.workspace_id,
        principal_id=run_context.actor_id,
        roles=run_context.roles,
        scopes=run_context.scopes,
        plan_id=run_context.plan_id,
        # Dropping this silently pinned every retrieval inside a run to
        # "internal", so a caller cleared for confidential material got an empty
        # result set rather than a refusal - a failure nobody would report.
        clearance=run_context.clearance,
        # The ADR-003 roll-up, same reason: dropping it made a run's CRM reads
        # ignore the owner subtree and see the whole workspace.
        record_visibility=run_context.record_visibility,
        visible_owners=run_context.visible_owners,
        # And the ceiling, for the same reason as the two above: a projection
        # that dropped it would read as the most restrictive level by default,
        # which is safe, but would not be what the run was granted.
        max_autonomy_level=run_context.autonomy_ceiling,
    )


def caller_run(
    context: AccessContext,
    *,
    run_id: uuid.UUID,
    worker_id: str,
    worker_version: str,
    trace: str,
    subject_ref: str,
    channel: str = WEB_CHANNEL,
) -> RunContext:
    """A one-call run as the person who asked (from the portal unless
    ``channel`` names the lane that asked for them): their plan is what the
    allowance checks, and the call is recorded under the context's worker.
    The inverse of `access_context_from_run` (sales, lifted by docs/adr/0013)."""
    return RunContext(
        run_id=run_id,
        tenant_id=context.tenant_id,
        workspace_id=context.workspace_id,
        actor_id=context.principal_id,
        worker_id=worker_id,
        worker_version=worker_version,
        channel=channel,
        plan_id=context.plan_id,
        roles=context.roles,
        scopes=context.scopes,
        clearance=context.clearance,
        record_visibility=context.record_visibility,
        visible_owners=context.visible_owners,
        autonomy_ceiling=context.max_autonomy_level,
        trace_id=f"{trace}-{run_id.hex[:12]}",
        subject_ref=subject_ref,
    )
