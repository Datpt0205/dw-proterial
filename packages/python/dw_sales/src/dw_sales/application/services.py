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

from dw_agent_runtime.model.interpretation import InterpretationPort
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.malware import MalwareScanPort
from dw_sales.application.access import Gate, SalesAuthorizationPort
from dw_sales.application.activity_ports import StepActivityReadPort
from dw_sales.application.artifact_content import ArtifactWriterPort
from dw_sales.application.artifacts_service import ArtifactService
from dw_sales.application.assignment import AssignmentService
from dw_sales.application.assistant import (
    AssistantService,
    AssistantStoreFactory,
    CaseChatStatements,
)
from dw_sales.application.auto_apply import AutoApply
from dw_sales.application.bravo_exports import BravoExportService, BravoExportUnitOfWorkFactory
from dw_sales.application.bravo_facts import BravoFactsService, BravoFactsStorePort
from dw_sales.application.bravo_line_writes import (
    BravoCommandsPort,
    BravoLineWrites,
    BravoOrdersPort,
    BravoWriteDecisions,
    BravoWriteWorkFactory,
    CaseBravoWrites,
    write_bravo_versions,
)
from dw_sales.application.bravo_sales_orders import (
    BravoCustomerPoPort,
    ReadBackService,
    ReadBackUnitOfWorkFactory,
)
from dw_sales.application.bravo_watch import BravoWatchService, BravoWatchStorePort
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.catalog_imports import (
    CatalogDecisions,
    CatalogImportService,
    CatalogTemplatePort,
    CatalogUnitOfWorkFactory,
)
from dw_sales.application.change_reading import ChangeReader
from dw_sales.application.change_requests import ChangeRequests
from dw_sales.application.confirmations import Confirmations
from dw_sales.application.convert_gaps import ConvertGapService, ConvertGapsPort
from dw_sales.application.customer_notations import CustomerNotations, NotationLedgerPort
from dw_sales.application.customer_reminders import CustomerReminders
from dw_sales.application.decisions import CaseDecisions
from dw_sales.application.design_requests import DesignRequests
from dw_sales.application.design_text_reading import DesignTextReplies
from dw_sales.application.finding_explanations import FindingExplanations
from dw_sales.application.inbox_service import InboxProcessing, InboxQueries
from dw_sales.application.internal_changes import InternalChanges
from dw_sales.application.layouts import LayoutChecks, LayoutDecisions, LayoutService
from dw_sales.application.master_data_service import MasterDataService
from dw_sales.application.model_readiness import ModelReadiness
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.order_ports import ConvertLedgerPort
from dw_sales.application.order_quotes import OrderQuotes
from dw_sales.application.orders_service import OrderCommands, OrderQueries
from dw_sales.application.outbound_mail import OutboundMailService
from dw_sales.application.overview_service import OverviewService
from dw_sales.application.pc_dates import PcDateReplies
from dw_sales.application.pc_requests import PcRequests
from dw_sales.application.pipeline import PipelineService
from dw_sales.application.po_uploads import PoUploads, UploadStorePort
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
from dw_sales.application.prompt_versions import PromptBook, PromptVersionsService
from dw_sales.application.quotation import QuotationService
from dw_sales.application.quotes_service import QuoteCommands, QuoteQueries
from dw_sales.application.reply_drafts import ReplyDrafts
from dw_sales.application.routed_mail import RoutedMailService
from dw_sales.application.rule_drafts import RuleDraftService, RuleDraftUnitOfWorkFactory
from dw_sales.application.rules import RuleDecisions, SalesRulesService, TenantRuleBook
from dw_sales.application.runs import (
    Dw1Runs,
    Dw1RunsPort,
    PendingDecisionsPort,
)
from dw_sales.application.salesorder_case_fill import CaseSalesOrderFill
from dw_sales.application.salesorder_fill import SalesOrderFiller
from dw_sales.application.salesorder_learning import (
    ExampleUnitOfWorkFactory,
    SalesOrderExamples,
)
from dw_sales.application.salesorder_pairs import WorkedPairs
from dw_sales.application.screening_followups import ScreeningFollowups
from dw_sales.application.sender_customers import SenderCustomers, SenderLedgerPort
from dw_sales.application.skills import (
    SkillBook,
    SkillDecisions,
    SkillReplayStorePort,
    SkillsService,
)
from dw_sales.application.source import SourceCachePort, SourceService, SourceViewPort
from dw_sales.application.telemetry import SalesSpans, SpanPort
from dw_sales.application.thread_summaries import ThreadSummaries
from dw_sales.application.threads import ThreadMembersPort
from dw_sales.application.today import FollowupNoticesPort, ReminderMarkStoreFactory, TodayService
from dw_sales.application.update_loop import UpdateLoops
from dw_sales.application.worker_service import WorkerService


