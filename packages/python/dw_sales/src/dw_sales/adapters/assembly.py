"""DW1 on its mock data, built one way for every process that hosts it.

The API mounts the Sales routes over it; the worker runs DW1's mailbox lane
over it (ticket 16). Both must read the same mailbox with the same readers,
rules and policies, and register the same graph, or a message processed by
the lane would be processed differently from one a person pressed "DW xử lý"
on. So neither composition root spells the list out: each hands in what its
process already built (sessions, the platform's ports, the runtime) and calls
`build_dw1`.

DW1's master data and mailbox are fictional mocks bound to one (tenant,
workspace), ``scope``; every other scope reads them empty. So is that
tenant's own version of the order rules, where the sample set holds one
(`adapters/mock/data/policies`): every other tenant reads the platform's.

Given ``model``, the gateway of a process with a model server for DW1's
profile, DW1 reads through it what its own code does not (dw_sales ADR 0005):
item descriptions outside its vocabulary (ticket 28), the intent of a
message no reader accepted (ticket 31) and of a customer's reply in a case's
thread (ticket 32), each for a tenant whose rules turn it on. Without one, no
model is called at all; a reply is still attached to its case by its thread
headers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_agent_runtime.approval_flow import ApproveAndResumeService
from dw_agent_runtime.model.profiles import ModelProfileRegistry
from dw_agent_runtime.ports import ModelGateway, WorkflowRunnerPort
from dw_agent_runtime.registry import (
    ConfigError,
    GraphRegistry,
    WorkerRegistry,
    parse_worker_file,
)
from dw_kernel.ports import IdGenerator, UtcClock
from dw_sales.adapters.artifact_files import ArtifactFiles
from dw_sales.adapters.memory_rules import static_rule_book
from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
from dw_sales.adapters.model_interpretation import GatewayInterpretation
from dw_sales.adapters.order_rules import load_tenant_order_rules
from dw_sales.adapters.persistence.layouts import SqlLayoutLookup
from dw_sales.adapters.persistence.orders import SqlOrderCaseLookup
from dw_sales.adapters.persistence.quotes import SqlQuoteCaseLookup
from dw_sales.adapters.persistence.rule_versions import SqlRuleVersionLookup
from dw_sales.adapters.persistence.uow import (
    ApprovalsFactory,
    AuditFactory,
    SqlSalesUnitOfWorkFactory,
)
from dw_sales.adapters.policy_files import load_sales_policies, rule_book
from dw_sales.adapters.readers import mock_po_readers
from dw_sales.adapters.readers.text_parts import AttachmentTexts
from dw_sales.adapters.rfq_excel import ExcelDesignReplyReader, ExcelQuoteForms, ExcelRfqReader
from dw_sales.adapters.runtime import RuntimeDw1Runs
from dw_sales.adapters.source_view import FileSourceView
from dw_sales.application.access import SalesAuthorizationPort
from dw_sales.application.handoffs import HandoffReader
from dw_sales.application.inbox_lane import InboxLane, ServiceAccessPort
from dw_sales.application.layouts import LayoutChecks, LayoutPrefiller, LayoutSettlement
from dw_sales.application.malware import MalwareScanPort, ScannedInbox
from dw_sales.application.message_intent import IntentReader
from dw_sales.application.model_reading import DescriptionReader, InterpretationPort
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.order_ports import OrderRulesPort
from dw_sales.application.ports import (
    ArtifactBytesPort,
    MemberDirectoryPort,
    NotificationSenderPort,
    SalesCatalogPort,
    SalesScope,
    ScopeHoldersPort,
)
from dw_sales.application.quotation import QuotationService
from dw_sales.application.reply_intent import ReplyReader
from dw_sales.application.rfq_reading import ModelRequests, RfqModelReader
from dw_sales.application.rules import RuleBookOrderRules
from dw_sales.application.services import SalesServices, assemble
from dw_sales.application.telemetry import SpanPort
from dw_sales.application.threads import ThreadLinks
from dw_sales.domain.order_checks import OrderRules
from dw_sales.workflows.graph import register


class Dw1Runtime(Protocol):
    """The runtime pieces DW1 plugs into: where its graph and worker are
    registered, what starts its runs, and the approvals its runs pause on.
    Each host's own bundle of them satisfies it."""

    @property
    def graphs(self) -> GraphRegistry: ...

    @property
    def workers(self) -> WorkerRegistry: ...

    @property
    def runner(self) -> WorkflowRunnerPort: ...

    @property
    def approval_flow(self) -> ApproveAndResumeService: ...


