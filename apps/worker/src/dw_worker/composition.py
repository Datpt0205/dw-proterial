"""Worker composition root: wires the knowledge ingest pipeline from settings,
and the runner for the graphs a context hosts here.

Mirrors the API's knowledge wiring but on the worker side, where the parse
layer lives. Only the composition root imports concrete adapters
(Clean/Hexagonal rule); consumers receive already-wired ports.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from dw_agent_runtime.adapters.checkpoint import SqlAlchemyCheckpointSaver
from dw_agent_runtime.adapters.langgraph_runner import LangGraphWorkflowRunner
from dw_agent_runtime.adapters.model_stack import (
    ModelProviderConfig,
    ModelStack,
    build_model_stack,
)
from dw_agent_runtime.adapters.run_store import SqlWorkerRunStore
from dw_agent_runtime.adapters.spend_guard import SqlSpendGuardStore
from dw_agent_runtime.approval_flow import ApproveAndResumeService
from dw_agent_runtime.autonomy import AutonomyApprovalPolicy
from dw_agent_runtime.model.gateway import RoutingModelGateway
from dw_agent_runtime.model.profiles import ModelProfileRegistry
from dw_agent_runtime.model.prompts import PromptRegistry
from dw_agent_runtime.model.run_policy import load_worker_run_policy
from dw_agent_runtime.registry import GraphRegistry, WorkerRegistry
from dw_kernel.net_guard import ensure_allowed_outbound_url
from dw_kernel.ports import IdGenerator, SystemClock, UtcClock, Uuid7Generator
from dw_knowledge.adapters.api_parsers import (
    DeepgramTranscriptParser,
    GatewayFileParser,
    PlaintextAttachmentParser,
)
from dw_knowledge.adapters.composite_parser import CompositeParser
from dw_knowledge.adapters.embedding_factory import build_embeddings as shared_build_embeddings
from dw_knowledge.attachment_policy import load_attachment_policy
from dw_knowledge.gateway import KnowledgeGateway
from dw_knowledge.ingest_jobs import IngestJobStore
from dw_knowledge.ports import DocumentParserPort, EmbeddingPort, ObjectStoragePort, VectorIndexPort
from dw_observability.telemetry import TelemetryPort
from dw_platform.adapters.persistence.uow import SqlPlatformUnitOfWorkFactory
from dw_platform.application.entitlement import DEFAULT_PLANS, PlanEntitlementService
from dw_worker.settings import WorkerSettings

if TYPE_CHECKING:
    from minio import Minio

# The image sets DW_REPO_ROOT=/app; outside a container the checkout root is
# four levels up from this file.
REPO_ROOT = Path(os.environ.get("DW_REPO_ROOT", str(Path(__file__).resolve().parents[4])))
ATTACHMENT_POLICY = "attachment_ingest@1.1.0.yaml"


@dataclass
class IngestComponents:
    engine: AsyncEngine
    gateway: KnowledgeGateway
    job_store: IngestJobStore
    parser: DocumentParserPort
    object_storage: ObjectStoragePort


def _build_minio_client(settings: WorkerSettings) -> Minio:
    from minio import Minio

    assert settings.s3_endpoint_url is not None
    endpoint = settings.s3_endpoint_url.replace("http://", "").replace("https://", "")
    return Minio(
        endpoint,
        access_key=settings.s3_access_key or "",
        secret_key=settings.s3_secret_key or "",
        secure=settings.s3_endpoint_url.startswith("https://"),
    )


def build_object_storage(settings: WorkerSettings) -> ObjectStoragePort:
    """Public: a context's own lane may stage artifacts in the same bucket."""
    from dw_knowledge.adapters.minio_storage import MinioObjectStorageAdapter

    return MinioObjectStorageAdapter(
        client=_build_minio_client(settings), bucket=settings.s3_bucket
    )


def build_export_bucket(settings: WorkerSettings) -> ObjectStoragePort:
    """Tenant offboarding's export destination — the `dw-exports` bucket
    already used elsewhere, not a new one made for this feature."""
    from dw_knowledge.adapters.minio_storage import MinioObjectStorageAdapter

    return MinioObjectStorageAdapter(
        client=_build_minio_client(settings), bucket=settings.s3_bucket_exports
    )


def build_feedback_bucket(settings: WorkerSettings) -> ObjectStoragePort:
    """The same bucket `dw_api`'s feedback attachments live in — offboarding
    reads and deletes from it, `dw_knowledge`'s generic adapter is reused
    rather than depending on `dw_api`'s own (see
    `dw_worker.consumers.offboarding.BucketPort`'s docstring)."""
    from dw_knowledge.adapters.minio_storage import MinioObjectStorageAdapter

    return MinioObjectStorageAdapter(
        client=_build_minio_client(settings), bucket=settings.feedback_bucket
    )


