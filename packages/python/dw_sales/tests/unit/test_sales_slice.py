"""The generated slice, end to end, no infrastructure.

Kept because a scaffold that shipped untested code would be teaching the wrong
habit on the first file a new context ever has.
"""

from __future__ import annotations

import uuid

import pytest

from dw_sales.adapters.sink import InMemorySalesSink
from dw_sales.application.handlers import HandleSales
from dw_sales.domain.entities import SalesRequest

pytestmark = pytest.mark.unit


async def test_a_handled_request_reaches_the_sink_and_comes_back_summarised() -> None:
    sink = InMemorySalesSink()
    request = SalesRequest(
        request_id=uuid.uuid4(), tenant_id=uuid.uuid4(), subject="  báo giá quý 4  "
    )

    summary = await HandleSales(sink)(request)

    assert summary == "báo giá quý 4"
    assert sink.recorded == [request]


def test_an_empty_subject_is_refused_by_the_entity() -> None:
    """In the constructor, so nothing downstream has to ask whether it is valid."""
    # One id for both fields, so this line stays inside the line limit whatever
    # the context is named — the generated code has to pass `ruff format --check`
    # for every legal name, not just a short one.
    an_id = uuid.uuid4()
    with pytest.raises(ValueError):
        SalesRequest(request_id=an_id, tenant_id=an_id, subject="")
