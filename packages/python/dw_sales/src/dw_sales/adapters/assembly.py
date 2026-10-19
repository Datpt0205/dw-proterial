"""DW1 on its mock data, built one way for every process that hosts it.

The API mounts the Sales routes over it; the worker runs DW1's mailbox lane
over it (ticket 16). Both must read the same mailbox with the same readers,
rules and policies, and register the same graph, or a message processed by
the lane would be processed differently from one a person pressed "DW xử lý"
on. So neither composition root spells the list out: each hands in what its
process already built (sessions, the platform's ports, the runtime) and calls
`build_dw1`.

DW1's mailbox is a fictional mock bound to one (tenant, workspace),
``scope``; every other scope reads it empty. So is its master data, list by
list, until a workspace imports and approves its own (ticket 41,
`SnapshotSalesCatalog`): then that list is the workspace's approved snapshot. So is that
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
from dw_sales.adapters.catalog_templates import XlsxCatalogTemplates
from dw_sales.adapters.memory_rules import static_rule_book
from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
from dw_sales.adapters.model_interpretation import GatewayInterpretation
from dw_sales.adapters.order_rules import load_tenant_order_rules
from dw_sales.adapters.persistence.catalog import (
    OutboxFactory,
    SqlApprovedLists,
    SqlCatalogUnitOfWorkFactory,
)
from dw_sales.adapters.persistence.layouts import SqlLayoutLookup
from dw_sales.adapters.persistence.orders import SqlOrderCaseLookup
from dw_sales.adapters.persistence.processing import SqlProcessingQueue
from dw_sales.adapters.persistence.quotes import SqlQuoteCaseLookup
from dw_sales.adapters.persistence.rule_versions import SqlRuleVersionLookup
from dw_sales.adapters.persistence.uow import (
    ApprovalsFactory,
    AuditFactory,
    SqlSalesUnitOfWorkFactory,
)
from dw_sales.adapters.policy_files import load_sales_policies, rule_book
from dw_sales.adapters.reader_client import ReaderTransport, client_readers
from dw_sales.adapters.runtime import RuntimeDw1Runs
from dw_sales.application.access import SalesAuthorizationPort
from dw_sales.application.catalog_imports import CatalogParsing, CatalogSettlement
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
from dw_sales.application.processing import (
    ProcessingDrain,
    ProcessingQueuePort,
    RequesterAccessPort,
)
from dw_sales.application.quotation import QuotationService
from dw_sales.application.reply_intent import ReplyReader
from dw_sales.application.rfq_reading import AttachmentTextPort, ModelRequests, RfqModelReader
from dw_sales.application.rules import RuleBookOrderRules, RuleSettlement
from dw_sales.application.services import SalesServices, assemble
from dw_sales.application.snapshot_catalog import SnapshotSalesCatalog
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
    # Built only for a process that drains the processing queue
    # (`requester_access`, ticket 25), with the queue its reaper settles.
    drain: ProcessingDrain | None = None
    queue: ProcessingQueuePort | None = None
    # What reads an uploaded master-data file in the worker (ticket 41).
    catalog_parsing: CatalogParsing | None = None


def build_dw1(
    *,
    scope: SalesScope,
    configs: Path,
    session_factory: async_sessionmaker[AsyncSession],
    audit: AuditFactory,
    approvals: ApprovalsFactory,
    outbox: OutboxFactory,
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
    reader: ReaderTransport,
    lane_access: ServiceAccessPort | None = None,
    requester_access: RequesterAccessPort | None = None,
    model: ModelGateway | None = None,
) -> Dw1Mount:
    """DW1's services over ``scope``'s mock data, its graph and worker
    (``configs/workers/sales.yaml``) registered on ``runtime``, every `sales.`
    approval made strict and checked by the context before it is recorded
    (`dw_sales.workflows.graph.register`); its spans through ``telemetry``,
    the process's own, cut to Sales' allowlist (`dw_sales.application.telemetry`);
    and, given ``lane_access``, the mailbox lane over the same services;
    given ``requester_access``, the drain of the processing queue that "DW
    xử lý" and the lane fill (ticket 25), which runs each job as whoever
    asked, resolved again by the platform. Every attachment is scanned by
    ``scanner`` before anything reads it (ticket 25): the mailbox each service
    holds is the scanned one. Every file is then read through ``reader``, the
    reader sandbox wherever a process is deployed
    (`dw_sales.adapters.reader_client`)."""
    # The lists Sales maintains by hand from each workspace's approved import,
    # the mock where none is approved yet (ticket 41); the ERP's records from
    # the mock until Bravo is connected.
    catalog = SnapshotSalesCatalog(SqlApprovedLists(session_factory), MockSalesCatalog.load(scope))
    catalog_uow = SqlCatalogUnitOfWorkFactory(
        session_factory, audit=audit, approvals=approvals, outbox=outbox
    )
    policies = load_sales_policies(configs / "policies", configs / "copy")
    readers = client_readers(reader, policies.order_rules.intake)
    inbox = ScannedInbox(MockInbox.load(scope), scanner, readers.po)
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
    layout_checks = LayoutChecks(readers.po, catalog)
    quotation = QuotationService(
        catalog=catalog,
        inbox=inbox,
        rfq_reader=readers.rfq,
        reply_reader=readers.design_reply,
        cases=SqlQuoteCaseLookup(session_factory),
        ledger=catalog,
        policies=book,
        requests=(
            None
            if interpretation is None
            else model_requests(interpretation, catalog, tenant_rules, readers.texts)
        ),
    )
    intake = OrderIntake(
        catalog=catalog,
        inbox=inbox,
        reader=readers.po,
        rules=tenant_rules,
        cases=order_cases,
        new_case_id=ids.new_uuid,
        quote_forms=readers.forms,
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
        files=readers.source,
        book=book,
        directory=directory,
        holders=holders,
        notifications=notifications,
        artifact_bytes=artifact_bytes,
        artifact_writer=ArtifactFiles(),
        layout_checks=layout_checks,
        release_manifest_ref=release_manifest_ref,
        runs=runs,
        pending=runs,
        telemetry=telemetry,
        catalog_uow=catalog_uow,
        templates=XlsxCatalogTemplates(),
    )
    register(
        graphs=runtime.graphs,
        workers=runtime.workers,
        approvals=runtime.approval_flow,
        steps=assembly.decisions,
        layouts=assembly.layout_decisions,
        rules=assembly.rule_decisions,
        catalog=assembly.catalog_decisions,
        worker_file=worker_file,
    )
    catalog_parsing = CatalogParsing(catalog_uow, readers.tables, scanner, catalog, clock, ids)
    lane = (
        None
        if lane_access is None
        else InboxLane(uow, inbox, assembly.services.processing, lane_access, clock)
    )
    if requester_access is None:
        return Dw1Mount(services=assembly.services, lane=lane, catalog_parsing=catalog_parsing)
    queue = SqlProcessingQueue(session_factory)
    drain = ProcessingDrain(
        queue, uow, assembly.services.dw1, requester_access, clock, ids, channels=lane
    )
    return Dw1Mount(
        services=assembly.services,
        lane=lane,
        drain=drain,
        queue=queue,
        catalog_parsing=catalog_parsing,
    )


def build_catalog_settlement(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    audit: AuditFactory,
    approvals: ApprovalsFactory,
    outbox: OutboxFactory,
    clock: UtcClock,
    ids: IdGenerator,
) -> CatalogSettlement:
    """What carries out a decided master-data import (`sales.catalog.decided`,
    ticket 41), for the worker's outbox handler. The snapshot and the approval
    are rows of the approval's own tenant and workspace; no file is read."""
    uow = SqlCatalogUnitOfWorkFactory(
        session_factory, audit=audit, approvals=approvals, outbox=outbox
    )
    return CatalogSettlement(uow, clock, ids)


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


def build_rule_settlement(
    *,
    configs: Path,
    session_factory: async_sessionmaker[AsyncSession],
    audit: AuditFactory,
    approvals: ApprovalsFactory,
    clock: UtcClock,
    ids: IdGenerator,
) -> RuleSettlement:
    """What carries out a decided rule version approval (`sales.rules.decided`,
    ticket 38), for the worker's outbox handler. The version and the approval
    are rows of the approval's own tenant; the platform's files say which
    numbers it has released, which an approved version may not take."""
    uow = SqlSalesUnitOfWorkFactory(session_factory, audit=audit, approvals=approvals)
    policies = load_sales_policies(configs / "policies", configs / "copy")
    return RuleSettlement(
        uow, rule_book(policies, SqlRuleVersionLookup(session_factory)), clock, ids
    )


def model_requests(
    model: InterpretationPort,
    catalog: SalesCatalogPort,
    rules: OrderRulesPort,
    texts: AttachmentTextPort,
) -> ModelRequests:
    """The quotation flow's model step over ``model`` (ticket 29): requests
    read from the mail and the attachments' ``texts``, item descriptions as
    ticket 28 reads them, switched by the tenant's rules."""
    reader = RfqModelReader(model, texts, catalog, DescriptionReader(model))
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
