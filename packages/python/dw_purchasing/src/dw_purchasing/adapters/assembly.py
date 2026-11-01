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

from dw_agent_runtime.adapters.model_interpretation import GatewayInterpretation, ProfileStepModel
from dw_agent_runtime.adapters.model_measurements import SqlModelMeasurements
from dw_agent_runtime.model.profiles import ModelProfileRegistry
from dw_agent_runtime.ports import ModelGateway
from dw_agent_runtime.registry import parse_worker_file
from dw_kernel.errors import ConfigError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.adapters.persistence.directory import SqlWorkspaceDirectory
from dw_platform.adapters.persistence.rule_versions import SqlRuleVersionLookup
from dw_purchasing.adapters.bravo_file import BravoFile
from dw_purchasing.adapters.mock.inbox import MockInbox
from dw_purchasing.adapters.mock.master_data import MockMasterData
from dw_purchasing.adapters.people import DirectoryPeople
from dw_purchasing.adapters.persistence.automation import SqlAutomationScopes
from dw_purchasing.adapters.persistence.store import (
    ApprovalsFactory,
    AuditFactory,
    SqlPurchasingStore,
)
from dw_purchasing.adapters.policy_files import platform_rule_book
from dw_purchasing.application.access import Gate, PurchasingAuthorizationPort
from dw_purchasing.application.approvals import (
    RequestApprovals,
    RequestDecisions,
    RequestSettlement,
)
from dw_purchasing.application.automation import Automation, AutomationChecks, SwitchesService
from dw_purchasing.application.automation_lane import AutomationLane, ServiceAccessPort
from dw_purchasing.application.intake import PurchaseRequests, Worker
from dw_purchasing.application.orders import PurchaseOrders
from dw_purchasing.application.ports import NoticesPort
from dw_purchasing.application.reapprovals import (
    ReapprovalDecisions,
    Reapprovals,
    ReapprovalSettlement,
)
from dw_purchasing.application.requesters import RequesterDesk
from dw_purchasing.application.rule_drafting import RuleWordsDesk
from dw_purchasing.application.rules import (
    PurchasingRuleBook,
    PurchasingRulesService,
    RuleDecisions,
    RuleSettlement,
)
from dw_purchasing.application.services import PurchasingServices
from dw_purchasing.application.sourcing import SupplierSourcing


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
    approvals: ApprovalsFactory,
    authorization: PurchasingAuthorizationPort,
    model: ModelGateway | None,
    clock: UtcClock,
    ids: IdGenerator,
    deployed: bool,
    notices: NoticesPort,
) -> PurchasingServices:
    worker, _ = parse_worker_file(configs / "workers" / "purchasing.yaml")
    store = SqlPurchasingStore(session_factory, audit, approvals)
    book = rule_book(configs, session_factory)
    automation = automation_for(configs, session_factory)
    checks = AutomationChecks(automation, book)
    requests = PurchaseRequests(
        uow=store,
        gate=Gate(authorization),
        rules=book,
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
    master = MockMasterData.load(tenant_id=demo_scope[0], workspace_id=demo_scope[1])
    return PurchasingServices(
        requests=requests,
        approvals=RequestApprovals(
            uow=store,
            gate=Gate(authorization),
            rules=book,
            master=master,
            clock=clock,
            ids=ids,
            notices=notices,
        ),
        orders=PurchaseOrders(
            uow=store,
            gate=Gate(authorization),
            rules=book,
            master=master,
            spreadsheet=BravoFile(),
            clock=clock,
            ids=ids,
            deployed=deployed,
        ),
        rules=PurchasingRulesService(
            uow=store, gate=Gate(authorization), book=book, clock=clock, ids=ids, checks=checks
        ),
        switches=SwitchesService(Gate(authorization), book, automation),
        words=RuleWordsDesk(
            gate=Gate(authorization),
            book=book,
            model=requests.model,
            worker=requests.worker,
            ids=ids,
        ),
        requester=RequesterDesk(
            uow=store,
            gate=Gate(authorization),
            rules=book,
            people=DirectoryPeople(SqlWorkspaceDirectory(session_factory)),
            model=requests.model,
            worker=requests.worker,
            clock=clock,
            ids=ids,
        ),
        sourcing=SupplierSourcing(
            uow=store,
            gate=Gate(authorization),
            rules=book,
            master=master,
            inbox=requests.inbox,
            model=requests.model,
            worker=requests.worker,
            clock=clock,
            ids=ids,
            reapprovals=Reapprovals(requests.model, requests.worker, clock, ids, notices),
        ),
    )


def rule_book(
    configs: Path, session_factory: async_sessionmaker[AsyncSession]
) -> PurchasingRuleBook:
    """The platform's files under the tenant's stored versions."""
    return platform_rule_book(configs / "policies", SqlRuleVersionLookup(session_factory))


def automation_for(configs: Path, session_factory: async_sessionmaker[AsyncSession]) -> Automation:
    """Whether a step's model readings have met their bars for a tenant: its
    measurements, under its RLS, on the model DW2's worker profile
    (`configs/workers/purchasing.yaml`) routes them to for that tenant. Built
    with or without a model server: a version raising a step is checked
    either way."""
    worker, _ = parse_worker_file(configs / "workers" / "purchasing.yaml")
    profiles = ModelProfileRegistry()
    profiles.load_directory(configs / "models")
    return Automation(
        SqlModelMeasurements(session_factory),
        ProfileStepModel(profiles, worker.default_model_profile),
    )


def _checks(configs: Path, session_factory: async_sessionmaker[AsyncSession]) -> AutomationChecks:
    return AutomationChecks(
        automation_for(configs, session_factory), rule_book(configs, session_factory)
    )


def rule_decisions(
    configs: Path,
    session_factory: async_sessionmaker[AsyncSession],
    audit: AuditFactory,
    approvals: ApprovalsFactory,
) -> RuleDecisions:
    """The decision guard the API's approval flow registers under
    `RULES_APPROVAL` (the longest prefix wins over `APPROVAL_PREFIX`'s)."""
    return RuleDecisions(
        SqlPurchasingStore(session_factory, audit, approvals),
        rule_book(configs, session_factory),
        _checks(configs, session_factory),
    )


def rule_settlement(
    configs: Path,
    session_factory: async_sessionmaker[AsyncSession],
    audit: AuditFactory,
    approvals: ApprovalsFactory,
    clock: UtcClock,
    ids: IdGenerator,
) -> RuleSettlement:
    """What the worker's handler for `RULES_DECIDED` carries a decision out with."""
    return RuleSettlement(
        SqlPurchasingStore(session_factory, audit, approvals),
        rule_book(configs, session_factory),
        clock,
        ids,
        _checks(configs, session_factory),
    )


def request_decisions(
    session_factory: async_sessionmaker[AsyncSession],
    audit: AuditFactory,
    approvals: ApprovalsFactory,
) -> RequestDecisions:
    """The decision guard the API's approval flow registers under
    `APPROVAL_PREFIX`."""
    return RequestDecisions(SqlPurchasingStore(session_factory, audit, approvals))


def request_settlement(
    session_factory: async_sessionmaker[AsyncSession],
    audit: AuditFactory,
    approvals: ApprovalsFactory,
    clock: UtcClock,
    ids: IdGenerator,
    notices: NoticesPort,
) -> RequestSettlement:
    """What the worker's handler for `REQUEST_DECIDED` carries a decision out
    with, telling who asked and who sent it."""
    return RequestSettlement(
        SqlPurchasingStore(session_factory, audit, approvals), clock, ids, notices
    )


def reapproval_decisions(
    session_factory: async_sessionmaker[AsyncSession],
    audit: AuditFactory,
    approvals: ApprovalsFactory,
) -> ReapprovalDecisions:
    """The decision guard the API registers under `REAPPROVAL` (longer than
    `APPROVAL_PREFIX`, so it, not the request's guard, checks one)."""
    return ReapprovalDecisions(SqlPurchasingStore(session_factory, audit, approvals))


def reapproval_settlement(
    session_factory: async_sessionmaker[AsyncSession],
    audit: AuditFactory,
    approvals: ApprovalsFactory,
    clock: UtcClock,
    ids: IdGenerator,
    notices: NoticesPort,
) -> ReapprovalSettlement:
    """What the worker's handler for `REAPPROVAL_DECIDED` carries a decision out with."""
    return ReapprovalSettlement(
        SqlPurchasingStore(session_factory, audit, approvals), clock, ids, notices
    )


def automation_lane(
    *,
    services: PurchasingServices,
    session_factory: async_sessionmaker[AsyncSession],
    audit: AuditFactory,
    approvals: ApprovalsFactory,
    access: ServiceAccessPort,
    mailboxes: tuple[tuple[uuid.UUID, uuid.UUID], ...],
    notices: NoticesPort,
    clock: UtcClock,
    ids: IdGenerator,
) -> AutomationLane:
    """The worker's `purchasing_automation` lane over the services it built."""
    return AutomationLane(
        access=access,
        scopes=SqlAutomationScopes(session_factory),
        mailboxes=mailboxes,
        services=services,
        uow=SqlPurchasingStore(session_factory, audit, approvals),
        notices=notices,
        clock=clock,
        ids=ids,
    )
