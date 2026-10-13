"""Sales spans: one allowlist, applied where a span's attributes are set (ticket 23, G32).

DW1 handles prices, customer names and mail text. A span leaves the process
(an OTLP collector, Langfuse), so what a Sales span may carry is said once,
here: `SPAN_ATTRIBUTES`, each key with the one shape its value may take. An
id is a `uuid.UUID`, a version or a count a non-negative int, a duration a
non-negative number, and anything else a code from a closed set (a case
kind, a status, a disposition, a routing reason, finding codes). A key not
listed, or a value not in its key's shape, is dropped by `SalesSpans`
before the telemetry port sees it: not merely not set by today's callers,
so a price put under `sales.status` is refused like a price under a key of
its own.

A Sales span is a marker emitted after the step it describes, the way the
runtime's `dw.model.call` is: its outcome (the case, its status, what the
checks found) is known only then, and how long the step took is
`sales.duration_ms`, not the span's own start and end. An error raised by
the step is not on a Sales span at all; it reaches the run's span as the
kernel's `DWError`, whose message is safe to log by contract.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Protocol

from dw_sales.domain.dispositions import CaseKind, DispositionKind, RoutingReason
from dw_sales.domain.orders import FindingCode, OrderCase, OrderStatus
from dw_sales.domain.quotes import QuoteCase, QuoteFindingCode, QuoteStatus

type AttributeValue = str | int | float | bool
type _Shape = Callable[[object], AttributeValue | None]


class SpanPort(Protocol):
    """Where a span goes. The platform's `TelemetryPort` satisfies it."""

    def span(self, name: str, attributes: Mapping[str, object]) -> AbstractContextManager[None]: ...


class SalesSpan(StrEnum):
    """Every span Sales emits."""

    MESSAGE_PROCESSED = "sales.message.processed"


def _id(value: object) -> AttributeValue | None:
    return str(value) if isinstance(value, uuid.UUID) else None


def _count(value: object) -> AttributeValue | None:
    return value if type(value) is int and value >= 0 else None


def _duration(value: object) -> AttributeValue | None:
    if isinstance(value, int | float) and not isinstance(value, bool) and value >= 0:
        return round(float(value), 1)
    return None


def _one_of(*codes: type[StrEnum]) -> _Shape:
    allowed = frozenset(member.value for enum in codes for member in enum)

    def shape(value: object) -> AttributeValue | None:
        return str(value) if isinstance(value, str) and value in allowed else None

    return shape


def _set_of(*codes: type[StrEnum]) -> _Shape:
    """Several codes as one sorted, comma-separated string; none if any is not one."""
    one = _one_of(*codes)

    def shape(value: object) -> AttributeValue | None:
        if isinstance(value, str) or not isinstance(value, Iterable):
            return None
        kept = [one(item) for item in value]
        if any(item is None for item in kept):
            return None
        return ",".join(sorted({str(item) for item in kept}))

    return shape


SPAN_ATTRIBUTES: Final[Mapping[str, _Shape]] = MappingProxyType(
    {
        "dw.tenant_id": _id,
        "dw.workspace_id": _id,
        "sales.case_kind": _one_of(CaseKind),
        "sales.case_id": _id,
        "sales.case_version": _count,
        "sales.status": _one_of(OrderStatus, QuoteStatus),
        "sales.disposition": _one_of(DispositionKind),
        "sales.routing_reason": _one_of(RoutingReason),
        "sales.finding_kinds": _set_of(FindingCode, QuoteFindingCode),
        "sales.finding_count": _count,
        "sales.line_count": _count,
        "sales.duration_ms": _duration,
    }
)


def allowed_attributes(attributes: Mapping[str, object]) -> dict[str, AttributeValue]:
    """What of ``attributes`` a Sales span may carry: listed keys in their shape."""
    kept: dict[str, AttributeValue] = {}
    for key, value in attributes.items():
        shape = SPAN_ATTRIBUTES.get(key)
        cleaned = None if shape is None else shape(value)
        if cleaned is not None:
            kept[key] = cleaned
    return kept


def case_attributes(case: OrderCase | QuoteCase) -> dict[str, object]:
    """A case as a span describes it: ids, version, status and what was found."""
    if isinstance(case, OrderCase):
        kind, lines = CaseKind.ORDER, len(case.lines)
    else:
        kind, lines = CaseKind.QUOTE, len(case.request.document.items)
    return {
        "sales.case_kind": kind,
        "sales.case_id": case.case_id,
        "sales.case_version": case.case_version,
        "sales.status": case.status,
        "sales.finding_kinds": [finding.code for finding in case.findings],
        "sales.finding_count": len(case.findings),
        "sales.line_count": lines,
    }


@dataclass(frozen=True)
class SalesSpans:
    """The one way Sales emits a span: through `allowed_attributes`."""

    telemetry: SpanPort

    def emit(self, name: SalesSpan, attributes: Mapping[str, object]) -> None:
        with self.telemetry.span(name.value, allowed_attributes(attributes)):
            pass
