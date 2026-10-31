"""DW2 assembled from its adapters: the one call a composition root makes.

`build_purchasing` takes what only the app has (the session factory, the
platform's audit repository and policy overrides, the authorization service,
the model gateway) and returns the services the router mounts. The mailbox is
the demo's mock, bound to the one demo (tenant, workspace); every other scope
reads it empty.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_agent_runtime.adapters.model_interpretation import GatewayInterpretation
from dw_agent_runtime.model.profiles import ModelProfileRegistry
from dw_agent_runtime.ports import ModelGateway
from dw_agent_runtime.registry import parse_worker_file
from dw_kernel.errors import ConfigError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_purchasing.adapters.mock.inbox import MockInbox
from dw_purchasing.adapters.persistence.store import AuditFactory, SqlPurchasingStore
from dw_purchasing.adapters.policy_files import PolicyFiles
from dw_purchasing.application.access import Gate, PurchasingAuthorizationPort
from dw_purchasing.application.intake import PurchaseRequests, Worker
from dw_purchasing.application.ports import TenantPolicyPort
from dw_purchasing.application.rules import RuleBook
from dw_purchasing.application.services import PurchasingServices


def interpretation_for(model: ModelGateway, configs: Path, profile: str) -> GatewayInterpretation:
    """DW2's door to ``model`` on ``profile``, bounded by what the profile's
    structured route declares it may be sent, read from the profile file so
    the bound has one owner; a route that declares none is refused at startup."""
    profiles = ModelProfileRegistry()
    profiles.load_directory(configs / "models")
    route = profiles.resolve(profile).structured_extraction
    if route.max_input_tokens is None:
        raise ConfigError(f"model profile {profile} declares no max_input_tokens")
    return GatewayInterpretation(model, profile, route.max_input_tokens)


def build_purchasing(
    *,
    demo_scope: tuple[uuid.UUID, uuid.UUID],
    configs: Path,
    session_factory: async_sessionmaker[AsyncSession],
    audit: AuditFactory,
    authorization: PurchasingAuthorizationPort,
    tenant_policies: TenantPolicyPort,
    model: ModelGateway | None,
    clock: UtcClock,
    ids: IdGenerator,
) -> PurchasingServices:
    worker, _ = parse_worker_file(configs / "workers" / "purchasing.yaml")
    files = PolicyFiles.load(configs / "policies")
    requests = PurchaseRequests(
        uow=SqlPurchasingStore(session_factory, audit),
        gate=Gate(authorization),
        rules=RuleBook(files, tenant_policies, files.versions),
        inbox=MockInbox.load(tenant_id=demo_scope[0], workspace_id=demo_scope[1]),
        model=(
            None
            if model is None
            else interpretation_for(model, configs, worker.default_model_profile)
        ),
        worker=Worker(worker.worker_id, worker.worker_version),
        clock=clock,
        ids=ids,
    )
    return PurchasingServices(requests=requests)
