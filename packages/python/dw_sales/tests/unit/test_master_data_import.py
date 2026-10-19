"""Master data imported from a file, previewed and approved (ticket 41)."""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

from dw_agent_runtime.approval_flow import ProposedDecision
from dw_kernel.errors import ConflictError, DomainError, NotFoundError, PermissionDeniedError
from dw_sales.adapters.mock import MockSalesCatalog
from dw_sales.adapters.mock.fixtures import DATA_DIR, read_records
from dw_sales.adapters.reader_client import ClientTableReader
from dw_sales.adapters.readers.operations import InProcessReaderTransport
from dw_sales.application.catalog_imports import (
    CATALOG_APPROVAL,
    CATALOG_IMPORTED,
    TableUnreadableError,
)
from dw_sales.application.snapshot_catalog import SnapshotSalesCatalog
from dw_sales.domain.catalog import ConvertEntry, Customer, Item, LmeMonth, Quotation
from dw_sales.domain.master_data import (
    SPECS,
    CatalogList,
    ImportedTable,
    TableRow,
    diff,
    header_key,
    parse_rows,
    read_decimal,
)
from dw_sales.evals.graders import AN, CALLERS, GIANG, OUTSIDER, READER
from dw_sales.evals.world import ALPHA, BETA, SampleSet, World, open_world
from dw_sales.testing.catalog_store import MemoryApprovedLists, MemoryCatalogStore

pytestmark = pytest.mark.unit

CatalogRecordModel = Customer | Item | ConvertEntry | Quotation | LmeMonth

REPO = Path(__file__).resolve().parents[5]


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), (*CALLERS, OUTSIDER))


def _customers() -> tuple[Customer, ...]:
    return read_records(DATA_DIR / "customers.json", Customer)


def _table(catalog_list: CatalogList, rows: Sequence[dict[str, str]]) -> ImportedTable:
    spec = SPECS[catalog_list]
    headers = [c.header for c in spec.columns]
    return ImportedTable(
        sheet="Dữ liệu",
        rows=[
            TableRow(row=1, cells=list(headers)),
            *(
                TableRow(row=i, cells=[row.get(h) for h in headers])
                for i, row in enumerate(rows, start=2)
            ),
        ],
    )


def _cells(catalog_list: CatalogList, records: Sequence[object]) -> list[dict[str, str]]:
    spec = SPECS[catalog_list]
    return [spec.cells(r.model_dump(mode="json")) for r in records]  # type: ignore[attr-defined]


def _xlsx(catalog_list: CatalogList, rows: Sequence[dict[str, str]]) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "Dữ liệu"
    headers = [c.header for c in SPECS[catalog_list].columns]
    sheet.append(headers)
    for row in rows:
        sheet.append([row.get(h) or None for h in headers])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


# ------------------------------------------------------------ the domain --


def test_a_header_matches_without_diacritics_case_or_punctuation() -> None:
    assert header_key("Mã khách hàng") == header_key("MA_KHACH_HANG") == "makhachhang"
    assert header_key("Đơn giá") == header_key("don gia")


@pytest.mark.parametrize("catalog_list", list(CatalogList))
def test_every_list_reads_back_from_its_own_template_rows(catalog_list: CatalogList) -> None:
    """The mock data printed as the template prints it parses to the same
    records: the columns cover every field a record has."""
    files: dict[CatalogList, tuple[str, type[CatalogRecordModel]]] = {
        CatalogList.CUSTOMERS: ("customers.json", Customer),
        CatalogList.ITEMS: ("items.json", Item),
        CatalogList.CONVERT_LIST: ("convert_list.json", ConvertEntry),
        CatalogList.QUOTATIONS: ("quotations.json", Quotation),
        CatalogList.LME: ("lme.json", LmeMonth),
    }
    name, model = files[catalog_list]
    records: tuple[CatalogRecordModel, ...] = read_records(DATA_DIR / name, model)
    parsed = parse_rows(catalog_list, _table(catalog_list, _cells(catalog_list, records)))
    assert parsed.rejected == ()
    assert [p.record for p in parsed.records] == list(records)
    assert diff(catalog_list, records, [p.record for p in parsed.records]).counts == {
        "added": 0,
        "changed": 0,
        "removed": 0,
        "unchanged": len(records),
    }


