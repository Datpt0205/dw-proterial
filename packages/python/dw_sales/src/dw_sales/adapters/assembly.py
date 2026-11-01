"""DW1 on its mock data, built one way for every process that hosts it.

The API mounts the Sales routes over it; the worker runs DW1's mailbox lane
over it (ticket 16). Both must read the same mailbox with the same readers,
rules and policies, and register the same graph, or a message processed by
the lane would be processed differently from one a person pressed "DW xử lý"
on. So neither composition root spells the list out: each hands in what its
process already built (sessions, the platform's ports, the runtime) and calls
`build_dw1`.

DW1's mailbox is a fictional mock bound to one (tenant, workspace),
``scope``; every other scope reads it empty. Or, given ``mailbox="stored"``,
the real mail the worker stores from the drop folder (ticket 43). So is its master data, list by
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
from typing import Literal, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_agent_runtime.adapters.model_interpretation import GatewayInterpretation, ProfileStepModel
from dw_agent_runtime.adapters.model_measurements import SqlModelMeasurements
from dw_agent_runtime.approval_flow import ApproveAndResumeService
from dw_agent_runtime.model.interpretation import InterpretationPort
from dw_agent_runtime.model.profiles import ModelProfileRegistry
from dw_agent_runtime.ports import ModelGateway, WorkflowRunnerPort
from dw_agent_runtime.registry import (
    ConfigError,
    GraphRegistry,
    WorkerRegistry,
    parse_worker_file,
)
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.adapters.outbox_folder import FolderOutbox
from dw_platform.adapters.persistence.rule_versions import SqlRuleVersionLookup
from dw_platform.application.malware import MalwareScanPort
from dw_sales.adapters.artifact_files import ArtifactFiles
from dw_sales.adapters.catalog_templates import XlsxCatalogTemplates
from dw_sales.adapters.mail_folder import LocalDropFolder
from dw_sales.adapters.memory_rules import static_rule_book
from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
from dw_sales.adapters.order_rules import load_tenant_order_rules
from dw_sales.adapters.persistence.activity import SqlStepActivityReader
from dw_sales.adapters.persistence.assistant import SqlAssistantStoreFactory
from dw_sales.adapters.persistence.catalog import (
    OutboxFactory,
    SqlApprovedLists,
    SqlCatalogUnitOfWorkFactory,
)
from dw_sales.adapters.persistence.followups import SqlFollowupScopes
from dw_sales.adapters.persistence.layouts import SqlLayoutLookup
from dw_sales.adapters.persistence.mailbox import SqlMailbox
from dw_sales.adapters.persistence.orders import SqlOrderCaseLookup
from dw_sales.adapters.persistence.outbound import SqlOutboundScopes
from dw_sales.adapters.persistence.processing import SqlProcessingQueue
from dw_sales.adapters.persistence.quotes import SqlQuoteCaseLookup
from dw_sales.adapters.persistence.recorded_converts import SqlRecordedConverts
from dw_sales.adapters.persistence.recorded_quotations import SqlRecordedQuotations
from dw_sales.adapters.persistence.recorded_senders import SqlRecordedSenders
from dw_sales.adapters.persistence.rule_drafts import SqlRuleDraftScopes
from dw_sales.adapters.persistence.uow import (
    ApprovalsFactory,
    AuditFactory,
    SqlSalesUnitOfWorkFactory,
)
from dw_sales.adapters.policy_files import load_sales_policies, rule_book
from dw_sales.adapters.reader_client import ReaderTransport, client_readers
from dw_sales.adapters.runtime import RuntimeDw1Runs
from dw_sales.application.access import SalesAuthorizationPort
from dw_sales.application.activity import ActivityService
from dw_sales.application.brief_writing import BriefWriter
from dw_sales.application.catalog_imports import CatalogParsing, CatalogSettlement
from dw_sales.application.column_mapping import ColumnMatcher
from dw_sales.application.followups import BriefWriterPort, FollowupLane
from dw_sales.application.handoffs import HandoffReader
from dw_sales.application.inbox_lane import InboxLane, ServiceAccessPort
from dw_sales.application.layouts import LayoutChecks, LayoutPrefiller, LayoutSettlement
from dw_sales.application.mail_drop import MailDrop, MailDropNotices, RulesMailIntake
from dw_sales.application.message_intent import IntentReader
from dw_sales.application.model_calls import TimedInterpretation
from dw_sales.application.model_readiness import ModelReadiness
from dw_sales.application.model_reading import DescriptionReader
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.order_ports import ModelStepGatePort, OrderRulesPort
from dw_sales.application.outbound_mail import OutboundLane
from dw_sales.application.po_body_reading import PoBodyReader
from dw_sales.application.ports import (
    ArtifactBytesPort,
    MemberDirectoryPort,
    NotificationSenderPort,
    SalesCatalogPort,
    SalesScope,
    ScopeHoldersPort,
)
from dw_sales.application.process_settings import RoleCatalogPort
from dw_sales.application.processing import (
    ProcessingDrain,
    ProcessingQueuePort,
    RequesterAccessPort,
)
from dw_sales.application.quotation import QuotationService
from dw_sales.application.reply_intent import ReplyReader
from dw_sales.application.rfq_reading import AttachmentTextPort, ModelRequests, RfqModelReader
from dw_sales.application.rule_drafts import RuleDrafting, RuleDraftSweep
from dw_sales.application.rules import RuleBookOrderRules, RuleSettlement
from dw_sales.application.scanned_inbox import ScannedInbox
from dw_sales.application.services import SalesServices, assemble
from dw_sales.application.snapshot_catalog import SnapshotSalesCatalog
from dw_sales.application.source import NoSourceCache, SourceCachePort
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
    # What drafts a rule version from an uploaded template in the worker
    # ("Tạo từ tệp mẫu"); built with the drain, which resolves who asked.
    rule_drafting: RuleDrafting | None = None
    # What fails a draft its event lost and drops old ones, with no request.
    rule_draft_sweep: RuleDraftSweep | None = None
    # What DW1's model steps did, per case and over time (slice 3), for the
    # activity routes (`dw_sales.presentation.activity_routes`).
    activity: ActivityService | None = None
    # What stores the mail dropped as `.eml` files (ticket 43): built only
    # for a process given the folder, over the stored mailbox.
    mail_drop: MailDrop | None = None
    # What writes the opening of the 07:30 brief (AI item 10): built with
    # the drain, which resolves each recipient, where a model is wired.
    brief_writer: BriefWriter | None = None
    # "Gửi cho khách": the lane writing jobs to the outbox share and reading
    # its receipts; built with the drain, given the share.
    outbound: OutboundLane | None = None


# Which mailbox DW1 reads: the fictional mock, or the mail stored from the
# drop folder (ticket 43). One value both processes are given.
Mailbox = Literal["mock", "stored"]


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
    roles: RoleCatalogPort,
    lane_access: ServiceAccessPort | None = None,
    requester_access: RequesterAccessPort | None = None,
    model: ModelGateway | None = None,
    one_call_model: ModelGateway | None = None,
    mailbox: Mailbox = "mock",
    mail_drop: Path | None = None,
    source_cache: SourceCachePort | None = None,
    # "Gửi cho khách": on in the API where the deployment says so; the share
    # itself, its outbox folders, only in the worker, which alone writes them.
    outbox_enabled: bool = False,
    outbox_dir: Path | None = None,
) -> Dw1Mount:
    """DW1's services over ``scope``'s mock data, its graph and worker
    (``configs/workers/sales.yaml``) registered on ``runtime``, every `sales.`
    approval made strict and checked by the context before it is recorded
    (`dw_sales.workflows.graph.register`); its spans through ``telemetry``,
    the process's own, cut to Sales' allowlist (`dw_sales.application.telemetry`);
    and, given ``lane_access``, the mailbox lane over the same services;
    given ``requester_access``, the drain of the processing queue that "DW
    xử lý" and the lane fill (ticket 25), which runs each job as whoever
    asked, resolved again by the platform, and the drafting of a rule version
    from an uploaded template, asked of ``one_call_model`` (the one-call door:
    the plan's daily allowance checked before the call), as whoever uploaded
    it. Every attachment is scanned by
    ``scanner`` before anything reads it (ticket 25): the mailbox each service
    holds is the scanned one. Every file is then read through ``reader``, the
    reader sandbox wherever a process is deployed
    (`dw_sales.adapters.reader_client`). A model step runs only where the
    tenant's rules turn it on and its live eval met the bar for the model and
    prompt it runs on (`model_readiness`, read from the database); the process
    page names who acts on each step from ``roles``, the platform's catalog.

    The mailbox is ``mailbox``: the mock bound to ``scope``, or the mail
    stored from the drop folder (ticket 43), which ``mail_drop`` names for the
    one process that reads it into the store."""
    # The lists Sales maintains by hand from each workspace's approved import,
    # the mock where none is approved yet (ticket 41); the ERP's records from
    # the mock until Bravo is connected.
    catalog = SnapshotSalesCatalog(
        SqlApprovedLists(session_factory),
        MockSalesCatalog.load(scope),
        SqlRecordedQuotations(session_factory),
        SqlRecordedConverts(session_factory),
        SqlRecordedSenders(session_factory),
    )
    catalog_uow = SqlCatalogUnitOfWorkFactory(
        session_factory, audit=audit, approvals=approvals, outbox=outbox
    )
    policies = load_sales_policies(configs / "policies", configs / "copy")
    readers = client_readers(reader, policies.order_rules.intake)
    stored = SqlMailbox(session_factory, audit)
    if mail_drop is not None and mailbox != "stored":
        raise ValueError("a drop folder is read into the stored mailbox only")
    inbox = ScannedInbox(
        stored if mailbox == "stored" else MockInbox.load(scope), scanner, readers.po
    )
    # The platform's rules, with a tenant's own approved version where it has
    # one (ticket 19): stored, proposed and approved through `/sales/rules`.
    book = rule_book(policies, SqlRuleVersionLookup(session_factory))
    dropped = (
        None
        if mail_drop is None
        else MailDrop(
            LocalDropFolder(mail_drop),
            readers.mail,
            stored,
            RulesMailIntake(book),
            MailDropNotices(holders, notifications),
            clock,
            ids,
        )
    )
    tenant_rules = RuleBookOrderRules(book)
    worker_file = configs / "workers" / "sales.yaml"
    worker, _ = parse_worker_file(worker_file)
    order_cases = SqlOrderCaseLookup(session_factory)
    # Each call timed, on the model it ran on, for the step rows (slice 3).
    interpretation = (
        None
        if model is None
        else TimedInterpretation(
            interpretation_for(model, configs, worker.default_model_profile),
            step_model(configs, worker.default_model_profile),
        )
    )
    readiness = model_readiness(configs, session_factory)
    # What DW1's model steps did: the activity routes, the process page's
    # share and the case lists' drill-down read it.
    step_activity = SqlStepActivityReader(session_factory)
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
            else model_requests(interpretation, catalog, tenant_rules, readers.texts, readiness)
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
        body_pos=None if interpretation is None else PoBodyReader(interpretation),
        model_steps=readiness,
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
        # The API's cache keeps an opened page or grid for a while; a process
        # serving no source view keeps nothing.
        source_cache=source_cache or NoSourceCache(),
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
        draft_uow=catalog_uow,
        readiness=readiness,
        roles=roles,
        step_activity=step_activity,
        # An uploaded signed quotation is scanned like every attachment.
        scanner=scanner,
        converts=catalog,
        senders=catalog,
        assistant=SqlAssistantStoreFactory(session_factory),
        one_call=(
            None
            if one_call_model is None
            else interpretation_for(one_call_model, configs, worker.default_model_profile)
        ),
        worker_id=worker.worker_id,
        worker_version=worker.worker_version,
        outbox_enabled=outbox_enabled or outbox_dir is not None,
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
    catalog_parsing = CatalogParsing(
        catalog_uow,
        readers.tables,
        scanner,
        catalog,
        clock,
        ids,
        # A file no template header matches, its columns matched by the model
        # as the importer (AI item 2): where a model and the drain are wired.
        columns=(
            None
            if one_call_model is None or requester_access is None
            else ColumnMatcher(
                interpretation_for(one_call_model, configs, worker.default_model_profile)
            )
        ),
        access=requester_access,
        worker_id=worker.worker_id,
        worker_version=worker.worker_version,
    )
    activity = ActivityService(uow, assembly.services.gate, step_activity, clock)
    lane = (
        None
        if lane_access is None
        else InboxLane(uow, inbox, assembly.services.processing, lane_access, clock)
    )
    if requester_access is None:
        return Dw1Mount(
            services=assembly.services,
            lane=lane,
            catalog_parsing=catalog_parsing,
            activity=activity,
            mail_drop=dropped,
        )
    queue = SqlProcessingQueue(session_factory)
    drain = ProcessingDrain(
        queue, uow, assembly.services.dw1, requester_access, clock, ids, channels=lane
    )
    rule_drafting = RuleDrafting(
        uow=catalog_uow,
        sheets=readers.source,
        scanner=scanner,
        rules=book,
        access=requester_access,
        model=(
            None
            if one_call_model is None
            else interpretation_for(one_call_model, configs, worker.default_model_profile)
        ),
        clock=clock,
        ids=ids,
        worker_id=worker.worker_id,
        worker_version=worker.worker_version,
    )
    return Dw1Mount(
        services=assembly.services,
        lane=lane,
        drain=drain,
        queue=queue,
        catalog_parsing=catalog_parsing,
        rule_drafting=rule_drafting,
        rule_draft_sweep=RuleDraftSweep(
            catalog_uow, SqlRuleDraftScopes(session_factory), clock, ids
        ),
        activity=activity,
        mail_drop=dropped,
        outbound=(
            None
            if outbox_dir is None
            else OutboundLane(
                uow=uow,
                scopes=SqlOutboundScopes(session_factory),
                outbox=FolderOutbox(outbox_dir),
                artifact_bytes=artifact_bytes,
                quotes=assembly.services.quote_commands,
                access=requester_access,
                notifications=notifications,
                clock=clock,
                ids=ids,
            )
        ),
        brief_writer=(
            None
            if one_call_model is None
            else BriefWriter(
                model=interpretation_for(one_call_model, configs, worker.default_model_profile),
                access=requester_access,
                ids=ids,
                worker_id=worker.worker_id,
                worker_version=worker.worker_version,
            )
        ),
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
        uow,
        rule_book(policies, SqlRuleVersionLookup(session_factory)),
        clock,
        ids,
        model_readiness(configs, session_factory),
    )


def build_followup_lane(
    *,
    configs: Path,
    session_factory: async_sessionmaker[AsyncSession],
    audit: AuditFactory,
    approvals: ApprovalsFactory,
    clock: UtcClock,
    ids: IdGenerator,
    holders: ScopeHoldersPort,
    notifications: NotificationSenderPort,
    # The brief's writer (AI item 10), from DW1's mount; None: counts only.
    writer: BriefWriterPort | None = None,
) -> tuple[FollowupLane, SqlFollowupScopes]:
    """DW1's follow-ups and morning brief (ticket 42), for the worker's
    `sales_followups` lane, and the workspaces it visits: every one with a
    Sales case (`sales.followup_scopes()`). Each tenant's timings are its
    resolved `sales_followups` policy, read through the rule book; nothing
    else here is DW1's services, so it needs no mailbox and no files."""
    uow = SqlSalesUnitOfWorkFactory(session_factory, audit=audit, approvals=approvals)
    policies = load_sales_policies(configs / "policies", configs / "copy")
    book = rule_book(policies, SqlRuleVersionLookup(session_factory))
    lane = FollowupLane(uow, book, holders, notifications, clock, ids, writer)
    return lane, SqlFollowupScopes(session_factory)


def model_requests(
    model: InterpretationPort,
    catalog: SalesCatalogPort,
    rules: OrderRulesPort,
    texts: AttachmentTextPort,
    gate: ModelStepGatePort,
) -> ModelRequests:
    """The quotation flow's model step over ``model`` (ticket 29): requests
    read from the mail and the attachments' ``texts``, item descriptions as
    ticket 28 reads them, switched by the tenant's rules and held to the
    step's bar by ``gate``."""
    reader = RfqModelReader(model, texts, catalog, DescriptionReader(model))
    return ModelRequests(reader=reader, rules=rules, gate=gate)


def _profiles(configs: Path) -> ModelProfileRegistry:
    profiles = ModelProfileRegistry()
    profiles.load_directory(configs / "models")
    return profiles


def step_model(configs: Path, profile: str) -> ProfileStepModel:
    """The model DW1's steps run on per tenant, read from the profile files
    the gateway reads."""
    return ProfileStepModel(_profiles(configs), profile)


def model_readiness(
    configs: Path, session_factory: async_sessionmaker[AsyncSession]
) -> ModelReadiness:
    """Whether a model step has met its bar for a tenant (dw_sales ADR 0005,
    addendum of 2026-10-23): the tenant's measurements, under its RLS, for
    the model DW1's worker profile (`configs/workers/sales.yaml`) routes it
    to. Built with or without a model server: a proposal that turns a step on
    is checked either way."""
    worker, _ = parse_worker_file(configs / "workers" / "sales.yaml")
    return ModelReadiness(
        SqlModelMeasurements(session_factory),
        step_model(configs, worker.default_model_profile),
    )


def interpretation_for(model: ModelGateway, configs: Path, profile: str) -> GatewayInterpretation:
    """DW1's door to ``model`` on ``profile``, bounded by what the profile's
    structured route declares it may be sent (`ModelRoute.max_input_tokens`):
    read here, from the profile file, so the bound has one owner. A route
    that declares none is refused at startup, not on the first long mail."""
    route = _profiles(configs).resolve(profile).structured_extraction
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