@dataclass(frozen=True)
class SalesServices:
    overview: OverviewService
    # Every case by status, and one case's history (the pipeline board).
    pipeline: PipelineService
    inbox: InboxQueries
    # "DW xử lý": the routes queue a message (ticket 25); the worker runs it.
    processing: ProcessingService
    # "Tải PO lên": a PO file a person downloaded, stored and queued (ticket 18).
    uploads: PoUploads
    dw1: Dw1Runs
    orders: OrderQueries
    order_commands: OrderCommands
    quotes: QuoteQueries
    quote_commands: QuoteCommands
    sources: SourceService
    artifacts: ArtifactService
    master_data: MasterDataService
    # How each customer writes numbers, dates and bare currency symbols, as
    # Sales' confirmations settled it (ticket 37).
    customer_notations: CustomerNotations
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
    # A customer's SalesOrder rules learned from a worked example (ticket 38).
    salesorder_examples: SalesOrderExamples
    # A customer's worked pairs, listed and one withdrawn (ticket 41).
    salesorder_pairs: WorkedPairs
    # Master data imported from a file, previewed and submitted (ticket 41).
    catalog_imports: CatalogImportService
    # Bravo's YCBG export, uploaded for Design's results to be read (ticket 16).
    bravo_exports: BravoExportService
    convert_gaps: ConvertGapService
    read_backs: ReadBackService
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
    # A reminder to a customer DW1 waits on, drafted (DW01 function 4).
    customer_reminders: CustomerReminders
    # A mail to the customer about an order worded by the model, beside the
    # template's draft, every figure checked (ticket 32).
    reply_drafts: ReplyDrafts
    # Status questions answered from live data, in sessions (ADR 0007).
    assistant: AssistantService
    # Design's reply written in the mail, read and confirmed (AI item 6).
    design_text_replies: DesignTextReplies
    # PC's delivery dates read from the mail Sales pastes (AI item 7).
    pc_dates: PcDateReplies
    # The request to PC drafted, the wait recorded, PC's answer per line (ticket 07).
    pc_requests: PcRequests
    # The request to Design for a new PRV code drafted, the wait recorded,
    # and the codes Design's mails name for Sales to confirm (ticket 06).
    design_requests: DesignRequests
    # What a customer asked to change by mail, confirmed line by line (ticket 27).
    change_requests: ChangeRequests
    # A customer's change on an order in Bravo, through PC and back (ticket 29).
    update_loops: UpdateLoops
    # Proterial's own change of a confirmed order, read from PC's mail and
    # applied by a person (ticket 10).
    internal_changes: InternalChanges
    # The confirmation sent, then the customer's agreement (ticket 28).
    confirmations: Confirmations
    # DW1's skills, and a version of one proposed for the head (ticket 40).
    skills: SkillsService
    # The description reading's prompt versions the optimiser proposed, for
    # the head (ticket 43).
    prompts: PromptVersionsService
    # A person's day: today's brief and their reminders, marked (tickets 47, 48).
    today: TodayService
    # A quote case opened from an order's lines with no valid quotation, and
    # those lines checked again once it is approved (ticket 09).
    order_quotes: OrderQuotes
    # The Bravo change watch: its state, and a baseline accepted (ticket 65).
    bravo_watch: BravoWatchService
    # How fresh DW's copy of Bravo's facts is, per table (ticket 50).
    bravo_facts: BravoFactsService
    # An SO line's change proposed for writing into Bravo (ticket 53).
    bravo_writes: BravoLineWrites
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
    # The decision guard of a skill version's approval (`sales.skills`, ticket 40).
    skill_decisions: SkillDecisions
    # The decision guard of a Bravo write's approval
    # (`bravo_write.sales_order`, ticket 53).
    bravo_write_decisions: BravoWriteDecisions


