"""Agent-runtime wiring: registries, model gateway, tool executor, workflow runner.

This is the half of the composition root a bounded context actually plugs into.
Nothing here names a context; what it produces is the ``RuntimeSeam`` a context's
``register_*`` function is later called with.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_agent_runtime.adapters.checkpoint import SqlAlchemyCheckpointSaver
from dw_agent_runtime.adapters.langchain_usage import LangchainUsageMeter
from dw_agent_runtime.adapters.langgraph_runner import LangGraphWorkflowRunner
from dw_agent_runtime.adapters.run_store import SqlWorkerRunStore
from dw_agent_runtime.adapters.sql_usage import CompositeUsageRecorder, SqlUsageRecorder
from dw_agent_runtime.adapters.telemetry_usage import TelemetryUsageRecorder
from dw_agent_runtime.adapters.tool_execution_store import SqlToolExecutionStore
from dw_agent_runtime.approval_flow import ApproveAndResumeService
from dw_agent_runtime.executor import ToolExecutor
from dw_agent_runtime.model.budget import RunBudgetLedger
from dw_agent_runtime.model.copy import load_runtime_copy
from dw_agent_runtime.model.gateway import RoutingModelGateway, UsageRecorderPort
from dw_agent_runtime.model.profiles import ModelProfileRegistry
from dw_agent_runtime.model.prompts import PromptRegistry
from dw_agent_runtime.ports import RunAllowancePort
from dw_agent_runtime.registry import GraphRegistry, WorkerRegistry
from dw_agent_runtime.tool_specs import ToolSpecRegistry
from dw_agent_runtime.tools import ToolRegistry
from dw_agent_runtime.toolsets import ToolsetRegistry
from dw_api.adapters.document_indexing import KnowledgeDocumentIndexingAdapter
from dw_api.bootstrap.container import RuntimeSeam
from dw_api.bootstrap.knowledge import build_embeddings, build_reranker, build_vector_index
from dw_api.bootstrap.models import build_chat_model_factory, build_model_adapters
from dw_api.bootstrap.paths import (
    ATTACHMENT_POLICY,
    MODEL_PROFILES_DIR,
    PROMPTS_DIR,
    RUNTIME_COPY_CONFIG,
    TOOL_SPECS_DIR,
    TOOLSETS_DIR,
    release_manifest_ref,
)
from dw_api.settings import ApiSettings
from dw_kernel.ports import IdGenerator, UtcClock
from dw_knowledge.attachment_policy import load_attachment_policy
from dw_knowledge.gateway import KnowledgeGateway
from dw_knowledge.ingest_jobs import IngestJobStore
from dw_knowledge.ports import ObjectStoragePort
from dw_memory.policy import MemoryWritePolicy
from dw_memory.service import MemoryService
from dw_observability.telemetry import NullTelemetry, TelemetryPort
from dw_platform.application.ports import PlatformUnitOfWorkFactory


@dataclass(frozen=True)
class RuntimeWiring:
    """Everything the runtime half produces, in one return value."""

    seam: RuntimeSeam
    runner: LangGraphWorkflowRunner
    approval_flow: ApproveAndResumeService
    knowledge_gateway: KnowledgeGateway
    ingest_jobs: IngestJobStore
    document_indexing: KnowledgeDocumentIndexingAdapter
    memory_service: MemoryService
    tool_registry: ToolRegistry


def build_runtime(
    settings: ApiSettings,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    uow_factory: PlatformUnitOfWorkFactory,
    run_store: SqlWorkerRunStore,
    allowance: RunAllowancePort,
    object_storage: ObjectStoragePort,
    telemetry: TelemetryPort,
    clock: UtcClock,
    ids: IdGenerator,
) -> RuntimeWiring:
    # ---- versioned artifact registries -----------------------------------
    profiles = ModelProfileRegistry()
    profiles.load_directory(MODEL_PROFILES_DIR)
    prompts = PromptRegistry()
    prompts.load_directory(PROMPTS_DIR)
    copy = load_runtime_copy(RUNTIME_COPY_CONFIG)

    # ---- model gateway ---------------------------------------------------
    # The ledger is where the invoice comes from and telemetry is where one
    # call is inspected, so both run. Composing rather than choosing is
    # deliberate: a wiring that picked one would eventually pick the one that
    # cannot answer the question being asked.
    recorders: list[UsageRecorderPort] = [
        SqlUsageRecorder(session_factory=session_factory, id_generator=ids, clock=clock)
    ]
    if not isinstance(telemetry, NullTelemetry):
        recorders.append(TelemetryUsageRecorder(telemetry))
    usage_recorder: UsageRecorderPort = CompositeUsageRecorder(recorders)
    # ONE per-run spend ledger for the whole process, shared by the structured
    # gateway, every agent's budget middleware (on the seam, below) and the
    # runner that frees a run's entry when it ends. Two ledgers would split a
    # run's spend so neither half reaches the ceiling, and the gateway's own
    # default was never freed at all.
    budget = RunBudgetLedger()
    gateway = RoutingModelGateway(
        profiles=profiles,
        prompts=prompts,
        adapters=build_model_adapters(settings),
        usage_recorder=usage_recorder,
        budget=budget,
    )
    # The LangChain path (agent loops, structured output) bills into the same
    # ledger through this meter rather than going unmetered.
    usage_meter = LangchainUsageMeter(profiles=profiles, recorder=usage_recorder)
    chat_models = build_chat_model_factory(settings, profiles, copy)

    # ---- retrieval -------------------------------------------------------
    knowledge_gateway = KnowledgeGateway(
        session_factory=session_factory,
        vector_index=build_vector_index(settings),
        embeddings=build_embeddings(settings, profiles),
        object_storage=object_storage,
        clock=clock,
        id_generator=ids,
        reranker=build_reranker(settings),
    )
    # Upload path: the API stages the raw file and enqueues; the worker ingests.
    ingest_jobs = IngestJobStore(session_factory=session_factory, clock=clock, id_generator=ids)
    document_indexing = KnowledgeDocumentIndexingAdapter(
        jobs=ingest_jobs, policy=load_attachment_policy(ATTACHMENT_POLICY)
    )

    # ---- tools -----------------------------------------------------------
    # A context registers its tool factories on `tools`; the policy each one
    # runs under (scopes, side-effect level, approval, idempotency, timeout)
    # comes from its spec in configs/tools, never from the factory.
    tool_registry = ToolRegistry()
    tool_executor = ToolExecutor(
        registry=tool_registry,
        execution_store=SqlToolExecutionStore(session_factory),
        uow_factory=uow_factory,
        clock=clock,
        id_generator=ids,
        telemetry=telemetry,
    )
    tool_specs = ToolSpecRegistry(copy=copy)
    tool_specs.load_directory(TOOL_SPECS_DIR)
    toolsets = ToolsetRegistry()
    toolsets.load_directory(TOOLSETS_DIR)

    # ---- memory ----------------------------------------------------------
    memory_service = MemoryService(
        session_factory=session_factory,
        policy=MemoryWritePolicy(),
        clock=clock,
        id_generator=ids,
    )

    # ---- graphs, workers, runner ----------------------------------------
    # A context calls its `register_*_graphs(graphs, services)` on the seam,
    # then `workers.load_file(...)` for the worker YAML whose graph it just
    # registered. A process loads only the workers it hosts: configs/workers is
    # shared, and loading a file whose graph lives in another process would fail
    # fast for the wrong reason.
    graphs = GraphRegistry()
    workers = WorkerRegistry(graph_registry=graphs)
    runner = LangGraphWorkflowRunner(
        worker_registry=workers,
        graph_registry=graphs,
        checkpoint_saver=SqlAlchemyCheckpointSaver(session_factory),
        run_store=run_store,
        uow_factory=uow_factory,
        clock=clock,
        id_generator=ids,
        allowance=allowance,
        budget=budget,
        release_manifest_ref=release_manifest_ref(),
        telemetry=telemetry,
        usage_meter=usage_meter,
    )
    approval_flow = ApproveAndResumeService(
        uow_factory=uow_factory,
        runner=runner,
        run_store=run_store,
        clock=clock,
        id_generator=ids,
    )

    seam = RuntimeSeam(
        session_factory=session_factory,
        clock=clock,
        ids=ids,
        telemetry=telemetry,
        profiles=profiles,
        prompts=prompts,
        copy=copy,
        gateway=gateway,
        chat_models=chat_models,
        usage_meter=usage_meter,
        budget=budget,
        tools=tool_registry,
        tool_executor=tool_executor,
        tool_specs=tool_specs,
        toolsets=toolsets,
        graphs=graphs,
        workers=workers,
        knowledge=knowledge_gateway,
        memory=memory_service,
    )
    return RuntimeWiring(
        seam=seam,
        runner=runner,
        approval_flow=approval_flow,
        knowledge_gateway=knowledge_gateway,
        ingest_jobs=ingest_jobs,
        document_indexing=document_indexing,
        memory_service=memory_service,
        tool_registry=tool_registry,
    )
