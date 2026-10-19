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
from dw_sales.application.inbox_service import InboxProcessing, InboxQueries
from dw_sales.application.layouts import LayoutChecks, LayoutDecisions, LayoutService
from dw_sales.application.master_data_service import MasterDataService
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.orders_service import OrderCommands, OrderQueries
from dw_sales.application.overview_service import OverviewService
from dw_sales.application.ports import (
    ArtifactBytesPort,
    InboxPort,
    MemberDirectoryPort,
    NotificationSenderPort,
    SalesCatalogPort,
    ScopeHoldersPort,
)
from dw_sales.application.processing import ProcessingService
from dw_sales.application.quotation import QuotationService
from dw_sales.application.quotes_service import QuoteCommands, QuoteQueries
from dw_sales.application.rules import RuleDecisions, SalesRulesService, TenantRuleBook
from dw_sales.application.runs import Dw1Runs, Dw1RunsPort, PendingDecisionsPort
from dw_sales.application.source import SourceService, SourceViewPort
from dw_sales.application.telemetry import SalesSpans, SpanPort
from dw_sales.application.worker_service import WorkerService


@dataclass(frozen=True)
class SalesServices:
    overview: OverviewService
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
    layouts: LayoutService
    # A tenant's own rule versions, proposed and approved (ticket 19).
    rules: SalesRulesService
    # Master data imported from a file, previewed and submitted (ticket 41).
    catalog_imports: CatalogImportService
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
) -> SalesAssembly:
    gate = Gate(authorization)
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
    )
    services = SalesServices(
        overview=OverviewService(uow, gate, clock, inbox, book, directory, pending),
        inbox=InboxQueries(uow, gate, inbox, book),
        processing=ProcessingService(uow, gate, clock, ids, inbox),
        dw1=Dw1Runs(uow, gate, inbox, runs, pending),
        orders=OrderQueries(uow, gate, pending),
        order_commands=OrderCommands(uow, gate, clock, ids, intake, pending),
        quotes=QuoteQueries(uow, gate, clock, quotation, pending),
        quote_commands=QuoteCommands(uow, gate, clock, ids, quotation, catalog, pending),
        sources=SourceService(uow, gate, clock, inbox, files),
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
        ),
        master_data=MasterDataService(gate, catalog),
        worker=WorkerService(uow, gate, clock, ids, holders, notifications, directory),
        assignment=AssignmentService(uow, gate, clock, ids, holders, directory, notifications),
        layouts=LayoutService(uow, gate, clock, ids, inbox, catalog, intake.rules, layout_checks),
        rules=SalesRulesService(uow, gate, book, clock, ids),
        catalog_imports=CatalogImportService(catalog_uow, gate, catalog, templates, clock, ids),
        gate=gate,
    )
    decisions = CaseDecisions(uow, gate, clock, ids, quotation, processing)
    return SalesAssembly(
        services=services,
        decisions=decisions,
        layout_decisions=LayoutDecisions(uow, clock),
        rule_decisions=RuleDecisions(uow, book),
        catalog_decisions=CatalogDecisions(catalog_uow),
    )
