"""The Sales services the API mounts, assembled from the ports they take.

Built by the composition root from concrete adapters; nothing here names
one. `None` in place of the whole bundle is a deployment where no data
source is configured: every Sales route then answers "chưa cấu hình nguồn
dữ liệu" (ticket 05, G31).

Two bundles, for two callers. `SalesServices` is what the routes get.
`CaseDecisions`, the steps a DW1 run takes and the check of a decision on a
Sales approval, goes only to the graph and the approval flow: a route that
could reach it would be a door around the run (the plan's run quota, the
approval it pauses on).
"""

from __future__ import annotations

from dataclasses import dataclass

from dw_kernel.ports import IdGenerator, UtcClock
from dw_sales.application.access import Gate, SalesAuthorizationPort
from dw_sales.application.activity_ports import StepActivityReadPort
from dw_sales.application.artifact_content import ArtifactWriterPort
from dw_sales.application.artifacts_service import ArtifactService
from dw_sales.application.assignment import AssignmentService
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.catalog_imports import (
    CatalogDecisions,
    CatalogImportService,
    CatalogTemplatePort,
    CatalogUnitOfWorkFactory,
)
from dw_sales.application.decisions import CaseDecisions
from dw_sales.application.design_text_reading import DesignTextReplies
from dw_sales.application.finding_explanations import FindingExplanations
from dw_sales.application.inbox_service import InboxProcessing, InboxQueries
from dw_sales.application.layouts import LayoutChecks, LayoutDecisions, LayoutService
from dw_sales.application.malware import MalwareScanPort
from dw_sales.application.master_data_service import MasterDataService
from dw_sales.application.model_readiness import ModelReadiness
from dw_sales.application.model_reading import InterpretationPort
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.order_ports import ConvertLedgerPort
from dw_sales.application.orders_service import OrderCommands, OrderQueries
from dw_sales.application.outbound_mail import OutboundMailService
from dw_sales.application.overview_service import OverviewService
from dw_sales.application.pc_dates import PcDateReplies
from dw_sales.application.pipeline import PipelineService
from dw_sales.application.ports import (
    ArtifactBytesPort,
    InboxPort,
    MemberDirectoryPort,
    NotificationSenderPort,
    SalesCatalogPort,
    ScopeHoldersPort,
)
from dw_sales.application.process_settings import ProcessSettingsService, RoleCatalogPort
from dw_sales.application.processing import ProcessingService
from dw_sales.application.quotation import QuotationService
from dw_sales.application.quotes_service import QuoteCommands, QuoteQueries
from dw_sales.application.routed_mail import RoutedMailService
from dw_sales.application.rule_drafts import RuleDraftService, RuleDraftUnitOfWorkFactory
from dw_sales.application.rules import RuleDecisions, SalesRulesService, TenantRuleBook
from dw_sales.application.runs import Dw1Runs, Dw1RunsPort, PendingDecisionsPort
from dw_sales.application.screening_followups import ScreeningFollowups
from dw_sales.application.sender_customers import SenderCustomers, SenderLedgerPort
from dw_sales.application.source import SourceCachePort, SourceService, SourceViewPort
from dw_sales.application.telemetry import SalesSpans, SpanPort
from dw_sales.application.thread_summaries import ThreadSummaries
from dw_sales.application.worker_service import WorkerService


@dataclass(frozen=True)
class SalesServices:
    overview: OverviewService
    # Every case by status, and one case's history (the pipeline board).
    pipeline: PipelineService
    inbox: InboxQueries
    # "DW xử lý": the routes queue a message (ticket 25); the worker runs it.
    processing: ProcessingService
    dw1: Dw1Runs
    orders: OrderQueries
    order_commands: OrderCommands
    quotes: QuoteQueries
    quote_commands: QuoteCommands
    sources: SourceService
    artifacts: ArtifactService
    master_data: MasterDataService
    worker: WorkerService
    assignment: AssignmentService
    # A routed message marked handled, or open again (2026-10-27).
    routed_mail: RoutedMailService
    layouts: LayoutService
    # A tenant's own rule versions, proposed and approved (ticket 19).
    rules: SalesRulesService
    # The process page: each step and the rule fields it reads (2026-10-22).
    process_settings: ProcessSettingsService
    # A rule version drafted from the company's own file ("Tạo từ tệp mẫu").
    rule_drafts: RuleDraftService
    # Master data imported from a file, previewed and submitted (ticket 41).
    catalog_imports: CatalogImportService
    # A finding explained in words by the model, on request (AI item 12).
    finding_explanations: FindingExplanations
    # A customer suggested for a sender no domain matched (AI item 5).
    sender_customers: SenderCustomers
    # A case's mail thread summarised, each point citing its mail (AI item 8).
    thread_summaries: ThreadSummaries
    # "Gửi cho khách" from the presser's own mailbox (the outbox folder).
    outbound: OutboundMailService
    # A mail asking about an unordered quotation, drafted (AI item 11, Q12).
    screening_followups: ScreeningFollowups
    # Design's reply written in the mail, read and confirmed (AI item 6).
    design_text_replies: DesignTextReplies
    # PC's delivery dates read from the mail Sales pastes (AI item 7).
    pc_dates: PcDateReplies
    gate: Gate


