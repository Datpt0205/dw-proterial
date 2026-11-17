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
headers. Given ``agent_turns`` too, a thread message is read with DW1's
read-only tools first where a tenant turns that on (tickets 30 and 31): the
tools are registered on it here and the turn built once, at startup.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_agent_runtime.adapters.agent_turn import AgentTurnKit
from dw_agent_runtime.adapters.model_interpretation import GatewayInterpretation, ProfileStepModel
from dw_agent_runtime.adapters.model_measurements import SqlModelMeasurements
from dw_agent_runtime.approval_flow import ApproveAndResumeService
from dw_agent_runtime.model.interpretation import InterpretationPort
from dw_agent_runtime.model.profiles import ModelProfileRegistry
from dw_agent_runtime.model.readiness import StepModelPort
from dw_agent_runtime.ports import ModelGateway, WorkflowRunnerPort
from dw_agent_runtime.registry import (
    ConfigError,
    GraphRegistry,
    WorkerRegistry,
    parse_worker_file,
)
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.adapters.drop_folder import LocalDropFolder
from dw_platform.adapters.outbox_folder import FolderOutbox
from dw_platform.adapters.persistence.rule_versions import SqlRuleVersionLookup
from dw_platform.adapters.persistence.scope_holders import HolderMailboxes, SqlScopeHolders
from dw_platform.application.drop_folder import OwnedFolders
from dw_platform.application.malware import MalwareScanPort
from dw_sales.adapters.artifact_files import ArtifactFiles
from dw_sales.adapters.catalog_templates import XlsxCatalogTemplates
from dw_sales.adapters.drafting_examples import (
    FixtureHandoffKindExamples,
    FixtureReplyKindExamples,
)
from dw_sales.adapters.memory_rules import static_rule_book
from dw_sales.adapters.mock import MockInbox, MockSalesCatalog, WithUploads
from dw_sales.adapters.order_rules import load_tenant_order_rules
from dw_sales.adapters.persistence.activity import SqlStepActivityReader
from dw_sales.adapters.persistence.assistant import SqlAssistantStoreFactory
from dw_sales.adapters.persistence.catalog import (
    OutboxFactory,
    SqlApprovedLists,
    SqlCatalogUnitOfWorkFactory,
)
from dw_sales.adapters.persistence.customer_notations import SqlCustomerNotations
from dw_sales.adapters.persistence.followups import SqlFollowupScopes
from dw_sales.adapters.persistence.labelled_cases import SqlLabelledCaseReader
from dw_sales.adapters.persistence.labelled_examples import SqlDescriptionExamples
from dw_sales.adapters.persistence.layouts import SqlLayoutLookup
from dw_sales.adapters.persistence.mailbox import SqlMailbox
from dw_sales.adapters.persistence.orders import SqlOrderCaseLookup
from dw_sales.adapters.persistence.outbound import SqlOutboundScopes
from dw_sales.adapters.persistence.processing import SqlProcessingQueue
from dw_sales.adapters.persistence.quotes import SqlQuoteCaseLookup
from dw_sales.adapters.persistence.recorded_converts import SqlRecordedConverts
from dw_sales.adapters.persistence.recorded_quotations import SqlRecordedQuotations
from dw_sales.adapters.persistence.recorded_senders import SqlRecordedSenders
from dw_sales.adapters.persistence.reminder_marks import SqlReminderMarkStoreFactory
from dw_sales.adapters.persistence.rule_drafts import SqlRuleDraftScopes
from dw_sales.adapters.persistence.skill_replays import SqlSkillReplays
from dw_sales.adapters.persistence.step_thresholds import SqlStepThresholds
from dw_sales.adapters.persistence.uow import (
    ApprovalsFactory,
    AuditFactory,
    SqlSalesUnitOfWorkFactory,
)
from dw_sales.adapters.policy_files import load_sales_policies, rule_book
from dw_sales.adapters.reader_client import ReaderTransport, client_readers
from dw_sales.adapters.runtime import RuntimeDw1Runs
from dw_sales.adapters.skill_examples import (
    FixtureDocumentFormExamples,
    FixtureMailKindExamples,
    FixtureReplayExamples,
)
from dw_sales.adapters.skill_files import load_dw1_skills, skills_book
from dw_sales.application.access import SalesAuthorizationPort, SalesScopes
from dw_sales.application.activity import ActivityService
from dw_sales.application.autonomy import AutonomyGate, ThresholdLane
from dw_sales.application.bravo_exports import BravoExportReading
from dw_sales.application.bravo_sales_orders import SalesOrderScreen
from dw_sales.application.brief_writing import BriefWriter
from dw_sales.application.catalog_imports import CatalogParsing, CatalogSettlement
from dw_sales.application.column_mapping import ColumnMatcher
from dw_sales.application.customer_notations import NotationRecordPort
from dw_sales.application.document_forms import DocumentFormReader, DocumentFormReplay
from dw_sales.application.examples import ExampleFinder, ExampleIndexLane, ExampleIndexPort
from dw_sales.application.followups import BriefWriterPort, FollowupLane, PushNoticePort
from dw_sales.application.handoff_kinds import HandoffKindReader, HandoffKindReplay
from dw_sales.application.handoffs import HandoffReader
from dw_sales.application.inbox_lane import InboxLane, ServiceAccessPort
from dw_sales.application.layouts import LayoutChecks, LayoutPrefiller, LayoutSettlement
from dw_sales.application.mail_drop import MailDrop, MailDropNotices
from dw_sales.application.mail_kinds import MailKindReader, MailKindReplay, SkillPort
from dw_sales.application.message_intent import IntentReader
from dw_sales.application.model_calls import TimedInterpretation
from dw_sales.application.model_readiness import ModelReadiness
from dw_sales.application.model_reading import DescriptionReader
from dw_sales.application.order_intake import CustomerPoReading, OrderIntake
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
from dw_sales.application.prompt_optimiser import PromptOptimiser, SecurityCase
from dw_sales.application.prompt_versions import (
    PromptDecisions,
    PromptSettlement,
    prompt_book,
)
from dw_sales.application.quotation import QuotationService
from dw_sales.application.reply_drafts import ReplyKindReplay
from dw_sales.application.reply_intent import ReplyReader
from dw_sales.application.rfq_reading import AttachmentTextPort, ModelRequests, RfqModelReader
from dw_sales.application.rule_drafts import RuleDrafting, RuleDraftSweep
from dw_sales.application.rules import RuleBookOrderRules, RuleSettlement
from dw_sales.application.salesorder_fill import SalesOrderFiller
from dw_sales.application.salesorder_learning import SalesOrderLearning
from dw_sales.application.salesorder_pairs import (
    SalesOrderSkillReplayer,
    WorkedPairRetention,
)
from dw_sales.application.scanned_inbox import ScannedInbox
from dw_sales.application.services import SalesServices, assemble
from dw_sales.application.skill_pick import PickModelPort, SkillPicker
from dw_sales.application.skill_replay import SkillReplayer
from dw_sales.application.skills import (
    READ_SKILL,
    READ_SKILL_VERSION,
    Dw1Skills,
    SkillSettlement,
)
from dw_sales.application.snapshot_catalog import SnapshotSalesCatalog
from dw_sales.application.source import NoSourceCache, SourceCachePort
from dw_sales.application.telemetry import SpanPort
from dw_sales.application.thread_agent import (
    CEILING,
    DW1_AGENT,
    SKILL_CEILING,
    THREAD_AGENT,
    SkillSetPort,
    ThreadAgent,
    TurnSkillChoice,
)
from dw_sales.application.thread_tools import (
    ThreadContext,
    ThreadContextPort,
    ThreadTools,
    registered_tools,
)
from dw_sales.application.threads import ThreadLinks
from dw_sales.application.today import FollowupNoticesPort
from dw_sales.application.triage import TriageReader
from dw_sales.application.ycbg_exports import DesignChecks, YcbgScreen
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
    # What learns a customer's SalesOrder rules from an uploaded worked
    # example in the worker (ticket 38); built with the drain, which
    # resolves who asked.
    salesorder_learning: SalesOrderLearning | None = None
    # What reads Design's results from an uploaded Bravo YCBG export in the
    # worker (ticket 16); built with the drain, which resolves who uploaded.
    bravo_export_reading: BravoExportReading | None = None
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
    # What fills the examples index from the decided lines (ticket 43): built
    # where an index is given.
    examples: ExampleIndexLane | None = None
    # What proposes a better prompt version from the decided lines (ticket
    # 43 part 3): built with the drain, where a model, an index and the
    # step's security cases are given.
    prompt_optimiser: PromptOptimiser | None = None
    # What replays a proposed skill version on example mails, with and
    # without it, for the head to see (ticket 40): built where DW1's agent
    # with skills is, a model and the agent turns wired.
    skill_replay: SkillReplayer | None = None
    # What replays a proposed version of a customer's SalesOrder skill on the
    # customer's worked pairs, for the head to see (ticket 41): built where
    # the one-call door is.
    salesorder_skill_replay: SalesOrderSkillReplayer | None = None
    # What drops a customer's worked pairs past the tenant's term (ticket
    # 41): built wherever DW1 is, since pairs are kept with or without a model.
    salesorder_pairs_retention: WorkedPairRetention | None = None


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
    # The same inbox, read back for a person's feed (tickets 47, 48).
    notices: FollowupNoticesPort,
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
    # What the thread agent's turn is built with (tickets 30 and 31): only a
    # process that processes mail and reaches the deployment's model server.
    agent_turns: AgentTurnKit | None = None,
    # Where deployed, nothing fictional answers (audit findings 1 and 11):
    # said by each composition root, never assumed.
    deployed: bool,
    mailbox: Mailbox = "mock",
    mail_drop: Path | None = None,
    source_cache: SourceCachePort | None = None,
    # "Gửi cho khách": on in the API where the deployment says so; the share
    # itself, its outbox folders, only in the worker, which alone writes them.
    outbox_enabled: bool = False,
    outbox_dir: Path | None = None,
    # The examples index (ticket 43): the knowledge gateway's, given by a
    # process that reads mail and reaches one; None shows no example.
    examples: ExampleIndexPort | None = None,
    # The description step's security cases, which a proposed prompt version
    # must pass (ticket 43 part 3); none, and nothing is proposed.
    security: tuple[SecurityCase, ...] = (),
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
    one process that reads it into the store: the folder every DW shares, of
    which DW1 reads the subfolders of those holding `sales.inbox.process`.

    Given ``deployed``, nothing fictional answers (audit findings 1 and 11):
    the mock mailbox is refused, a list with no approved import and the ERP
    answer "not connected" (`CatalogNotConnectedError`) instead of the mock, and
    a file drawn from copy marked mock is refused."""
    if deployed and mailbox == "mock":
        raise ValueError("the mock mailbox is refused where deployed")
    policies = load_sales_policies(configs / "policies", configs / "copy")
    # The platform's rules, with a tenant's own approved version where it has
    # one (ticket 19): stored, proposed and approved through `/sales/rules`.
    book = rule_book(policies, SqlRuleVersionLookup(session_factory))
    tenant_rules = RuleBookOrderRules(book)
    # The lists Sales maintains by hand from each workspace's approved import,
    # the mock where none is approved yet (ticket 41); the ERP's records from
    # the mock until Bravo is connected. Deployed: no mock at all. A sender's
    # customer by address, then by a domain the tenant's rules do not mark
    # shared (ticket 20).
    catalog = SnapshotSalesCatalog(
        SqlApprovedLists(session_factory),
        None if deployed else MockSalesCatalog.load(scope),
        SqlRecordedQuotations(session_factory),
        SqlRecordedConverts(session_factory),
        SqlRecordedSenders(session_factory),
        tenant_rules,
    )
    catalog_uow = SqlCatalogUnitOfWorkFactory(
        session_factory, audit=audit, approvals=approvals, outbox=outbox
    )
    # How each customer writes numbers, dates and bare symbols (ticket 37):
    # learned from Sales' confirmations, read by every reader of their words.
    notations = SqlCustomerNotations(session_factory, audit)
    readers = client_readers(reader, policies.order_rules.intake)
    stored = SqlMailbox(session_factory, audit)
    if mail_drop is not None and mailbox != "stored":
        raise ValueError("a drop folder is read into the stored mailbox only")
    # The mock beside the stored mailbox in a demo: what people upload ("Tải
    # PO lên", ticket 18) is stored either way, and read with the mail.
    # A thread is read from the mail itself, not through the scanner: listing
    # one reads no file (ticket 24).
    mail = stored if mailbox == "stored" else WithUploads(MockInbox.load(scope), stored)
    inbox = ScannedInbox(mail, scanner, readers.po)
    dropped = (
        None
        if mail_drop is None
        else MailDrop(
            # The one drop folder every DW shares: only the subfolders of the
            # members who process this mailbox, the people told when a file
            # is refused (`MailDropNotices`).
            OwnedFolders(
                LocalDropFolder(mail_drop),
                HolderMailboxes(
                    SqlScopeHolders(session_factory),
                    scope.tenant_id.value,
                    scope.workspace_id.value,
                    frozenset({SalesScopes.INBOX_PROCESS.value}),
                ),
            ),
            readers.mail,
            stored,
            MailDropNotices(holders, notifications),
            clock,
            ids,
        )
    )
    worker_file = configs / "workers" / "sales.yaml"
    worker, _ = parse_worker_file(worker_file)
    order_cases = SqlOrderCaseLookup(session_factory)
    # A tenant's approved version of the description reading's prompt, and
    # the decided lines shown beside each reading (ticket 43).
    prompts = prompt_book(SqlRuleVersionLookup(session_factory))
    decided_lines = SqlDescriptionExamples(session_factory)
    finder = None if examples is None else ExampleFinder(examples, decided_lines)
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
    # Each step's threshold from its labelled cases (ticket 44): read by the
    # gate the intake asks, set by the worker's `sales_auto_apply` lane.
    thresholds = SqlStepThresholds(session_factory, audit)
    # DW1's skills (ticket 40): the platform's in `configs/skills/dw1`, a
    # tenant's own approved version of one in `platform.rule_versions`.
    dw1_skills = load_dw1_skills(configs / "skills" / "dw1")
    # And every customer's SalesOrder skill (ticket 41), the generic one
    # where the tenant approved none of its own.
    skills = skills_book(configs / "skills", dw1_skills, SqlRuleVersionLookup(session_factory))
    thread_tools = ThreadTools(order_cases, catalog, tenant_rules)
    # What DW1's model steps did: the activity routes, the process page's
    # share and the case lists' drill-down read it.
    step_activity = SqlStepActivityReader(session_factory)
    uow = SqlSalesUnitOfWorkFactory(session_factory, audit=audit, approvals=approvals)
    # DW1's agent with its skills (ticket 40): the intake reads with it, the
    # worker's replay lane replays proposed skill versions with it.
    dw1_agent = (
        None
        if agent_turns is None or model is None
        else skill_agent(
            agent_turns,
            worker_file,
            thread_tools,
            ThreadContext(uow, mail),
            step_model(configs, worker.default_model_profile),
            dw1_skills,
            skills,
            interpretation_for(model, configs, worker.default_model_profile),
        )
    )
    layout_checks = LayoutChecks(readers.po, catalog)
    # Ticket 29's reading of a request, and the tenant's document forms read
    # first (ticket 42 family 3), on one reader.
    requests = (
        None
        if interpretation is None
        else model_requests(
            interpretation, catalog, tenant_rules, readers.texts, readiness, notations, skills
        )
    )
    quotation = QuotationService(
        catalog=catalog,
        inbox=inbox,
        rfq_reader=readers.rfq,
        reply_reader=readers.design_reply,
        cases=SqlQuoteCaseLookup(session_factory),
        ledger=catalog,
        policies=book,
        requests=requests,
    )
    # A message classified by the tenant's mail kinds (ticket 42), its numbers
    # resolved by the one call's own resolution.
    mail_kinds = (
        None
        if interpretation is None
        else MailKindReader(
            interpretation, skills, IntentReader(interpretation, catalog, order_cases)
        )
    )
    intake = OrderIntake(
        catalog=catalog,
        inbox=inbox,
        reader=readers.po,
        rules=tenant_rules,
        cases=order_cases,
        new_case_id=ids.new_uuid,
        quote_forms=readers.forms,
        zones=book,
        descriptions=(
            None
            if interpretation is None
            else DescriptionReader(interpretation, examples=finder, prompts=prompts)
        ),
        intents=(
            None if interpretation is None else IntentReader(interpretation, catalog, order_cases)
        ),
        mail_kinds=mail_kinds,
        # A message still routed "other" gets a card on the same reader
        # (ticket 33): the served kinds, the one call, the one resolution.
        triage=None if mail_kinds is None else TriageReader(mail_kinds),
        # A customer's own request form, by the tenant's document forms.
        document_forms=None if requests is None else DocumentFormReader(requests.reader, skills),
        threads=ThreadLinks(uow, mail),
        replies=None if interpretation is None else ReplyReader(interpretation),
        thread_agent=(
            None
            if agent_turns is None
            else thread_agent(
                agent_turns,
                worker_file,
                thread_tools,
                ThreadContext(uow, mail),
                step_model(configs, worker.default_model_profile),
            )
        ),
        # DW1's agent with its skills (ticket 40), on the same kit: the
        # platform's skills with the tenant's approved versions of them.
        skill_agent=dw1_agent,
        handoffs=(
            None
            if interpretation is None
            else HandoffReader(interpretation, catalog, order_cases, notations)
        ),
        # The same hand-off by the tenant's hand-off kinds (ticket 42 family 5).
        handoff_kinds=(
            None
            if interpretation is None
            else HandoffKindReader(
                HandoffReader(interpretation, catalog, order_cases, notations), skills
            )
        ),
        layouts=SqlLayoutLookup(session_factory),
        layout_prefiller=(
            None if interpretation is None else LayoutPrefiller(interpretation, layout_checks)
        ),
        body_pos=None if interpretation is None else PoBodyReader(interpretation, notations),
        model_steps=readiness,
        autonomy=AutonomyGate(thresholds),
        uploads=stored,
        design_senders=quotation,
        # The quote cases opened from an order (ticket 09).
        linked_quotes=SqlQuoteCaseLookup(session_factory),
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
        threads=mail,
        intake=intake,
        quotation=quotation,
        files=readers.source,
        # The API's cache keeps an opened page or grid for a while; a process
        # serving no source view keeps nothing.
        source_cache=source_cache or NoSourceCache(),
        book=book,
        skills=skills,
        skill_replays=SqlSkillReplays(session_factory, audit),
        prompts=prompts,
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
        example_uow=catalog_uow,
        bravo_uow=catalog_uow,
        read_back_uow=catalog_uow,
        gaps=catalog,
        readiness=readiness,
        roles=roles,
        step_activity=step_activity,
        # An uploaded signed quotation is scanned like every attachment.
        scanner=scanner,
        converts=catalog,
        senders=catalog,
        notations=notations,
        assistant=SqlAssistantStoreFactory(session_factory),
        notices=notices,
        reminder_marks=SqlReminderMarkStoreFactory(session_factory),
        uploads=stored,
        one_call=(
            None
            if one_call_model is None
            else interpretation_for(one_call_model, configs, worker.default_model_profile)
        ),
        worker_id=worker.worker_id,
        worker_version=worker.worker_version,
        deployed=deployed,
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
        skills=assembly.skill_decisions,
        prompts=PromptDecisions(uow, prompts),
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
    activity = ActivityService(
        uow,
        assembly.services.gate,
        step_activity,
        clock,
        book,
        SqlLabelledCaseReader(session_factory),
        thresholds,
        tenant_rules,
    )
    lane = (
        None
        if lane_access is None
        else InboxLane(
            uow, inbox, assembly.services.processing, lane_access, clock, directory, intake
        )
    )
    indexing = None if examples is None else ExampleIndexLane(decided_lines, examples)
    if requester_access is None:
        return Dw1Mount(
            services=assembly.services,
            lane=lane,
            catalog_parsing=catalog_parsing,
            activity=activity,
            mail_drop=dropped,
            examples=indexing,
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
    salesorder_learning = SalesOrderLearning(
        uow=catalog_uow,
        po_reading=CustomerPoReading(intake.reader, intake.layouts),
        sheets=readers.source,
        scanner=scanner,
        catalog=catalog,
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
    # Every Bravo screen Sales may upload, and its reader (tickets 16, 03).
    bravo_export_reading = BravoExportReading(
        uow=catalog_uow,
        tables=readers.tables,
        scanner=scanner,
        access=requester_access,
        readers={
            "ycbg": YcbgScreen(DesignChecks(uow, SqlQuoteCaseLookup(session_factory), clock, ids)),
            "sales_orders": SalesOrderScreen(order_cases, catalog_uow, clock, ids),
        },
        clock=clock,
        ids=ids,
    )
    return Dw1Mount(
        services=assembly.services,
        lane=lane,
        drain=drain,
        queue=queue,
        catalog_parsing=catalog_parsing,
        rule_drafting=rule_drafting,
        salesorder_learning=salesorder_learning,
        bravo_export_reading=bravo_export_reading,
        rule_draft_sweep=RuleDraftSweep(
            catalog_uow, SqlRuleDraftScopes(session_factory), clock, ids
        ),
        activity=activity,
        mail_drop=dropped,
        examples=indexing,
        skill_replay=(
            None
            if dw1_agent is None or agent_turns is None
            else SkillReplayer(
                uow=uow,
                replays=SqlSkillReplays(session_factory, audit),
                agent=dw1_agent,
                book=skills,
                rules=tenant_rules,
                # The worker image ships `evals/fixtures` beside `configs`.
                examples=FixtureReplayExamples.load(configs.parent),
                clock=clock,
                ids=ids,
                worker_id=worker.worker_id,
                worker_version=worker.worker_version,
                forget_run=agent_turns.budget.forget,
                mail_kinds=(
                    None
                    if mail_kinds is None
                    else MailKindReplay(mail_kinds, FixtureMailKindExamples.load(configs.parent))
                ),
                # The mail a mail-kinds version was taught from (ticket 34).
                inbox=inbox,
                # The hand-offs and the reply drafts, replayed on the eval
                # fixtures' mails and drafts (ticket 42 family 5).
                handoffs=(
                    None
                    if interpretation is None
                    else HandoffKindReplay(
                        HandoffReader(interpretation, catalog, order_cases, notations),
                        FixtureHandoffKindExamples.load(configs.parent),
                    )
                ),
                reply_drafts=(
                    None
                    if one_call_model is None
                    else ReplyKindReplay(
                        interpretation_for(one_call_model, configs, worker.default_model_profile),
                        FixtureReplyKindExamples.load(configs.parent),
                    )
                ),
                # The document forms, replayed on the request files of the
                # eval fixtures (ticket 42 family 3).
                document_forms=(
                    None
                    if requests is None
                    else DocumentFormReplay(
                        DocumentFormReader(requests.reader, skills),
                        FixtureDocumentFormExamples.load(configs.parent),
                        tenant_rules,
                    )
                ),
            )
        ),
        salesorder_skill_replay=(
            None
            if one_call_model is None
            else SalesOrderSkillReplayer(
                uow=uow,
                pairs=catalog_uow,
                replays=SqlSkillReplays(session_factory, audit),
                book=skills,
                rules=book,
                catalog=catalog,
                filler=SalesOrderFiller(
                    interpretation_for(one_call_model, configs, worker.default_model_profile)
                ),
                clock=clock,
                ids=ids,
                worker_id=worker.worker_id,
                worker_version=worker.worker_version,
            )
        ),
        salesorder_pairs_retention=WorkedPairRetention(
            pairs=catalog_uow, rules=book, clock=clock, ids=ids
        ),
        prompt_optimiser=(
            None
            if interpretation is None or finder is None or not security
            else PromptOptimiser(
                examples=decided_lines,
                reader=DescriptionReader(interpretation, examples=finder, prompts=prompts),
                book=prompts,
                rules=tenant_rules,
                gate=readiness,
                catalog=catalog,
                uow=uow,
                directory=directory,
                security=security,
                clock=clock,
                ids=ids,
                worker_id=worker.worker_id,
                worker_version=worker.worker_version,
            )
        ),
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


def build_skill_settlement(
    *,
    configs: Path,
    session_factory: async_sessionmaker[AsyncSession],
    audit: AuditFactory,
    approvals: ApprovalsFactory,
    clock: UtcClock,
    ids: IdGenerator,
) -> SkillSettlement:
    """What carries out a decided skill version approval
    (`sales.skills.decided`, ticket 40), for the worker's outbox handler. The
    version and the approval are rows of the approval's own tenant; the
    platform's skill files say which numbers it ships."""
    uow = SqlSalesUnitOfWorkFactory(session_factory, audit=audit, approvals=approvals)
    dw1_skills = load_dw1_skills(configs / "skills" / "dw1")
    return SkillSettlement(
        uow,
        skills_book(configs / "skills", dw1_skills, SqlRuleVersionLookup(session_factory)),
        clock,
        ids,
    )


