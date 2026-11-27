# ruff: noqa: E501 - the layouts below are XML kept on the lines Bravo would write them
"""A screen's window (its form layout, 8213 for the SO screen), read and run
(ticket 72), on layouts written for these tests in the shapes the SO screen
uses (no Bravo data): the grid's item lookup binds the item's columns into a
new line, and the DataSource's own rules then run on what it set, as 8212's
`Eval_Detail_QuantityBox_SetValue` does for a '-' carton."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal

import pytest

from dw_bravo.adapters.recorded import RecordedProcedures
from dw_bravo.expression import UNKNOWN, RuleRefusedError, UndecidableError, UnsupportedSyntaxError
from dw_bravo.layout import merge_windows, read_layout, read_window, with_window
from dw_bravo.ports import Session
from dw_bravo.runner import Document, Row, RuleRunner

pytestmark = pytest.mark.unit

DATA_SOURCE = """<root><Tables>
<ParentTable><Name>vDoc_Edit</Name></ParentTable>
<ChildTable_Detail><Name>vLine_Edit</Name><Alias>Detail</Alias>
  <ParentKey>DocKey</ParentKey><ChildKey>DocKey</ChildKey>
  <ColumnChanged>
    <CartonSize><Eval_QuantityBox /></CartonSize>
    <QuantityBox><Eval_QuantityBox /></QuantityBox>
    <Unit_Item><Eval_Unit /></Unit_Item>
  </ColumnChanged>
  <Evaluators>
    <Eval_QuantityBox><DataMember>QuantityBox</DataMember><Value>1</Value><Expr>CartonSize='-'</Expr></Eval_QuantityBox>
    <Eval_Unit><DataMember>Unit</DataMember><Value>Unit_Item</Value></Eval_Unit>
  </Evaluators>
</ChildTable_Detail>
</Tables></root>"""

WINDOW = """<root><menuStrip1 /><panelEditor><Controls>
<General><Controls>
  <lookupCustomerCode><bindingMembers><Name>CustomerName</Name><CustomerCurrencyCode>CurrencyCode</CustomerCurrencyCode></bindingMembers>
    <ClassName>BravoLookupBox</ClassName><DataMember>CustomerCode</DataMember><LookupKey>Customer</LookupKey>
    <SelectKey>IsGroup=0 AND ISNULL(Status,0) = 0</SelectKey></lookupCustomerCode>
</Controls></General>
<BravoGridContainer><ClassName>BravoGridContainer</ClassName><Items><Item_0><DataMember>Detail</DataMember><Cols>
  <POLine />
  <ItemCode><Editor><Expr>Empty(CheckEdit)</Expr><bindingMembers><Name>Description</Name><Unit>Unit_Item</Unit>
    <QuantityBox>QuantityBox</QuantityBox><CartonSize>CartonSize</CartonSize></bindingMembers>
    <ClassName>BravoLookupBox</ClassName><LookupKey>Item</LookupKey><FilterKey>IsGroup = 0</FilterKey></Editor></ItemCode>
  <Description><Editor><Expr>!Empty(ItemCode)</Expr></Editor></Description>
  <Unit><Editor><bindingMembers><ConvertRate>ConvertRate9</ConvertRate></bindingMembers><ClassName>BravoLookupBox</ClassName>
    <LookupKey>ItemUnit</LookupKey><FilterKey>ItemCode='{=ISNULL(ItemCode,'')}'</FilterKey><Expr>!Empty(ItemCode)</Expr></Editor></Unit>
  <Quantity9 />
