"""DW2's master-data page and the worker lane that reads its workbooks
(`application.master_data`): who may load the lists, what the API keeps and
refuses, what the lane does with a file the scanner or reader turns down,
and what a submitted workbook changes."""

from __future__ import annotations

import io
import uuid
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path

import pytest
from openpyxl import load_workbook

from dw_kernel.errors import ConflictError, DomainError, InfrastructureError, PermissionDeniedError
from dw_kernel.ports import Uuid4Generator
from dw_platform.application.malware import ScanVerdict
from dw_platform.application.rule_versions import ContextScope
from dw_purchasing.adapters.master_data import DemoMasterData
from dw_purchasing.adapters.mock.master_data import MockMasterData
from dw_purchasing.application.access import PurchasingScopes
from dw_purchasing.application.master_data import (
    INFECTED,
    KEEP_FOR,
    MASTER_IMPORT_LANE,
    MasterImportLane,
    WorkbookUnreadableError,
)
from dw_purchasing.domain.master_lists import SHEETS, SheetRows
from dw_purchasing.testing.world import ALPHA, BETA, World, caller, open_world

REPO = Path(__file__).resolve().parents[5]
XLSX = b"PK\x03\x04 a workbook as the API sees it: bytes it never opens"
ITEMS: SheetRows = {
    "Vật tư": [
        (1, ["Mã vật tư", "Mô tả", "Đơn vị"]),
        (2, ["GT-01", "Găng tay", "đôi"]),
        (3, ["bad!", "x", "cái"]),
    ]
}
CONFIGURER = frozenset({PurchasingScopes.RULES_PROPOSE.value})
HEAD = frozenset({PurchasingScopes.RULES_PROPOSE.value, PurchasingScopes.RULES_APPROVE.value})


class Reader:
    def __init__(self, sheets: SheetRows | Exception) -> None:
        self.sheets_ = sheets
        self.asked: list[Sequence[str]] = []

    async def sheets(self, data: bytes, wanted: Sequence[str]) -> SheetRows:
        self.asked.append(wanted)
        if isinstance(self.sheets_, Exception):
            raise self.sheets_
        return self.sheets_


class Scanner:
    def __init__(self, verdict: ScanVerdict | None = None) -> None:
        self.verdict = verdict or ScanVerdict.clean()

    async def scan(self, data: bytes) -> ScanVerdict:
        return self.verdict


def _lane(world: World, reader: Reader, scanner: Scanner | None = None) -> MasterImportLane:
    return MasterImportLane(
        world.master_imports, reader, scanner or Scanner(), world.clock, Uuid4Generator()
    )


SCOPE = ContextScope.of(caller())


async def _uploaded_and_read(world: World, sheets: SheetRows = ITEMS) -> uuid.UUID:
    view = await world.master_data.upload(caller(scopes=HEAD), "C:\\data\\lists.xlsx", XLSX)
    assert await _lane(world, Reader(sheets)).tick(SCOPE) == 1
    return view.import_id


# ------------------------------------------------------------- who loads --


async def test_only_who_configures_dw2_uploads_or_downloads_the_template() -> None:
    world = open_world(REPO, {})
    reader = caller(scopes=frozenset({PurchasingScopes.REQUEST_READ.value}))
    with pytest.raises(PermissionDeniedError):
        await world.master_data.upload(reader, "a.xlsx", XLSX)
    with pytest.raises(PermissionDeniedError):
        await world.master_data.template_file(reader)
    with pytest.raises(PermissionDeniedError):
        await world.master_data.overview(reader)
    approver = caller(scopes=frozenset({PurchasingScopes.RULES_APPROVE.value}))
    # Who decides reads the page, and may not load a file.
    assert (await world.master_data.overview(approver)).can_upload is False
    with pytest.raises(PermissionDeniedError):
        await world.master_data.upload(approver, "a.xlsx", XLSX)
    assert world.master_imports.rows == {}


