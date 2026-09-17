"""Two records, one filename: the data-loss case, end to end.

The unit tests pin the id arithmetic. This one proves what the arithmetic causes
against a real database and a real index - that the first document's chunks and
vectors survive the second ingest, which is the part no amount of id comparison
can demonstrate.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest

from dw_knowledge.contracts import SearchQuery
from dw_knowledge.gateway import IngestDocumentCommand, KnowledgeGateway
from dw_platform.application.access_context import AccessContext

pytestmark = pytest.mark.integration

TENANT = uuid.UUID(int=0xCC00)
WORKSPACE = uuid.UUID(int=0xCC01)
DOMAIN = "crm_attachment"

ContextFactory = Callable[..., AccessContext]

ACCOUNT_QUOTE = "Báo giá cho Công ty Alpha: đơn giá 120 triệu đồng cho mỗi giấy phép."
OPPORTUNITY_QUOTE = "Báo giá cho Công ty Beta: đơn giá 95 triệu đồng cho mỗi giấy phép."


def _attachment(identity_key: str, content: str) -> IngestDocumentCommand:
    """Same filename as a title, different owner as an identity."""
    return IngestDocumentCommand(
        title="bao-gia.pdf",
        identity_key=identity_key,
        content=content,
        domain=DOMAIN,
    )


async def _retrieved(
    gateway: KnowledgeGateway, context: AccessContext
) -> tuple[set[uuid.UUID], str]:
    """Everything this caller can reach in the domain, ids and text.

    Deliberately not asserting on rank: these tests run on the deterministic
    hash embedding, whose similarity is arbitrary, so what a query returns FIRST
    proves nothing. What is present at all is the property under test.
    """
    hits = await gateway.search(
        SearchQuery(text="báo giá đơn giá", domain=DOMAIN, top_k=50), context
    )
    return {hit.evidence.source_document_id for hit in hits}, " ".join(hit.content for hit in hits)


async def test_two_records_can_hold_a_same_named_file(
    gateway: KnowledgeGateway, make_context: ContextFactory
) -> None:
    context = make_context(TENANT, WORKSPACE)

    first = await gateway.ingest_document(
        _attachment("account:1111:bao-gia.pdf", ACCOUNT_QUOTE), context
    )
    second = await gateway.ingest_document(
        _attachment("opportunity:2222:bao-gia.pdf", OPPORTUNITY_QUOTE), context
    )
    assert first.document_id != second.document_id

    # The older document is the one that used to disappear: its row was
    # overwritten, its chunks deleted and its points dropped by the second
    # ingest, with no error and nothing in the timeline.
    document_ids, text = await _retrieved(gateway, context)
    assert {first.document_id, second.document_id} <= document_ids
    assert "120 triệu" in text, "the first attachment must survive the second"
    assert "95 triệu" in text


async def test_re_uploading_the_same_file_still_replaces_it(
    gateway: KnowledgeGateway, make_context: ContextFactory
) -> None:
    """Separating identity from the title must not cost idempotent re-ingest.

    Attaching a corrected file to the same record is an update, not a second
    document - the point of a deterministic id in the first place.
    """
    context = make_context(TENANT, WORKSPACE)
    identity = "account:3333:bao-gia.pdf"

    original = await gateway.ingest_document(
        _attachment(identity, "Báo giá cũ: đơn giá 200 triệu đồng."), context
    )
    corrected = await gateway.ingest_document(
        _attachment(identity, "Báo giá sửa: đơn giá 180 triệu đồng."), context
    )
    assert original.document_id == corrected.document_id

    document_ids, text = await _retrieved(gateway, context)
    assert document_ids == {original.document_id}, "one record, one document"
    assert "180 triệu" in text, "the corrected content must be retrievable"
    assert "200 triệu" not in text, "the replaced content must not stay retrievable"


async def test_a_document_without_an_identity_key_keeps_its_old_behaviour(
    gateway: KnowledgeGateway, make_context: ContextFactory
) -> None:
    """The curated corpus still treats a shared title as one document."""
    context = make_context(TENANT, WORKSPACE)

    first = await gateway.ingest_document(
        IngestDocumentCommand(title="Quy chế mua sắm", content="Bản cũ: hạn mức 300 triệu."),
        context,
    )
    second = await gateway.ingest_document(
        IngestDocumentCommand(title="Quy chế mua sắm", content="Bản mới: hạn mức 500 triệu."),
        context,
    )
    assert first.document_id == second.document_id