</Cols></Item_0></Items></BravoGridContainer>
</Controls></panelEditor></root>"""

SESSION = Session(user={"Id": Decimal(7)}, branch="B1", now=datetime(2026, 11, 25))
LINE: dict[str, object] = dict.fromkeys(
    [
        "ItemCode",
        "Description",
        "Unit_Item",
        "Unit",
        "QuantityBox",
        "CartonSize",
        "ConvertRate9",
        "CheckEdit",
    ]
)
ITEMS = {
    "I-DASH": {"Name": "Roller", "Unit": "Pc", "QuantityBox": Decimal(0), "CartonSize": "-"},
    "I-BOX": {
        "Name": "Cable",
        "Unit": "Pc",
        "QuantityBox": Decimal(50),
        "CartonSize": "305x305x165",
    },
}


@dataclass
class Lookups:
    """Lookup rows by (key, code), and every read with the filter it carried."""

    rows: dict[tuple[str, object], Mapping[str, object]] = field(default_factory=dict)
    reads: list[tuple[str, object, str | None]] = field(default_factory=list)

    def find(
        self, lookup_key: str, code: object, filter_key: str | None
    ) -> Mapping[str, object] | None:
        self.reads.append((lookup_key, code, filter_key))
        if (lookup_key, code) not in self.rows:
            raise UndecidableError(f"{lookup_key} {code!r} not recorded")
        return self.rows[(lookup_key, code)]

    def key_taken(
        self, table: str, values: Mapping[str, object], filter_key: str | None, own_id: object
    ) -> bool:
        raise NotImplementedError("not exercised by the window tests")


def _lookups() -> Lookups:
    rows: dict[tuple[str, object], Mapping[str, object]] = {
        ("Item", k): v for k, v in ITEMS.items()
    }
    rows[("ItemUnit", "Pc")] = {"ConvertRate": Decimal(1)}
    rows[("Customer", "C1")] = {"Name": "Khách 1", "CustomerCurrencyCode": "USD"}
    return Lookups(rows)


def _runner(lookups: Lookups, window: str = WINDOW) -> RuleRunner:
    layout = with_window(read_layout(DATA_SOURCE, "EDIT_Test"), read_window(window, "EDIT_Test"))
    return RuleRunner(layout, RecordedProcedures(), lookups, SESSION)


def _document() -> Document:
    return Document(Row({"Id": Decimal(-1), "DocKey": "", "CustomerCode": None}), {"Detail": []})


def _new_line(item: str, lookups: Lookups | None = None) -> Row:
    run, doc = _runner(lookups or _lookups()), _document()
    index = run.add_row(doc, "Detail", LINE, stored=LINE)
    run.edit(doc, "Detail", index, "ItemCode", item)
    return doc.children["Detail"][index]


def test_a_new_lines_item_with_a_dash_carton_gets_one_per_box() -> None:
    line = _new_line("I-DASH")
    assert (line.get("QuantityBox"), line.get("CartonSize")) == (Decimal(1), "-")


def test_a_new_lines_item_with_a_carton_keeps_the_items_own_quantity_per_box() -> None:
    line = _new_line("I-BOX")
    assert line.get("QuantityBox") == Decimal(50)
    assert line.get("Description") == "Cable"  # the item's Name, into the line's column


def test_a_value_a_rule_sets_binds_too_as_the_unit_lookup_after_the_item_shows() -> None:
    lookups = _lookups()
    line = _new_line("I-BOX", lookups)
    assert (line.get("Unit"), line.get("ConvertRate9")) == ("Pc", Decimal(1))
    # The item read with its FilterKey; the unit read with its own, filled in.
    assert lookups.reads == [
        ("Item", "I-BOX", "(IsGroup = 0)"),
        ("ItemUnit", "Pc", "(ItemCode='I-BOX')"),
    ]


def test_a_header_lookup_reads_with_its_select_key_and_sets_its_members() -> None:
    lookups = _lookups()
    run = _runner(lookups)
    doc = Document(
        Row({"Id": Decimal(-1), "CustomerCode": None, "CustomerName": None, "CurrencyCode": "VND"}),
        {},
    )
    run.edit(doc, "Parent", 0, "CustomerCode", "C1")
    assert (doc.parent.get("CustomerName"), doc.parent.get("CurrencyCode")) == ("Khách 1", "USD")
    assert lookups.reads == [("Customer", "C1", "(IsGroup=0 AND ISNULL(Status,0) = 0)")]


def test_a_column_set_while_its_editor_is_closed_refuses() -> None:
    run, doc = _runner(_lookups()), _document()
    index = run.add_row(doc, "Detail", {**LINE, "CheckEdit": Decimal(1)}, stored=LINE)
    with pytest.raises(RuleRefusedError, match="editor is closed"):
        run.edit(doc, "Detail", index, "ItemCode", "I-BOX")


def test_without_the_window_nothing_binds() -> None:
    layout = read_layout(DATA_SOURCE, "EDIT_Test")
    run, doc = RuleRunner(layout, RecordedProcedures(), _lookups(), SESSION), _document()
    index = run.add_row(doc, "Detail", LINE, stored=LINE)
    run.edit(doc, "Detail", index, "ItemCode", "I-DASH")
    assert doc.children["Detail"][index].get("QuantityBox") is None


def test_a_plan_whose_window_could_not_be_read_never_writes() -> None:
    layout = replace(read_layout(DATA_SOURCE, "EDIT_Test"), missing_window="2 form layouts")
    run = RuleRunner(layout, RecordedProcedures(), _lookups(), SESSION)
    plan = run.save(Document(Row({"Id": Decimal(1), "DocKey": "K"}), {"Detail": []}))
    assert not plan.may_write and "window" in plan.provisional[0]


def test_every_binding_lookup_is_read_on_the_header_and_on_a_grids_column() -> None:
    window = read_window(WINDOW, "EDIT_Test")
    assert set(window.lookups) == {
        ("Parent", "customercode"),
        ("Detail", "itemcode"),
        ("Detail", "unit"),
    }


def test_a_window_whose_binding_cannot_be_placed_is_refused_whole() -> None:
    with pytest.raises(UnsupportedSyntaxError, match="names no column"):
        read_window(WINDOW.replace("<DataMember>CustomerCode</DataMember>", ""), "EDIT_Test")
    with pytest.raises(UnsupportedSyntaxError, match="not a window"):
        read_window(DATA_SOURCE, "EDIT_Test")


def test_a_users_own_window_that_binds_differently_refuses_that_lookup_only() -> None:
    """A user's copy (`B00LayoutDataEdit`; Proterial's 8213 copy drops the
    item's `PackingNote`): which copy a user gets is not measured, so the
    lookups the copies bind differently refuse when they bind, and the rest
    still bind."""
    base = read_window(WINDOW, "EDIT_Test")
    edited = read_window(WINDOW.replace("<CartonSize>CartonSize</CartonSize>", ""), "EDIT_Test")
    merged = merge_windows(base, [edited], "a user's own window binds it differently")
    layout = with_window(read_layout(DATA_SOURCE, "EDIT_Test"), merged)
    run, doc = RuleRunner(layout, RecordedProcedures(), _lookups(), SESSION), _document()
    index = run.add_row(doc, "Detail", LINE, stored=LINE)
    with pytest.raises(RuleRefusedError, match="binds it differently"):
        run.edit(doc, "Detail", index, "ItemCode", "I-BOX")
    run.edit(doc, "Parent", 0, "CustomerCode", "C1")  # bound the same in both: binds


def test_a_lookup_set_as_the_document_loads_leaves_what_it_would_bind_unknown() -> None:
    loading = DATA_SOURCE.replace(
        "<ColumnChanged>",
        "<ServerLoaded><Eval_Item /></ServerLoaded><ColumnChanged>",
    ).replace(
        "<Evaluators>",
        "<Evaluators><Eval_Item><DataMember>ItemCode</DataMember><Value>'I-BOX'</Value></Eval_Item>",
    )
    layout = with_window(read_layout(loading, "EDIT_Test"), read_window(WINDOW, "EDIT_Test"))
    run = RuleRunner(layout, RecordedProcedures(), _lookups(), SESSION)
    line = Row({**LINE, "Id": Decimal(11), "DocKey": "K"}, stored=["Id", "DocKey", "ItemCode"])
    doc = Document(Row({"Id": Decimal(1), "DocKey": "K"}), {"Detail": [line]})
    run.load(doc)
    assert line.get("ItemCode") == "I-BOX"
    assert line.get("Description") is UNKNOWN and "Description" in doc.unknown


NEW_DOC = DATA_SOURCE.replace(
    "<ParentTable><Name>vDoc_Edit</Name></ParentTable>",
    """<ParentTable><Name>vDoc_Edit</Name>
  <DefaultValues><DocCode>'SO'</DocCode><BranchCode>BRANCH()</BranchCode><BizDocId>''</BizDocId></DefaultValues>
  <RowAdded><Eval_DocCode_Bind /></RowAdded>
  <Evaluators><Eval_DocCode_Bind><ClassName>BravoBindingMember</ClassName><DataMember>DocCode</DataMember>
    <LookupKey>DmCt</LookupKey><bindingMembers><DocStatus_Ct>DocStatus</DocStatus_Ct>
    <Ma_Gd_Ct><Condition_0><DataMember>TransCode</DataMember><Expr>Empty(TransCode)</Expr></Condition_0></Ma_Gd_Ct>
    </bindingMembers></Eval_DocCode_Bind></Evaluators>
