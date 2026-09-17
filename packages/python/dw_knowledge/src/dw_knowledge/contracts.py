"""Evidence and retrieval contracts.

``SearchQuery`` deliberately has NO tenant/workspace/ACL fields: callers cannot
supply them. The retrieval gateway injects mandatory filters from the trusted
``AccessContext`` — that asymmetry is the security boundary.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Classification = str  # "internal" | "confidential" | "restricted" (validated by policy)

# The domain a document carries when it belongs to no particular corpus, and the
# domain a search names when it wants that common pool. It is NOT a wildcard:
# searching "shared" reads shared documents, not every domain. The adapters used
# to skip the domain condition entirely for this value, which quietly turned the
# default query into "read everything this tenant owns".
SHARED_DOMAIN = "shared"

# The vector collection the gateway reads and writes. Here rather than beside
# the Qdrant adapter because composition roots need the default without pulling
# the vector SDK into their settings module - the adapter itself is imported
# lazily so an app that never retrieves does not need it installed.
#
# A collection's vector width is fixed when it is created, so moving to another
# embedding model means naming a new collection, not editing this one.
DEFAULT_COLLECTION = "dw_knowledge"

# Business metadata a caller may narrow a search by. A closed list, because an
# open one would let a caller name a security field: asking to filter on
# `tenant_id` or `acl_principals` looks like narrowing but lands in the same
# query clause the gateway uses to enforce isolation. Adding a key here is a
# deliberate act; anything absent raises rather than being ignored, so a typo
# fails loudly instead of silently widening the result set.
SEARCH_FILTER_KEYS: frozenset[str] = frozenset(
    {
        "account_id",  # everything intel writes is scoped to one account
        # "{record_type}:{uuid}" — the record a user attached a file to. One
        # string rather than a type/id pair, because a two-key filter can be
        # half-satisfied by a caller that forgets one of them.
        "attachment_scope",
        "source_type",  # web_page | pdf | news_article | facebook_post | ...
        "record_type",  # derived records: research_narrative | tender_summary | ...
        "channel_id",  # which collection channel produced it
        "url_hash",  # exact source page
        "lang",
        "section_key",  # research profile section
        "metric_code",  # financial fact
        "filter_tag",  # tender notice type
        "tender_id",  # the `tenders` row a package document was rendered from
    }
)


class EvidenceRef(BaseModel):
    """Provenance-carrying reference to a chunk of source material (§13.4)."""

    model_config = ConfigDict(frozen=True)

    evidence_id: UUID
    source_document_id: UUID
    source_version: str
    chunk_id: UUID | None = None
    page: int | None = Field(default=None, ge=1)
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    quote: str | None = None
    relevance_score: float = Field(ge=0.0, le=1.0)
    classification: Classification
    provenance_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class SearchQuery(BaseModel):
    """Caller-controllable part of a retrieval request.

    Tenant, workspace and ACL constraints are intentionally absent — the
    knowledge gateway derives them from ``AccessContext`` and callers (including
    model output) can never override them.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1)
    domain: str = "shared"
    top_k: int = Field(default=8, ge=1, le=50)
    document_ids: tuple[UUID, ...] = ()
    min_relevance: float = Field(default=0.0, ge=0.0, le=1.0)
    # Business-metadata narrowing, e.g. (("account_id", "..."),). Applied as
    # ADDITIONAL constraints on top of the trusted filter - they can only ever
    # remove results, never reach a document the caller could not already see.
    filters: tuple[tuple[str, str], ...] = ()

    @field_validator("filters")
    @classmethod
    def _keys_are_whitelisted(
        cls, value: tuple[tuple[str, str], ...]
    ) -> tuple[tuple[str, str], ...]:
        unknown = sorted({key for key, _ in value} - SEARCH_FILTER_KEYS)
        if unknown:
            raise ValueError(
                f"unknown search filter key(s): {unknown}. Allowed: {sorted(SEARCH_FILTER_KEYS)}"
            )
        return value


class EvidenceChunk(BaseModel):
    """A retrieved chunk plus its evidence reference."""

    model_config = ConfigDict(frozen=True)

    content: str
    evidence: EvidenceRef