def test_headers_are_matched_tolerantly_and_an_unknown_one_is_reported() -> None:
    rows = _cells(CatalogList.LME, [LmeMonth(month="2026-01", usd_per_tonne=Decimal(9500))])
    table = ImportedTable(
        sheet="CSV",
        rows=[
            TableRow(row=1, cells=["THANG", "gia dong lme (usd/tan)", "Ghi chú"]),
            TableRow(row=2, cells=[rows[0]["Tháng"], "9500", "x"]),
        ],
    )
    parsed = parse_rows(CatalogList.LME, table)
    assert [p.record for p in parsed.records] == [
        LmeMonth(month="2026-01", usd_per_tonne=Decimal(9500))
    ]
    assert parsed.unknown_headers == ("Ghi chú",)


def test_a_file_without_a_required_column_is_refused_whole() -> None:
    table = ImportedTable(sheet="x", rows=[TableRow(row=1, cells=["Tháng"])])
    with pytest.raises(ValueError, match="thiếu cột: Giá đồng LME"):
        parse_rows(CatalogList.LME, table)


def test_each_bad_row_is_rejected_with_its_row_column_and_a_vietnamese_reason() -> None:
    good, other = _customers()[:2]
    rows = _cells(CatalogList.CUSTOMERS, [good, other])
    broken_contact = dict(rows[1]) | {"Mã khách hàng": "ZZZ", "Email liên hệ": "x@nowhere.example"}
    no_yes = dict(rows[1]) | {
        "Mã khách hàng": "YYY",
        "Tên miền email": "y.example",
        "Email liên hệ": "a@y.example",
        "NOC đã xác nhận": "có lẽ",
    }
    duplicate = dict(rows[0])
    bad_code = dict(rows[1]) | {
        "Mã khách hàng": "lower",
        "Tên miền email": "l.example",
        "Email liên hệ": "a@l.example",
    }
    shared = dict(rows[1]) | {"Mã khách hàng": "SHR"}
    parsed = parse_rows(
        CatalogList.CUSTOMERS,
        _table(
            CatalogList.CUSTOMERS,
            [rows[0], rows[1], broken_contact, no_yes, duplicate, bad_code, shared],
        ),
    )
    assert [p.record.code for p in parsed.records] == [good.code, other.code]  # type: ignore[union-attr]
    refused = {(r.row, r.column, r.reason) for r in parsed.rejected}
    assert refused == {
        (4, "Email liên hệ", "có email không thuộc tên miền của khách"),
        (5, "NOC đã xác nhận", "ghi Có hoặc Không"),
        (6, "Mã khách hàng", "trùng khóa với dòng 2"),
        (7, "Mã khách hàng", "sai định dạng"),
        (8, "Tên miền email", "tên miền đã thuộc khách hàng ở dòng 3"),
    }
    # A reason names the column, never the value it refused.
    assert not any("lower" in r.reason or "có lẽ" in r.reason for r in parsed.rejected)


def test_a_number_is_read_in_either_grouping_and_an_ambiguous_one_is_refused() -> None:
    assert read_decimal("1.234,5") == read_decimal("1,234.5") == read_decimal(1234.5)
    assert str(read_decimal("0,042")) == "0.042"
    with pytest.raises(ValueError, match="không rõ dấu thập phân"):
        read_decimal("1.000")


def test_the_diff_says_what_is_added_changed_old_to_new_and_removed() -> None:
    a, b, c = _customers()[:3]
    renamed = a.model_copy(update={"name": "Tên mới"})
    changes = diff(CatalogList.CUSTOMERS, [a, b], [renamed, c])
    assert [r.key for r in changes.added] == [c.code]
    assert [r.key for r in changes.removed] == [b.code]
    assert [(ch.column, ch.old, ch.new) for ch in changes.changed[0].changes] == [
        ("Tên khách hàng", a.name, "Tên mới")
    ]


# ------------------------------------------------------- the catalog read --


async def test_without_an_approved_import_every_list_is_the_mock() -> None:
    mock = MockSalesCatalog.load(ALPHA)
    store = MemoryCatalogStore(approvals=_world().runtime.approvals)
    catalog = SnapshotSalesCatalog(MemoryApprovedLists(store), mock)
    assert await catalog.customers(ALPHA) == await mock.customers(ALPHA)
    assert await catalog.lme_months(ALPHA) == await mock.lme_months(ALPHA)


# ------------------------------------------------------------- the flow --


async def _import(
    world: World, catalog_list: CatalogList, data: bytes, *, caller=AN, name: str = "kh.xlsx"
) -> uuid.UUID:
    view = await world.services.catalog_imports.upload(caller.context(), catalog_list, name, data)
    assert view.status == "queued"
    await world.read_imports()
    return view.snapshot_id


