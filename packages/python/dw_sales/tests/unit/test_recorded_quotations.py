"""A quotation Sales confirmed is a valid quotation for the next PO, in every
process (WIV-03-023 step 11, 2026-10-29): `SnapshotSalesCatalog` over
`RecordedQuotationsPort`. The SQL store's half is
`tests/integration/test_recorded_quotations_db.py`."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from dw_kernel.errors import ConflictError
from dw_kernel.ports import FixedClock
from dw_sales.adapters.mock import MockSalesCatalog
from dw_sales.application.ports import SalesScope
from dw_sales.application.snapshot_catalog import ApprovedList, SnapshotSalesCatalog
from dw_sales.domain.catalog import Quotation
from dw_sales.domain.master_data import CatalogList
from dw_sales.evals.world import ALPHA, BETA
from dw_sales.testing.catalog_store import MemoryRecordedQuotations

LISTED_AT = datetime(2026, 10, 1, tzinfo=UTC)
RECORDED_AT = datetime(2026, 10, 29, 9, 0, tzinfo=UTC)
DAY = date(2026, 11, 3)


class Lists:
    """`ApprovedListsPort` holding at most one approved quotation list."""

    def __init__(self, quotations: tuple[Quotation, ...] | None = None) -> None:
        self.quotations = quotations

    async def approved(self, scope: SalesScope, catalog_list: CatalogList) -> ApprovedList | None:
        if catalog_list is not CatalogList.QUOTATIONS or self.quotations is None:
            return None
        return ApprovedList.of(catalog_list, uuid.UUID(int=1), LISTED_AT, self.quotations)


def _catalog(
    recorded: MemoryRecordedQuotations, lists: Lists | None = None
) -> SnapshotSalesCatalog:
    # A process of its own: its own mock, loaded from the sample files.
    return SnapshotSalesCatalog(lists or Lists(), MockSalesCatalog.load(ALPHA), recorded)


async def _sent() -> Quotation:
    """A new quotation, KMH's first for an item the sample quotes VLX."""
    (sample,) = [
        q
        for q in (await MockSalesCatalog.load(ALPHA).quotations(ALPHA)).data
        if q.quote_no == "Q26-0104"
    ]
    return sample.model_copy(
        update={
            "quote_no": "Q26-0999",
            "customer_code": "KMH",
            "unit_price": Decimal("1.2345"),
            "valid_from": date(2026, 10, 29),
            "valid_to": date(2027, 3, 31),
        }
    )


async def test_a_recorded_quotation_is_read_by_another_process() -> None:
    recorded = MemoryRecordedQuotations(FixedClock(RECORDED_AT))
    api, worker = _catalog(recorded), _catalog(recorded)
    sent = await _sent()
    assert not (
        await worker.quotations_valid_on(ALPHA, sent.customer_code, sent.prv_code, DAY)
    ).data

    await api.record(ALPHA, [sent])

    found = await worker.quotations_valid_on(ALPHA, sent.customer_code, sent.prv_code, DAY)
    assert found.data == (sent,)
    # The read says it holds a row recorded after the list was taken.
    assert found.as_of == RECORDED_AT
    assert sent in (await worker.quotations_for_item(ALPHA, sent.prv_code)).data


async def test_recording_again_writes_nothing_more() -> None:
    recorded = MemoryRecordedQuotations(FixedClock(RECORDED_AT))
    catalog, sent = _catalog(recorded), await _sent()
    await catalog.record(ALPHA, [sent])
    await catalog.record(ALPHA, [sent])
    assert len(await recorded.recorded(ALPHA)) == 1


async def test_other_terms_under_a_held_number_refuse_the_whole_record() -> None:
    recorded = MemoryRecordedQuotations(FixedClock(RECORDED_AT))
    catalog, sent = _catalog(recorded), await _sent()
    await catalog.record(ALPHA, [sent])
    other_item = sent.model_copy(update={"quote_no": "Q26-0998"})

    with pytest.raises(ConflictError):
        await catalog.record(
            ALPHA, [other_item, sent.model_copy(update={"unit_price": Decimal("9")})]
        )
    with pytest.raises(ConflictError):
        await catalog.record(ALPHA, [sent.model_copy(update={"customer_code": "VLX"})])
    # All or none: the good row in the refused record was not kept.
    assert [r.quotation for r in await recorded.recorded(ALPHA)] == [sent]


async def test_the_next_import_that_carries_it_shadows_the_recorded_row() -> None:
    recorded = MemoryRecordedQuotations(FixedClock(RECORDED_AT))
    sent = await _sent()
    await _catalog(recorded).record(ALPHA, [sent])

    imported = _catalog(recorded, Lists((sent,)))
    found = await imported.quotations(ALPHA)
    assert found.data == (sent,)
    # Nothing recorded is newer than the list now answering for it.
    assert found.as_of == LISTED_AT


async def test_a_number_the_list_holds_with_other_terms_is_refused() -> None:
    recorded = MemoryRecordedQuotations(FixedClock(RECORDED_AT))
    sent = await _sent()
    listed = _catalog(recorded, Lists((sent.model_copy(update={"moq": Decimal(999)}),)))

    with pytest.raises(ConflictError):
        await listed.record(ALPHA, [sent])
    assert not await recorded.recorded(ALPHA)


async def test_another_workspace_reads_none_of_it() -> None:
    recorded = MemoryRecordedQuotations(FixedClock(RECORDED_AT))
    sent = await _sent()
    await _catalog(recorded).record(ALPHA, [sent])
    assert not await recorded.recorded(BETA)