@pytest.mark.parametrize(
    ("data", "rule"),
    [
        (b"", "empty_file"),
        (b"%PDF-1.7 not a workbook", "not_a_workbook"),
        (b"PK\x03\x04", "file_too_large"),
    ],
    ids=["empty", "pdf", "too_large"],
)
async def test_what_is_not_a_workbook_is_refused_before_it_is_kept(data: bytes, rule: str) -> None:
    if rule == "file_too_large":
        data += b"0" * (10 * 1024 * 1024)
    world = open_world(REPO, {})
    with pytest.raises(DomainError) as refused:
        await world.master_data.upload(caller(scopes=CONFIGURER), "a.xlsx", data)
    assert refused.value.details["rule"] == rule
    assert world.master_imports.rows == {}


async def test_the_template_has_a_guide_and_one_empty_sheet_per_list() -> None:
    world = open_world(REPO, {})
    data = await world.master_data.template_file(caller(scopes=CONFIGURER))
    book = load_workbook(io.BytesIO(data))

    assert book.sheetnames == ["Hướng dẫn", *(s.sheet for s in SHEETS)]
    for spec in SHEETS:
        sheet = book[spec.sheet]
        assert [c.value for c in sheet[1]] == [c.header for c in spec.columns]
        # No example row on a list's sheet: it would be loaded as data.
        assert sheet.max_row == 1


async def test_an_upload_keeps_the_name_not_the_path_and_forgets_the_open_one() -> None:
    world = open_world(REPO, {})
    first = await world.master_data.upload(caller(scopes=CONFIGURER), "a.xlsx", XLSX)
    second = await world.master_data.upload(caller(scopes=CONFIGURER), "C:\\x\\b.xlsx", XLSX)

    assert second.file_name == "b.xlsx"
    assert second.status == "queued"
    held = world.master_imports.rows[ALPHA]
    assert set(held) == {second.import_id} and first.import_id not in held
    assert [e.action for e in world.master_imports.audit] == ["purchasing.master_data.uploaded"] * 2


# --------------------------------------------------------------- the lane --


async def test_the_lane_reads_a_file_audits_as_itself_and_forgets_its_bytes() -> None:
    world = open_world(REPO, {})
    import_id = await _uploaded_and_read(world)

    record = world.master_imports.rows[ALPHA][import_id]
    assert record[0].status == "parsed" and record[1] is None
    assert record[0].lists is not None and [r["code"] for r in record[0].lists["items"]] == [
        "GT-01"
    ]
    assert record[0].rejected_total == 1
    read = world.master_imports.audit[-1]
    assert read.action == "purchasing.master_data.read"
    assert read.details["actor"] == f"system:{MASTER_IMPORT_LANE}"
    # Read once: the next tick finds nothing queued.
    assert await _lane(world, Reader(ITEMS)).tick(SCOPE) == 0


async def test_an_infected_file_fails_and_is_never_read() -> None:
    world = open_world(REPO, {})
    await world.master_data.upload(caller(scopes=CONFIGURER), "a.xlsx", XLSX)
    reader = Reader(ITEMS)

    await _lane(world, reader, Scanner(ScanVerdict.infected("Eicar"))).tick(SCOPE)

    (record, content), *_ = world.master_imports.rows[ALPHA].values()
    assert (record.status, record.failure, content) == ("failed", INFECTED, None)
    assert reader.asked == []


async def test_a_scanner_that_does_not_answer_leaves_the_file_queued_unread() -> None:
    world = open_world(REPO, {})
    await world.master_data.upload(caller(scopes=CONFIGURER), "a.xlsx", XLSX)
    reader = Reader(ITEMS)

    with pytest.raises(InfrastructureError):
        await _lane(world, reader, Scanner(ScanVerdict.unavailable("down"))).tick(SCOPE)

    (record, content), *_ = world.master_imports.rows[ALPHA].values()
    assert (record.status, content) == ("queued", XLSX)
    assert reader.asked == []


async def test_a_file_the_reader_cannot_open_fails_with_the_readers_reason() -> None:
    world = open_world(REPO, {})
    await world.master_data.upload(caller(scopes=CONFIGURER), "a.xlsx", XLSX)

    await _lane(world, Reader(WorkbookUnreadableError("bảng tính có mật khẩu"))).tick(SCOPE)

    (record, _), *_ = world.master_imports.rows[ALPHA].values()
    assert (record.status, record.failure) == ("failed", "bảng tính có mật khẩu")


