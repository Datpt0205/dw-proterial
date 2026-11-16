"""Bravo's own customer list, item master and convert list, imported as
exported (ticket 36). Every file here is synthetic, shaped as Bravo exports
the real ones (Box B04, B05, B06): a merged title row, the header on row 2,
Bravo's own column labels, and for the convert list a group's label row with
its SUBTOTAL before the data."""

from __future__ import annotations

import io
import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from openpyxl import Workbook

from dw_sales.adapters.reader_client import ClientTableReader
from dw_sales.adapters.readers.operations import InProcessReaderTransport
from dw_sales.application.order_intake import _convert_entry
from dw_sales.application.snapshot_catalog import SnapshotSalesCatalog
from dw_sales.domain.anchors import SourceAnchor
from dw_sales.domain.bravo_exports import find_header
from dw_sales.domain.catalog import ConvertEntry, Customer, Item
from dw_sales.domain.descriptions import StatedAttributes, candidates
from dw_sales.domain.item_names import read_name
from dw_sales.domain.master_data import (
    SPECS,
    CatalogList,
    ImportedTable,
    TableRow,
    parse_rows,
)
from dw_sales.domain.order_checks import map_line
from dw_sales.domain.orders import PoLine, PoLineAnchors
from dw_sales.evals.graders import AN, CALLERS, GIANG, OUTSIDER
from dw_sales.evals.world import ALPHA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]

# Bravo's own column labels, as its exports print them (not customer data).
B05_HEADERS = [
    "Code",
    "Nhóm KH",
    "Tên đối tượng",
    "Địa chỉ",
    "Payment terms (Acc)",
    "Nhóm mẹ",
    "Tên miền email",
    "Ngôn ngữ",
    "PIC phụ trách",
    "E-mail liên hệ",
    "Người làm thay khi vắng",
    "E-mail liên hệ",
]
B06_HEADERS = [
    "Mã",
    "Tên vật tư",
    "Đvt",
    "Đvt quy đổi",
    "Hệ số quy đổi",
    "Loại vật tư",
    "Specification",
    "Packaging style",
    "Unit Packing",
    "Catergory",
    "BP Code",
]
B04_HEADERS = [
    "Input date",
    "PRV code",
    "PRV item name",
    "Specification",
    "Direct customer code",
    "Direct customer name",
    "Converting description",
    "Invoice description",
    "All customer code",
    "All customer description",
    "Remark",
    "Id",
]

WIRE = "Hook up wire - UL1007 1X24AWG(11/0.16) LF WHITE P-30K"
CABLE = "Cabling - UL2464 3x17AWG(50/0.18TA) LF BK C200"


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), (*CALLERS, OUTSIDER))