def assemble(
    *,
    uow: SalesUnitOfWorkFactory,
    authorization: SalesAuthorizationPort,
    clock: UtcClock,
    ids: IdGenerator,
    catalog: SalesCatalogPort,
    inbox: InboxPort,
    # The same mailbox's threads (ticket 24): a case's talk before it opened.
    threads: ThreadMembersPort,
    intake: OrderIntake,
    quotation: QuotationService,
    # The Bravo change watch's tables (ticket 65).
    bravo_watch_store: BravoWatchStorePort,
    # DW's copy of Bravo's facts (ticket 50).
    bravo_facts_store: BravoFactsStorePort,
    # An SO in Bravo, read through the gateway, and the unit of work that
    # holds a proposed write with its approval (ticket 53).
    bravo_orders: BravoOrdersPort,
    bravo_commands: BravoCommandsPort,
    bravo_writes_uow: BravoWriteWorkFactory,
    # A customer's PO as Bravo holds it, for the read-back (ticket 51); None:
    # only an uploaded export is read back.
    bravo_po: BravoCustomerPoPort | None,
    files: SourceViewPort,
    source_cache: SourceCachePort,
    book: TenantRuleBook,
    # DW1's skills, the platform's and the tenant's versions (ticket 40),
    # and the worker's replays of proposed versions.
    skills: SkillBook,
    skill_replays: SkillReplayStorePort,
    # The description reading's prompt, the platform's and the tenant's
    # versions (ticket 43).
    prompts: PromptBook,
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
    # Where a worked example's pair is kept until learned (ticket 38).
    example_uow: ExampleUnitOfWorkFactory,
    # Where a Bravo export is kept until read (tickets 16, 03), and where a
    # sales order read back from one is kept for its case.
    bravo_uow: BravoExportUnitOfWorkFactory,
    read_back_uow: ReadBackUnitOfWorkFactory,
    # What Bravo's convert list lacks of the codes Sales confirmed (ticket 04).
    gaps: ConvertGapsPort,
    readiness: ModelReadiness,
    roles: RoleCatalogPort,
    step_activity: StepActivityReadPort,
    scanner: MalwareScanPort,
    # Where an item code Sales confirms is kept (the catalog, in practice).
    converts: ConvertLedgerPort,
    # Where a sender Sales confirms as a customer's is kept (the catalog too).
    senders: SenderLedgerPort,
    # Where each customer's notation record is kept (ticket 37).
    notations: NotationLedgerPort,
    # The status assistant's sessions, each bound to its person (ADR 0007).
    assistant: AssistantStoreFactory,
    # What the follow-ups told a person, read back for their feed, and what
    # they did with each reminder (tickets 47, 48).
    notices: FollowupNoticesPort,
    reminder_marks: ReminderMarkStoreFactory,
    # Where an uploaded PO is stored, with whose it is (ticket 18).
    uploads: UploadStorePort,
    # The one-call door's model, for the steps a person asks for on a page
    # (AI items 5 and 12); None where no model is configured.
    one_call: InterpretationPort | None,
    worker_id: str,
    worker_version: str,
    # Where deployed, no file is drawn from copy marked mock (audit 11).
    deployed: bool,
    # Whether the deployment names an outbox share ("Gửi cho khách").
    outbox_enabled: bool = False,
) -> SalesAssembly:
    gate = Gate(authorization)
    queue = ProcessingService(uow, gate, clock, ids, inbox)
    sources = SourceService(uow, gate, clock, inbox, files, source_cache)
    rules = SalesRulesService(uow, gate, book, clock, ids, directory, readiness)
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
        # What code's gate let apply itself (ticket 44): nothing unless the
        # intake's gate stamps a line so.
        auto_apply=AutoApply(intake, clock, ids),
    )
    overview = OverviewService(uow, gate, clock, inbox, book, directory, pending, book)
    orders = OrderQueries(
        uow,
        gate,
        pending,
        step_activity,
        book,
        threads,
        directory,
        CaseBravoWrites(bravo_writes_uow),
    )
    order_quotes = OrderQuotes(uow, gate, clock, ids, inbox, intake, book, release_manifest_ref)
    quotes = QuoteQueries(
        uow, gate, clock, quotation, pending, step_activity, book, threads, directory
    )
    order_commands = OrderCommands(
        uow,
        gate,
        clock,
        ids,
        intake,
        pending,
        converts,
        notations,
        # What the chat stated on a flag, labelled with its decision (ticket 57).
        chat=CaseChatStatements(assistant),
    )
    line_writes = BravoLineWrites(
        bravo_writes_uow, gate, bravo_orders, write_bravo_versions(bravo_commands), clock, ids
    )
    services = SalesServices(
        overview=overview,
        pipeline=PipelineService(uow, gate, clock, overview),
        inbox=InboxQueries(uow, gate, inbox, book, directory),
        processing=queue,
        uploads=PoUploads(uow, gate, clock, ids, catalog, intake.rules, directory, uploads, queue),
        dw1=Dw1Runs(uow, gate, inbox, runs, pending),
        orders=orders,
        order_commands=order_commands,
        quotes=quotes,
        quote_commands=QuoteCommands(uow, gate, clock, ids, quotation, catalog, pending, notations),
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
            deployed,
            inbox,
            # A case's upload file filled with its customer's SalesOrder
            # skill, through the one-call door, where the step runs (ticket
            # 41); no model, and the rules fill it.
            None
            if one_call is None
            else CaseSalesOrderFill(
                intake.rules,
                readiness,
                book,
                catalog,
                skills,
                SalesOrderFiller(one_call),
                ids,
                worker_id,
                worker_version,
            ),
        ),
        master_data=MasterDataService(gate, catalog),
        customer_notations=CustomerNotations(gate, notations, catalog, clock, ids),
        worker=WorkerService(uow, gate, clock, ids, holders, notifications, directory, book),
        assignment=AssignmentService(uow, gate, clock, ids, holders, directory, notifications),
        routed_mail=RoutedMailService(uow, gate, directory, clock, ids, catalog),
        layouts=LayoutService(
            uow, gate, clock, ids, inbox, catalog, intake.rules, layout_checks, intake
        ),
        rules=rules,
        process_settings=ProcessSettingsService(
            gate, intake.rules, readiness, roles, step_activity, clock
        ),
        rule_drafts=RuleDraftService(draft_uow, gate, clock, ids),
        bravo_exports=BravoExportService(bravo_uow, uow, gate, clock, ids),
        convert_gaps=ConvertGapService(gaps, gate),
        read_backs=ReadBackService(uow, read_back_uow, gate, bravo_po, clock, ids),
        salesorder_examples=SalesOrderExamples(example_uow, gate, clock, ids, catalog, book, rules),
        salesorder_pairs=WorkedPairs(example_uow, gate, clock, ids),
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
        pc_dates=PcDateReplies(
            uow,
            gate,
            one_call,
            clock,
            ids,
            worker_id,
            worker_version,
            inbox,
            catalog,
            rules=intake.rules,
        ),
        pc_requests=PcRequests(uow, gate, clock, ids, intake, book, book),
        design_requests=DesignRequests(uow, gate, clock, ids, catalog, book, book, inbox),
        update_loops=UpdateLoops(uow, gate, clock, ids, intake, book, book),
        internal_changes=InternalChanges(
            uow,
            gate,
            clock,
            ids,
            intake,
            intake.zones,
            intake.rules,
            intake.model_steps,
            one_call,
            worker_id,
            worker_version,
        ),
        confirmations=Confirmations(uow, gate, clock, ids, intake, pending, threads, directory),
        change_requests=ChangeRequests(
            uow,
            gate,
            clock,
            ids,
            intake,
            inbox,
            intake.rules,
            intake.zones,
            intake.model_steps,
            None if one_call is None else ChangeReader(one_call),
            worker_id,
            worker_version,
        ),
        design_text_replies=DesignTextReplies(
            uow, gate, inbox, quotation, one_call, clock, ids, worker_id, worker_version
        ),
        screening_followups=ScreeningFollowups(
            gate, catalog, quotation, one_call, clock, ids, worker_id, worker_version
        ),
        customer_reminders=CustomerReminders(
            uow, gate, catalog, one_call, clock, ids, worker_id, worker_version, book
        ),
        reply_drafts=ReplyDrafts(
            uow,
            gate,
            catalog,
            directory,
            book,
            intake.rules,
            intake.model_steps,
            one_call,
            ids,
            worker_id,
            worker_version,
            deployed,
            # Worded by the tenant's reply-drafts skill where its step runs
            # (ticket 42 family 5).
            skills=skills,
        ),
        assistant=AssistantService(
            assistant,
            gate,
            orders,
            quotes,
            overview,
            one_call,
            clock,
            ids,
            worker_id,
            worker_version,
            book,
            # A flag's decision the PIC confirms in the case's conversation
            # (ticket 56) is the same command the page's button sends.
            decisions=order_commands,
            # And a Bravo write the PIC confirms there is ticket 53's own
            # proposal, checked again in full.
            bravo_writes=line_writes,
            # Whether the chat states either: `model_assist.case_chat` (ticket 57).
            rules=intake.rules,
        ),
        outbound=OutboundMailService(
            uow, gate, catalog, directory, artifact_bytes, clock, ids, outbox_enabled, design=book
        ),
        skills=SkillsService(uow, gate, skills, clock, ids, directory, skill_replays, catalog),
        prompts=PromptVersionsService(uow, gate, prompts),
        today=TodayService(gate, clock, notices, reminder_marks, book),
        order_quotes=order_quotes,
        bravo_watch=BravoWatchService(bravo_watch_store, authorization, clock, ids),
        bravo_facts=BravoFactsService(bravo_facts_store, gate, clock),
        bravo_writes=line_writes,
        gate=gate,
    )
    decisions = CaseDecisions(
        uow, gate, clock, ids, quotation, processing, notifications, read_back_uow, order_quotes
    )
    return SalesAssembly(
        services=services,
        decisions=decisions,
        layout_decisions=LayoutDecisions(uow, clock),
        rule_decisions=RuleDecisions(uow, book, readiness),
        catalog_decisions=CatalogDecisions(catalog_uow),
        skill_decisions=SkillDecisions(uow, skills, skill_replays),
        bravo_write_decisions=BravoWriteDecisions(bravo_writes_uow),
    )