def build_prompt_settlement(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    audit: AuditFactory,
    approvals: ApprovalsFactory,
    clock: UtcClock,
    ids: IdGenerator,
) -> PromptSettlement:
    """What carries out a decided prompt version approval (`sales.prompts`,
    ticket 43), for the worker's outbox handler. The version and the approval
    are rows of the approval's own tenant."""
    uow = SqlSalesUnitOfWorkFactory(session_factory, audit=audit, approvals=approvals)
    return PromptSettlement(uow, prompt_book(SqlRuleVersionLookup(session_factory)), clock, ids)


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
    # Web push to the people told (ticket 48); None where it is off.
    push: PushNoticePort | None = None,
) -> tuple[FollowupLane, SqlFollowupScopes]:
    """DW1's follow-ups and morning brief (ticket 42), for the worker's
    `sales_followups` lane, and the workspaces it visits: every one with a
    Sales case (`sales.followup_scopes()`). Each tenant's timings are its
    resolved `sales_followups` policy, read through the rule book; nothing
    else here is DW1's services, so it needs no mailbox and no files."""
    uow = SqlSalesUnitOfWorkFactory(session_factory, audit=audit, approvals=approvals)
    policies = load_sales_policies(configs / "policies", configs / "copy")
    book = rule_book(policies, SqlRuleVersionLookup(session_factory))
    lane = FollowupLane(uow, book, holders, notifications, clock, ids, writer, push)
    return lane, SqlFollowupScopes(session_factory)