def _bravo_xlsx(
    title: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    *,
    hints: Sequence[Any] = (),
    group: str | None = None,
) -> bytes:
    """A sheet as Bravo exports a list: the title merged across row 1 (with
    whatever hints Sales typed beside it), the header on row 2, then, for a
    list kept by approval state, one group's label merged across the row
    with a SUBTOTAL formula in the last column, then the rows."""
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "Control_Explorer"
    width = len(headers)
    sheet.append([title, *[None] * (width - 1 - len(hints)), *hints])
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=width - len(hints))
    sheet.append(list(headers))
    first = 3
    if group is not None:
        last = 3 + len(rows)
        sheet.append([group, *[None] * (width - 2), f"=SUBTOTAL(3,L4:L{last})"])
        sheet.merge_cells(start_row=3, start_column=1, end_row=3, end_column=width - 1)
        first = 4
    for offset, row in enumerate(rows):
        sheet.append([*row][:width])
        assert sheet.max_row == first + offset
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def _b05() -> bytes:
    return _bravo_xlsx(
        "Danh mục đối tượng",
        B05_HEADERS,
        [
            # code, channel, name, address, terms, group, domain, language,
            # contact names, their mail, stand-in, stand-in's mail
            [
                "FG00000001",
                "PRV",
                "Alpha Wire Co",
                None,
                "AMS30",
                "01.CUSTOMER",
                "@alpha.example",
                "English",
                "A. Buyer",
                "buyer@alpha.example",
                "B. Backup",
                "backup@alpha.example",
            ],
            [
                "FG00000002",
                "PCS",
                "Group Cable East",
                None,
                None,
                "01.CUSTOMER",
                "@group.example",
                "English",
                "C",
                "c.east@group.example",
                None,
                None,
            ],
            [
                "FG00000003",
                "PCS",
                "Group Cable West",
                None,
                None,
                "01.CUSTOMER",
                "@group.example",
                "Vietnamese",
                "D",
                "D Person <d.west@group.example>",
                None,
                None,
            ],
            [
                "TDC0001",
                None,
                "Trial Buyer",
                None,
                None,
                "02.TEMPSALES",
                None,
                "English",
                None,
                "t@trial.example",
                None,
                None,
            ],
            [
                "IC0001",
                None,
                "End User Ltd",
                None,
                None,
                "03.INDIRECTCUSTOMER",
                None,
                "English",
                None,
                "e@enduser.example",
                None,
                None,
            ],
            # Two languages in one cell: drafts in the first named.
            [
                "FG00000004",
                None,
                "Two Tongues",
                None,
                None,
                "01.CUSTOMER",
                None,
                "Vietnamese/English",
                None,
                "x@two.example",
                None,
                None,
            ],
            # A language DW1 does not write in: refused, never another picked.
            [
                "FG00000006",
                None,
                "Far Away",
                None,
                None,
                "01.CUSTOMER",
                None,
                "English/Korean",
                None,
                "f@far.example",
                None,
                None,
            ],
            # No contact: DW1 could not write to it.
            [
                "FG00000005",
                None,
                "Silent Co",
                None,
                None,
                "01.CUSTOMER",
                None,
                "English",
                None,
                None,
                None,
                None,
            ],
        ],
        hints=["@group.example", "Vietnamese/English/Japanese"],
    )


def _b06() -> bytes:
    return _bravo_xlsx(
        "Danh mục vật tư hàng hóa",
        B06_HEADERS,
        [
            [
                "05-01-0001",
                WIRE,
                "m",
                "Cuon",
                "610.000000000",
                "Thành phẩm",
                "SPV-1-1",
                "P-30K",
                610,
                "HK",
                "BP1",
            ],
            [
                "05-01-0002",
                CABLE,
                "m",
                "km,m",
                "0.001000000,1.000000000",
                "Thành phẩm",
                "SPV-2-1;SPV-2-2",
                "Coil",
                0,
                "CA",
                None,
            ],
            [
                "35-00-0001",
                "Cable assembly - ASSY-0001",
                "Pcs",
                None,
                None,
                "Thành phẩm",
                None,
                "bag",
                0,
                None,
                None,
            ],
            # Two units and one factor: which unit it is for is not written.
            [
                "05-01-0003",
                WIRE,
                "m",
                "km,m",
                "0.001000000",
                "Thành phẩm",
                None,
                "Coil",
                305,
                "HK",
                None,
            ],
        ],
    )


def _b04() -> bytes:
    day = "2026-11-09"
    return _bravo_xlsx(
        "Converting customer to PRV item",
        B04_HEADERS,
        [
            # The same customer words name a different item at each customer.
            [
                day,
                "05-01-0001",
                WIRE,
                "SPV-1-1",
                "FG00000001",
                "Alpha Wire Co",
                "WIRE-24-WH",
                None,
                None,
                None,
                "Customer code-->old code",
                1,
            ],
            [
                day,
                "05-01-0002",
                CABLE,
                None,
                "FG00000002",
                "Group Cable East",
                "WIRE-24-WH",
                None,
                None,
                None,
                None,
                2,
            ],
            # A converting description in the customer's own words.
            [
                day,
                "05-01-0002",
                CABLE,
                None,
                "FG00000001",
                "Alpha Wire Co",
                "UL2464 3x17AWG BK CABLE (SPV2)",
                None,
                None,
                None,
                None,
                3,
            ],
            # No converting description: refused with why, never guessed.
            [
                day,
                "05-01-0001",
                WIRE,
                None,
                "FG00000002",
                "Group Cable East",
                None,
                "WIRE 24",
                None,
                None,
                None,
                4,
            ],
            [
                day,
                "05-01-0001",
                WIRE,
                None,
                "IC0001",
                "End User Ltd",
                "EU-1",
                None,
                None,
                None,
                None,
                5,
            ],
            [
                day,
                "99-99-9999",
                "Gone",
                None,
                "FG00000001",
                "Alpha Wire Co",
                "OLD-1",
                None,
                None,
                None,
                None,
                6,
            ],
            [
                day,
                "05-01-0001",
                WIRE,
                None,
                "FG09999999",
                "Unknown",
                "UNK-1",
                None,
                None,
                None,
                None,
                7,
            ],
        ],
        group="3. Đã duyệt (synthetic)",
    )


