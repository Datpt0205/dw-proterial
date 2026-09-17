"""Deterministic ids for documents/chunks → idempotent re-ingest & upsert.

Same logical document always maps to the same ``document_id``; each chunk to the
same ``chunk_id`` = uuid5(doc, index, seq). Re-ingesting therefore OVERWRITES the
same Postgres rows and Qdrant points instead of creating duplicates — this is how
we "find the exact chunk again" on update.

What makes a document "the same" is its ``identity_key``, and when a caller does
not supply one it falls back to the title. That fallback is what every document
ingested before this parameter existed relies on, so it must stay.

A title is a fine identity for a corpus a human curates, where two documents
called the same thing ARE the same thing. It is a bad one for files users upload
against their own records: two people attaching "bao-gia.pdf" to two different
accounts are not describing one document, but a title-keyed id says they are, and
the second ingest then overwrites the first — same tenant, so no isolation test
would ever catch it. Such callers pass an identity_key that includes whatever
they consider the owner.
"""

from __future__ import annotations

import uuid

# Stable namespace for the knowledge plane (do not change — ids depend on it).
NAMESPACE = uuid.UUID("b6d1e6a2-3c4f-5a70-9b21-000000000d20")


def _identity(title: str, identity_key: str | None) -> str:
    return (identity_key or title).strip()


def document_id_for(
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    domain: str,
    title: str,
    source_version: str,
    scope: str = "tenant",
    identity_key: str | None = None,
) -> uuid.UUID:
    name = _identity(title, identity_key)
    key = f"doc:{scope}:{tenant_id}:{workspace_id}:{domain}:{name}:{source_version}"
    if scope == "global":
        # Global (e.g. legal) docs are identity-independent of the ingesting tenant.
        key = f"doc:global:{domain}:{name}:{source_version}"
    return uuid.uuid5(NAMESPACE, key)


def doc_key_for(
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    domain: str,
    title: str,
    scope: str = "tenant",
    identity_key: str | None = None,
) -> uuid.UUID:
    """Version-independent logical key: groups all versions of the same document
    so a new version can supersede the previous current one.

    It deliberately excludes ``source_version``, which is why passing a distinct
    version is NOT a way to avoid a collision: two documents sharing an identity
    still share a doc_key, and the newer one supersedes the older.
    """
    name = _identity(title, identity_key)
    if scope == "global":
        return uuid.uuid5(NAMESPACE, f"dockey:global:{domain}:{name}")
    return uuid.uuid5(NAMESPACE, f"dockey:{tenant_id}:{workspace_id}:{domain}:{name}")


def chunk_id_for(*, document_id: uuid.UUID, index_version: str, seq: int) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"chunk:{document_id}:{index_version}:{seq}")
