"""DW1 on its mock data, built one way for every process that hosts it.

The API mounts the Sales routes over it; the worker runs DW1's mailbox lane
over it (ticket 16). Both must read the same mailbox with the same readers,
rules and policies, and register the same graph, or a message processed by
the lane would be processed differently from one a person pressed "DW xử lý"
on. So neither composition root spells the list out: each hands in what its
process already built (sessions, the platform's ports, the runtime) and calls
`build_dw1`.

DW1's master data and mailbox are fictional mocks bound to one (tenant,
workspace), ``scope``; every other scope reads them empty.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_agent_runtime.approval_flow import ApproveAndResumeService
from dw_agent_runtime.ports import WorkflowRunnerPort
from dw_agent_runtime.registry import GraphRegistry, WorkerRegistry, parse_worker_file
from dw_kernel.ports import IdGenerator, UtcClock
from dw_sales.adapters.artifact_files import ArtifactFiles
from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
from dw_sales.adapters.order_rules import PlatformOrderRules
from dw_sales.adapters.persistence.orders import SqlOrderCaseLookup
from dw_sales.adapters.persistence.quotes import SqlQuoteCaseLookup
from dw_sales.adapters.persistence.uow import AuditFactory, SqlSalesUnitOfWorkFactory
from dw_sales.adapters.policy_files import load_sales_policies
from dw_sales.adapters.readers import mock_po_readers
from dw_sales.adapters.rfq_excel import ExcelDesignReplyReader, ExcelRfqReader
from dw_sales.adapters.runtime import RuntimeDw1Runs
from dw_sales.adapters.source_view import FileSourceView
from dw_sales.application.access import SalesAuthorizationPort
from dw_sales.application.inbox_lane import InboxLane, ServiceAccessPort
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.ports import (
    ArtifactBytesPort,
    MemberDirectoryPort,
    NotificationSenderPort,
    SalesScope,
    ScopeHoldersPort,
)
from dw_sales.application.quotation import QuotationService
from dw_sales.application.services import SalesServices, assemble
from dw_sales.application.telemetry import SpanPort
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
    lane_access: ServiceAccessPort | None = None,
) -> Dw1Mount:
    """DW1's services over ``scope``'s mock data, its graph and worker
    (``configs/workers/sales.yaml``) registered on ``runtime``, every `sales.`
    approval made strict and checked by the context before it is recorded
    (`dw_sales.workflows.graph.register`); its spans through ``telemetry``,
    the process's own, cut to Sales' allowlist (`dw_sales.application.telemetry`);
    and, given ``lane_access``, the mailbox lane over the same services."""
    catalog = MockSalesCatalog.load(scope)
    inbox = MockInbox.load(scope)
    policies = load_sales_policies(configs / "policies", configs / "copy")
    quotation = QuotationService(
        catalog=catalog,
        inbox=inbox,
        rfq_reader=ExcelRfqReader(),
        reply_reader=ExcelDesignReplyReader(),
        cases=SqlQuoteCaseLookup(session_factory),
        ledger=catalog,
        rules=policies.quote_rules,
        pricing=policies.pricing,
    )
    intake = OrderIntake(
        catalog=catalog,
        inbox=inbox,
        reader=mock_po_readers(),
        rules=PlatformOrderRules(policies.order_rules),
        cases=SqlOrderCaseLookup(session_factory),
        new_case_id=ids.new_uuid,
    )
    worker_file = configs / "workers" / "sales.yaml"
    worker, _ = parse_worker_file(worker_file)
    runs = RuntimeDw1Runs(
        runtime.runner,
        runtime.approval_flow,
        runtime.approval_flow.run_store,
        ids,
        worker_id=worker.worker_id,
        worker_version=worker.worker_version,
    )
    uow = SqlSalesUnitOfWorkFactory(session_factory, audit=audit)
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
        kpi=policies.kpi,
        directory=directory,
        holders=holders,
        notifications=notifications,
        artifact_bytes=artifact_bytes,
        artifact_writer=ArtifactFiles(),
        artifact_copy=policies.artifact_copy,
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
        worker_file=worker_file,
    )
    lane = (
        None
        if lane_access is None
        else InboxLane(uow, inbox, assembly.services.dw1, lane_access, clock, ids)
    )
    return Dw1Mount(services=assembly.services, lane=lane)