async def _read(data: bytes, world: World) -> ImportedTable:
    reader = ClientTableReader(InProcessReaderTransport(), world.policies.order_rules.intake)
    return await reader.read(data, "bravo.xlsx")


async def _approved(world: World, catalog_list: CatalogList, data: bytes) -> Any:
    view = await world.services.catalog_imports.upload(
        AN.context(), catalog_list, "bravo.xlsx", data
    )
    await world.read_imports()
    preview = await world.services.catalog_imports.preview(AN.context(), view.snapshot_id)
    if preview.snapshot.status == "parsed":
        await world.services.catalog_imports.submit(AN.context(), view.snapshot_id)
        await world.decide_catalog(GIANG, view.snapshot_id, approve=True, comment="Đồng ý")
    return preview


# ------------------------------------------------------------ the header --


def test_the_header_is_found_by_its_titles_under_a_title_and_its_hints() -> None:
    customers = SPECS[CatalogList.CUSTOMERS].columns
    rows = [
        TableRow(row=1, cells=["Danh mục", None, None, None, None, None, "@x.example", "vi/en"]),
        TableRow(row=2, cells=[*B05_HEADERS]),
        TableRow(row=3, cells=["A1", "B", "C", "D", "E", "F", None, 7]),
    ]
    assert find_header(rows, customers).index == 1
    # The template's own file: its first row is its header.
    assert find_header(rows[1:], customers).index == 0
    # A two-column list (LME) whose data rows are text too.
    lme = [TableRow(row=1, cells=["Tháng", "Giá LME"]), TableRow(row=2, cells=["01/2026", "9500"])]
    assert find_header(lme, SPECS[CatalogList.LME].columns).index == 0


# ------------------------------------------------------------ the reader --


async def test_the_reader_leaves_out_a_group_label_row_by_its_shape() -> None:
    """A label merged across the row with only a formula beside it labels a
    group; a title, merged with no formula, does not, and stays for the
    header search to pass over."""
    table = await _read(_b04(), _world())
    numbers = [r.row for r in table.rows]

    assert numbers[:2] == [1, 2] and 3 not in numbers
    assert numbers[2:] == list(range(4, 11))


# ------------------------------------------------------ each list as read --


async def test_bravos_customer_list_reads_as_exported() -> None:
    parsed = parse_rows(CatalogList.CUSTOMERS, await _read(_b05(), _world()))
    customers = {p.record.code: p.record for p in parsed.records if isinstance(p.record, Customer)}

    assert sorted(customers) == [
        "FG00000001",
        "FG00000002",
        "FG00000003",
        "FG00000004",
        "IC0001",
        "TDC0001",
    ]
    assert customers["FG00000004"].language == "vi"
    alpha = customers["FG00000001"]
    # Both of Bravo's "E-mail liên hệ" columns are the customer's contacts.
    assert [c.address for c in alpha.contacts] == ["buyer@alpha.example", "backup@alpha.example"]
    assert (alpha.email_domains, alpha.language, alpha.group) == (
        ("alpha.example",),
        "en",
        "direct",
    )
    # Bravo has no NOC, intra-group or channel column: none is confirmed,
    # and a confirmation is a mail draft.
    assert alpha.compliance.noc_confirmed is False
    assert (alpha.intra_group, alpha.confirmation_channel) == (False, "email")
    # A domain two customers claim recognises neither; their contacts stay.
    east, west = customers["FG00000002"], customers["FG00000003"]
    assert east.email_domains == west.email_domains == ()
    assert [c.address for c in west.contacts] == ["d.west@group.example"]
    assert (customers["TDC0001"].status, customers["IC0001"].status) == ("temporary", "official")
    assert customers["IC0001"].group == "indirect"
    assert [(r.row, r.column) for r in parsed.rejected] == [
        (0, "Tên miền email"),
        (9, "Ngôn ngữ"),
        (10, "Email liên hệ"),
    ]
    assert "Payment terms (Acc)" in parsed.unknown_headers