@dataclass(frozen=True)
class Dw1Mount:
    services: SalesServices
    # Built only for a process that runs the mailbox lane (`lane_access`).
    lane: InboxLane | None


def build_dw1(
    *,
    scope: SalesScope,
    configs: Path,
    session_factory: async_sessionmaker[AsyncSession],
    audit: AuditFactory,
    approvals: ApprovalsFactory,
    clock: UtcClock,
    ids: IdGenerator,
    authorization: SalesAuthorizationPort,
    directory: MemberDirectoryPort,
    holders: ScopeHoldersPort,
    notifications: NotificationSenderPort,
    artifact_bytes: ArtifactBytesPort,
    release_manifest_ref: str | None,
    runtime: Dw1Runtime,
    telemetry: SpanPort,
    scanner: MalwareScanPort,
    lane_access: ServiceAccessPort | None = None,
    model: ModelGateway | None = None,
) -> Dw1Mount:
    """DW1's services over ``scope``'s mock data, its graph and worker
    (``configs/workers/sales.yaml``) registered on ``runtime``, every `sales.`
    approval made strict and checked by the context before it is recorded
    (`dw_sales.workflows.graph.register`); its spans through ``telemetry``,
    the process's own, cut to Sales' allowlist (`dw_sales.application.telemetry`);
    and, given ``lane_access``, the mailbox lane over the same services.
    Every attachment is scanned by ``scanner`` before anything reads it
    (ticket 25): the mailbox each service holds is the scanned one."""
    catalog = MockSalesCatalog.load(scope)
    readers = mock_po_readers()
    inbox = ScannedInbox(MockInbox.load(scope), scanner, readers)
    policies = load_sales_policies(configs / "policies", configs / "copy")
    # The platform's rules, with a tenant's own approved version where it has
    # one (ticket 19): stored, proposed and approved through `/sales/rules`.
    book = rule_book(policies, SqlRuleVersionLookup(session_factory))
    tenant_rules = RuleBookOrderRules(book)
    worker_file = configs / "workers" / "sales.yaml"
    worker, _ = parse_worker_file(worker_file)
    order_cases = SqlOrderCaseLookup(session_factory)
    interpretation = (
        None if model is None else interpretation_for(model, configs, worker.default_model_profile)
    )
    uow = SqlSalesUnitOfWorkFactory(session_factory, audit=audit, approvals=approvals)
    layout_checks = LayoutChecks(readers, catalog)
    quotation = QuotationService(
        catalog=catalog,
        inbox=inbox,
        rfq_reader=ExcelRfqReader(),
        reply_reader=ExcelDesignReplyReader(),
        cases=SqlQuoteCaseLookup(session_factory),
        ledger=catalog,
        rules=policies.quote_rules,
        pricing=policies.pricing,
        requests=(
            None
            if interpretation is None
            else model_requests(interpretation, catalog, tenant_rules)
        ),
    )
    intake = OrderIntake(
        catalog=catalog,
        inbox=inbox,
        reader=readers,
        rules=tenant_rules,
        cases=order_cases,
        new_case_id=ids.new_uuid,
        quote_forms=ExcelQuoteForms(),
        descriptions=None if interpretation is None else DescriptionReader(interpretation),
        intents=(
            None if interpretation is None else IntentReader(interpretation, catalog, order_cases)
        ),
        threads=ThreadLinks(uow, inbox),
        replies=None if interpretation is None else ReplyReader(interpretation),
        handoffs=(
            None if interpretation is None else HandoffReader(interpretation, catalog, order_cases)
        ),
        layouts=SqlLayoutLookup(session_factory),
        layout_prefiller=(
            None if interpretation is None else LayoutPrefiller(interpretation, layout_checks)
        ),
    )
    runs = RuntimeDw1Runs(
        runtime.runner,
        runtime.approval_flow,
        runtime.approval_flow.run_store,
        ids,
        worker_id=worker.worker_id,
        worker_version=worker.worker_version,
    )
    assembly = assemble(
        uow=uow,
        authorization=authorization,
        clock=clock,
        ids=ids,
        catalog=catalog,
        inbox=inbox,
        intake=intake,
        quotation=quotation,
        files=FileSourceView(policies.order_rules.intake),
        book=book,
        directory=directory,
        holders=holders,
        notifications=notifications,
        artifact_bytes=artifact_bytes,
        artifact_writer=ArtifactFiles(),
        artifact_copy=policies.artifact_copy,
        handoff_copy=policies.handoff_copy,
        layout_checks=layout_checks,
        release_manifest_ref=release_manifest_ref,
        runs=runs,
        pending=runs,
        telemetry=telemetry,
    )
    register(
        graphs=runtime.graphs,
        workers=runtime.workers,
        approvals=runtime.approval_flow,
        steps=assembly.decisions,
        layouts=assembly.layout_decisions,
        worker_file=worker_file,
    )
    lane = (
        None
        if lane_access is None
        else InboxLane(uow, inbox, assembly.services.dw1, lane_access, clock, ids)
    )
    return Dw1Mount(services=assembly.services, lane=lane)