</ParentTable>""",
)
HEADER: dict[str, object] = dict.fromkeys(
    ["DocCode", "BranchCode", "BizDocId", "DocStatus", "TransCode", "DocKey", "CreatedBy"]
)


def test_a_new_document_takes_its_default_values_then_its_row_added_rules() -> None:
    """A document made in the `New` window (ticket 72): 8212's shapes, the
    `DefaultValues` and the DmCt binding its `RowAdded` runs."""
    lookups = _lookups()
    lookups.rows[("DmCt", "SO")] = {"DocStatus_Ct": Decimal(4), "Ma_Gd_Ct": "3201"}
    run = RuleRunner(read_layout(NEW_DOC, "EDIT_Test"), RecordedProcedures(), lookups, SESSION)
    doc = run.new_document({**HEADER, "ParentId": Decimal(-1)}, stored=[*HEADER, "ParentId"])

    parent = doc.parent
    assert (parent.get("DocCode"), parent.get("BranchCode"), parent.get("BizDocId")) == (
        "SO",
        "B1",
        "",
    )
    assert (parent.get("DocStatus"), parent.get("TransCode")) == (Decimal(4), "3201")
    assert parent.get("Id") == Decimal(-1) and doc.children == {"Detail": []}
    [insert] = run.save(doc).commands
    assert insert.kind == "insert" and insert.columns["CreatedBy"] == Decimal(7)
    assert "Id" not in insert.columns and insert.columns["ParentId"] == Decimal(-1)
    assert insert.columns["TransCode"] == "3201"


def test_a_rule_setting_several_columns_binds_each_it_changed() -> None:
    picking = DATA_SOURCE.replace(
        "<ColumnChanged>", "<ColumnChanged><POLine><Eval_Pick /></POLine>"
    ).replace(
        "<Evaluators>",
        "<Evaluators><Eval_Pick><DataMember>ItemCode,Note</DataMember><Value>'I-DASH'</Value></Eval_Pick>",
    )
    layout = with_window(read_layout(picking, "EDIT_Test"), read_window(WINDOW, "EDIT_Test"))
    run, doc = RuleRunner(layout, RecordedProcedures(), _lookups(), SESSION), _document()
    index = run.add_row(doc, "Detail", {**LINE, "POLine": None, "Note": None}, stored=LINE)
    run.edit(doc, "Detail", index, "POLine", "1")
    assert doc.children["Detail"][index].get("QuantityBox") == Decimal(1)


def test_an_emptied_lookup_refuses() -> None:
    run, doc = _runner(_lookups()), _document()
    index = run.add_row(doc, "Detail", LINE, stored=LINE)
    run.edit(doc, "Detail", index, "ItemCode", "I-BOX")
    with pytest.raises(UndecidableError, match="emptied lookup"):
        run.edit(doc, "Detail", index, "ItemCode", None)


class _NotFound(Lookups):
    def find(
        self, lookup_key: str, code: object, filter_key: str | None
    ) -> Mapping[str, object] | None:
        self.reads.append((lookup_key, code, filter_key))
        return None


def test_a_lookup_whose_row_is_not_found_refuses() -> None:
    run, doc = _runner(_NotFound()), _document()
    index = run.add_row(doc, "Detail", LINE, stored=LINE)
    with pytest.raises(UndecidableError, match="Item 'I-GONE' not found"):
        run.edit(doc, "Detail", index, "ItemCode", "I-GONE")


def test_a_conditional_member_whose_condition_the_members_before_it_change_refuses() -> None:
    """Whether a member's condition is read before the lookup sets anything,
    or as its turn comes, is not measured: here the currency the first
    member sets decides whether the name is set."""
    window = WINDOW.replace(
        "<Name>CustomerName</Name><CustomerCurrencyCode>CurrencyCode</CustomerCurrencyCode>",
        "<CustomerCurrencyCode>CurrencyCode</CustomerCurrencyCode><Name><Condition_0>"
        "<DataMember>CustomerName</DataMember><Expr>Empty(CurrencyCode)</Expr></Condition_0></Name>",
    )
    run = _runner(_lookups(), window)
    doc = Document(
        Row({"Id": Decimal(-1), "CustomerCode": None, "CustomerName": None, "CurrencyCode": None}),
        {},
    )
    with pytest.raises(RuleRefusedError, match="CustomerName's condition changes"):
        run.edit(doc, "Parent", 0, "CustomerCode", "C1")


def test_lookups_that_bind_each_other_round_and_round_refuse() -> None:
    """The customer's lookup sets `Agent`, whose lookup sets the customer
    back, and so on: the runner stops at its depth, as it does for rules."""
    window = WINDOW.replace(
        "<Name>CustomerName</Name><CustomerCurrencyCode>CurrencyCode</CustomerCurrencyCode>",
        "<Agent>Agent</Agent>",
    ).replace(
        "</Controls></General>",
        "<lookupAgent><bindingMembers><Customer>CustomerCode</Customer></bindingMembers>"
        "<ClassName>BravoLookupBox</ClassName><DataMember>Agent</DataMember><LookupKey>Agent</LookupKey>"
        "</lookupAgent></Controls></General>",
    )
    lookups = Lookups(
        {
            ("Customer", "C1"): {"Agent": "A1"},
            ("Agent", "A1"): {"Customer": "C2"},
            ("Customer", "C2"): {"Agent": "A2"},
            ("Agent", "A2"): {"Customer": "C1"},
        }
    )
    run = _runner(lookups, window)
    doc = Document(Row({"Id": Decimal(-1), "CustomerCode": None, "Agent": None}), {})
    with pytest.raises(RuleRefusedError, match="rules nest deeper than 64 at lookup"):
        run.edit(doc, "Parent", 0, "CustomerCode", "C1")


def test_a_binding_box_that_is_not_a_lookup_with_a_key_refuses_when_it_binds() -> None:
    """Read, not refused whole: the window still reads; the box refuses
    when its column is set, never reading a lookup with no key."""
    for unread in (
        WINDOW.replace("<LookupKey>ItemUnit</LookupKey>", ""),
        WINDOW.replace(
            "<ClassName>BravoLookupBox</ClassName>\n    <LookupKey>ItemUnit</LookupKey>",
            "<ClassName>zLookupSource</ClassName>\n    <LookupKey>ItemUnit</LookupKey>",
        ),
    ):
        assert unread != WINDOW
        lookups = _lookups()
        run, doc = _runner(lookups, unread), _document()
        index = run.add_row(doc, "Detail", LINE, stored=LINE)
        with pytest.raises(RuleRefusedError, match="not a BravoLookupBox with a LookupKey"):
            run.edit(doc, "Detail", index, "ItemCode", "I-BOX")
        assert [key for key, _, _ in lookups.reads] == ["Item"]


def test_a_member_that_binds_to_no_column_refuses_when_it_binds() -> None:
    window = WINDOW.replace("<ConvertRate>ConvertRate9</ConvertRate>", "<ConvertRate />")
    run, doc = _runner(_lookups(), window), _document()
    index = run.add_row(doc, "Detail", LINE, stored=LINE)
    with pytest.raises(RuleRefusedError, match="ConvertRate binds to no column"):
        run.edit(doc, "Detail", index, "ItemCode", "I-BOX")


def test_the_short_form_binds_each_column_to_its_own_name() -> None:
    window = WINDOW.replace(
        "<bindingMembers><Name>CustomerName</Name><CustomerCurrencyCode>CurrencyCode"
        "</CustomerCurrencyCode></bindingMembers>",
        "<bindingMembers>Name, CustomerCurrencyCode</bindingMembers>",
    )
    lookup = read_window(window, "EDIT_Test").lookup("Parent", "CustomerCode")
    assert lookup is not None and not lookup.unread
    assert [(m.source, m.target) for m in lookup.members] == [
        ("Name", "Name"),
        ("CustomerCurrencyCode", "CustomerCurrencyCode"),
    ]


def test_a_window_that_cannot_say_which_columns_bind_is_refused_whole() -> None:
    twice = WINDOW.replace(
        "</Controls></General>",
        "<lookupAgain><bindingMembers><Name>CustomerName</Name></bindingMembers>"
        "<ClassName>BravoLookupBox</ClassName><DataMember>CustomerCode</DataMember>"
        "<LookupKey>Customer</LookupKey></lookupAgain></Controls></General>",
    )
    with pytest.raises(UnsupportedSyntaxError, match=r"two lookups bind Parent\.CustomerCode"):
        read_window(twice, "EDIT_Test")
    for broken in (
        WINDOW.replace("<DataMember>Detail</DataMember>", ""),
        WINDOW.replace("<Cols>", "<Kols>").replace("</Cols>", "</Kols>"),
    ):
        with pytest.raises(UnsupportedSyntaxError, match="grid Item_0 names no table or columns"):
            read_window(broken, "EDIT_Test")