def build_embeddings(settings: WorkerSettings) -> EmbeddingPort:
    """Public because two lanes need it: knowledge ingestion, and the memory
    index. Built by `dw_knowledge`'s one builder, the one the API embeds
    questions with, so "which model embeds this deployment's text" has a
    single answer: the `embedding` route of the configured model profile.
    """
    profiles = ModelProfileRegistry()
    profiles.load_directory(REPO_ROOT / "configs" / "models")
    return shared_build_embeddings(
        settings.embedding_provider,
        profiles.resolve(settings.model_profile).embedding,
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
        profile_id=settings.model_profile,
        # Guarded as the chat routes on the same server are (`model_stack`).
        onprem_base_url=(
            ensure_allowed_outbound_url(
                settings.onprem_model_base_url,
                allow_private=not settings.is_deployed,
                allowed_hosts=tuple(settings.outbound_allowed_hosts),
            )
            if settings.onprem_model_base_url
            else None
        ),
        onprem_api_key=settings.onprem_model_api_key or None,
    )


def build_vector_index(settings: WorkerSettings) -> VectorIndexPort:
    if settings.qdrant_url:
        from qdrant_client import AsyncQdrantClient

        from dw_knowledge.adapters.qdrant_index import QdrantVectorIndexAdapter

        return QdrantVectorIndexAdapter(
            client=AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key),
            collection=settings.qdrant_collection,
        )
    from dw_knowledge.adapters.memory_index import InMemoryVectorIndexAdapter

    return InMemoryVectorIndexAdapter()


def build_parser(settings: WorkerSettings) -> DocumentParserPort:
    """Route by extension: plaintext in process, everything else to an API.

    Public because a context's own lane reads PDFs through the same parser: a
    report an agent fetches and the same report a person uploads must chunk
    identically, or a search returns two shapes of one document.

    Order matters only in that each parser answers `supports` for its own kinds;
    the policy is the single place that decides which kind a file is.
    """
    policy = load_attachment_policy(REPO_ROOT / "configs" / "policies" / ATTACHMENT_POLICY)
    parsers: list[DocumentParserPort] = [PlaintextAttachmentParser(policy=policy)]

    if settings.openai_base_url and settings.openai_api_key:
        parsers.append(
            GatewayFileParser(
                base_url=settings.openai_base_url,
                api_key=settings.openai_api_key,
                model=settings.extraction_model,
                policy=policy,
            )
        )
    if settings.deepgram_api_key:
        parsers.append(DeepgramTranscriptParser(api_key=settings.deepgram_api_key, policy=policy))
    # A missing key is not silently a missing format: CompositeParser raises
    # "no parser supports ..." and the job records that as its error, which is
    # what the upload status shows.
    return CompositeParser(parsers=parsers)


def build_ingest_components(settings: WorkerSettings) -> IngestComponents | None:
    """Return wired ingest components, or ``None`` if infra is not configured."""
    if not (settings.database_url and settings.s3_endpoint_url):
        return None

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    clock = SystemClock()
    id_generator = Uuid7Generator()
    storage = build_object_storage(settings)

    gateway = KnowledgeGateway(
        session_factory=session_factory,
        vector_index=build_vector_index(settings),
        embeddings=build_embeddings(settings),
        object_storage=storage,
        clock=clock,
        id_generator=id_generator,
    )
    job_store = IngestJobStore(
        session_factory=session_factory,
        clock=clock,
        id_generator=id_generator,
        retry_backoff_seconds=settings.ingest_retry_backoff_seconds,
    )
    return IngestComponents(
        engine=engine,
        gateway=gateway,
        job_store=job_store,
        parser=build_parser(settings),
        object_storage=storage,
    )


# The recorded answers the mock provider replays, the directory the API reads.
MOCK_MODEL_FIXTURES = REPO_ROOT / "evals" / "fixtures" / "mock_model"


def model_provider_config(settings: WorkerSettings) -> ModelProviderConfig:
    """This process's settings, read for the model builder the API uses too."""
    return ModelProviderConfig(
        provider=settings.model_provider,
        model_profile=settings.model_profile,
        profile=settings.profile,
        is_deployed=settings.is_deployed,
        openai_api_key=settings.openai_api_key or None,
        openai_base_url=settings.openai_base_url or None,
        openai_structured_mode=settings.openai_structured_mode,
        openai_strict_schema=settings.openai_strict_schema,
        outbound_allowed_hosts=tuple(settings.outbound_allowed_hosts),
        onprem_base_url=settings.onprem_model_base_url or None,
        onprem_api_key=settings.onprem_model_api_key or None,
    )


