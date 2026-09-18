import uuid

import pytest
from pydantic import ValidationError

from dw_agent_runtime.contracts import RunContext, ToolDefinition, WorkerDefinition

pytestmark = pytest.mark.unit


def make_worker(**overrides: object) -> WorkerDefinition:
    defaults: dict[str, object] = {
        "worker_id": "demo",
        "worker_version": "1.0.0",
        "domain": "demo",
        "graph_version": "1.0.0",
        "prompt_bundle_version": "1.0.0",
        "toolset_version": "1.0.0",
        "policy_version": "1.0.0",
        "memory_policy_version": "1.0.0",
        "default_model_profile": "balanced",
        "supported_channels": frozenset({"web"}),
        "autonomy_level": "A2",
    }
    defaults.update(overrides)
    return WorkerDefinition(**defaults)


def make_tool(**overrides: object) -> ToolDefinition:
    defaults: dict[str, object] = {
        "name": "task.prepare",
        "version": "1.0.0",
        "description": "Prepare a task draft",
        "input_schema_ref": "contracts/tools/task.prepare/1.0.0/input.json",
        "output_schema_ref": "contracts/tools/task.prepare/1.0.0/output.json",
        "required_scopes": frozenset({"demo.write"}),
        "side_effect_level": "internal",
        "approval_policy": "conditional",
        "timeout_seconds": 30,
        "max_retries": 2,
        "idempotent": True,
        "data_classification": frozenset({"internal"}),
    }
    defaults.update(overrides)
    return ToolDefinition(**defaults)


def test_worker_definition_is_frozen_and_versioned() -> None:
    worker = make_worker()
    with pytest.raises(ValidationError):
        worker.worker_version = "2.0.0"  # type: ignore[misc]


def test_worker_rejects_non_semver_versions() -> None:
    with pytest.raises(ValidationError):
        make_worker(graph_version="v1")
    with pytest.raises(ValidationError):
        make_worker(worker_version="1.0")


def test_worker_rejects_non_slug_domain_and_unknown_autonomy() -> None:
    with pytest.raises(ValidationError):
        make_worker(domain="Sales Chat")
    with pytest.raises(ValidationError):
        make_worker(autonomy_level="A9")


def test_tool_name_must_be_namespaced() -> None:
    with pytest.raises(ValidationError):
        make_tool(name="prepare")


def test_critical_side_effect_always_requires_approval() -> None:
    # `conditional`, not `never`: a critical tool may no longer claim it needs no
    # person, so the weakest policy a critical tool can carry is what proves the
    # floor holds on its own. The old spelling stated the same thing with a
    # combination the contract now refuses outright.
    tool = make_tool(side_effect_level="critical", approval_policy="conditional")
    assert tool.always_requires_approval()
    assert make_tool(approval_policy="always").always_requires_approval()
    assert not make_tool().always_requires_approval()


def test_tool_timeout_and_retry_bounds() -> None:
    with pytest.raises(ValidationError):
        make_tool(timeout_seconds=0)
    with pytest.raises(ValidationError):
        make_tool(max_retries=99)


def test_never_is_refused_on_a_tool_that_reaches_outside() -> None:
    """`never` is a claim, not an instruction, and a false claim is refused.

    A tool's author cannot lower the tenant's ceiling, so a `never` on an external
    tool could only ever be read as `conditional` — which is exactly how the two
    values came to be indistinguishable. Refusing the contradiction is what gives
    `never` a reader.
    """
    with pytest.raises(ValidationError):
        make_tool(approval_policy="never", side_effect_level="external")
    with pytest.raises(ValidationError):
        make_tool(approval_policy="never", side_effect_level="critical")


def test_never_stays_legal_where_the_claim_is_true() -> None:
    for level in ("none", "internal"):
        tool = make_tool(approval_policy="never", side_effect_level=level)
        assert tool.approval_policy == "never"


def test_conditional_carries_no_such_restriction() -> None:
    """The value to reach for when a tool does reach outside."""
    tool = make_tool(approval_policy="conditional", side_effect_level="external")
    assert tool.side_effect_level == "external"


def test_run_context_defaults_to_vietnamese_locale() -> None:
    ctx = RunContext(
        run_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        worker_id="demo",
        worker_version="1.0.0",
        channel="web",
        plan_id="professional",
        roles=frozenset({"member"}),
        scopes=frozenset({"demo.read"}),
        trace_id="trace-123",
    )
    assert ctx.locale == "vi-VN"