async def test_an_import_is_read_by_the_worker_previewed_submitted_and_approved_by_another() -> (
    None
):
    world = _world()
    catalog = world.services.catalog_imports.catalog
    first, *rest = _customers()
    renamed = first.model_copy(update={"name": "Velatrix Renamed Co., Ltd."})
    new = Customer.model_validate(
        first.model_dump()
        | {
            "code": "NEWC",
            "email_domains": ("newc.example",),
            "contacts": ({"address": "a@newc.example", "display_name": "A"},),
        }
    )
    rows = _cells(CatalogList.CUSTOMERS, [renamed, *rest[:-1], new])
    rows.append({"Mã khách hàng": "BAD"})  # every other cell blank
    data = _xlsx(CatalogList.CUSTOMERS, rows)

    view = await world.services.catalog_imports.upload(
        AN.context(), CatalogList.CUSTOMERS, "kh.xlsx", data
    )
    # The upload reads nothing: the bytes are kept, and the worker is asked.
    assert [e.event_type for e in world.runtime.outbox.events] == [CATALOG_IMPORTED]
    assert (await catalog.customer_by_code(ALPHA, "NEWC")).data is None
    assert await world.read_imports() == ["import parsed"]

    preview = await world.services.catalog_imports.preview(AN.context(), view.snapshot_id)
    assert preview.snapshot.status == "parsed"
    assert preview.compared_with.source == "mock"
    assert [r.key for r in preview.added] == ["NEWC"]
    assert [r.key for r in preview.changed] == [first.code]
    assert [r.key for r in preview.removed] == [rest[-1].code]
    assert preview.rejected_count == 1 and preview.rejected[0].row == len(rows) + 1
    # Nothing applies before the approval.
    assert (await catalog.customer_by_code(ALPHA, "NEWC")).data is None

    submitted = await world.services.catalog_imports.submit(AN.context(), view.snapshot_id)
    assert submitted.approval_id is not None
    approval = world.runtime.approvals.rows[submitted.approval_id]
    assert (approval.approval_type, approval.required_scope) == (
        CATALOG_APPROVAL,
        "sales.master_data.approve",
    )
    assert approval.makers == {AN.user_id}
    # Counts and ids, never a row.
    assert (
        approval.payload["added"],
        approval.payload["changed"],
        approval.payload["removed"],
    ) == (1, 1, 1)
    assert "Velatrix" not in str(approval.payload)

    await world.decide_catalog(GIANG, view.snapshot_id, approve=True, comment="Đồng ý")
    state = await world.services.catalog_imports.state(AN.context())
    customers = next(s for s in state.lists if s.catalog_list is CatalogList.CUSTOMERS)
    assert customers.in_force.source == "file"
    assert customers.in_force.snapshot is not None
    assert customers.in_force.snapshot.decided_by == GIANG.user_id
    # The imported list replaces the mock whole, with exact lookups.
    assert (await catalog.customer_by_code(ALPHA, "NEWC")).data == new
    assert (await catalog.customer_by_code(ALPHA, rest[-1].code)).data is None
    assert (await catalog.customer_by_email_domain(ALPHA, "NEWC.EXAMPLE")).data == new
    assert (await catalog.customer_by_email_domain(ALPHA, "mail.newc.example")).data is None
    assert (await catalog.customer_by_code(ALPHA, first.code)).data == renamed
    assert (await catalog.customers(ALPHA)).as_of == view.as_of
    # The other lists are still the mock's.
    assert (await catalog.items(ALPHA)).data == (await world.catalog.items(ALPHA)).data
    actions = [e.action for e in world.catalog_store.audit.events]
    assert actions == [
        "sales.catalog.imported",
        "sales.catalog.parsed",
        "sales.catalog.submitted",
        "sales.catalog.approved",
    ]
    # The worker's read is audited as its lane, never as a person.
    assert world.catalog_store.audit.events[1].details["actor"] == "system:sales_catalog_import"

    # A second approved import supersedes the first, which stays readable.
    again = await _import(world, CatalogList.CUSTOMERS, _xlsx(CatalogList.CUSTOMERS, rows[:2]))
    await world.services.catalog_imports.submit(AN.context(), again)
    await world.decide_catalog(GIANG, again, approve=True, comment="Đồng ý")
    earlier = await world.services.catalog_imports.preview(GIANG.context(), view.snapshot_id)
    assert earlier.snapshot.status == "superseded"
    assert len((await catalog.customers(ALPHA)).data) == 2