@dataclass(frozen=True)
class SalesAssembly:
    services: SalesServices
    decisions: CaseDecisions
    # The decision guard of a PO layout's approval (`sales.layout`, ticket 30).
    layout_decisions: LayoutDecisions
    # The decision guard of a rule version's approval (`sales.rules`, ticket 38).
    rule_decisions: RuleDecisions
    # The decision guard of a master-data import's approval (`sales.catalog`, ticket 41).
    catalog_decisions: CatalogDecisions


def assemble(
    *,
    uow: SalesUnitOfWorkFactory,
    authorization: SalesAuthorizationPort,
    clock: UtcClock,
    ids: IdGenerator,
    catalog: SalesCatalogPort,
    inbox: InboxPort,
    intake: OrderIntake,
    quotation: QuotationService,
    files: SourceViewPort,
    source_cache: SourceCachePort,
    book: TenantRuleBook,
    directory: MemberDirectoryPort,
    holders: ScopeHoldersPort,
    notifications: NotificationSenderPort,
    artifact_bytes: ArtifactBytesPort,
    artifact_writer: ArtifactWriterPort,
    layout_checks: LayoutChecks,
    release_manifest_ref: str | None,
    runs: Dw1RunsPort,
    pending: PendingDecisionsPort,
    telemetry: SpanPort,
    catalog_uow: CatalogUnitOfWorkFactory,
    templates: CatalogTemplatePort,
    draft_uow: RuleDraftUnitOfWorkFactory,
    readiness: ModelReadiness,
    roles: RoleCatalogPort,
    step_activity: StepActivityReadPort,
    scanner: MalwareScanPort,
    # Where an item code Sales confirms is kept (the catalog, in practice).
    converts: ConvertLedgerPort,
    # Where a sender Sales confirms as a customer's is kept (the catalog too).
    senders: SenderLedgerPort,
    # The one-call door's model, for the steps a person asks for on a page
    # (AI items 5 and 12); None where no model is configured.
    one_call: InterpretationPort | None,
    worker_id: str,
    worker_version: str,
    # Whether the deployment names an outbox share ("Gửi cho khách").
    outbox_enabled: bool = False,
) -> SalesAssembly:
    gate = Gate(authorization)
    queue = ProcessingService(uow, gate, clock, ids, inbox)
    sources = SourceService(uow, gate, clock, inbox, files, source_cache)
    processing = InboxProcessing(
        uow,
        gate,
        clock,
        ids,
        inbox,
        catalog,
        intake,
        quotation,
        directory,
        pending,
        release_manifest_ref,
        SalesSpans(telemetry),
        sources,
    )
    overview = OverviewService(uow, gate, clock, inbox, book, directory, pending)
    services = SalesServices(
        overview=overview,
        pipeline=PipelineService(uow, gate, clock, overview),
        inbox=InboxQueries(uow, gate, inbox, book),
        processing=queue,
        dw1=Dw1Runs(uow, gate, inbox, runs, pending),
        orders=OrderQueries(uow, gate, pending, step_activity),
        order_commands=OrderCommands(uow, gate, clock, ids, intake, pending, converts),
        quotes=QuoteQueries(uow, gate, clock, quotation, pending, step_activity),
        quote_commands=QuoteCommands(uow, gate, clock, ids, quotation, catalog, pending),
        sources=sources,
        artifacts=ArtifactService(
            uow,
            gate,
            artifact_bytes,
            clock,
            ids,
            artifact_writer,
            book,
            catalog,
            directory,
            quotation,
            scanner,
        ),
        master_data=MasterDataService(gate, catalog),
        worker=WorkerService(uow, gate, clock, ids, holders, notifications, directory),
        assignment=AssignmentService(uow, gate, clock, ids, holders, directory, notifications),
        routed_mail=RoutedMailService(uow, gate, directory, clock, ids),
        layouts=LayoutService(uow, gate, clock, ids, inbox, catalog, intake.rules, layout_checks),
        rules=SalesRulesService(uow, gate, book, clock, ids, directory, readiness),
        process_settings=ProcessSettingsService(
            gate, intake.rules, readiness, roles, step_activity, clock
        ),
        rule_drafts=RuleDraftService(draft_uow, gate, clock, ids),
        catalog_imports=CatalogImportService(catalog_uow, gate, catalog, templates, clock, ids),
        finding_explanations=FindingExplanations(
            uow, gate, catalog, one_call, clock, ids, worker_id, worker_version
        ),
        sender_customers=SenderCustomers(
            uow,
            gate,
            inbox,
            catalog,
            senders,
            queue,
            one_call,
            clock,
            ids,
            worker_id,
            worker_version,
        ),
        thread_summaries=ThreadSummaries(
            uow, gate, inbox, one_call, clock, ids, worker_id, worker_version
        ),
        pc_dates=PcDateReplies(uow, gate, one_call, clock, ids, worker_id, worker_version),
        design_text_replies=DesignTextReplies(
            uow, gate, inbox, quotation, one_call, clock, ids, worker_id, worker_version
        ),
        screening_followups=ScreeningFollowups(
            gate, catalog, quotation, one_call, clock, ids, worker_id, worker_version
        ),
        outbound=OutboundMailService(
            uow, gate, catalog, directory, artifact_bytes, clock, ids, outbox_enabled
        ),
        gate=gate,
    )
    decisions = CaseDecisions(uow, gate, clock, ids, quotation, processing, notifications)
    return SalesAssembly(
        services=services,
        decisions=decisions,
        layout_decisions=LayoutDecisions(uow, clock),
        rule_decisions=RuleDecisions(uow, book, readiness),
        catalog_decisions=CatalogDecisions(catalog_uow),
    )
