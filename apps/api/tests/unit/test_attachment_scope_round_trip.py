"""The scope written at upload is the scope every reader looks for.

This string has two ends in two processes. The API stamps it onto the ingest job;
the worker reads it back to learn which lead a finished file belongs to, and the
scorer's tool rebuilds it to search. A mismatch does not raise anywhere - it
reads as "this lead has no files", which is the one answer that looks like a fact
instead of a bug.

The format itself is tested in dw_knowledge. What is tested here is the join: the
adapter that writes it, and the parser the far end runs, agreeing about one
uploaded file.
"""

from __future__ import annotations

import pathlib
import uuid
from dataclasses import dataclass, field

import pytest

from dw_api.adapters.document_indexing import KnowledgeDocumentIndexingAdapter
from dw_knowledge.attachment_policy import load_attachment_policy
from dw_knowledge.attachments import ATTACHMENT_DOMAIN, parse_attachment_scope
from dw_knowledge.ingest_jobs import EnqueueIngestCommand
from dw_platform.application.access_context import AccessContext

pytestmark = pytest.mark.unit

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
POLICY = REPO_ROOT / "configs" / "policies" / "attachment_ingest@1.1.0.yaml"

LEAD = uuid.uuid4()
DOCUMENT = uuid.uuid4()
CONTEXT = AccessContext(
    tenant_id=uuid.uuid4(),
    workspace_id=uuid.uuid4(),
    principal_id=uuid.uuid4(),
    roles=frozenset({"member"}),
    scopes=frozenset({"crm.write"}),
    clearance="internal",
    plan_id="professional",
)


@dataclass
class _RecordingJobs:
    queued: list[EnqueueIngestCommand] = field(default_factory=list)

    async def enqueue(
        self, command: EnqueueIngestCommand, context: AccessContext, *, storage_key: str
    ) -> uuid.UUID:
        self.queued.append(command)
        return uuid.uuid4()


async def _upload(filename: str, mime: str) -> tuple[_RecordingJobs, uuid.UUID | None]:
    jobs = _RecordingJobs()
    adapter = KnowledgeDocumentIndexingAdapter(
        jobs=jobs,  # type: ignore[arg-type]
        policy=load_attachment_policy(POLICY),
    )
    job_id = await adapter.enqueue(
        context=CONTEXT,
        document_id=DOCUMENT,
        scope_type="lead",
        scope_id=LEAD,
        account_id=None,
        filename=filename,
        mime=mime,
        storage_key=f"crm-documents/{LEAD}/{filename}",
    )
    return jobs, job_id


async def test_the_far_end_reads_back_the_lead_the_file_was_attached_to() -> None:
    jobs, _ = await _upload("bien-ban-hop-12-08.pdf", "application/pdf")

    queued = jobs.queued[0]
    assert queued.domain == ATTACHMENT_DOMAIN
    assert parse_attachment_scope(dict(queued.extra)["attachment_scope"]) == ("lead", LEAD)


async def test_the_document_id_travels_so_the_announcement_can_name_the_file() -> None:
    """The ingest lane has the job, not the CRM row; without this it could say
    only that some file finished."""
    jobs, _ = await _upload("bien-ban-hop-12-08.pdf", "application/pdf")

    assert jobs.queued[0].source_version == str(DOCUMENT)


async def test_a_file_the_parser_cannot_read_is_never_queued() -> None:
    """Which is also why it never wakes the scorer: there is no job to finish."""
    jobs, job_id = await _upload("ban-ve.dwg", "application/acad")

    assert jobs.queued == [] and job_id is None
