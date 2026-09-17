"""Keyset pagination: the one page shape every list endpoint returns.

A list endpoint that takes only ``limit`` hands a client the first page and
nothing after it. The obvious repair is ``OFFSET``, and it is wrong twice over.
Skipping N rows costs the database a scan of those N rows, so page 500 costs
five hundred pages of work; and a row inserted while a client is paging shifts
every later page down by one, so a record slides across the boundary the client
has already passed and is never returned at all. Both failures grow with the
tenant's data, which is to say they arrive first on the largest customer.

Keyset pagination remembers *where* the previous page ended — the sort key plus
the row id that breaks ties — and asks for rows strictly beyond that point. The
database seeks to the position through an index instead of counting to it, and
an insert elsewhere in the table cannot move a boundary that is expressed as a
value rather than as a count.

The cursor is deliberately opaque: a base64url blob, not a number. A client that
can compute "page 7" will, and from that moment the page size, the sort column
and the ordering are all part of the contract we have to keep forever. It also
carries a fingerprint of the query it was issued for, so a cursor replayed
against different filters is refused instead of quietly answering from a window
that does not describe it.

The encoding is *not* signed, and that is deliberate rather than an oversight.
Anyone can base64-decode a cursor and edit it; all that buys them is a different
window into a result set they are already authorized to read, because every
query still runs under the caller's verified tenant context and RLS. Signing
would require a secret, and the kernel has no configuration by design.
"""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from dw_kernel.errors import DomainError

# What a caller gets when it does not ask, and the most it may ask for. The
# ceiling exists so one client cannot turn a paged endpoint back into a full
# table scan by requesting every row in a single page.
DEFAULT_PAGE_SIZE: Final = 50
MAX_PAGE_SIZE: Final = 200

# Bumped only when the encoded payload changes shape. A cursor carrying any
# other version is refused rather than guessed at, which is what stops a client's
# in-flight cursor from being reinterpreted under new rules after a deploy.
_CURSOR_FORMAT_VERSION: Final = 1

# 64 bits of query fingerprint. This detects an honest mistake — a cursor
# replayed against a different filter or a different endpoint — rather than
# resisting an attacker, and eight bytes keep the cursor short enough to sit
# comfortably in a URL.
_FINGERPRINT_BYTES: Final = 8


class InvalidCursorError(DomainError):
    """The cursor is unreadable, or was issued for a different query.

    A ``DomainError`` because it is bad client input and maps onto the existing
    ``validation_failed`` code; a distinct type because a caller that wants to
    restart the listing from the beginning needs to tell this apart from every
    other validation failure.
    """


@dataclass(frozen=True)
class PageQuery:
    """The identity of the query a cursor belongs to.

    ``key`` names the endpoint. An endpoint's sort order is fixed, so the name
    implies the ordering and the ordering never has to be spelled out twice.
    ``filters`` carries the values that narrow the listing.

    A cursor encodes a fingerprint of both, so one taken from a different
    endpoint — or from the same endpoint with a different filter — is refused
    rather than applied to a window it does not describe. Anything a caller can
    vary that changes which rows come back, including a sort direction an
    endpoint chooses to offer, belongs in ``filters``.
    """

    key: str
    filters: Mapping[str, object] = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        """A short, stable digest of this query's identity.

        Values are stringified rather than serialized structurally: the digest
        only has to be equal for equal queries and different for different ones,
        and stringifying keeps a UUID filter from depending on whether the route
        happened to pass the object or its text.
        """
        canonical = json.dumps(
            [self.key, {key: str(value) for key, value in sorted(self.filters.items())}],
            separators=(",", ":"),
        )
        digest = hashlib.blake2b(canonical.encode("utf-8"), digest_size=_FINGERPRINT_BYTES)
        return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class CursorPosition:
    """The exact row a page ended on: the sort key, plus the id breaking ties.

    The id is not decoration. Sort columns tie — two audit events appended in one
    transaction share ``occurred_at`` down to the microsecond — and a cursor that
    remembered only the timestamp would either repeat every tied row on the next
    page or skip all but one of them, depending on which way the comparison was
    written. With the id in the position the comparison is exact.
    """

    sort_value: datetime
    tiebreaker: uuid.UUID


