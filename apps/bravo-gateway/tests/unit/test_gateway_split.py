# ruff: noqa: E501 - the layout below is XML kept on the lines Bravo would write it
"""Ticket 73: splitting an SO line as a person does it on the SO screen.

A small layout written for these tests in the SO screen's own rule shapes
(layout 8212's `Eval_QuantityGroup_GetVaule`, `Eval_Detail_Divi_GetData`,
`Eval_Detail_OriginalQuantity_SetValue`, `CheckDivide`), no Bravo data. The
client's own statements for a traced split are
`test_gateway_trace_replay.test_a_traced_split_is_the_clients_own_statement`.

`so.line.split@1` is still pending (its UAT split is not traced): each test
here lifts it to exercise what follows the kind check, and the first test
shows the shipped contract holds it back.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal

import pytest
from gateway_fakes import (
    LINE,
    ROWVERSION,
    FakeEngine,
    Gateway,
    gateway,
    token,
)

from dw_bravo.contract import WRITE_KINDS, ContractError, SetQuantity, SplitLine, SplitPart
from dw_bravo.expression import UndecidableError
from dw_bravo.layout import read_layout
from dw_bravo_gateway.pipeline import AddRow, Edit, group_label, typed_edits
from dw_bravo_gateway.ports import ColumnRight, StoredDocument
from dw_bravo_gateway.statements import UnmeasuredError, render_insert

pytestmark = pytest.mark.unit

SPLIT_LAYOUT = """<root><Tables>
<ParentTable>
  <Name>vB30BizDoc_Edit</Name>
  <Evaluators>
    <Eval_Total><DataMember>TotalQuantity</DataMember><Value>SUM(Detail.Quantity9)</Value></Eval_Total>
  </Evaluators>
  <ServerUpdating><Eval_Order /></ServerUpdating>
</ParentTable>
<ChildTable_Detail>
  <Name>vB30BizDocDetailSO_Edit</Name><Alias>Detail</Alias><ParentKey>BizDocId</ParentKey><ChildKey>BizDocId</ChildKey>
  <RowAdded><Eval_DocDate /></RowAdded>
  <ColumnChanged>
    <Quantity9><Eval_Amount9 /><Eval_Total /><Eval_OriginalQuantity /><Eval_BeforeDivi /></Quantity9>
    <OriginalUnitCost><Eval_Amount9 /></OriginalUnitCost>
    <Divide><Eval_QuantityGroup_GetVaule /><Eval_QuantityGroup_ResetValue /></Divide>
    <GroupDivi><Eval_Detail_Divi_GetData /><Eval_BeforeDivi /></GroupDivi>
  </ColumnChanged>
  <Evaluators>
    <Eval_DocDate><DataMember>DocDate</DataMember><Value>Parent.DocDate</Value></Eval_DocDate>
    <Eval_Amount9><DataMember>Amount9</DataMember><Value>ISNULL(Quantity9,0) * ISNULL(OriginalUnitCost,0)</Value></Eval_Amount9>
    <Eval_OriginalQuantity><DataMember>OriginalQuantity</DataMember><Value>Quantity9</Value><Expr>Id &lt; 0</Expr></Eval_OriginalQuantity>
    <Eval_QuantityGroup_GetVaule><DataMember>QuantityGroup</DataMember><Value>Quantity9</Value><Expr>!Empty(Divide)</Expr></Eval_QuantityGroup_GetVaule>
    <Eval_QuantityGroup_ResetValue><DataMember>QuantityGroup</DataMember><Value>0</Value><Expr>Empty(Divide)</Expr></Eval_QuantityGroup_ResetValue>
    <Eval_Detail_Divi_GetData><ClassName>BravoCopyValue</ClassName><Expr>!Empty(GroupDivi) AND Empty(Divide)</Expr>
      <CopyValues>
        <ItemCode>VLOOKUP(Detail,ItemCode, !Empty(Divide) AND GroupDivi='{=ISNULL(GroupDivi,'')}')</ItemCode>
        <POLine>VLOOKUP(Detail,POLine, !Empty(Divide) AND GroupDivi='{=ISNULL(GroupDivi,'')}')</POLine>
        <Length>VLOOKUP(Detail,Length, !Empty(Divide) AND GroupDivi='{=ISNULL(GroupDivi,'')}')</Length>
        <OriginalUnitCost>VLOOKUP(Detail,OriginalUnitCost, !Empty(Divide) AND GroupDivi='{=ISNULL(GroupDivi,'')}')</OriginalUnitCost>
      </CopyValues></Eval_Detail_Divi_GetData>
    <Eval_BeforeDivi><DataMember>QuantityGroupBeforeDivi</DataMember><Value>SUMIF(Detail.Quantity9,GroupDivi='{=ISNULL(GroupDivi,'')}')</Value><zScopeExpr>!Empty(GroupDivi)</zScopeExpr><Expr>!Empty(GroupDivi)</Expr></Eval_BeforeDivi>
    <Eval_Order><ClassName>BravoTableOrderer</ClassName><DataMember>BuiltinOrder</DataMember></Eval_Order>
  </Evaluators>
  <TempColumns><QuantityGroupBeforeDivi><DataType>System.Decimal</DataType></QuantityGroupBeforeDivi></TempColumns>
  <Validators>
    <CheckDivide><ClassName>BravoValidator</ClassName><SourceColumn>QuantityGroup,QuantityGroupBeforeDivi</SourceColumn>
      <zValidateExpr>Empty(Divide) OR (!Empty(Divide) AND QuantityGroup == QuantityGroupBeforeDivi)</zValidateExpr></CheckDivide>
    <NewLineHasItem><ClassName>BravoValidator</ClassName><SourceColumn>ItemCode</SourceColumn>
      <Expr>Id &lt; 0</Expr><zValidateExpr>!Empty(ItemCode)</zValidateExpr></NewLineHasItem>
  </Validators>
