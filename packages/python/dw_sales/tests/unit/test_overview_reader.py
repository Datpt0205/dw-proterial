"""The work list's store narrowing (Sales ticket 24)."""

from __future__ import annotations

import pytest

from dw_sales.adapters.persistence.overview import SETTLED_ORDERS, SETTLED_QUOTES
from dw_sales.application.overview_service import _ORDER_NEXT, _QUOTE_NEXT

pytestmark = pytest.mark.unit


def test_no_work_list_step_is_on_a_settled_status() -> None:
    """The SQL reader reads open cases through partial indexes that leave the
    settled ones out; a step added on a settled status would never be listed,
    and nothing else would say so."""
    assert not set(_ORDER_NEXT) & set(SETTLED_ORDERS)
    assert not set(_QUOTE_NEXT) & set(SETTLED_QUOTES)