async def test_bravos_item_master_reads_as_exported() -> None:
    parsed = parse_rows(CatalogList.ITEMS, await _read(_b06(), _world()))
    items = {p.record.prv_code: p.record for p in parsed.records if isinstance(p.record, Item)}

    wire, cable, assembly = items["05-01-0001"], items["05-01-0002"], items["35-00-0001"]
    assert (wire.name, wire.unit, wire.uom, wire.pack_multiple) == (WIRE, "m", "m", Decimal(610))
    assert [(c.unit, c.factor) for c in wire.conversions] == [("Cuon", Decimal(610))]
    assert [(c.unit, c.factor) for c in cable.conversions] == [
        ("km", Decimal("0.001")),
        ("m", Decimal(1)),
    ]
    # Unit Packing 0 is "not known", never a pack of nothing.
    assert cable.pack_multiple is None
    # A unit DW1 has no word for keeps Bravo's spelling; DW1's is None.
    assert (assembly.unit, assembly.uom) == ("Pcs", None)
    assert (wire.category, wire.bp_code, wire.packaging_style, cable.specification) == (
        "HK",
        "BP1",
        "P-30K",
        "SPV-2-1;SPV-2-2",
    )
    assert (wire.moq, wire.standard_lead_time_days) == (None, None)
    # The attributes are read from the name's spec string.
    attributes = wire.attributes
    assert (attributes.standard, attributes.cores, attributes.gauge) == ("UL1007", 1, "AWG24")
    assert (attributes.stranding, attributes.colour) == ("stranded", "white")
    assert [(r.row, r.column) for r in parsed.rejected] == [(6, "Hệ số quy đổi")]


async def test_bravos_convert_list_reads_as_exported_with_every_refusal_said() -> None:
    world = _world()
    await _approved(world, CatalogList.CUSTOMERS, _b05())
    await _approved(world, CatalogList.ITEMS, _b06())
    preview = await _approved(world, CatalogList.CONVERT_LIST, _b04())

    assert preview.snapshot.status == "parsed"
    assert preview.snapshot.row_count == 3
    assert {r.key for r in preview.added} == {
        "FG00000001 · WIRE-24-WH",
        "FG00000002 · WIRE-24-WH",
        "FG00000001 · UL2464 3x17AWG BK CABLE (SPV2)",
    }
    reasons = [(r.row, r.column, r.reason) for r in preview.rejected]
    assert reasons == [
        (7, "Mã hàng của khách", "thiếu giá trị"),
        (
            8,
            "Mã khách hàng",
            "khách hàng IC0001 là khách gián tiếp: bảng quy đổi ghi theo khách trực tiếp",
        ),
        (9, "Mã PRV", "mã 99-99-9999 chưa có trong danh mục mã hàng"),
        (10, "Mã khách hàng", "khách hàng FG09999999 chưa có trong danh mục khách hàng"),
    ]
    assert preview.rejected_count == 4


# ----------------------------------------- one customer's mapping is its own --


def _po_line(code: str, description: str = "") -> PoLine:
    anchor = SourceAnchor(attachment_id="A1", attachment_sha256="b" * 64, cell_ref="PO!B10")
    return PoLine(
        line_no=1,
        customer_item_code=code,
        description=description,
        quantity=Decimal(610),
        uom="m",
        unit_price=Decimal("0.05"),
        amount=Decimal("30.5"),
        requested_date=date(2026, 12, 4),
        anchors=PoLineAnchors(**dict.fromkeys(PoLineAnchors.model_fields, anchor)),
    )