async def test_the_proposer_cannot_approve_their_own_import() -> None:
    world = _world()
    snapshot_id = await _import(
        world,
        CatalogList.CUSTOMERS,
        _xlsx(CatalogList.CUSTOMERS, _cells(CatalogList.CUSTOMERS, _customers())),
    )
    # GIANG imports and submits: GIANG holds the stamp but made it.
    view = await world.services.catalog_imports.submit(GIANG.context(), snapshot_id)
    with pytest.raises((ConflictError, PermissionDeniedError)):
        await world.decide_catalog(GIANG, snapshot_id, approve=True, comment="tự duyệt")
    # The guard says so on its own, behind the platform's strict rule.
    guard = world.runtime.approval_flow.decision_guards[CATALOG_APPROVAL]
    request = world.runtime.approvals.rows[view.approval_id]  # type: ignore[index]
    with pytest.raises(ConflictError, match="tách nhiệm"):
        await guard.check(request, ProposedDecision(True, "x", {}, None), GIANG.context())
    with pytest.raises(ConflictError, match="tách nhiệm"):
        await guard.check(request, ProposedDecision(True, "x", {}, None), AN.context())
    stored = world.catalog_store.state(ALPHA).snapshots[snapshot_id]
    assert stored.status == "submitted"


async def test_approving_an_import_compared_with_a_list_that_changed_since_is_refused() -> None:
    world = _world()
    rows = _cells(CatalogList.CUSTOMERS, _customers())
    first = await _import(world, CatalogList.CUSTOMERS, _xlsx(CatalogList.CUSTOMERS, rows))
    view = await world.services.catalog_imports.submit(AN.context(), first)
    guard = world.runtime.approval_flow.decision_guards[CATALOG_APPROVAL]
    # Another snapshot is approved behind its back (as a sync might).
    state = world.catalog_store.state(ALPHA)
    other = state.snapshots[first].model_copy(
        update={
            "snapshot_id": uuid.uuid4(),
            "status": "approved",
            "decided_by": GIANG.user_id,
            "decided_at": datetime.now(UTC),
            "approval_id": uuid.uuid4(),
        }
    )
    state.snapshots[other.snapshot_id] = other
    request = world.runtime.approvals.rows[view.approval_id]  # type: ignore[index]
    with pytest.raises(ConflictError, match="bản khác được duyệt"):
        await guard.check(request, ProposedDecision(True, "ok", {}, None), GIANG.context())
    # Rejecting it is still allowed.
    await guard.check(request, ProposedDecision(False, "không", {}, None), GIANG.context())


async def test_another_tenant_never_reads_previews_or_approves_a_snapshot() -> None:
    world = _world()
    rows = _cells(CatalogList.CUSTOMERS, _customers())
    snapshot_id = await _import(world, CatalogList.CUSTOMERS, _xlsx(CatalogList.CUSTOMERS, rows))
    view = await world.services.catalog_imports.submit(AN.context(), snapshot_id)
    with pytest.raises(NotFoundError):
        await world.services.catalog_imports.preview(OUTSIDER.context(BETA), snapshot_id)
    with pytest.raises(NotFoundError):
        await world.services.catalog_imports.submit(OUTSIDER.context(BETA), snapshot_id)
    beta_head = GIANG.context(BETA)
    guard = world.runtime.approval_flow.decision_guards[CATALOG_APPROVAL]
    request = world.runtime.approvals.rows[view.approval_id]  # type: ignore[index]
    with pytest.raises(NotFoundError):
        await guard.check(request, ProposedDecision(True, "x", {}, None), beta_head)
    await world.decide_catalog(GIANG, snapshot_id, approve=True, comment="Đồng ý")
    # Alpha's approved list is never served to beta, which reads its own source.
    catalog = world.services.catalog_imports.catalog
    assert (await catalog.customers(BETA)).data == ()
    state = await world.services.catalog_imports.state(OUTSIDER.context(BETA))
    assert all(s.in_force.source == "mock" and s.history == [] for s in state.lists)


async def test_a_caller_without_the_scope_is_refused_and_prices_need_the_price_scopes() -> None:
    world = _world()
    data = _xlsx(CatalogList.CUSTOMERS, _cells(CatalogList.CUSTOMERS, _customers()))
    with pytest.raises(PermissionDeniedError):
        await world.services.catalog_imports.upload(
            READER.context(), CatalogList.CUSTOMERS, "a.xlsx", data
        )
    with pytest.raises(PermissionDeniedError):
        await world.services.catalog_imports.template(READER.context(), CatalogList.CUSTOMERS)
    # AN holds no other customers' prices: the quotation list is not AN's to import.
    quotations = read_records(DATA_DIR / "quotations.json", Quotation)
    priced = _xlsx(CatalogList.QUOTATIONS, _cells(CatalogList.QUOTATIONS, quotations))
    with pytest.raises(PermissionDeniedError):
        await world.services.catalog_imports.upload(
            AN.context(), CatalogList.QUOTATIONS, "bg.xlsx", priced
        )
    snapshot_id = await _import(world, CatalogList.QUOTATIONS, priced, caller=GIANG)
    with pytest.raises(PermissionDeniedError):
        await world.services.catalog_imports.preview(AN.context(), snapshot_id)
    state = await world.services.catalog_imports.state(READER.context())
    assert not any(s.can_import for s in state.lists)