@dataclass(frozen=True, slots=True)
class PageRequest:
    """One page of a query: how many rows, and where to resume.

    ``query`` travels with the request so that whatever mints the next cursor
    cannot disagree with whatever validated the incoming one.
    """

    limit: int
    after: CursorPosition | None
    query: PageQuery

    @property
    def fetch_limit(self) -> int:
        """How many rows to ask the database for: one more than the client gets.

        The extra row is how a query learns that a further page exists without a
        second ``COUNT`` over the whole table. It is dropped by :func:`build_page`
        and never returned, and its absence is what keeps the final page from
        handing back a cursor that resolves to nothing.
        """
        return self.limit + 1


@dataclass(frozen=True, slots=True)
class Page[ItemT]:
    """A page of results and the cursor that continues it.

    ``next_cursor`` is ``None`` on the last page, and that — not an empty
    ``items`` — is the client's stop condition: a filtered listing can return an
    empty page in the middle of a run and still have more rows behind it.
    """

    items: tuple[ItemT, ...]
    next_cursor: str | None

    def map_items[MappedT](self, transform: Callable[[ItemT], MappedT]) -> Page[MappedT]:
        """Re-type the rows while carrying the cursor across unchanged.

        Every list endpoint maps a domain object onto a view model. Doing that by
        rebuilding the page by hand loses the cursor the first time someone
        forgets to copy it, and a lost cursor looks exactly like the last page.
        """
        return Page(
            items=tuple(transform(item) for item in self.items),
            next_cursor=self.next_cursor,
        )


def encode_cursor(position: CursorPosition, query: PageQuery) -> str:
    """Render a position as the opaque string a client sends back."""
    payload = {
        "v": _CURSOR_FORMAT_VERSION,
        "k": position.sort_value.isoformat(),
        "i": str(position.tiebreaker),
        "q": query.fingerprint,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    # Padding is stripped so the cursor survives a query string without
    # percent-encoding; :func:`decode_cursor` puts it back.
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str, query: PageQuery) -> CursorPosition:
    """Read a cursor back, refusing one that does not belong to ``query``.

    Raises :class:`InvalidCursorError` for anything unreadable, for a payload
    written by a different format version, and for a cursor whose fingerprint
    does not match — a stale or foreign cursor is refused rather than silently
    applied, because applying it would return a window of the wrong result set
    and the client would have no way to notice.
    """
    try:
        # ``binascii.Error`` and ``json.JSONDecodeError`` are both ValueError.
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, TypeError) as exc:
        raise InvalidCursorError(
            "cursor is not readable; drop it and request the first page again"
        ) from exc
    if not isinstance(payload, dict):
        raise InvalidCursorError("cursor is not readable; drop it and request the first page again")
    if payload.get("v") != _CURSOR_FORMAT_VERSION:
        raise InvalidCursorError(
            "cursor was issued by an older version of this API; "
            "drop it and request the first page again"
        )
    if payload.get("q") != query.fingerprint:
        raise InvalidCursorError(
            "cursor was issued for a different query; "
            "request the first page again with the filters you want"
        )
    try:
        sort_value = datetime.fromisoformat(str(payload["k"]))
        tiebreaker = uuid.UUID(str(payload["i"]))
    except (KeyError, ValueError) as exc:
        raise InvalidCursorError(
            "cursor is not readable; drop it and request the first page again"
        ) from exc
    return CursorPosition(sort_value=sort_value, tiebreaker=tiebreaker)


def page_request(*, limit: int, cursor: str | None, query: PageQuery) -> PageRequest:
    """Turn a client's ``limit``/``cursor`` pair into a validated request."""
    if limit < 1 or limit > MAX_PAGE_SIZE:
        raise DomainError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
    return PageRequest(
        limit=limit,
        after=decode_cursor(cursor, query) if cursor else None,
        query=query,
    )


def build_page[ItemT](
    rows: Sequence[ItemT],
    *,
    request: PageRequest,
    position_of: Callable[[ItemT], CursorPosition],
) -> Page[ItemT]:
    """Trim an over-fetched result set into a page and mint its next cursor.

    ``rows`` is whatever came back for :attr:`PageRequest.fetch_limit` — one row
    more than the client asked for, when a further page exists. The surplus row
    is dropped here and its presence is the only thing consulted to decide
    whether ``next_cursor`` is set, so the last page reliably ends the run.
    """
    kept = tuple(rows[: request.limit])
    has_more = len(rows) > request.limit
    next_cursor = encode_cursor(position_of(kept[-1]), request.query) if has_more and kept else None
    return Page(items=kept, next_cursor=next_cursor)