async def test_one_customers_words_never_take_another_customers_mapping() -> None:
    """B04 holds 66 converting descriptions that name different items at
    different customers. A line is looked up under its own customer only, by
    its code, else by its description; a customer with no row has none."""
    world = _world()
    await _approved(world, CatalogList.CUSTOMERS, _b05())
    await _approved(world, CatalogList.ITEMS, _b06())
    await _approved(world, CatalogList.CONVERT_LIST, _b04())
    catalog = world.services.catalog_imports.catalog

    async def mapped(customer: str, line: PoLine) -> str | None:
        entry = (await _convert_entry(catalog, ALPHA, customer, line)).data
        return None if entry is None else entry.prv_code

    same = _po_line("WIRE-24-WH")
    assert await mapped("FG00000001", same) == "05-01-0001"
    assert await mapped("FG00000002", same) == "05-01-0002"
    assert await mapped("FG00000003", same) is None
    # By description where the PO's code is not the customer's key.
    worded = _po_line("L-0001", "UL2464 3x17AWG BK CABLE (SPV2)")
    assert await mapped("FG00000001", worded) == "05-01-0002"
    assert await mapped("FG00000002", worded) is None


async def test_two_group_companies_on_one_domain_are_told_apart_by_their_contacts() -> None:
    """Ticket 20 on Bravo's own list: both claim the group's domain, so it
    recognises neither (`_unshared`); each is known by its contacts'
    addresses, and an address neither lists is a person's to place."""
    world = _world()
    await _approved(world, CatalogList.CUSTOMERS, _b05())
    catalog = world.services.catalog_imports.catalog

    async def code(address: str) -> str | None:
        found = (await catalog.customer_by_sender(ALPHA, address)).data
        return None if found is None else found.code

    assert await code("c.east@group.example") == "FG00000002"
    assert await code("D.West@group.example") == "FG00000003"
    assert await code("someone@group.example") is None
    assert await code("backup@alpha.example") == "FG00000001"


async def test_a_customer_with_no_rows_gets_candidates_and_keeps_what_the_pic_confirms() -> None:
    """Ticket 21: Group Cable West has no row in the convert list. Its line is
    never mapped through another customer's row for the same words: it is
    unmapped, with the item master's candidates by description, never exact.
    The code the PIC confirms (`OrderCommands.confirm_mapping`'s hook,
    `test_convert_learning.py`) is kept for that customer alone, and its next
    PO maps through it."""
    world = _world()
    await _approved(world, CatalogList.CUSTOMERS, _b05())
    await _approved(world, CatalogList.ITEMS, _b06())
    await _approved(world, CatalogList.CONVERT_LIST, _b04())
    catalog = world.services.catalog_imports.catalog
    assert isinstance(catalog, SnapshotSalesCatalog)
    items = (await catalog.items(ALPHA)).data

    async def mapping(customer: str, line: PoLine) -> tuple[str, str | None, tuple[str, ...]]:
        entry = (await _convert_entry(catalog, ALPHA, customer, line)).data
        mapped = map_line(line, entry=entry, items=items)
        return mapped.mapping.status, mapped.convert_prv_code, mapped.mapping.candidates

    # Customer 1's code, and customer 1's own words for an item, as customer 3 prints them.
    by_code = _po_line("WIRE-24-WH", "UL1007 AWG24 WHITE")
    worded = _po_line("UL2464 3x17AWG BK CABLE (SPV2)", "UL2464 3x17AWG BK CABLE (SPV2)")
    for line in (by_code, worded):
        status, listed, _ = await mapping("FG00000003", line)
        assert status != "exact" and listed is None
    assert await mapping("FG00000003", by_code) == ("candidate", None, ("05-01-0001",))

    await catalog.learn_convert(
        ALPHA,
        ConvertEntry(
            customer_code="FG00000003", customer_item_code="WIRE-24-WH", prv_code="05-01-0002"
        ),
        by=AN.user_id,
        case_id=uuid.UUID(int=21),
    )

    assert await mapping("FG00000003", by_code) == ("exact", "05-01-0002", ())
    # Every other customer's line reads as before.
    assert (await mapping("FG00000001", by_code))[:2] == ("exact", "05-01-0001")
    assert (await mapping("FG00000002", by_code))[:2] == ("exact", "05-01-0002")
    assert (await mapping("TDC0001", by_code))[:2] == ("candidate", None)


