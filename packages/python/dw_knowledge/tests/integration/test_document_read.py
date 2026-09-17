"""Reading one attachment end to end, and the four ways that read is refused.

`search` has always been the only way into a document's text, and it answers
"which passages bear on this question". Minutes are drawn from the other
question - what the file says - so the gateway now answers it directly. This
pins the part no fake can: the SQL that decides whether the caller may have it,
and what a document too long to return looks like.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest

from dw_knowledge.gateway import IngestDocumentCommand, KnowledgeGateway
from dw_platform.application.access_context import AccessContext

pytestmark = pytest.mark.integration

TENANT = uuid.UUID(int=0xDD00)
WORKSPACE = uuid.UUID(int=0xDD01)
OTHER_WORKSPACE = uuid.UUID(int=0xDD02)
OTHER_TENANT = uuid.UUID(int=0xDD03)
DOMAIN = "crm_attachment"

ContextFactory = Callable[..., AccessContext]

_TURN = """## Người nói {n}

Ý kiến thứ {n} về ngân sách công nghệ thông tin của dự án trong năm nay, viết
đủ dài để đoạn này không bị gộp vào đoạn kế tiếp khi tài liệu được chia nhỏ, và
để cả bản ghi vượt quá một đoạn duy nhất.

"""

TRANSCRIPT = "".join(_TURN.format(n=n) for n in range(1, 13))


def _transcript(identity: str, **overrides: object) -> IngestDocumentCommand:
    """One transcript, under an identity of this test's own.

    `doc_key` is derived from tenant, workspace, domain, title and identity, and
    a second ingest under the same key updates the row it finds rather than
    writing a new one. Sharing a title across tests here meant a test asserting
    on the document it had just ingested was handed the previous test's.
    """
    fields: dict[str, object] = {
        "title": "bien-ban-hop-19-08.txt",
        "identity_key": identity,
        "content": TRANSCRIPT,
        "domain": DOMAIN,
    }
    fields.update(overrides)
    return IngestDocumentCommand(**fields)


async def test_a_document_comes_back_whole_and_in_the_order_it_was_written(
    gateway: KnowledgeGateway, make_context: ContextFactory
) -> None:
    context = make_context(TENANT, WORKSPACE)
    ingested = await gateway.ingest_document(_transcript("whole"), context)

    found = await gateway.read_document(ingested.document_id, context)

    assert found is not None
    assert found.truncated is False
    assert found.title == "bien-ban-hop-19-08.txt"
    # Every turn is present, and turn 12 comes after turn 1: chunks are joined
    # by `seq`, and a transcript reassembled out of order is a different meeting.
    assert "Người nói 1" in found.text and "Người nói 12" in found.text
    assert found.text.index("Người nói 1") < found.text.index("Người nói 12")


async def test_a_document_too_long_to_return_says_so(
    gateway: KnowledgeGateway, make_context: ContextFactory
) -> None:
    """The ceiling is reported, not applied in silence.

    A transcript cut in half still reads like a transcript. Minutes drawn from
    one would be wrong about what the meeting decided, and nothing downstream
    could tell - which is why `truncated` exists at all.
    """
    context = make_context(TENANT, WORKSPACE)
    ingested = await gateway.ingest_document(_transcript("truncated"), context)

    whole = await gateway.read_document(ingested.document_id, context)
    assert whole is not None
    cut = await gateway.read_document(ingested.document_id, context, max_chars=len(whole.text) // 3)

    assert cut is not None
    assert cut.truncated is True
    assert cut.chunk_count < whole.chunk_count
    assert len(cut.text) < len(whole.text)


async def test_another_workspace_in_the_same_tenant_cannot_read_it(
    gateway: KnowledgeGateway, make_context: ContextFactory
) -> None:
    owner = make_context(TENANT, WORKSPACE)
    ingested = await gateway.ingest_document(_transcript("other-workspace"), owner)

    assert (
        await gateway.read_document(ingested.document_id, make_context(TENANT, OTHER_WORKSPACE))
        is None
    )


async def test_another_tenant_cannot_read_it(
    gateway: KnowledgeGateway, make_context: ContextFactory
) -> None:
    owner = make_context(TENANT, WORKSPACE)
    ingested = await gateway.ingest_document(_transcript("other-tenant"), owner)

    assert (
        await gateway.read_document(ingested.document_id, make_context(OTHER_TENANT, WORKSPACE))
        is None
    )


async def test_a_clearance_below_the_document_cannot_read_it(
    gateway: KnowledgeGateway, make_context: ContextFactory
) -> None:
    """Search has always applied clearance; a second door onto the same text
    that did not would be a way around it."""
    owner = make_context(TENANT, WORKSPACE, clearance="restricted")
    ingested = await gateway.ingest_document(
        _transcript("clearance", classification="restricted"), owner
    )

    assert (
        await gateway.read_document(ingested.document_id, make_context(TENANT, WORKSPACE)) is None
    )


async def test_an_acl_the_caller_does_not_hold_cannot_read_it(
    gateway: KnowledgeGateway, make_context: ContextFactory
) -> None:
    context = make_context(TENANT, WORKSPACE)
    ingested = await gateway.ingest_document(
        _transcript("acl", acl_principals=("role:finance",)), context
    )

    assert await gateway.read_document(ingested.document_id, context) is None