def build_model_stack_for(
    settings: WorkerSettings,
    sessions: async_sessionmaker[AsyncSession],
    *,
    clock: UtcClock,
    telemetry: TelemetryPort,
) -> ModelStack:
    """The worker's model gateway, spend ledger and usage recorders, built by
    the same `build_model_stack` the API builds its own with: the profiles,
    the shipped prompts, the daily spend guard. A chat command's model call
    therefore spends against the same per-run ceiling and the same daily
    guard as a request's."""
    profiles = ModelProfileRegistry()
    profiles.load_directory(REPO_ROOT / "configs" / "models")
    prompts = PromptRegistry()
    prompts.load_directory(REPO_ROOT / "configs" / "prompts")
    return build_model_stack(
        model_provider_config(settings),
        profiles=profiles,
        prompts=prompts,
        session_factory=sessions,
        clock=clock,
        telemetry=telemetry,
        mock_fixtures_dir=MOCK_MODEL_FIXTURES,
    )


# ---- graphs this process hosts ---------------------------------------------

# Pinned like the API pins them (`dw_api.bootstrap.paths`): the stale-run rule
# both processes' runs are held to, and the release a run records. A test
# holds the two pins together (`test_worker_sales_settings.py`).
WORKER_RUN_POLICY = REPO_ROOT / "configs" / "policies" / "worker_runs@1.0.0.yaml"
_RELEASE_MANIFEST_REF = REPO_ROOT / "contracts" / "release" / "manifest.ref"


def release_manifest_ref() -> str:
    """The content-addressed release this process serves; every run records it.
    Absent only in an unreleased development tree."""
    if _RELEASE_MANIFEST_REF.exists():
        return _RELEASE_MANIFEST_REF.read_text(encoding="utf-8").strip()
    return "unreleased"


@dataclass(frozen=True)
class WorkflowRuntime:
    """Where a context registers the graphs this process hosts, the runner
    that starts their runs, and the approvals those runs pause on."""

    graphs: GraphRegistry
    workers: WorkerRegistry
    runner: LangGraphWorkflowRunner
    approval_flow: ApproveAndResumeService
    # The process's model gateway, the one whose ledger the runner frees: a
    # context's step that reads a document through a model calls this one.
    gateway: RoutingModelGateway


def build_workflow_runtime(
    settings: WorkerSettings,
    sessions: async_sessionmaker[AsyncSession],
    *,
    clock: UtcClock,
    ids: IdGenerator,
    telemetry: TelemetryPort,
) -> WorkflowRuntime:
    """A runner as the API builds its own, for a context whose graph runs here.

    Runs, checkpoints and approvals are PostgreSQL rows, so a run started in
    this process is a run like any other: counted against the tenant's plan
    where it begins (`allowance`, the daily spend guard beside it), recorded
    with this release, and resumable by either process that registered its
    graph. The per-run ledger is the one this process's model gateway holds
    (`build_model_stack_for`), not a second one. No approval prefix is made
    strict here beyond what a context registers: this process decides no
    approval through this flow.
    """
    stack = build_model_stack_for(settings, sessions, clock=clock, telemetry=telemetry)
    uow_factory = SqlPlatformUnitOfWorkFactory(sessions)
    run_store = SqlWorkerRunStore(
        sessions,
        stale_run_after_seconds=load_worker_run_policy(WORKER_RUN_POLICY).stale_run_after_seconds,
    )
    graphs = GraphRegistry()
    workers = WorkerRegistry(graph_registry=graphs)
    runner = LangGraphWorkflowRunner(
        worker_registry=workers,
        graph_registry=graphs,
        checkpoint_saver=SqlAlchemyCheckpointSaver(sessions),
        run_store=run_store,
        uow_factory=uow_factory,
        clock=clock,
        id_generator=ids,
        allowance=PlanEntitlementService(DEFAULT_PLANS),
        budget=stack.budget,
        approval_policy=AutonomyApprovalPolicy(),
        release_manifest_ref=release_manifest_ref(),
        telemetry=telemetry,
        spend_store=SqlSpendGuardStore(session_factory=sessions),
    )
    approval_flow = ApproveAndResumeService(
        uow_factory=uow_factory,
        runner=runner,
        run_store=run_store,
        clock=clock,
        id_generator=ids,
    )
    return WorkflowRuntime(graphs, workers, runner, approval_flow, stack.gateway)