def build_layout_settlement(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    audit: AuditFactory,
    approvals: ApprovalsFactory,
    clock: UtcClock,
    ids: IdGenerator,
) -> LayoutSettlement:
    """What carries out a decided PO layout approval (`sales.layout.decided`,
    ticket 30), for the worker's outbox handler. It needs no mailbox and no
    mock data: the layout and the approval are both rows, read under the
    decided approval's own tenant and workspace."""
    uow = SqlSalesUnitOfWorkFactory(session_factory, audit=audit, approvals=approvals)
    return LayoutSettlement(uow, clock, ids)


def model_requests(
    model: InterpretationPort, catalog: SalesCatalogPort, rules: OrderRulesPort
) -> ModelRequests:
    """The quotation flow's model step over ``model`` (ticket 29): requests
    read from the mail and the attachments' text, item descriptions as
    ticket 28 reads them, switched by the tenant's rules."""
    reader = RfqModelReader(model, AttachmentTexts(), catalog, DescriptionReader(model))
    return ModelRequests(reader=reader, rules=rules)


def interpretation_for(model: ModelGateway, configs: Path, profile: str) -> GatewayInterpretation:
    """DW1's door to ``model`` on ``profile``, bounded by what the profile's
    structured route declares it may be sent (`ModelRoute.max_input_tokens`):
    read here, from the profile file, so the bound has one owner. A route
    that declares none is refused at startup, not on the first long mail."""
    profiles = ModelProfileRegistry()
    profiles.load_directory(configs / "models")
    route = profiles.resolve(profile).structured_extraction
    if route.max_input_tokens is None:
        raise ConfigError(f"model profile {profile} declares no max_input_tokens for DW1's route")
    return GatewayInterpretation(model, profile, route.max_input_tokens)


def demo_order_rules(
    platform: OrderRules, scope: SalesScope, tenant_dir: Path
) -> RuleBookOrderRules:
    """The platform's order rules, with the demo tenant's own version where
    the sample set holds one, for an eval with no database: the version is
    held as approved in memory (`static_rule_book`). A process with a
    database stores it through the propose and approve route instead
    (`dw_sales.testing.seed_rules`)."""
    return RuleBookOrderRules(
        static_rule_book(platform, scope, load_tenant_order_rules(tenant_dir))
    )
