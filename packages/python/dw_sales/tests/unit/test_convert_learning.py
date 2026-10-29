"""An item code Sales confirms is kept for the customer's next PO (the AI list,
item 3, 2026-10-29): `SnapshotSalesCatalog.learn_convert` and the hook in
`OrderCommands.confirm_mapping`. The SQL store's half is
`tests/integration/test_recorded_converts_db.py`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dw_kernel.ports import FixedClock
from dw_sales.adapters.mock import MockSalesCatalog
from dw_sales.application.snapshot_catalog import ApprovedList, SnapshotSalesCatalog
from dw_sales.domain.catalog import ConvertEntry
from dw_sales.domain.master_data import CatalogList
from dw_sales.domain.orders import OrderCase
from dw_sales.evals.graders import AN, CALLERS
from dw_sales.evals.world import ALPHA, BETA, SampleSet, open_world
from dw_sales.testing.catalog_store import (
    MemoryRecordedConverts,
    MemoryRecordedQuotations,
    MemoryRecordedSenders,
)

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
AT = datetime(2026, 10, 29, 9, 0, tzinfo=UTC)
CASE = uuid.UUID(int=7)


class Lists:
    """`ApprovedListsPort` holding at most one approved convert list."""

    def __init__(self, entries: tuple[ConvertEntry, ...] | None = None) -> None:
        self.entries = entries

    async def approved(self, scope: object, catalog_list: CatalogList) -> ApprovedList | None:
        if catalog_list is not CatalogList.CONVERT_LIST or self.entries is None:
            return None
        return ApprovedList.of(catalog_list, uuid.UUID(int=1), AT, self.entries)


def _catalog(converts: MemoryRecordedConverts, lists: Lists | None = None) -> SnapshotSalesCatalog:
    clock = FixedClock(AT)
    return SnapshotSalesCatalog(
        lists or Lists(),
        MockSalesCatalog.load(ALPHA),
        MemoryRecordedQuotations(clock),
        converts,
        MemoryRecordedSenders(clock),
    )


NEW = ConvertEntry(customer_code="KMH", customer_item_code="KMH-NEW-01", prv_code="CB-2005")


async def test_a_confirmed_code_maps_the_customers_next_line_in_every_process() -> None:
    converts = MemoryRecordedConverts(FixedClock(AT))
    api, worker = _catalog(converts), _catalog(converts)
    assert (await worker.convert_entry(ALPHA, "KMH", "KMH-NEW-01")).data is None

    assert await api.learn_convert(ALPHA, NEW, by=AN.user_id, case_id=CASE)

    found = await worker.convert_entry(ALPHA, "KMH", "KMH-NEW-01")
    assert found.data == NEW and found.as_of == AT
    assert NEW in (await worker.convert_list(ALPHA)).data
    # Another tenant's catalog has none of it.
    assert not await converts.converts(BETA)


async def test_the_first_confirmation_is_kept() -> None:
    converts = MemoryRecordedConverts(FixedClock(AT))
    catalog = _catalog(converts)
    await catalog.learn_convert(ALPHA, NEW, by=AN.user_id, case_id=CASE)
    other = NEW.model_copy(update={"prv_code": "CB-2008"})
    await catalog.learn_convert(ALPHA, other, by=AN.user_id, case_id=CASE)
    assert (await catalog.convert_entry(ALPHA, "KMH", "KMH-NEW-01")).data == NEW


async def test_the_companys_own_list_answers_first_and_is_not_overridden() -> None:
    listed = NEW.model_copy(update={"prv_code": "CB-2002"})
    converts = MemoryRecordedConverts(FixedClock(AT))
    catalog = _catalog(converts, Lists((listed,)))

    assert not await catalog.learn_convert(ALPHA, NEW, by=AN.user_id, case_id=CASE)

    assert (await catalog.convert_entry(ALPHA, "KMH", "KMH-NEW-01")).data == listed
    assert not await converts.converts(ALPHA)


async def test_confirming_a_lines_code_teaches_the_catalog() -> None:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    _, case = (await world.process_each(AN, ["M05"]))["M05"]
    assert isinstance(case, OrderCase)
    line = case.line(2)
    assert line.mapping.status == "candidate"
    code = line.effective.customer_item_code
    catalog = world.services.order_commands.converts
    assert isinstance(catalog, SnapshotSalesCatalog)
    assert (await catalog.convert_entry(ALPHA, case.customer_code, code)).data is None

    await world.services.order_commands.confirm_mapping(
        AN.context(), case.case_id, 2, case_version=case.case_version, prv_code="CB-2005"
    )

    learned = (await catalog.convert_entry(ALPHA, case.customer_code, code)).data
    assert learned == ConvertEntry(
        customer_code=case.customer_code, customer_item_code=code, prv_code="CB-2005"
    )
