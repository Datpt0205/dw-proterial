"""The scope string has two ends, and a lookup that tells apart two silences.

`attachment_scope_of` is written onto every ingest job at the upload edge and
read back by every consumer that wants a record's files. The pair only works if
it round-trips, so that is pinned here rather than left to a comment asking two
apps to agree.

The second half is the distinction the callers actually depend on: a record with
no files and a record whose files do not answer the question both come back with
nothing to quote, and they call for different next moves.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from dw_knowledge.attachments import (
    ATTACHMENT_DOMAIN,
    AttachmentSearchService,
    attachment_scope_of,
    parse_attachment_scope,
)
from dw_knowledge.chunking import MAX_CHUNK_CHARS
from dw_knowledge.contracts import EvidenceChunk, EvidenceRef, SearchQuery
from dw_knowledge.gateway import DocumentInfo, DocumentText
from dw_platform.application.access_context import AccessContext

pytestmark = pytest.mark.unit

TENANT = uuid.uuid4()
WORKSPACE = uuid.uuid4()
LEAD = uuid.uuid4()
OTHER_LEAD = uuid.uuid4()
MINUTES_DOC = uuid.uuid4()

CONTEXT = AccessContext(
    tenant_id=TENANT,
    workspace_id=WORKSPACE,
    principal_id=uuid.uuid4(),
    roles=frozenset({"BD"}),
    scopes=frozenset({"lead_scoring.read"}),
    clearance="internal",
    plan_id="pro",
)


def _document(document_id: uuid.UUID, title: str, scope: str, domain: str) -> DocumentInfo:
    return DocumentInfo(
        document_id=document_id,
        title=title,
        domain=domain,
        classification="internal",
        source_version=str(document_id),
        index_version="1",
        chunk_count=3,
        created_at=datetime.now(UTC),
        extra={"attachment_scope": scope},
    )


def _chunk(document_id: uuid.UUID, content: str) -> EvidenceChunk:
    return EvidenceChunk(
        content=content,
        evidence=EvidenceRef(
            evidence_id=uuid.uuid4(),
            source_document_id=document_id,
            source_version=str(document_id),
            relevance_score=0.82,
            classification="internal",
            provenance_hash="a" * 64,
        ),
    )


@dataclass
class FakeGateway:
    """Records what it was asked, returns what it was told to."""

    hits: list[EvidenceChunk]
    documents: list[DocumentInfo]
    queries: list[SearchQuery] | None = None
    texts: dict[uuid.UUID, DocumentText] = field(default_factory=dict)
    read_calls: list[uuid.UUID] = field(default_factory=list)

    async def search(self, query: SearchQuery, context: AccessContext) -> list[EvidenceChunk]:
        if self.queries is None:
            self.queries = []
        self.queries.append(query)
        return self.hits

    async def list_documents(
        self, context: AccessContext, *, limit: int = 100, domain: str | None = None
    ) -> list[DocumentInfo]:
        return [doc for doc in self.documents if domain is None or doc.domain == domain]

    async def read_document(
        self, document_id: uuid.UUID, context: AccessContext, *, max_chars: int = 60_000
    ) -> DocumentText | None:
        self.read_calls.append(document_id)
        return self.texts.get(document_id)


def _service(hits: list[EvidenceChunk], documents: list[DocumentInfo]) -> AttachmentSearchService:
    return AttachmentSearchService(gateway=FakeGateway(hits=hits, documents=documents))  # type: ignore[arg-type]


def test_a_scope_written_at_upload_reads_back_as_the_record_it_named() -> None:
    scope = attachment_scope_of("lead", LEAD)
    assert parse_attachment_scope(scope) == ("lead", LEAD)


@pytest.mark.parametrize("value", ["", "lead", "lead:", ":123", "lead:not-a-uuid"])
def test_a_string_that_is_not_a_scope_is_reported_as_such_rather_than_raising(value: str) -> None:
    assert parse_attachment_scope(value) is None


async def test_the_search_is_narrowed_to_the_record_the_caller_named() -> None:
    gateway = FakeGateway(hits=[], documents=[])
    service = AttachmentSearchService(gateway=gateway)  # type: ignore[arg-type]

    await service.search(
        CONTEXT, scope_type="lead", scope_ref=LEAD, query="ngân sách CNTT", top_k=5
    )

    assert gateway.queries is not None
    sent = gateway.queries[0]
    assert sent.domain == ATTACHMENT_DOMAIN
    assert sent.filters == (("attachment_scope", f"lead:{LEAD}"),)


async def test_an_excerpt_carries_the_name_of_the_file_it_came_from() -> None:
    service = _service(
        hits=[_chunk(MINUTES_DOC, "ngân sách CNTT năm nay khoảng 20 tỷ")],
        documents=[
            _document(MINUTES_DOC, "bien-ban-hop-12-08.pdf", f"lead:{LEAD}", ATTACHMENT_DOMAIN)
        ],
    )

    found = await service.search(
        CONTEXT, scope_type="lead", scope_ref=LEAD, query="ngân sách", top_k=5
    )

    assert [(e.filename, e.excerpt) for e in found.excerpts] == [
        ("bien-ban-hop-12-08.pdf", "ngân sách CNTT năm nay khoảng 20 tỷ")
    ]


async def test_no_files_at_all_and_no_answer_in_the_files_are_told_apart() -> None:
    empty = await _service(hits=[], documents=[]).search(
        CONTEXT, scope_type="lead", scope_ref=LEAD, query="ngân sách", top_k=5
    )
    unanswered = await _service(
        hits=[],
        documents=[
            _document(MINUTES_DOC, "bien-ban-hop-12-08.pdf", f"lead:{LEAD}", ATTACHMENT_DOMAIN)
        ],
    ).search(CONTEXT, scope_type="lead", scope_ref=LEAD, query="ngân sách", top_k=5)

    assert empty.excerpts == () and empty.indexed_files == 0
    assert unanswered.excerpts == () and unanswered.indexed_files == 1


async def test_another_records_files_are_not_counted_as_this_records() -> None:
    """The listing is tenant-wide, so the scope filter has to be applied here too.

    Counting every attachment in the workspace would report "we searched 40
    files" to a lead that has none, which reads as "asked and answered".
    """
    service = _service(
        hits=[],
        documents=[
            _document(uuid.uuid4(), "khac.pdf", f"lead:{OTHER_LEAD}", ATTACHMENT_DOMAIN),
            _document(uuid.uuid4(), "ho-so-nganh.pdf", f"lead:{LEAD}", "research_profile"),
        ],
    )

    found = await service.search(
        CONTEXT, scope_type="lead", scope_ref=LEAD, query="ngân sách", top_k=5
    )

    assert found.indexed_files == 0


def _text(document_id: uuid.UUID, title: str, body: str) -> DocumentText:
    return DocumentText(
        document_id=document_id, title=title, text=body, chunk_count=2, truncated=False
    )


async def test_a_file_on_this_record_is_handed_back_whole() -> None:
    """What minutes are drawn from: the transcript, not the parts that matched.

    Search answers a question; this answers "what does the file say", and the
    two return different things from the same document on purpose.
    """
    gateway = FakeGateway(
        hits=[],
        documents=[
            _document(MINUTES_DOC, "bien-ban-hop-12-08.pdf", f"lead:{LEAD}", ATTACHMENT_DOMAIN)
        ],
        texts={MINUTES_DOC: _text(MINUTES_DOC, "bien-ban-hop-12-08.pdf", "## Người nói 1: chào")},
    )
    service = AttachmentSearchService(gateway=gateway)  # type: ignore[arg-type]

    found = await service.read(CONTEXT, scope_type="lead", scope_ref=LEAD, document_id=MINUTES_DOC)

    assert found is not None
    assert found.text == "## Người nói 1: chào"


async def test_a_file_belonging_to_another_record_is_refused_before_it_is_read() -> None:
    """The id is the one argument a model can be talked into supplying.

    A chunk this conversation is allowed to see can name a file it is not, and
    "read document X" would otherwise open any file in the workspace. The read
    itself never happens - that is the assertion, not an implementation detail:
    refusing after reading is not refusing.
    """
    other_file = uuid.uuid4()
    gateway = FakeGateway(
        hits=[],
        documents=[
            _document(other_file, "khac.pdf", f"lead:{OTHER_LEAD}", ATTACHMENT_DOMAIN),
        ],
        texts={other_file: _text(other_file, "khac.pdf", "bí mật của hồ sơ khác")},
    )
    service = AttachmentSearchService(gateway=gateway)  # type: ignore[arg-type]

    found = await service.read(CONTEXT, scope_type="lead", scope_ref=LEAD, document_id=other_file)

    assert found is None
    assert gateway.read_calls == []


async def test_a_long_hit_reaches_the_caller_with_its_last_sentence_still_on_it() -> None:
    """The figure a scorer is looking for is as likely to be at the end.

    A leaf chunk is the retrieval unit and runs up to `MAX_CHUNK_CHARS`. Cutting
    it shorter here returned a hit that search had matched on words the reader
    could no longer see: a set of minutes whose budget line sat past character
    700 came back looking like minutes that never mention a budget.
    """
    tail = "HĐQT đã phê duyệt ngân sách 18 tỷ VND cho dự án chuyển đổi số."
    body = "Biên bản họp. " * 70 + tail
    assert len(body) > 700, "the passage has to outrun the old ceiling to prove anything"
    assert len(body) <= MAX_CHUNK_CHARS

    service = _service(
        hits=[_chunk(MINUTES_DOC, body)],
        documents=[
            _document(MINUTES_DOC, "bien-ban-hop-12-08.pdf", f"lead:{LEAD}", ATTACHMENT_DOMAIN)
        ],
    )

    found = await service.search(
        CONTEXT, scope_type="lead", scope_ref=LEAD, query="ngân sách", top_k=5
    )

    assert found.excerpts[0].excerpt.endswith(tail)