async def test_the_lane_forgets_an_import_read_long_ago() -> None:
    world = open_world(REPO, {})
    await _uploaded_and_read(world)
    world.clock.advance_to(world.clock.now() + KEEP_FOR + timedelta(seconds=1))

    await _lane(world, Reader(ITEMS)).tick(SCOPE)

    assert world.master_imports.rows[ALPHA] == {}


# ------------------------------------------------------------- the version --


async def test_the_heads_submission_applies_and_every_check_reads_it_at_once() -> None:
    world = open_world(REPO, {})
    import_id = await _uploaded_and_read(world)
    head = caller(scopes=HEAD)

    preview = await world.master_data.get(head, import_id)
    items = next(c for c in preview.changes if c.list == "items")
    assert (items.in_file, items.rows, items.added) == (True, 1, 1)
    sent = await world.master_data.submit(head, import_id)

    assert sent.status == "submitted" and sent.version_ref == "purchasing_master_data@1.0.1"
    page = await world.master_data.overview(head)
    assert (page.layer, page.waiting) == ("tenant", None)
    assert {c.list: c.rows for c in page.lists}["items"] == 1
    master = DemoMasterData(
        world.rules.book, MockMasterData.load(tenant_id=ALPHA[0], workspace_id=ALPHA[1])
    )
    assert set((await master.for_context(head)).items) == {"GT-01"}
    with pytest.raises(ConflictError):
        await world.master_data.submit(head, import_id)
    # Refused before anything was proposed: the version in force is the one sent.
    assert (await world.master_data.overview(head)).ref == "purchasing_master_data@1.0.1"


async def test_a_configurers_submission_waits_for_the_head_and_holds_the_next_one() -> None:
    world = open_world(REPO, {})
    import_id = await _uploaded_and_read(world)
    configurer = caller(scopes=CONFIGURER)

    sent = await world.master_data.submit(configurer, import_id)

    page = await world.master_data.overview(configurer)
    assert page.layer == "platform"
    assert page.waiting == sent.version_ref
    next_id = await _uploaded_and_read(world)
    assert (await world.master_data.get(configurer, next_id)).blocked is not None


async def test_a_list_the_file_leaves_out_is_kept() -> None:
    world = open_world(REPO, {})
    head = caller(scopes=HEAD)
    budgets: SheetRows = {
        "Ngân sách": [(1, ["Mã ngân sách", "Còn lại", "Tiền tệ"]), (2, ["NS-1", 100, "VND"])]
    }
    await world.master_data.submit(head, await _uploaded_and_read(world, budgets))

    await world.master_data.submit(head, await _uploaded_and_read(world))

    lists, _ = await world.rules.book.master_data(SCOPE)
    assert [b.code for b in lists.budgets] == ["NS-1"]
    assert [i.code for i in lists.items] == ["GT-01"]


async def test_another_tenant_reads_none_of_it() -> None:
    world = open_world(REPO, {})
    import_id = await _uploaded_and_read(world)
    other = caller(BETA, scopes=HEAD)

    with pytest.raises(Exception, match="no such import"):
        await world.master_data.get(other, import_id)
    with pytest.raises(Exception, match="no such import"):
        await world.master_data.submit(other, import_id)
    assert (await world.master_data.overview(other)).imports == []


async def test_the_master_data_is_neither_on_the_settings_page_nor_changed_in_words() -> None:
    world = open_world(REPO, {})
    head = caller(scopes=HEAD)
    await world.master_data.submit(head, await _uploaded_and_read(world))

    listed = await world.rules.list(head)

    assert "purchasing_master_data" not in {k.key for k in listed.keys}
    assert "purchasing_master_data" not in {v.key for v in listed.versions}
    with pytest.raises(Exception, match="no such rule key"):
        await world.words.draft(head, "purchasing_master_data", "thêm vật tư")
