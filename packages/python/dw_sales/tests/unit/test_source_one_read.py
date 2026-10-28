"""A source view is one reading process, not two (2026-10-28).

Each reader call is a fresh sandboxed process, the bulk of a call's time, and
a sheet view used to ask twice: the grid, then the workbook's sheet names. The
grid now carries the names.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from functools import partial
from pathlib import Path

import pytest

from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.adapters.reader_wire import ReaderOp, ReaderReply, ReaderRequest
from dw_sales.adapters.readers.operations import InProcessReaderTransport
from dw_sales.application.ports import SalesScope
from dw_sales.application.source import (
    WARM_MAX_REGIONS,
    SheetGrid,
    SourceService,
    source_cache_key,
)
from dw_sales.domain.orders import OrderCase
from dw_sales.evals.graders import AN, CALLERS
from dw_sales.evals.world import ALPHA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]


async def test_a_sheet_view_is_one_read_and_names_every_sheet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    ((_, case),) = (await world.process_each(AN, ["M02"])).values()
    assert isinstance(case, OrderCase)
    first = case.header.anchors.po_no.sheet
    assert first is not None

    asked: list[ReaderOp] = []
    original = InProcessReaderTransport.call

    async def counted(self: InProcessReaderTransport, request: ReaderRequest) -> ReaderReply:
        asked.append(request.operation)
        return await original(self, request)

    monkeypatch.setattr(InProcessReaderTransport, "call", counted)
    view = await world.services.sources.order_source(
        AN.context(), case.case_id, case.document.attachment_id, page=None, sheet=first
    )

    assert asked == [ReaderOp.SOURCE_SHEET_GRID]
    # M02 reads its 18 lines from four sheets; the view names all of them.
    assert view.sheets is not None and len(view.sheets) == 4
    assert first in view.sheets


# ------------------------------------------------ an opened page is kept ----


class MemoryCache:
    """`SourceCachePort` in a dict, as the platform's Valkey cache keeps it."""

    def __init__(self) -> None:
        self.entries: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.entries.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int) -> None:
        assert 0 < ttl_seconds <= 3600
        self.entries[key] = value


async def _opened(
    monkeypatch: pytest.MonkeyPatch, cache: MemoryCache
) -> tuple[World, OrderCase, str, list[ReaderOp], SourceService]:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    ((_, case),) = (await world.process_each(AN, ["M02"])).values()
    assert isinstance(case, OrderCase)
    sheet = case.header.anchors.po_no.sheet
    assert sheet is not None
    asked: list[ReaderOp] = []
    original = InProcessReaderTransport.call

    async def counted(self: InProcessReaderTransport, request: ReaderRequest) -> ReaderReply:
        asked.append(request.operation)
        return await original(self, request)

    monkeypatch.setattr(InProcessReaderTransport, "call", counted)
    return world, case, sheet, asked, replace(world.services.sources, cache=cache)


async def test_a_page_opened_again_reads_no_file_and_is_still_recorded_as_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = MemoryCache()
    world, case, sheet, asked, sources = await _opened(monkeypatch, cache)
    open_ = partial(
        sources.order_source, case_id=case.case_id, attachment_id=case.document.attachment_id
    )
    first = await open_(AN.context(), page=None, sheet=sheet)
    world.store.state(ALPHA).served.clear()
    again = await open_(AN.context(), page=None, sheet=sheet)

    assert asked == [ReaderOp.SOURCE_SHEET_GRID]
    assert again.grid == first.grid
    # The evidence gate reads who was served what: a kept page counts too.
    assert {s.sheet for s in world.store.state(ALPHA).served} == {sheet}


async def test_another_companys_entry_for_the_same_file_is_never_served(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = MemoryCache()
    _, case, sheet, asked, sources = await _opened(monkeypatch, cache)
    sha = case.document.attachment_sha256
    other = SalesScope(TenantId(uuid.uuid4()), WorkspaceId(uuid.uuid4()))
    planted = SheetGrid(
        sheet=sheet,
        hidden_sheet=False,
        rows=1,
        columns=1,
        truncated=False,
        cells=[],
        sheets=[sheet],
    )
    cache.entries[source_cache_key(other, sha, page=None, sheet=sheet)] = planted.model_dump_json()

    view = await sources.order_source(
        AN.context(),
        case.case_id,
        case.document.attachment_id,
        page=None,
        sheet=sheet,
    )

    assert asked == [ReaderOp.SOURCE_SHEET_GRID]  # read from the file, not the plant
    assert view.grid is not None and view.grid.cells
    assert source_cache_key(ALPHA, sha, page=None, sheet=sheet) in cache.entries


def test_the_key_leads_with_the_tenant_and_workspace() -> None:
    key = source_cache_key(ALPHA, "ab" * 32, page=3, sheet=None)
    assert key.startswith(f"sales:source:v1:{ALPHA.tenant_id}:{ALPHA.workspace_id}:")
    assert key.endswith(":page:3")


# ---------------------------------------------- read ahead as DW1 opens it ----


async def test_reading_ahead_fills_the_cache_and_records_nobody_as_served(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = MemoryCache()
    world, case, _, asked, sources = await _opened(monkeypatch, cache)
    world.store.state(ALPHA).served.clear()

    await sources.warm(ALPHA, case)

    sha = case.document.attachment_sha256
    kept = [k for k in cache.entries if k.startswith(f"sales:source:v1:{ALPHA.tenant_id}:")]
    assert kept and all(sha in k for k in kept)
    assert 0 < len(asked) <= WARM_MAX_REGIONS
    # A page read ahead is a kept parse, not a person having looked at it.
    assert not world.store.state(ALPHA).served

    # Whoever opens it now waits for no file.
    asked.clear()
    sheet = case.header.anchors.po_no.sheet
    await sources.order_source(
        AN.context(), case.case_id, case.document.attachment_id, page=None, sheet=sheet
    )
    assert asked == []


async def test_dw1_reads_a_new_case_ahead_and_a_failure_to_does_not_stop_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warmed: list[uuid.UUID] = []

    async def failing(self: SourceService, scope: SalesScope, case: object) -> None:
        warmed.append(case.case_id)
        raise RuntimeError("the cache is down")

    monkeypatch.setattr(SourceService, "warm", failing)
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    ((_, case),) = (await world.process_each(AN, ["M02"])).values()

    assert isinstance(case, OrderCase)
    assert warmed == [case.case_id]
    assert world.order(case.case_id).case_id == case.case_id