async def test_a_bad_file_fails_with_a_reason_and_a_waiting_import_blocks_another() -> None:
    world = _world()
    failed = await world.services.catalog_imports.upload(
        AN.context(), CatalogList.LME, "lme.csv", "Tháng\n01/2026\n".encode()
    )
    assert await world.read_imports() == ["import failed"]
    preview = await world.services.catalog_imports.preview(AN.context(), failed.snapshot_id)
    assert preview.snapshot.error == "thiếu cột: Giá đồng LME (USD/tấn)"
    with pytest.raises(ConflictError):
        await world.services.catalog_imports.submit(AN.context(), failed.snapshot_id)
    with pytest.raises(DomainError, match="chỉ nhận tệp"):
        await world.services.catalog_imports.upload(
            AN.context(), CatalogList.LME, "a.pdf", b"%PDF-1"
        )

    rows = _cells(CatalogList.CUSTOMERS, _customers())
    first = await _import(world, CatalogList.CUSTOMERS, _xlsx(CatalogList.CUSTOMERS, rows))
    # A new upload of a list lets go of an open import nobody submitted.
    second = await _import(world, CatalogList.CUSTOMERS, _xlsx(CatalogList.CUSTOMERS, rows))
    assert world.catalog_store.state(ALPHA).snapshots[first].status == "discarded"
    await world.services.catalog_imports.submit(AN.context(), second)
    with pytest.raises(ConflictError, match="chờ duyệt"):
        await world.services.catalog_imports.upload(
            AN.context(), CatalogList.CUSTOMERS, "kh.xlsx", _xlsx(CatalogList.CUSTOMERS, rows)
        )


async def test_a_convert_entry_naming_an_unknown_customer_or_item_is_rejected() -> None:
    world = _world()
    entries = list(read_records(DATA_DIR / "convert_list.json", ConvertEntry))
    rows = _cells(CatalogList.CONVERT_LIST, entries[:2])
    rows.append({"Mã khách hàng": "NOPE", "Mã hàng của khách": "X1", "Mã PRV": entries[0].prv_code})
    rows.append(
        {"Mã khách hàng": entries[0].customer_code, "Mã hàng của khách": "X2", "Mã PRV": "NO-ITEM"}
    )
    snapshot_id = await _import(
        world, CatalogList.CONVERT_LIST, _xlsx(CatalogList.CONVERT_LIST, rows)
    )
    preview = await world.services.catalog_imports.preview(AN.context(), snapshot_id)
    assert preview.snapshot.row_count == 2
    assert [(r.row, r.column) for r in preview.rejected] == [(4, "Mã khách hàng"), (5, "Mã PRV")]


async def test_the_template_has_the_lists_vietnamese_headers() -> None:
    world = _world()
    data, name = await world.services.catalog_imports.template(GIANG.context(), CatalogList.ITEMS)
    assert name == "mau-items.xlsx"
    table = await ClientTableReader(
        InProcessReaderTransport(), world.policies.order_rules.intake
    ).read(data, name)
    assert table.sheet == "Dữ liệu"
    assert table.rows[0].cells == [c.header for c in SPECS[CatalogList.ITEMS].columns]


# ------------------------------------------------------------ the reader --


async def test_the_reader_reads_a_semicolon_csv_in_utf8_and_refuses_another_encoding() -> None:
    caps = _world().policies.order_rules.intake
    reader = ClientTableReader(InProcessReaderTransport(), caps)
    out = io.StringIO()
    csv.writer(out, delimiter=";").writerows(
        [["Tháng", "Giá đồng LME (USD/tấn)"], ["01/2026", "9500,5"]]
    )
    table = await reader.read(("﻿" + out.getvalue()).encode(), "lme.csv")
    assert table.rows[1].cells == ["01/2026", "9500,5"]
    parsed = parse_rows(CatalogList.LME, table)
    assert str(parsed.records[0].record.usd_per_tonne) == "9500.5"  # type: ignore[union-attr]
    with pytest.raises(TableUnreadableError, match="UTF-8"):
        await reader.read("Tháng;Giá\n".encode("cp1258"), "lme.csv")
    with pytest.raises(TableUnreadableError):
        await reader.read(b"%PDF-1.4 not a table", "lme.csv")
