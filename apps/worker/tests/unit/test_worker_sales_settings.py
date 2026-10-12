"""The worker and the API agree on what DW1's mailbox lane reads (ticket 16).

Two processes, two settings classes, one fact each: which (tenant, workspace)
DW1's mock mailbox is bound to, and which run policy a run is held to. The
worker's copy exists because it cannot import the API; this is what makes the
two disagree loudly instead of the lane processing a mailbox nobody sees.
"""

from __future__ import annotations

import uuid

import pytest

from dw_api.bootstrap import paths as api_paths
from dw_api.settings import ApiSettings
from dw_worker import composition
from dw_worker.settings import WorkerSettings

pytestmark = pytest.mark.unit

_ENV = (
    "SALES_DEMO_TENANT_ID",
    "SALES_DEMO_WORKSPACE_ID",
    "DW_API_SALES_DEMO_TENANT_ID",
    "DW_API_SALES_DEMO_WORKSPACE_ID",
    "DW_WORKER_SALES_DEMO_TENANT_ID",
    "DW_WORKER_SALES_DEMO_WORKSPACE_ID",
    "DW_API_DEFAULT_TENANT_ID",
    "DW_API_DEFAULT_WORKSPACE_ID",
    "DW_WORKER_DEFAULT_TENANT_ID",
    "DW_WORKER_DEFAULT_WORKSPACE_ID",
    "DW_API_PROFILE",
    "DW_WORKER_PROFILE",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("profile", ["local", "test", "uat", "production"])
def test_unnamed_both_bind_the_mailbox_to_the_same_workspace_or_none(profile: str) -> None:
    worker = WorkerSettings(profile=profile)  # type: ignore[call-arg]
    api = ApiSettings(profile=profile)  # type: ignore[call-arg]

    assert worker.sales_demo_scope() == api.sales_demo_scope()


def test_named_both_bind_it_to_the_pair_named(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant, workspace = uuid.uuid4(), uuid.uuid4()
    monkeypatch.setenv("SALES_DEMO_TENANT_ID", str(tenant))
    monkeypatch.setenv("SALES_DEMO_WORKSPACE_ID", str(workspace))

    for profile in ("local", "production"):
        worker = WorkerSettings(profile=profile)  # type: ignore[call-arg]
        api = ApiSettings(profile=profile)  # type: ignore[call-arg]
        assert worker.sales_demo_scope() == api.sales_demo_scope() == (tenant, workspace)


def test_both_hold_runs_to_the_same_run_policy() -> None:
    assert composition.WORKER_RUN_POLICY.name == api_paths.WORKER_RUN_POLICY.name
