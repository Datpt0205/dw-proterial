"""Finding the files a user attached to one CRM record.

The scope string is one format with two ends: the API writes it onto every
ingest job, and every reader narrows by it. Those two ends used to live in two
different apps that cannot import each other, held in step by a comment asking
them to agree — which works until a third reader appears. It has: the lead
scorer now reads a lead's meeting records, so the vocabulary moves here, where
both ends can share one definition.

What this module is NOT is a second retrieval path. Every search still goes
through ``KnowledgeGateway.search``, which derives tenant, workspace, clearance
and ACL from the verified context; ``attachment_scope`` is a business filter on
top, so it can only ever narrow what the caller could already see.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from dw_kernel.pagination import PageQuery, PageRequest
from dw_knowledge.chunking import MAX_CHUNK_CHARS
from dw_knowledge.contracts import SearchQuery
from dw_knowledge.gateway import DocumentText, KnowledgeGateway
from dw_platform.application.access_context import AccessContext

# Attachments live in their own domain so a search that names no domain cannot
# reach them: "shared" is the common pool, not a wildcard.
ATTACHMENT_DOMAIN = "crm_attachment"

# How much of a hit travels back to a caller: the whole leaf chunk, never part
# of one. This was 700 against a 1200-char chunk ceiling, which silently cut the
# tail off every long hit - a meeting record whose budget line sat at offset 942
# came back matched and with the figure removed, and the scorer that asked for
# it wrote "the minutes do not state a budget". Search decided the chunk was the
# answer; shortening it here overrules that decision with a number that knows
# nothing about the text.
EXCERPT_CHARS = MAX_CHUNK_CHARS

# One listing covers the files on a single record; nobody attaches more.
_DOCUMENT_LISTING_LIMIT = 200


def attachment_scope_of(scope_type: str, scope_id: uuid.UUID) -> str:
    """One string, not a pair.

    A two-key filter can be half-satisfied by a caller that forgets one of them;
    a single value either matches the record or it does not.
    """
    return f"{scope_type}:{scope_id}"


def parse_attachment_scope(value: str) -> tuple[str, uuid.UUID] | None:
    """Read the scope back, or None if this is not one.

    Returning None rather than raising: the caller asking is a consumer walking
    past every kind of ingest job, and "not an attachment" is the ordinary
    answer, not a fault.
    """
    record_type, _, raw_id = value.partition(":")
    if not record_type or not raw_id:
        return None
    try:
        return record_type, uuid.UUID(raw_id)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class AttachmentExcerpt:
    filename: str
    excerpt: str
    relevance: float


@dataclass(frozen=True, slots=True)
class AttachmentLookup:
    excerpts: tuple[AttachmentExcerpt, ...]
    # Told apart on purpose: "this record has no files" and "its files do not
    # answer this" lead to different next moves, and a caller given only an
    # empty list has to guess which one it is.
    indexed_files: int


@dataclass(frozen=True)
class AttachmentSearchService:
    """Reads the files on one record. The record comes from the caller, always.

    No overload takes a scope from model output — a consumer resolves the record
    from its own trusted state (a conversation's scope, a scoring run's lead)
    before it gets here.
    """

    gateway: KnowledgeGateway
    excerpt_chars: int = EXCERPT_CHARS

    async def search(
        self,
        context: AccessContext,
        *,
        scope_type: str,
        scope_ref: uuid.UUID,
        query: str,
        top_k: int,
    ) -> AttachmentLookup:
        evidence = await self.gateway.search(
            SearchQuery(
                text=query,
                domain=ATTACHMENT_DOMAIN,
                top_k=top_k,
                filters=(("attachment_scope", attachment_scope_of(scope_type, scope_ref)),),
            ),
            context,
        )
        titles = await self.titles(context, scope_type=scope_type, scope_ref=scope_ref)
        by_document = {str(document_id): title for document_id, title in titles.items()}
        return AttachmentLookup(
            excerpts=tuple(
                AttachmentExcerpt(
                    filename=by_document.get(
                        str(chunk.evidence.source_document_id), "tệp đính kèm"
                    ),
                    excerpt=chunk.content[: self.excerpt_chars],
                    relevance=chunk.evidence.relevance_score,
                )
                for chunk in evidence
            ),
            indexed_files=len(titles),
        )

    async def titles(
        self, context: AccessContext, *, scope_type: str, scope_ref: uuid.UUID
    ) -> dict[uuid.UUID, str]:
        """Indexed files for this record, by document id.

        Read from Postgres rather than from the vector payload: a file whose
        ingest failed has no points at all, and "how many files are searchable"
        has to be answerable without finding any.
        """
        wanted = attachment_scope_of(scope_type, scope_ref)
        # Narrowed to attachments in SQL: the listing window is shared with
        # the research lanes' pages, which outnumber uploads a thousand to one.
        #
        # One page, deliberately: this is the bounded set of files on a single
        # record, not a listing a caller walks. The cursor is unused, so the
        # query identity is only a label.
        page = await self.gateway.list_documents(
            context,
            PageRequest(
                limit=_DOCUMENT_LISTING_LIMIT,
                after=None,
                query=PageQuery(key="knowledge.attachments"),
            ),
            domain=ATTACHMENT_DOMAIN,
        )
        return {
            document.document_id: document.title
            for document in page.items
            if document.domain == ATTACHMENT_DOMAIN
            and document.extra.get("attachment_scope") == wanted
        }

    async def read(
        self,
        context: AccessContext,
        *,
        scope_type: str,
        scope_ref: uuid.UUID,
        document_id: uuid.UUID,
    ) -> DocumentText | None:
        """One of this record's files, whole. ``None`` if it is not one of them.

        The document id is the one argument here a caller can be talked into
        supplying - a model reads a filename in a chunk and asks for it by id.
        So it is checked against this record's own listing before anything is
        read: a file the user can see on another record is still not a file
        this conversation may open.
        """
        listed = await self.titles(context, scope_type=scope_type, scope_ref=scope_ref)
        if document_id not in listed:
            return None
        return await self.gateway.read_document(document_id, context)
