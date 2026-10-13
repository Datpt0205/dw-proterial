"""The Sales span allowlist (ticket 23, G32): listed keys, each in its own shape.

The end-to-end search of spans, logs and error bodies for a fixture PO's
values is `apps/api/tests/unit/test_sales_telemetry.py`; this file holds the
helper's own rule, key by key.
"""

from __future__ import annotations

import uuid

import pytest

from dw_observability.telemetry import RecordingTelemetry
from dw_sales.application.telemetry import (
    SalesSpan,
    SalesSpans,
    allowed_attributes,
)
from dw_sales.domain.dispositions import CaseKind, DispositionKind
from dw_sales.domain.orders import FindingCode, OrderStatus
from dw_sales.domain.quotes import QuoteFindingCode

pytestmark = pytest.mark.unit

CASE = uuid.UUID(int=0xCA5E)


def test_listed_keys_in_their_shape_are_kept() -> None:
    kept = allowed_attributes(
        {
            "dw.tenant_id": uuid.UUID(int=1),
            "sales.case_id": CASE,
            "sales.case_kind": CaseKind.ORDER,
            "sales.case_version": 3,
            "sales.status": OrderStatus.IN_REVIEW,
            "sales.disposition": DispositionKind.CASE_CREATED,
            "sales.finding_kinds": [FindingCode.PRICE_MISMATCH, QuoteFindingCode.RFQ_INCOMPLETE],
            "sales.finding_count": 0,
            "sales.duration_ms": 12.345,
        }
    )
    assert kept == {
        "dw.tenant_id": str(uuid.UUID(int=1)),
        "sales.case_id": str(CASE),
        "sales.case_kind": "order",
        "sales.case_version": 3,
        "sales.status": "in_review",
        "sales.disposition": "case_created",
        "sales.finding_kinds": "price_mismatch,rfq_incomplete",
        "sales.finding_count": 0,
        "sales.duration_ms": 12.3,
    }


@pytest.mark.parametrize(
    ("key", "value"),
    [
        # Not listed: dropped whatever it holds.
        ("sales.unit_price", "0.0420"),
        ("sales.customer_name", "Velatrix Electronics Vietnam Co., Ltd."),
        ("sales.subject", "PO VLX-PO-2609-0118"),
        ("sales.message_id", "M01"),
        # Listed, the value not in its key's shape.
        ("sales.status", "0.0420"),
        ("sales.case_kind", "Velatrix"),
        ("sales.case_id", str(CASE)),
        ("dw.tenant_id", "Velatrix Electronics Vietnam Co., Ltd."),
        ("sales.case_version", "3"),
        ("sales.line_count", -1),
        ("sales.line_count", True),
        ("sales.line_count", 4.0),
        ("sales.duration_ms", "12.5"),
        ("sales.duration_ms", -1.0),
        ("sales.finding_kinds", "price_mismatch"),
        ("sales.finding_kinds", ["price_mismatch", "0.0420"]),
        ("sales.routing_reason", None),
    ],
)
def test_anything_else_is_dropped(key: str, value: object) -> None:
    assert allowed_attributes({key: value}) == {}


def test_the_helper_hands_the_port_only_what_the_allowlist_keeps() -> None:
    port = RecordingTelemetry()
    SalesSpans(port).emit(
        SalesSpan.MESSAGE_PROCESSED,
        {"sales.case_id": CASE, "sales.unit_price": "0.0420", "sales.status": "Velatrix"},
    )
    assert port.spans == [("sales.message.processed", {"sales.case_id": str(CASE)})]