def build_threshold_lane(
    *,
    configs: Path,
    session_factory: async_sessionmaker[AsyncSession],
    audit: AuditFactory,
    clock: UtcClock,
    ids: IdGenerator,
) -> tuple[ThresholdLane, SqlFollowupScopes]:
    """The worker's `sales_auto_apply` lane (ticket 44): each workspace's
    thresholds set again from its labelled cases, at the targets of the
    tenant's resolved `sales_order_rules`, and the workspaces it visits:
    every one with a Sales case, as the follow-ups visit them."""
    policies = load_sales_policies(configs / "policies", configs / "copy")
    book = rule_book(policies, SqlRuleVersionLookup(session_factory))
    lane = ThresholdLane(
        labels=SqlLabelledCaseReader(session_factory),
        thresholds=SqlStepThresholds(session_factory, audit),
        rules=RuleBookOrderRules(book),
        clock=clock,
        ids=ids,
    )
    return lane, SqlFollowupScopes(session_factory)


def thread_agent(
    kit: AgentTurnKit,
    worker_file: Path,
    tools: ThreadTools,
    context: ThreadContextPort,
    models: StepModelPort,
) -> ThreadAgent:
    """The thread agent (tickets 30 and 31): DW1's read-only tools registered
    on ``kit`` with their specs' policy, and the turn of DW1's worker (its
    toolset, its profile's chat route) under the step's prompt and ceiling,
    built once."""
    worker, _ = parse_worker_file(worker_file)
    _register_dw1_tools(kit, tools)
    return ThreadAgent(kit.turn(worker, THREAD_AGENT, CEILING), context, models)


