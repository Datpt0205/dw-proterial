"""RunContext -> AccessContext must carry the record-visibility roll-up.

Regression guard for the agent-path IDOR: a run in a restricted tenant used to
rebuild its AccessContext without `visible_owners`, so every CRM read inside the
run saw the whole workspace instead of the caller's owner subtree (ADR-003).
"""

from __future__ import annotations

import uuid

from dw_agent_runtime.context import access_context_from_run
from dw_agent_runtime.contracts import RunContext


def _run(**overrides: object) -> RunContext:
    base: dict[str, object] = {
        "run_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "workspace_id": uuid.uuid4(),
        "actor_id": uuid.uuid4(),
        "worker_id": "lookup",
        "worker_version": "0.0.0",
        "channel": "web",
        "plan_id": "pro",
        "roles": frozenset(),
        "scopes": frozenset(),
        "trace_id": "t",
    }
    base.update(overrides)
    return RunContext(**base)


def test_restricted_roll_up_is_carried_into_the_access_context() -> None:
    owner = uuid.uuid4()
    ac = access_context_from_run(
        _run(record_visibility="restricted", visible_owners=frozenset({owner}))
    )
    assert ac.record_visibility == "restricted"
    assert ac.visible_owners == frozenset({owner})


def test_defaults_stay_open_for_system_runs() -> None:
    ac = access_context_from_run(_run())
    assert ac.record_visibility == "open"
    assert ac.visible_owners is None