</ChildTable_Detail>
</Tables></root>"""

LINE_COLUMNS = [
    "Id",
    "BizDocId",
    "BuiltinOrder",
    "DocDate",
    "RowId",
    "ItemCode",
    "EstimatedTimeDelivery",
    "Quantity9",
    "OriginalUnitCost",
    "Amount9",
    "IsCancel",
    "CreatedBy",
    "CreatedAt",
    "ModifiedBy",
    "ModifiedAt",
    "timestamp",
    "Length",
    "POLine",
    "OriginalQuantity",
    "QuantityGroup",
    "GroupDivi",
    "Divide",
    "PCNote",  # the table's, not the view's: a new line never lists it
]
# What the line's load view holds: the table's columns but PCNote, and a
# column it joins in (`ItemName`), which no INSERT lists either.
VIEW = [c for c in LINE_COLUMNS if c != "PCNote"] + ["ItemName"]

SPLIT = SplitLine(line=LINE, parts=(SplitPart(Decimal(150)), SplitPart(Decimal(100))))


def _line(**over: object) -> dict[str, object]:
    line: dict[str, object] = {
        "Id": 20,
        "BizDocId": "D10",
        "BuiltinOrder": Decimal(1),
        "DocDate": datetime(2026, 11, 20),
        "RowId": "R20",
        "ItemCode": "PRV-1",
        "EstimatedTimeDelivery": None,
        "Quantity9": Decimal(250),
        "OriginalUnitCost": Decimal(2),
        "Amount9": Decimal(500),
        "IsCancel": "",
        "CreatedBy": 1,
        "CreatedAt": datetime(2026, 11, 20),
        "ModifiedBy": 1,
        "ModifiedAt": datetime(2026, 11, 20),
        "timestamp": ROWVERSION,
        "Length": Decimal(500),
        "POLine": Decimal(3),
        "OriginalQuantity": Decimal(250),
        "QuantityGroup": Decimal(0),
        "GroupDivi": "",
        "Divide": Decimal(0),
        "PCNote": None,
    }
    return line | over


def _stored(*lines: dict[str, object]) -> StoredDocument:
    return StoredDocument(
        header={
            "Id": 10,
            "BizDocId": "D10",
            "BranchCode": "A01",
            "DocDate": datetime(2026, 11, 20),
            "TotalQuantity": Decimal(250),
            "ModifiedBy": 1,
            "timestamp": "0x00000000000007D1",
        },
        lines=[dict(x) for x in lines] or [_line()],
        column_order={
            "B30BizDoc": ["Id", "BizDocId", "BranchCode", "DocDate", "ModifiedBy", "TotalQuantity"],
            "B30BizDocDetailSO": LINE_COLUMNS,
        },
        prevent_edit={str(x.get("RowId")): 0 for x in (lines or [_line()])},
        no_default={
            "B30BizDocDetailSO": frozenset(
                {"bizdocid", "docdate", "estimatedtimedelivery", "pcnote"}
            )
        },
        generated={"B30BizDocDetailSO": frozenset({"id", "timestamp"})},
    )


def _gateway(*lines: dict[str, object]) -> Gateway:
    gw = gateway(
        engine=FakeEngine(
            read_layout(SPLIT_LAYOUT, "EDIT_BizDocSO"), views={"vB30BizDocDetailSO_Edit": VIEW}
        )
    )
    gw.bravo.document = _stored(*lines)
    return gw


@pytest.fixture
def unpended(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    key = "so.line.split@1"
    monkeypatch.setitem(WRITE_KINDS, key, replace(WRITE_KINDS[key], pending=None))
    yield


async def test_the_shipped_contract_holds_a_split_back_until_its_uat_split_is_traced() -> None:
    gw = _gateway()
    result = await gw.pipeline.execute(SPLIT, token(SPLIT))
    assert result.check == "kind" and (result.reason or "").startswith("pending: ")
    assert gw.bravo.batches == []


def test_a_split_is_typed_in_the_order_the_screen_allows() -> None:
    assert typed_edits(SPLIT, group="1") == [
        Edit("Detail", "Divide", Decimal(1)),
        Edit("Detail", "GroupDivi", "1"),
        Edit("Detail", "Quantity9", Decimal(150)),
        AddRow("Detail"),
        Edit("Detail", "GroupDivi", "1", new_row=0),
        Edit("Detail", "Quantity9", Decimal(100), new_row=0),
    ]


@pytest.mark.usefixtures("unpended")
async def test_a_split_saves_as_an_edit_with_the_new_line_inserted_before_the_lines_update() -> (
    None
):
    gw = _gateway()

    result = await gw.pipeline.execute(SPLIT, token(SPLIT))

    assert result.outcome == "written", result
    [batch] = gw.bravo.batches
    assert batch.context.startswith("EDIT_BizDocSO|Edit ")
    assert [(s.table, s.sql.split(" ", 1)[0]) for s in batch.statements] == [
        ("B30BizDoc", "UPDATE"),
        ("B30BizDocDetailSO", "INSERT"),
        ("B30BizDocDetailSO", "UPDATE"),
    ]
    _, insert, head = batch.statements
    assert head.parameters["_Divide"] == Decimal(1)
    assert head.parameters["_GroupDivi"] == "1"
    assert head.parameters["_Quantity9"] == Decimal(150)
    assert head.parameters["_QuantityGroup"] == Decimal(250)  # the whole, typed before
    assert insert.row_id is None and "_Id" not in insert.parameters
    assert "_timestamp" not in insert.parameters
    assert insert.sql.endswith("FROM B30BizDocDetailSO WHERE Id=SCOPE_IDENTITY();")
    # The head's columns, copied by the layout's rule, not by code.
    assert {k: insert.parameters[k] for k in ("_ItemCode", "_POLine", "_Length")} == {
        "_ItemCode": "PRV-1",
        "_POLine": Decimal(3),
        "_Length": Decimal(500),
    }
    assert insert.parameters["_OriginalUnitCost"] == Decimal(2)
    assert insert.parameters["_Quantity9"] == Decimal(100)
    assert insert.parameters["_OriginalQuantity"] == Decimal(100)  # `Id < 0`
    assert insert.parameters["_GroupDivi"] == "1"
    assert insert.parameters["_BizDocId"] == "D10"  # the layout's relation key
    assert insert.parameters["_BuiltinOrder"] == Decimal(2)
    assert insert.parameters["_RowId"] == ""  # Bravo's trigger fills it
    assert insert.parameters["_CreatedBy"] == Decimal(2413)
    # A NULL with no default is listed NULL; one with a default is not, nor
    # anything the view does not store, nor what the table generates.
    assert (
        "[EstimatedTimeDelivery]" in insert.sql
        and insert.parameters["_EstimatedTimeDelivery"] is None
    )
    for absent in ("PCNote", "ItemName", "ModifiedBy", "CreatedAt", "IsCancel"):
        assert f"[{absent}]" not in insert.sql
    assert [line["RowId"] for line in gw.bravo.document.lines] == ["R20", "R21"]


@pytest.mark.usefixtures("unpended")
async def test_parts_that_do_not_add_up_are_blocked_by_the_layouts_check() -> None:
    gw = _gateway()
    short = SplitLine(line=LINE, parts=(SplitPart(Decimal(150)), SplitPart(Decimal(90))))
    approval = uuid.uuid4()

    result = await gw.pipeline.execute(short, token(short, approval=approval))

    assert (result.check, result.reason) == ("rules", "blocked: CheckDivide")
    assert approval not in gw.ledger.entries and gw.bravo.batches == []


@pytest.mark.usefixtures("unpended")
async def test_the_layouts_checks_run_over_the_new_line_too() -> None:
    # A validator only a new line answers (`Id < 0`): the head held no item
    # to copy, so the new line has none.
    gw = _gateway(_line(ItemCode=""))

    result = await gw.pipeline.execute(SPLIT, token(SPLIT))

    assert (result.check, result.reason) == ("rules", "blocked: NewLineHasItem")
    assert gw.bravo.batches == []


@pytest.mark.parametrize(
    ("lines", "reason"),
    [
        ((_line(Divide=Decimal(1), GroupDivi="1"),), "a split of a line already in a split group"),
        (
            (
                _line(
                    Id=19, RowId="R19", Divide=Decimal(1), GroupDivi="1", BuiltinOrder=Decimal(1)
                ),
                _line(GroupDivi="1", BuiltinOrder=Decimal(2)),
            ),
            "a split of a line already in a split group",
        ),
        (
            (_line(), _line(Id=21, RowId="R21", BuiltinOrder=Decimal(2))),
            "a split of a line other lines follow",
        ),
    ],
    ids=["head_of_a_group", "part_of_a_group", "not_the_last_line"],
)
@pytest.mark.usefixtures("unpended")
async def test_a_split_no_trace_shows_is_refused_before_the_approval_is_spent(
    lines: tuple[dict[str, object], ...], reason: str
) -> None:
    gw = _gateway(*lines)
    approval = uuid.uuid4()

    result = await gw.pipeline.execute(SPLIT, token(SPLIT, approval=approval))

    assert (result.check, result.reason) == ("rules", f"unmeasured: {reason}")
    assert approval not in gw.ledger.entries and gw.bravo.batches == []


@pytest.mark.parametrize("part", [0, 1], ids=["on_the_line", "on_a_new_line"])
@pytest.mark.usefixtures("unpended")
async def test_a_confirmed_date_on_a_split_part_is_refused_as_unmeasured(part: int) -> None:
    parts = [SplitPart(Decimal(150)), SplitPart(Decimal(100))]
    parts[part] = replace(parts[part], confirmed_date=date(2026, 12, 2))
    dated = SplitLine(line=LINE, parts=tuple(parts))
    gw = _gateway()
    approval = uuid.uuid4()

    result = await gw.pipeline.execute(dated, token(dated, approval=approval))

    assert (result.check, result.reason) == (
        "rules",
        "unmeasured: a confirmed date on a split part",
    )
    assert approval not in gw.ledger.entries and gw.bravo.batches == []


def test_group_label_picks_the_smallest_number_no_other_line_uses() -> None:
    assert group_label(_stored(_line()), 0) == "1"
    # The line's own stale label is not kept (11-25: '2' became '1').
    assert group_label(_stored(_line(GroupDivi="2")), 0) == "1"
    used = _stored(_line(Id=18, GroupDivi="1"), _line(Id=19, GroupDivi="A"), _line(GroupDivi="2"))
    assert group_label(used, 2) == "2"
    taken = _stored(_line(Id=18, GroupDivi="1"), _line(Id=19, GroupDivi="2"), _line())
    assert group_label(taken, 2) == "3"


@pytest.mark.usefixtures("unpended")
async def test_a_split_asks_both_the_edit_and_the_new_right() -> None:
    # Whether a grid line added to a stored SO needs Bravo's New right is not
    # measured (ticket 75): either refusal refuses.
    gw = _gateway()
    gw.rights.by_operation = {"insert": "denied"}

    result = await gw.pipeline.execute(SPLIT, token(SPLIT))

    assert (result.check, result.reason) == ("right", "command_right_denied")
    assert gw.rights.asked == ["update", "insert"]
    assert gw.bravo.batches == []


@pytest.mark.parametrize(
    ("right", "command"),
    [
        (ColumnRight("B30BizDocDetailSO", "Quantity9", no_add_new=True, no_edit=False), SPLIT),
        (ColumnRight("B30BizDocDetailSO", "Divide", no_add_new=False, no_edit=True), SPLIT),
    ],
    ids=["no_add_new_on_the_new_line", "no_edit_on_the_line"],
)
@pytest.mark.usefixtures("unpended")
async def test_column_rights_bar_the_new_line_by_add_new_and_the_line_by_edit(
    right: ColumnRight, command: SplitLine
) -> None:
    gw = _gateway()
    gw.rights.columns = [right]

    result = await gw.pipeline.execute(command, token(command))

    assert (result.check, result.reason) == ("right", f"no_right_on_{right.column}")


async def test_an_add_new_bar_does_not_touch_an_edit_of_a_stored_line() -> None:
    gw = gateway()
    gw.rights.columns = [ColumnRight("B30BizDocDetailSO", "Quantity9", True, False)]
    command = SetQuantity(line=LINE, quantity=Decimal(5))

    result = await gw.pipeline.execute(command, token(command))

    assert result.outcome == "written", result
    assert gw.rights.asked == ["update"]


@pytest.mark.usefixtures("unpended")
async def test_the_lock_is_checked_on_the_line_and_not_on_the_new_one() -> None:
    gw = _gateway()
    gw.bravo.document.prevent_edit = {"R20": 1}

    result = await gw.pipeline.execute(SPLIT, token(SPLIT))

    assert (result.check, result.reason) == ("lock", "line_locked_or_could_not_check")
    assert gw.bravo.batches == []


@pytest.mark.parametrize(
    ("bravo", "difference"),
    [
        ({"tamper_new": {"Quantity9": Decimal(99)}}, "Detail#1.Quantity9"),
        ({"fills_row_id": False}, "Detail#1.RowId: not filled"),
    ],
    ids=["new_line_held_differently", "rowid_left_empty"],
)
@pytest.mark.usefixtures("unpended")
async def test_a_new_line_bravo_holds_differently_is_a_difference(
    bravo: dict[str, object], difference: str
) -> None:
    gw = _gateway()
    for name, value in bravo.items():
        setattr(gw.bravo, name, value)

    result = await gw.pipeline.execute(SPLIT, token(SPLIT))

    assert result.outcome == "written_with_differences", result
    assert difference in result.differences


@pytest.mark.usefixtures("unpended")
async def test_a_new_line_bravo_does_not_hold_is_a_difference() -> None:
    gw = _gateway()
    real = gw.bravo.load
    loads = 0

    async def without_new_lines(screen: str, doc_id: int) -> StoredDocument:
        nonlocal loads
        loads += 1
        stored = await real(screen, doc_id)
        if loads > 1:
            stored.lines = [x for x in stored.lines if x["Id"] == 20]
        return stored

    gw.bravo.load = without_new_lines  # type: ignore[method-assign]

    result = await gw.pipeline.execute(SPLIT, token(SPLIT))

    assert result.outcome == "written_with_differences", result
    assert "Detail#1: row gone" in result.differences


@pytest.mark.usefixtures("unpended")
async def test_a_line_a_colleague_added_meanwhile_is_a_difference_not_a_match() -> None:
    gw = _gateway()
    real = gw.bravo.load
    loads = 0

    async def with_a_colleagues_line(screen: str, doc_id: int) -> StoredDocument:
        nonlocal loads
        loads += 1
        stored = await real(screen, doc_id)
        if loads > 1:
            stored.lines.append(_line(Id=99, RowId="R99", BuiltinOrder=Decimal(3)))
        return stored

    gw.bravo.load = with_a_colleagues_line  # type: ignore[method-assign]

    result = await gw.pipeline.execute(SPLIT, token(SPLIT))

    assert result.outcome == "written_with_differences", result
    assert result.differences == ("a line not planned: Id 99",)


@pytest.mark.parametrize(
    "unread",
    [{"generated": {}}, {"views": {}}],
    ids=["table_columns_not_read", "view_columns_not_read"],
)
@pytest.mark.usefixtures("unpended")
async def test_a_new_line_whose_columns_are_not_read_is_refused(unread: dict[str, object]) -> None:
    gw = _gateway()
    if "generated" in unread:
        gw.bravo.document.generated = {}
    else:
        gw.pipeline.engine.views = {}  # type: ignore[attr-defined]
    approval = uuid.uuid4()

    result = await gw.pipeline.execute(SPLIT, token(SPLIT, approval=approval))

    assert (result.check, result.reason) == (
        "rules",
        "unmeasured: the columns a new line of B30BizDocDetailSO holds",
    )
    assert approval not in gw.ledger.entries


@pytest.mark.usefixtures("unpended")
async def test_a_view_name_the_engine_will_not_read_is_a_refusal_not_an_error() -> None:
    # `SqlServerBravo.view_columns` refuses a layout `Name` it would have to
    # quote (`dbo.` or brackets, which an admin can type into Bravo's layout
    # row); that is an unread fact like any other, on the preview too.
    gw = _gateway()

    async def refuses(view: str) -> list[str]:
        raise UndecidableError(f"{view!r} is not a view name the layout gives")

    gw.pipeline.engine.view_columns = refuses  # type: ignore[method-assign]
    approval = uuid.uuid4()
    reason = (
        "unmeasured: the columns a new line of B30BizDocDetailSO holds:"
        " 'vB30BizDocDetailSO_Edit' is not a view name the layout gives"
    )

    result = await gw.pipeline.execute(SPLIT, token(SPLIT, approval=approval))
    preview = await gw.pipeline.preview(SPLIT, token(SPLIT))

    assert (result.outcome, result.check, result.reason) == ("refused", "rules", reason)
    assert (preview.batch, preview.check, preview.reason) == (None, "rules", reason)
    assert approval not in gw.ledger.entries and gw.bravo.batches == []


@pytest.mark.usefixtures("unpended")
async def test_a_split_in_three_inserts_each_new_line_in_order_and_reads_each_back() -> None:
    # Every other test splits in two, so `new_row` is only ever 0: this pins
    # the second new line's edits, its place in the order and the read-back
    # pairing new lines with the plan's inserts one by one.
    three = SplitLine(
        line=LINE, parts=(SplitPart(Decimal(100)), SplitPart(Decimal(90)), SplitPart(Decimal(60)))
    )
    gw = _gateway()

    result = await gw.pipeline.execute(three, token(three))

    assert result.outcome == "written", result
    [batch] = gw.bravo.batches
    _, first, second, head = batch.statements
    assert [(s.sql.split(" ", 1)[0], s.row_id) for s in (first, second, head)] == [
        ("INSERT", None),
        ("INSERT", None),
        ("UPDATE", 20),
    ]
    assert [
        {k: s.parameters[k] for k in ("_BuiltinOrder", "_Quantity9", "_OriginalQuantity")}
        for s in (first, second)
    ] == [
        {"_BuiltinOrder": Decimal(2), "_Quantity9": Decimal(90), "_OriginalQuantity": Decimal(90)},
        {"_BuiltinOrder": Decimal(3), "_Quantity9": Decimal(60), "_OriginalQuantity": Decimal(60)},
    ]
    assert first.parameters["_GroupDivi"] == second.parameters["_GroupDivi"] == "1"
    assert head.parameters["_Quantity9"] == Decimal(100)
    assert head.parameters["_QuantityGroup"] == Decimal(250)
    assert [(x["RowId"], x["Quantity9"]) for x in gw.bravo.document.lines] == [
        ("R20", Decimal(100)),
        ("R21", Decimal(90)),
        ("R22", Decimal(60)),
    ]


def test_an_insert_lists_what_the_row_holds_and_the_nulls_without_a_default() -> None:
    statement = render_insert(
        "B30BizDocDetailSO",
        {"BizDocId": "D1", "Quantity9": Decimal(3), "RowId": ""},
        ["BizDocId", "RowId", "ParentRowId", "TaxCode", "Quantity9"],
        frozenset({"bizdocid", "parentrowid"}),
        read_back_key="RowId",
    )
    assert statement.sql == (
        "INSERT INTO B30BizDocDetailSO ([BizDocId],[RowId],[ParentRowId],[Quantity9])"
        " VALUES (@_BizDocId,@_RowId,@_ParentRowId,@_Quantity9);"
        "SELECT TOP (1) Id,RowId,CreatedAt,ModifiedAt,timestamp FROM B30BizDocDetailSO"
        " WHERE Id=SCOPE_IDENTITY();"
    )
    assert statement.parameters == {
        "_BizDocId": "D1",
        "_RowId": "",
        "_ParentRowId": None,
        "_Quantity9": Decimal(3),
    }


@pytest.mark.parametrize(
    ("insertable", "match"),
    [([], "not read"), (["BizDocId"], "holds no column Quantity9")],
    ids=["columns_not_read", "a_column_the_row_does_not_hold"],
)
def test_an_insert_refuses_columns_it_cannot_check(insertable: list[str], match: str) -> None:
    # INSERT is granted on the whole table: this list is the only column guard.
    with pytest.raises(UnmeasuredError, match=match):
        render_insert(
            "B30BizDocDetailSO",
            {"BizDocId": "D1", "Quantity9": Decimal(3)},
            insertable,
            frozenset(),
            read_back_key="RowId",
        )


def test_a_split_has_two_to_ten_parts() -> None:
    with pytest.raises(ContractError):
        SplitLine(line=LINE, parts=(SplitPart(Decimal(1)),))
    assert SplitLine(line=LINE, parts=tuple(SplitPart(Decimal(1)) for _ in range(10)))
    with pytest.raises(ContractError, match="ten"):
        SplitLine(line=LINE, parts=tuple(SplitPart(Decimal(1)) for _ in range(11)))