def skill_agent(
    kit: AgentTurnKit,
    worker_file: Path,
    tools: ThreadTools,
    context: ThreadContextPort,
    models: StepModelPort,
    skills: Dw1Skills,
    book: SkillSetPort,
    pick: PickModelPort,
) -> ThreadAgent:
    """DW1's agent with its skills (ticket 40, dw_sales ADR 0014): the
    skill ``book`` resolves for each run's tenant picked by one scored call
    on ``pick`` (ADR 0015 decision 5), then read with the thread reader's
    tools and binding on a turn under `DW1_AGENT` that carries DW1's conduct
    and the picked skill's words, built once. No catalogue and no loading
    tool: the turn is not served skills (`AgentTurnKit.turn`)."""
    worker, _ = parse_worker_file(worker_file)
    _register_dw1_tools(kit, tools)
    # Thinking on for this step alone (ticket 40: 0.700 off, 0.867 on, on
    # Strata), on the profile the worker's names for it.
    turn = kit.turn(worker, DW1_AGENT, SKILL_CEILING, thinking=True)
    choice = TurnSkillChoice(book=book, picker=SkillPicker(pick, models), agent=skills.agent)
    return ThreadAgent(turn, context, models, skills=choice)


def _register_dw1_tools(kit: AgentTurnKit, tools: ThreadTools) -> None:
    """DW1's read-only tools and its skill loader on ``kit``, each with its
    spec's policy, once: both readers are built over one kit."""
    if READ_SKILL in kit.skill_readers:
        return
    for tool in registered_tools(tools, kit.definition):
        kit.register(tool)
    kit.register_skill_reader(kit.definition(READ_SKILL, READ_SKILL_VERSION))


def model_requests(
    model: InterpretationPort,
    catalog: SalesCatalogPort,
    rules: OrderRulesPort,
    texts: AttachmentTextPort,
    gate: ModelStepGatePort,
    records: NotationRecordPort,
    skills: SkillPort | None = None,
) -> ModelRequests:
    """The quotation flow's model step over ``model`` (ticket 29): requests
    read from the mail and the attachments' ``texts``, item descriptions as
    ticket 28 reads them, ambiguous values settled by the customer's notation
    ``records`` where a document leaves them open (ticket 37), switched by the
    tenant's rules and held to the step's bar by ``gate``; and, where the
    tenant's ``skills`` are served, its document forms read first (ticket 42
    family 3)."""
    reader = RfqModelReader(model, texts, catalog, DescriptionReader(model), records)
    forms = None if skills is None else DocumentFormReader(reader, skills)
    return ModelRequests(reader=reader, rules=rules, gate=gate, forms=forms)


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
