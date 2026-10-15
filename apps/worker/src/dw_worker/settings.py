"""Worker process settings."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Literal

from pydantic import (
    AliasChoices,
    Field,
    SecretStr,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from dw_agent_runtime.model.profiles import DEFAULT_PROFILE_ID
from dw_knowledge.contracts import DEFAULT_COLLECTION
from dw_knowledge.ingest_jobs import (
    DEFAULT_HEARTBEAT_SECONDS,
    DEFAULT_JOB_TIMEOUT_SECONDS,
    DEFAULT_LEASE_SECONDS,
    DEFAULT_RETRY_BACKOFF_SECONDS,
)

# Mirrors dw_api.settings: the same four profiles, and the same rule that
# anything forbidden in production is forbidden in UAT, because the difference
# between them is who a mistake reaches, not how strict the configuration is.
Profile = Literal["local", "test", "uat", "production"]
DEPLOYED_PROFILES: frozenset[str] = frozenset({"uat", "production"})


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DW_WORKER_",
        extra="ignore",
        populate_by_name=True,
    )

    profile: Profile = Field(
        default="local",
        validation_alias=AliasChoices("DW_WORKER_PROFILE", "DW_API_PROFILE"),
    )

    # Where configs/, evals/fixtures/ and the rest of the repo live. In dev this
    # is the source tree; the image ships them at /app and sets DW_REPO_ROOT.
    repo_root: Path = Field(
        default=Path(__file__).resolve().parents[4],
        validation_alias=AliasChoices("DW_WORKER_REPO_ROOT", "DW_REPO_ROOT"),
    )

    heartbeat_file: Path = Path("/tmp/dw-worker-heartbeat")  # nosec B108  # container liveness probe path
    heartbeat_interval_seconds: float = Field(default=5.0, gt=0, le=60)
    poll_interval_seconds: float = Field(default=1.0, gt=0, le=60)
    # How often the `channel_delivery` lane looks for notifications to send
    # through a linked chat (channels Z2). Thirty seconds: a Zalo
    # message trails its in-app notification by at most that.
    channel_delivery_interval_seconds: float = Field(default=30.0, ge=5, le=3600)

    # Prometheus scrape target for this process (Ops hardening Phase 5). 9464
    # is the OTel/Prometheus exporter's own convention default; dw-api has no
    # equivalent setting because it serves `/metrics` on its existing HTTP port.
    metrics_port: int = Field(default=9464, ge=1, le=65535)

    # Infrastructure for the knowledge ingest consumer (B5). When database_url /
    # s3_endpoint_url are unset, the consumer is skipped (heartbeat-only worker).
    # database_url takes no alias: DW_DATABASE_URL names the migrator connection,
    # which holds BYPASSRLS and would disable every row-level policy silently.
    # The other fields still accept the plain env vars compose already provides.
    database_url: str | None = None
    qdrant_url: str | None = Field(
        default=None, validation_alias=AliasChoices("DW_WORKER_QDRANT_URL", "QDRANT_URL")
    )
    # Required when the server enforces QDRANT__SERVICE__API_KEY (shared dev
    # server override); None keeps plain local Qdrant working.
    qdrant_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DW_WORKER_QDRANT_API_KEY", "QDRANT_API_KEY"),
    )
    s3_endpoint_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DW_WORKER_S3_ENDPOINT_URL", "S3_ENDPOINT_URL"),
    )
    s3_access_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DW_WORKER_S3_ACCESS_KEY", "MINIO_ROOT_USER"),
    )
    s3_secret_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DW_WORKER_S3_SECRET_KEY", "MINIO_ROOT_PASSWORD"),
    )
    s3_bucket: str = Field(
        default="dw-artifacts",
        validation_alias=AliasChoices("DW_WORKER_S3_BUCKET", "S3_BUCKET_ARTIFACTS"),
    )
    # Tenant offboarding's export destination — the bucket already exists
    # (infra/compose/docker-compose.yml's minio-setup), matched here rather
    # than a new one made for this feature.
    s3_bucket_exports: str = Field(
        default="dw-exports",
        validation_alias=AliasChoices("DW_WORKER_S3_BUCKET_EXPORTS", "S3_BUCKET_EXPORTS"),
    )
    # Same bucket dw_api's feedback attachments live in (dw_api/settings.py's
    # `feedback_bucket`) — offboarding needs to read and delete a tenant's
    # attachments from the same place they were written to.
    feedback_bucket: str = Field(
        default="feedback", validation_alias=AliasChoices("DW_WORKER_FEEDBACK_BUCKET")
    )

    # Which Qdrant collection this process reads and writes. Named explicitly
    # because the collection's vector width is fixed at creation: moving to a
    # different embedding model means a new collection and a reindex, and
    # pointing two widths at one name is refused rather than resolved.
    qdrant_collection: str = Field(
        default=DEFAULT_COLLECTION,
        validation_alias=AliasChoices("DW_WORKER_QDRANT_COLLECTION", "QDRANT_COLLECTION"),
    )

    # "hash" (offline default) | "openai_compatible" (the configured gateway;
    # model and width come from the profile below). Anything else is refused
    # at startup rather than quietly read as "hash".
    embedding_provider: str = Field(
        default="hash", validation_alias=AliasChoices("DW_WORKER_EMBEDDING_PROVIDER")
    )
    model_profile: str = Field(
        default=DEFAULT_PROFILE_ID,
        validation_alias=AliasChoices("DW_WORKER_MODEL_PROFILE", "DW_API_MODEL_PROFILE"),
    )
    # Observability → Langfuse (OTLP). Empty = NullTelemetry (no export). Same four
    # knobs api/chat read, so every research/scoring/news run traces to one project.
    otel_endpoint: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DW_WORKER_OTEL_ENDPOINT", "OTEL_EXPORTER_OTLP_ENDPOINT"),
    )
    langfuse_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("DW_WORKER_LANGFUSE_ENABLED", "LANGFUSE_ENABLED"),
    )
    langfuse_host: str | None = Field(
        default=None, validation_alias=AliasChoices("DW_WORKER_LANGFUSE_HOST", "LANGFUSE_HOST")
    )
    langfuse_public_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DW_WORKER_LANGFUSE_PUBLIC_KEY", "LANGFUSE_PUBLIC_KEY"),
    )
    langfuse_secret_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DW_WORKER_LANGFUSE_SECRET_KEY", "LANGFUSE_SECRET_KEY"),
    )
    openai_base_url: str = Field(
        default="", validation_alias=AliasChoices("DW_WORKER_OPENAI_BASE_URL", "OPENAI_BASE_URL")
    )
    openai_api_key: str = Field(
        default="", validation_alias=AliasChoices("DW_WORKER_OPENAI_API_KEY", "OPENAI_API_KEY")
    )
    # The model server the deployment runs itself (provider ``onprem``), read
    # under the same names the API reads it, so DW1's mailbox lane and "DW xử
    # lý" read a description on the same model.
    onprem_model_base_url: str = Field(
        default="",
        validation_alias=AliasChoices(
            "DW_WORKER_ONPREM_MODEL_BASE_URL",
            "DW_API_ONPREM_MODEL_BASE_URL",
            "DW_ONPREM_MODEL_BASE_URL",
        ),
    )
    onprem_model_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "DW_WORKER_ONPREM_MODEL_API_KEY",
            "DW_API_ONPREM_MODEL_API_KEY",
            "DW_ONPREM_MODEL_API_KEY",
        ),
    )
    # The structured-output model a chat command reads a message with. Same
    # names and defaults the API reads, mapped onto the one builder both
    # processes use (`dw_agent_runtime.adapters.model_stack`, through
    # `dw_worker.composition.build_model_stack_for`), which refuses "mock" in
    # a deployed profile.
    model_provider: str = Field(
        default="mock",
        validation_alias=AliasChoices(
            "DW_WORKER_MODEL_PROVIDER", "DW_API_MODEL_PROVIDER", "DW_MODEL_PROVIDER"
        ),
    )
    openai_structured_mode: str = Field(
        default="json_schema",
        validation_alias=AliasChoices(
            "DW_WORKER_OPENAI_STRUCTURED_MODE", "DW_API_OPENAI_STRUCTURED_MODE"
        ),
    )
    openai_strict_schema: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "DW_WORKER_OPENAI_STRICT_SCHEMA", "DW_API_OPENAI_STRICT_SCHEMA"
        ),
    )
    outbound_allowed_hosts: list[str] = Field(
        default=[],
        validation_alias=AliasChoices(
            "DW_WORKER_OUTBOUND_ALLOWED_HOSTS", "DW_API_OUTBOUND_ALLOWED_HOSTS"
        ),
    )
    # Reads uploaded documents and images. Verified per modality, not chosen by
    # tier: gpt-4.1-mini reads a PDF correctly through this gateway but does NOT
    # receive images - asked the colour of a solid blue square it answered
    # "Green", and asked to transcribe one it invented a book cover. A model
    # that cannot see the image still answers, so this is only ever caught by
    # asking it something the image alone can answer.
    extraction_model: str = Field(
        default="gpt-5.6-luna", validation_alias=AliasChoices("DW_WORKER_EXTRACTION_MODEL")
    )
    deepgram_api_key: str = Field(
        default="", validation_alias=AliasChoices("DW_WORKER_DEEPGRAM_API_KEY", "DEEPGRAM_API_KEY")
    )

    # Jobs drained concurrently per tick. More than one because a single slow
    # file must not hold up every other tenant's uploads.
    ingest_batch_size: int = Field(default=4, ge=1, le=16)
    # How long a claim is held. Must exceed the job timeout below, or a second
    # worker takes over a job the first is still running.
    ingest_lease_seconds: int = Field(default=DEFAULT_LEASE_SECONDS, ge=60, le=7200)
    # No longer capped by the lease: the consumer renews the lease on a
    # heartbeat, so this is the budget for the work itself. A four-hour customer
    # meeting is a real recording and needs tens of minutes end to end.
    ingest_job_timeout_seconds: float = Field(default=DEFAULT_JOB_TIMEOUT_SECONDS, gt=0, le=21600)
    ingest_heartbeat_seconds: float = Field(default=DEFAULT_HEARTBEAT_SECONDS, gt=0, le=3600)
    ingest_retry_backoff_seconds: float = Field(
        default=DEFAULT_RETRY_BACKOFF_SECONDS, gt=0, le=3600
    )

    # Outbox events are cheap to dispatch, so a batch keeps an import of many
    # accounts from taking one poll tick each.
    outbox_batch_size: int = Field(default=8, ge=1, le=64)
    # After this many delivery attempts an event stops being claimed and waits
    # for a human, with `last_error` saying what it kept failing on. Three is a
    # transient fault survived twice, not a broken handler retried for ever.
    outbox_max_attempts: int = Field(default=3, ge=1, le=10)

    @field_validator("embedding_provider", mode="before")
    @classmethod
    def _blank_means_unset(cls, value: object, info: ValidationInfo) -> object:
        """Compose reads ``${X:-default}``, so a blank line in .env is "unset" in
        a container; the same .env on the host must not mean something else."""
        if value == "" and info.field_name is not None:
            return cls.model_fields[info.field_name].default
        return value

    # --- Zalo self-link (channels Z1) ---
    # The bot token is a credential (it rides in every Bot API URL) and the link
    # secret must equal the API's: it verifies the ``/start`` token the API
    # signed. ``SecretStr`` so neither prints in a repr, a log or an error.
    zalo_bot_token: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("DW_WORKER_ZALO_BOT_TOKEN", "ZALO_BOT_TOKEN"),
    )
    zalo_link_secret: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("DW_WORKER_ZALO_LINK_SECRET", "ZALO_LINK_SECRET"),
    )
    # The key decision codes are hashed under; must equal the API's, which
    # issued them (ADR 0007-chat-decisions-after-a-portal-view, channels Z5). Empty = a decision
    # sent from Zalo is answered "not enabled" and nothing is decided.
    approval_code_secret: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("DW_WORKER_APPROVAL_CODE_SECRET", "DW_APPROVAL_CODE_SECRET"),
    )
    # poll = this process long-polls getUpdates (no public URL needed);
    # webhook = Zalo POSTs to the API and nothing here polls. One bot answers
    # one reader: two processes polling the same bot steal each other's updates.
    zalo_updates_mode: Literal["poll", "webhook"] = Field(
        default="poll",
        validation_alias=AliasChoices("DW_WORKER_ZALO_UPDATES_MODE", "ZALO_UPDATES_MODE"),
    )
    # What the bot calls this deployment in its replies ("tài khoản <name>").
    product_name: str = Field(
        default="Digital Worker",
        min_length=1,
        validation_alias=AliasChoices("DW_WORKER_PRODUCT_NAME", "DW_PRODUCT_NAME"),
    )
    # The web app's public URL, the API's value: the bot links a person with
    # several workspaces to `<this>/settings` to choose the one for Zalo.
    public_web_url: str = Field(
        default="http://localhost:3000",
        validation_alias=AliasChoices("DW_WORKER_PUBLIC_WEB_URL", "DW_PUBLIC_WEB_URL"),
    )

    # --- Sales (DW1): the mailbox lane (ticket 16) ---
    # The one (tenant, workspace) DW1's mock mailbox is bound to, read the way
    # the API reads it (`ApiSettings.sales_demo_scope`): the same variables,
    # and locally the same first-login tenant and workspace. Two processes
    # bound to two different mailboxes would be a lane processing mail nobody
    # sees; `test_worker_sales_settings.py` holds the two readings together.
    sales_demo_tenant_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DW_WORKER_SALES_DEMO_TENANT_ID", "SALES_DEMO_TENANT_ID"),
    )
    sales_demo_workspace_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "DW_WORKER_SALES_DEMO_WORKSPACE_ID", "SALES_DEMO_WORKSPACE_ID"
        ),
    )
    default_tenant_id: str = Field(
        default="d6b43d0e-c3c6-5dbc-bc08-150621bd9a5d",
        validation_alias=AliasChoices("DW_WORKER_DEFAULT_TENANT_ID", "DW_API_DEFAULT_TENANT_ID"),
    )
    default_workspace_id: str = Field(
        default="64764894-718d-5558-ba17-9a2949214063",
        validation_alias=AliasChoices(
            "DW_WORKER_DEFAULT_WORKSPACE_ID", "DW_API_DEFAULT_WORKSPACE_ID"
        ),
    )
    # Whether this host runs the lane at all. On by default: DW1 processes
    # new mail on its own. Off is for a walk-through that presses "DW xử lý"
    # by hand on a mailbox the lane would otherwise empty within a minute
    # (`.claude/plans/sales/dw1-portal-demo/demo.md`). Whether DW1 works in a
    # workspace is its pause switch, not this.
    sales_inbox_lane: bool = Field(
        default=True, validation_alias=AliasChoices("DW_WORKER_SALES_INBOX_LANE")
    )

    # --- Sales: the malware scanner (ticket 25) ---
    # `clamd`: every attachment is scanned by the `clamav` compose service
    # before anything reads it. `skip`: files are handed over unscanned, for a
    # host-run local process that cannot reach a scanner publishing no port;
    # refused in a deployed profile (`dw_sales.adapters.clamd.malware_scanner`,
    # the one rule both processes read).
    sales_malware_scan: Literal["clamd", "skip"] = Field(
        default="clamd", validation_alias=AliasChoices("DW_SALES_MALWARE_SCAN")
    )
    sales_clamd_host: str = Field(
        default="clamav", validation_alias=AliasChoices("DW_SALES_CLAMD_HOST")
    )
    sales_clamd_port: int = Field(
        default=3310, validation_alias=AliasChoices("DW_SALES_CLAMD_PORT")
    )

    # --- Sales: the reader sandbox (ticket 25) ---
    # Every customer file is read by the `reader` compose service: over its
    # Unix socket where this container mounts it (compose fixes the path),
    # else over the loopback gateway a host-run local process reaches
    # (`reader-gateway`, profile `infra`).
    sales_reader_socket: str | None = Field(
        default=None, validation_alias=AliasChoices("DW_SALES_READER_SOCKET")
    )
    sales_reader_url: str = Field(
        default="http://127.0.0.1:8120", validation_alias=AliasChoices("DW_SALES_READER_URL")
    )
    # `sandbox` reads there. `in_process` reads in this process, with no
    # containment: for a host-run local worker without the reader image only,
    # refused in a deployed profile (here, and where it is built,
    # `dw_worker.main.sales_reader`). The API has no such switch: it imports
    # no reader at all (an import-linter contract).
    sales_reader: Literal["sandbox", "in_process"] = Field(
        default="sandbox", validation_alias=AliasChoices("DW_SALES_READER")
    )

    def sales_demo_scope(self) -> tuple[uuid.UUID, uuid.UUID] | None:
        """The one (tenant, workspace) DW1's mocks stand in for, or None.

        Named explicitly, it is that pair in any profile. Unnamed, a deployed
        profile has none (the mocks are not wired), and local/test fall back to
        the first-login tenant and workspace, where the demo personas live.
        """
        if self.sales_demo_tenant_id is not None:
            if self.sales_demo_workspace_id is None:
                raise RuntimeError("SALES_DEMO_TENANT_ID needs SALES_DEMO_WORKSPACE_ID beside it")
            return uuid.UUID(self.sales_demo_tenant_id), uuid.UUID(self.sales_demo_workspace_id)
        if self.is_deployed:
            return None
        return uuid.UUID(self.default_tenant_id), uuid.UUID(self.default_workspace_id)

    @property
    def zalo_poll_enabled(self) -> bool:
        """Poll only with a token to poll with and a secret to verify with."""
        return (
            self.zalo_updates_mode == "poll"
            and bool(self.zalo_bot_token.get_secret_value())
            and bool(self.zalo_link_secret.get_secret_value())
        )

    @property
    def zalo_webhook_drain_enabled(self) -> bool:
        """Drain what the API's webhook queued: webhook mode, never with the
        poll lane, and with the same token and secret the poll lane needs."""
        return (
            self.zalo_updates_mode == "webhook"
            and bool(self.zalo_bot_token.get_secret_value())
            and bool(self.zalo_link_secret.get_secret_value())
        )

    @property
    def zalo_send_enabled(self) -> bool:
        """Send through the bot whenever there is a token to send with, polled
        or webhooked: a webhook host's notifications go out the same way."""
        return bool(self.zalo_bot_token.get_secret_value())

    @model_validator(mode="after")
    def _the_heartbeat_outruns_the_lease(self) -> WorkerSettings:
        """Caught at startup, because the failure mode is a silent double bill.

        The job budget used to be capped by the lease, which capped every upload
        at the shortest lease anybody would wait out - and a customer meeting
        runs three or four hours. The consumer now renews the lease while it
        works, so the budget is free and this is the invariant that replaces it:
        a heartbeat slower than the lease renews nothing. The lease lapses
        between beats, a second worker claims a job the first is still running,
        and the same file is parsed and transcribed twice - both writes landing
        on the same deterministic document id, so nothing downstream looks wrong.
        """
        if self.ingest_heartbeat_seconds >= self.ingest_lease_seconds:
            raise RuntimeError(
                "DW_WORKER_INGEST_HEARTBEAT_SECONDS must be shorter than "
                "DW_WORKER_INGEST_LEASE_SECONDS"
            )
        return self

    @property
    def is_deployed(self) -> bool:
        """True for profiles real people's data flows through."""
        return self.profile in DEPLOYED_PROFILES

    def validate_for_profile(self) -> None:
        """Fail fast on configurations that must never reach a deployed profile."""
        if not self.is_deployed:
            return
        if not self.database_url:
            raise RuntimeError(f"a database is required in the {self.profile} profile")
        if self.sales_malware_scan == "skip" and self.sales_demo_scope() is not None:
            raise RuntimeError(
                f"unscanned attachments are forbidden in the {self.profile} profile:"
                " DW_SALES_MALWARE_SCAN=skip"
            )
        if self.sales_reader == "in_process" and self.sales_demo_scope() is not None:
            raise RuntimeError(
                "reading attachments outside the reader sandbox is forbidden in the "
                f"{self.profile} profile: DW_SALES_READER=in_process"
            )
        if self.embedding_provider == "hash":
            raise RuntimeError(
                "the hash embedding provider carries no meaning and is forbidden in the "
                f"{self.profile} profile - configure 'openai_compatible'"
            )
        if not self.qdrant_url:
            raise RuntimeError(
                f"a vector store is required in the {self.profile} profile - "
                "the in-memory index is not durable"
            )
