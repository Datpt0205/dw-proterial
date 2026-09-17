"""Queue a CRM document for retrieval indexing.

The composition root is the only place the two contexts meet: the owning context
declares `DocumentIndexingPort` in primitives and never learns what a knowledge
document or a vector is, and `dw_knowledge` never learns what a CRM record is.

Everything the retrieval side needs to answer "which record does this file
belong to?" is decided here, once:

- `identity_key` carries the owning record, so two records holding a file of the
  same name stay two documents (see dw_knowledge.identity).
- `attachment_scope` is the filter every reader narrows by, built server-side
  from the record's own identity so no model ever names one. Its format lives in
  `dw_knowledge.attachments`, which is also where the readers get it from - the
  two ends of one string, defined once.
- `account_id` is set when the record IS an account, so an account-scoped
  conversation can reach it. It is deliberately left unset for leads and
  opportunities: this adapter would have to query the CRM to resolve an owner,
  and a wrong answer here is a file answering in the wrong conversation.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from dw_knowledge.attachment_policy import AttachmentPolicy
from dw_knowledge.attachments import ATTACHMENT_DOMAIN, attachment_scope_of
from dw_knowledge.ingest_jobs import EnqueueIngestCommand, IngestJobStore
from dw_platform.application.access_context import AccessContext

__all__ = ["ATTACHMENT_DOMAIN", "KnowledgeDocumentIndexingAdapter", "attachment_scope_of"]


@dataclass(frozen=True)
class KnowledgeDocumentIndexingAdapter:
    """Implements ``DocumentIndexingPort`` over the knowledge ingest queue."""

    jobs: IngestJobStore
    policy: AttachmentPolicy

    async def enqueue(
        self,
        *,
        context: AccessContext,
        document_id: uuid.UUID,
        scope_type: str,
        scope_id: uuid.UUID,
        account_id: uuid.UUID | None,
        filename: str,
        mime: str,
        storage_key: str,
    ) -> uuid.UUID | None:
        # Formats the parse layer cannot read are not queued: a job that can only
        # fail is noise in the status list, and the upload itself is still fine.
        if self.policy.kind_of(filename) is None:
            return None

        extra: list[tuple[str, str]] = [
            ("attachment_scope", attachment_scope_of(scope_type, scope_id)),
            ("source_type", scope_type),
        ]
        if account_id is not None:
            extra.append(("account_id", str(account_id)))

        return await self.jobs.enqueue(
            EnqueueIngestCommand(
                title=filename,
                # The record owns the identity; the filename is only its name.
                identity_key=f"{scope_type}:{scope_id}:{filename}",
                filename=filename,
                content_type=mime,
                domain=ATTACHMENT_DOMAIN,
                # Re-uploading the same name to the same record supersedes the
                # previous version rather than accumulating duplicates.
                source_version=str(document_id),
                extra=tuple(extra),
            ),
            context,
            storage_key=storage_key,
        )

    async def jobs_for(
        self, document_ids: Sequence[uuid.UUID], context: AccessContext
    ) -> dict[uuid.UUID, uuid.UUID]:
        """Which ingest job read each of these documents, if any.

        The join is `source_version`: `enqueue` above stamps the document id
        there so a re-upload of the same filename supersedes rather than
        duplicates. That makes it the one column pointing back at the record,
        and reading it here is what lets a file row say "read" or "could not be
        read" after a page reload.
        """
        found = await self.jobs.latest_for_sources([str(item) for item in document_ids], context)
        return {uuid.UUID(source): job_id for source, job_id in found.items()}