# ------------------------------------------------------ the name's grammar --


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (
            WIRE,
            {
                "standard": "UL1007",
                "cores": 1,
                "gauge": "AWG24",
                "strands": 11,
                "strand_mm": Decimal("0.16"),
                "colour": "white",
            },
        ),
        (
            CABLE,
            {
                "standard": "UL2464",
                "cores": 3,
                "gauge": "AWG17",
                "strands": 50,
                "strand_mm": Decimal("0.18"),
            },
        ),
        (
            "Cabling - XX-FHV (FLEX) 24x0.3SQ(60/0.08TA) LF BK C100",
            {"cores": 24, "gauge": "0.3mm2", "strands": 60, "strand_mm": Decimal("0.08")},
        ),
        (
            "Hook up wire - UL1007 LF (EC1) 16AWG 54/0.18TA BL C305",
            {"standard": "UL1007", "gauge": "AWG16", "strands": 54, "strand_mm": Decimal("0.18")},
        ),
        (
            "UL1061(SPV004) AWG24(11/0.16) GRAY WIRE",
            {
                "standard": "UL1061",
                "gauge": "AWG24",
                "strands": 11,
                "strand_mm": Decimal("0.16"),
                "colour": "grey",
            },
        ),
        (
            "Irradiating wire - UL1430 AWM 1x26AWG(7/0.16TA) LF LIGHT BLUE C610",
            {
                "standard": "UL1430",
                "cores": 1,
                "gauge": "AWG26",
                "strands": 7,
                "strand_mm": Decimal("0.16"),
            },
        ),
        (
            "Twisted - UL1007 2x24AWG(1/0.5) LF RED, BLACK",
            {
                "standard": "UL1007",
                "cores": 2,
                "gauge": "AWG24",
                "strands": 1,
                "strand_mm": Decimal("0.5"),
            },
        ),
        ("Cable assembly - ASSY-0001", {}),
    ],
    ids=[
        "wire",
        "cable",
        "section",
        "size_alone",
        "awg_first",
        "light_blue",
        "two_colours",
        "none",
    ],
)
def test_a_prv_name_is_read_by_its_spec_string(name: str, expected: dict[str, object]) -> None:
    assert read_name(name).model_dump(exclude_none=True) == expected


def test_a_real_item_is_a_candidate_only_for_what_its_name_states() -> None:
    """The matcher compares a real item by the attributes its name gave; one
    its name does not state never fits a stated value."""
    table = ImportedTable(
        sheet="x",
        rows=[
            TableRow(row=1, cells=["Mã", "Tên vật tư", "Đvt", "Unit Packing"]),
            TableRow(row=2, cells=["05-01-0001", WIRE, "m", 610]),
            TableRow(
                row=3, cells=["05-01-0009", "Hook up wire - UL1007 1X24AWG(11/0.16) LF", "m", 610]
            ),
        ],
    )
    items = [p.record for p in parse_rows(CatalogList.ITEMS, table).records]
    assert all(isinstance(i, Item) for i in items)
    typed = [i for i in items if isinstance(i, Item)]

    white = StatedAttributes(cores=1, gauge="AWG24", colour="white", standard="UL1007")
    assert [i.prv_code for i in candidates(white, typed)] == ["05-01-0001"]
    assert [i.prv_code for i in candidates(StatedAttributes(gauge="AWG24"), typed)] == [
        "05-01-0001",
        "05-01-0009",
    ]


def test_a_convert_entry_keeps_the_customers_words_as_printed() -> None:
    entry = ConvertEntry(
        customer_code="FG00000001",
        customer_item_code="UL1061(SPV004) AWG24(11/0.16) GRAY WIRE",
        prv_code="05-01-0001",
    )
    assert entry.customer_item_code.endswith("GRAY WIRE")
    with pytest.raises(ValueError, match="customer_item_code"):
        ConvertEntry(
            customer_code="FG00000001", customer_item_code=" padded", prv_code="05-01-0001"
        )
