"""The Sales services the API mounts, assembled from the ports they take.

Built by the composition root from concrete adapters; nothing here names
one. `None` in place of the whole bundle is a deployment where no data
source is configured: every Sales route then answers "chưa cấu hình nguồn
dữ liệu" (ticket 05, G31).
"""

from __future__ import annotations

from dataclasses import dataclass

from dw_kernel.ports import IdGenerator, UtcClock
from dw_sales.application.access import Gate, SalesAuthorizationPort
from dw_sales.application.artifacts_service import ArtifactService
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.inbox_service import InboxService
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
from dw_sales.application.quotation import QuotationService
from dw_sales.application.quotes_service import QuoteCommands, QuoteQueries
from dw_sales.application.source import SourceService, SourceViewPort
from dw_sales.application.worker_service import WorkerService
from dw_sales.domain.kpi import SalesKpi


@dataclass(frozen=True)
class SalesServices:
    overview: OverviewService
    inbox: InboxService
    orders: OrderQueries
    order_commands: OrderCommands
    quotes: QuoteQueries
    quote_commands: QuoteCommands
    sources: SourceService
    artifacts: ArtifactService
    master_data: MasterDataService
    worker: WorkerService
    gate: Gate


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
    kpi: SalesKpi,
    directory: MemberDirectoryPort,
    holders: ScopeHoldersPort,
    notifications: NotificationSenderPort,
    artifact_bytes: ArtifactBytesPort,
    release_manifest_ref: str | None,
) -> SalesServices:
    gate = Gate(authorization)
    return SalesServices(
        overview=OverviewService(uow, gate, clock, inbox, kpi, directory),
        inbox=InboxService(
            uow,
            gate,
            clock,
            ids,
            inbox,
            catalog,
            intake,
            quotation,
            directory,
            release_manifest_ref,
        ),
        orders=OrderQueries(uow, gate),
        order_commands=OrderCommands(uow, gate, clock, ids, intake),
        quotes=QuoteQueries(uow, gate, clock, quotation),
        quote_commands=QuoteCommands(uow, gate, clock, ids, quotation, catalog),
        sources=SourceService(uow, gate, clock, inbox, files),
        artifacts=ArtifactService(uow, gate, artifact_bytes),
        master_data=MasterDataService(gate, catalog),
        worker=WorkerService(uow, gate, clock, ids, holders, notifications, directory),
        gate=gate,
    )
