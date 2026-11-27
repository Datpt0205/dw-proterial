# ruff: noqa: E501 - the layout below is XML kept on the lines Bravo would write it
"""The rule runner on a small layout written for these tests (no Bravo data).

The layout has the shapes the SO screen uses: a money evaluator, a value
rule with rounding, a cascade into the header's total, a server constraint,
rules defined inline in an event, a group, validators of each kind, and a rule
the shared template would define.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from dw_bravo.adapters.recorded import RecordedProcedures, RecordedReferences
from dw_bravo.expression import RuleRefusedError, UndecidableError, UnsupportedSyntaxError
from dw_bravo.layout import PARENT, read_layout
from dw_bravo.ports import Session
from dw_bravo.runner import Document, Row, RuleRunner

pytestmark = pytest.mark.unit

LAYOUT = """<root><Tables>
<ParentTable>
  <Name>vDoc_Edit</Name>
  <ColumnChanged>
    <DocDate><Eval_Detail_DocDate_FromParent /></DocDate>
    <Kind><Eval_FromTemplate /></Kind>
  </ColumnChanged>
  <Evaluators>
    <Eval_Total><DataMember>Total</DataMember><Value>SUM(Child(Detail).Amount)</Value></Eval_Total>
  </Evaluators>
  <ServerUpdating><Eval_Order /></ServerUpdating>
  <Validators>
    <NeedsLines><ClassName>BravoValidator</ClassName><SourceColumn>Total</SourceColumn>
      <zValidateExpr>Exists(Detail)</zValidateExpr><Text><Vietnamese>Cần có dòng</Vietnamese></Text></NeedsLines>
    <PoTaken><ClassName>BravoUniqueKeyValidator</ClassName><SourceColumn>PO</SourceColumn>
      <bValidateWarning>True</bValidateWarning></PoTaken>
    <NotNull><SourceColumn>Customer</SourceColumn></NotNull>
  </Validators>
</ParentTable>
<ChildTable_Detail>
  <Name>vLine_Edit</Name><Alias>Detail</Alias>
  <Expressions><Rate>PARENT.Rate</Rate><Places>PARENT.Places</Places></Expressions>
  <TempColumns><Flag><DataType>System.Int16</DataType></Flag></TempColumns>
  <ColumnChanged>
    <Qty><Eval_Amount /><Eval_Usd /></Qty>
    <Price><Eval_Amount /><Eval_Usd /></Price>
    <Amount><Eval_Total /></Amount>
    <Eta>
      <Eval_Cd><ClassName>BravoServerConstraint</ClassName><Command>ufn_Cd</Command>
        <Parameters><Customer>Parent.Customer</Customer><Eta>Eta</Eta></Parameters>
        <DataMember>CdDate</DataMember><Expr>!Empty(Eta)</Expr></Eval_Cd>
      <Eval_Accounting>Flag = 1</Eval_Accounting>
    </Eta>
    <Group><Eval_Mark /></Group>
  </ColumnChanged>
  <Evaluators>
    <Eval_Amount><ClassName>BravoMoneyEvaluator</ClassName><DataMember>Amount</DataMember>
      <zNumberValue>Qty</zNumberValue><zMoneyValue>Price</zMoneyValue>
      <zResultDecimalRound>Places</zResultDecimalRound></Eval_Amount>
    <Eval_Usd><DataMember>Usd</DataMember><Value>Amount / Rate</Value>
      <zResultDecimalRound>2</zResultDecimalRound></Eval_Usd>
    <Eval_Accounting><DataMember>Accounting</DataMember><Value>Eta</Value></Eval_Accounting>
    <Eval_Detail_DocDate_FromParent><DataMember>DocDate</DataMember><Value>Parent.DocDate</Value></Eval_Detail_DocDate_FromParent>
    <Eval_Mark><DataMember>Marked</DataMember><Value>1</Value><zScopeExpr>Group='{=Group}'</zScopeExpr></Eval_Mark>
    <Eval_Order><ClassName>BravoTableOrderer</ClassName><DataMember>Ord</DataMember></Eval_Order>
  </Evaluators>
  <Validators>
    <Late><ClassName>BravoValidator</ClassName><SourceColumn>Eta</SourceColumn>
      <zValidateExpr>Empty(Eta) OR Eta &gt;= Parent.DocDate</zValidateExpr>
      <bValidateWarning>True</bValidateWarning><Text><Vietnamese>Ngày giao trước ngày đặt</Vietnamese></Text></Late>
    <Mp><ClassName>BravoServerConstraintValidator</ClassName><SourceColumn>Item</SourceColumn>
      <Command>usp_CheckMp</Command><Parameters><Item>Item</Item></Parameters>
      <Expr>Parent.Kind IN ('Mass')</Expr><bValidateWarning>True</bValidateWarning></Mp>
    <QtyNotBelowMade><ClassName>BravoValidator</ClassName><SourceColumn>Qty</SourceColumn>
      <zValidateExpr>Qty &gt;= Made</zValidateExpr></QtyNotBelowMade>
  </Validators>
</ChildTable_Detail>
</Tables></root>"""

DAY = datetime(2026, 1, 10)
SESSION = Session(user={"Id": Decimal(7)}, branch="B1", now=DAY)


def document() -> Document:
    parent = Row(
        {
            "Id": 1,
            "Customer": "C1",
            "DocDate": DAY,
            "Kind": "Mass",
            "Rate": Decimal(4),
            "Places": Decimal(0),
            "Total": Decimal(40),
            "PO": "PO-1",
            "ModifiedBy": Decimal(3),
        },
        stored=["Id", "Customer", "DocDate", "Kind", "Total", "PO", "ModifiedBy"],
    )
    line = {
        "Id": 11,
        "Item": "I1",
        "Qty": Decimal(2),
        "Price": Decimal(20),
        "Amount": Decimal(40),
        "Usd": Decimal(10),
        "Eta": None,
        "CdDate": None,
        "Accounting": None,
        "DocDate": DAY,
        "Made": Decimal(0),
        "Group": "",
        "Marked": None,
        "Ord": Decimal(1),
        "ModifiedBy": Decimal(3),
    }
    second = {**line, "Id": 12, "Ord": Decimal(2), "Qty": Decimal(1), "Amount": Decimal(20)}
    second["Usd"] = Decimal(5)
    parent.set("Total", Decimal(60))
    parent.accept()
    return Document(parent, {"Detail": [Row(line), Row(second)]})


def runner(
    layout_text: str = LAYOUT,
    procedures: RecordedProcedures | None = None,
    references: RecordedReferences | None = None,
    missing_template: str | None = None,
) -> RuleRunner:
    layout = read_layout(layout_text, "EDIT_Test", missing_template=missing_template)
    return RuleRunner(
        layout, procedures or RecordedProcedures(), references or RecordedReferences(), SESSION
    )


def test_an_edit_cascades_through_the_layouts_own_rules() -> None:
    doc, run = document(), runner()
    run.load(doc)
    run.edit(doc, "Detail", 0, "Qty", Decimal(5))
    line = doc.children["Detail"][0]
    assert line.get("Amount") == Decimal(100)
    assert line.get("Usd") == Decimal(25)
    assert doc.parent.get("Total") == Decimal(120)
    rules = [(s.rule, s.column) for s in doc.trail]
    assert rules[:3] == [("<user>", "Qty"), ("Eval_Amount", "Amount"), ("Eval_Total", "Total")]


def test_save_writes_exactly_what_changed_plus_modified_by() -> None:
    doc, run = document(), runner()
    run.load(doc)
    run.edit(doc, "Detail", 0, "Qty", Decimal(5))
    plan = run.save(doc)
    by_table = {(c.table, c.row): dict(c.columns) for c in plan.commands}
    assert by_table[("Parent", 0)] == {"Total": Decimal(120), "ModifiedBy": Decimal(7)}
    assert by_table[("Detail", 0)] == {
        "Qty": Decimal(5),
        "Amount": Decimal(100),
        "Usd": Decimal(25),
        "ModifiedBy": Decimal(7),
    }
    assert ("Detail", 1) not in by_table


def test_the_header_is_saved_whenever_a_line_is() -> None:
    doc, run = document(), runner(procedures=_cd_recorded())
    run.load(doc)
    run.edit(doc, "Detail", 0, "Eta", datetime(2026, 2, 2))
    header = next(c for c in run.save(doc).commands if c.table == "Parent")
    assert dict(header.columns) == {"ModifiedBy": Decimal(7)}


def test_a_row_whose_view_holds_no_modified_by_is_written_without_it() -> None:
    # The YCBG line's view has no ModifiedBy: the client passes the parameter
    # and sets no such column (11-20 trace); the header's view has it.
    doc, run = document(), runner()
    first = doc.children["Detail"][0]
    doc.children["Detail"][0] = Row(
        first.values(), stored=[c for c in first.stored if c != "modifiedby"]
    )
    run.load(doc)
    run.edit(doc, "Detail", 0, "Qty", Decimal(5))
    by_table = {(c.table, c.row): dict(c.columns) for c in run.save(doc).commands}
    assert "ModifiedBy" not in by_table[("Detail", 0)]
    assert by_table[("Parent", 0)]["ModifiedBy"] == Decimal(7)


def test_a_new_row_is_inserted_with_created_by_only_where_its_view_holds_it() -> None:
    doc, run = document(), runner()
    run.load(doc)
    values = {"Id": 13, "Item": "I2", "Qty": Decimal(1), "Ord": Decimal(3)}
    doc.children["Detail"].append(Row(values, new=True))
    doc.children["Detail"].append(Row(values, stored=[*values, "CreatedBy"], new=True))
    inserts = [c for c in run.save(doc).commands if c.kind == "insert"]
    assert ["CreatedBy" in c.columns for c in inserts] == [False, True]


def _cd_recorded() -> RecordedProcedures:
    procedures = RecordedProcedures()
    procedures.record(
        "ufn_Cd", {"Customer": "C1", "Eta": datetime(2026, 2, 2)}, {"CdDate": datetime(2026, 1, 28)}
    )
    return procedures


def test_a_server_constraint_runs_the_recorded_procedure_with_the_rules_parameters() -> None:
    doc, procedures = document(), _cd_recorded()
    run = runner(procedures=procedures)
    run.load(doc)
    run.edit(doc, "Detail", 0, "Eta", datetime(2026, 2, 2))
    assert doc.children["Detail"][0].get("CdDate") == datetime(2026, 1, 28)
    assert procedures.calls == [("ufn_Cd", {"Customer": "C1", "Eta": datetime(2026, 2, 2)})]


def test_an_unrecorded_procedure_call_refuses_the_edit() -> None:
    doc, run = document(), runner()
    run.load(doc)
    with pytest.raises(UndecidableError, match="ufn_Cd"):
        run.edit(doc, "Detail", 0, "Eta", datetime(2026, 2, 3))


def test_a_uses_own_condition_gates_an_inline_defined_rule() -> None:
    doc, run = document(), runner(procedures=_cd_recorded())
    run.load(doc)
    run.edit(doc, "Detail", 0, "Eta", datetime(2026, 2, 2))
    assert doc.children["Detail"][0].get("Accounting") is None  # Flag is not 1
    line = doc.children["Detail"][1]
    line.set("Flag", Decimal(1))
    procedures = _cd_recorded()
    run = runner(procedures=procedures)
    run.edit(doc, "Detail", 1, "Eta", datetime(2026, 2, 2))
    assert line.get("Accounting") == datetime(2026, 2, 2)


def test_a_header_change_reaches_every_line() -> None:
    doc, run = document(), runner()
    run.load(doc)
    run.edit(doc, "Parent", 0, "DocDate", datetime(2026, 1, 12))
    assert [r.get("DocDate") for r in doc.children["Detail"]] == [datetime(2026, 1, 12)] * 2


def test_a_scoped_rule_applies_to_every_row_its_scope_selects() -> None:
    doc, run = document(), runner()
    run.load(doc)
    doc.children["Detail"][1].set("Group", "A")
    run.edit(doc, "Detail", 0, "Group", "A")
    assert [r.get("Marked") for r in doc.children["Detail"]] == [Decimal(1), Decimal(1)]


def test_a_rule_only_the_template_defines_refuses() -> None:
    doc, run = document(), runner()
    run.load(doc)
    with pytest.raises(RuleRefusedError, match="template"):
        run.edit(doc, "Parent", 0, "Kind", "Sample")


def test_money_evaluator_counts_a_null_operand_as_zero() -> None:
    # UAT trace 11-25 17:31:50: the client wrote UnitCost 0 over a NULL
    # OriginalUnitCost; "left alone" would have kept the old value.
    doc, run = document(), runner()
    run.load(doc)
    run.edit(doc, "Detail", 0, "Price", None)
    assert doc.children["Detail"][0].get("Amount") == Decimal(0)


# A rule setting two columns, one of them read by a money rule homed on the
# other's change: the shape of Bravo's cancel reset (`OriginalUnitCost,UnitCost`).
RESET_LAYOUT = LAYOUT.replace(
    "    <Group><Eval_Mark /></Group>\n",
    "    <Group><Eval_Mark /></Group>\n    <Cut><Eval_Reset /></Cut>\n",
).replace(
    "    <Eval_Order>",
    "    <Eval_Reset><DataMember>Price,Amount</DataMember><Value>NULL</Value>"
    "<Expr>Cut = 1</Expr></Eval_Reset>\n    <Eval_Order>",
    1,
)


def test_a_rule_setting_several_columns_sets_them_all_before_their_events() -> None:
    doc, run = document(), runner(RESET_LAYOUT)
    doc.children["Detail"][0].set("Cut", None)
    run.load(doc)
    run.edit(doc, "Detail", 0, "Cut", Decimal(1))
    line = doc.children["Detail"][0]
    # Price and Amount are both NULL first; Price's change then runs the
    # money rule over the NULL, leaving Amount 0, as the client's cancel does.
    # One at a time, Amount's own reset would come last and leave it NULL.
    assert line.get("Price") is None
    assert line.get("Amount") == Decimal(0)


def test_validators_fire_by_level() -> None:
    procedures = RecordedProcedures()
    procedures.record("usp_CheckMp", {"Item": "I1"}, {"Result": Decimal(1)})
    references = RecordedReferences(taken={})
    from dw_bravo.adapters.recorded import call_key

    references.taken[call_key("vDoc_Edit", {"PO": "PO-1"})] = True
    doc, run = document(), runner(procedures=procedures, references=references)
    run.load(doc)
    doc.children["Detail"][0].set("Eta", datetime(2026, 1, 1))
    doc.children["Detail"][1].set("Made", Decimal(9))
    check = run.check(doc)
    fired = {(f.rule, f.row, f.level) for f in check.blocking + check.warnings}
    assert ("Late", 0, "warning") in fired
    assert ("QtyNotBelowMade", 1, "block") in fired
    assert ("Mp", 0, "warning") in fired
    assert ("PoTaken", 0, "warning") in fired
    assert ("Late", 1, "warning") not in fired
    assert not check.may_save


def test_a_validator_whose_kind_lives_in_the_template_is_undecided_and_blocks() -> None:
    doc, run = document(), runner()
    run.load(doc)
    check = run.check(doc)
    not_null = next(f for f in check.findings if f.rule == "NotNull")
    assert not_null.status == "undecided" and "template" in (not_null.reason or "")
    # Fail closed: an undecided blocking rule blocks the save.
    assert check.may_save is False


def test_a_plan_made_without_the_template_never_writes() -> None:
    clean = LAYOUT.replace("<NotNull><SourceColumn>Customer</SourceColumn></NotNull>", "")
    references = RecordedReferences()
    from dw_bravo.adapters.recorded import call_key

    references.taken[call_key("vDoc_Edit", {"PO": "PO-1"})] = False
    procedures = RecordedProcedures()
    procedures.record("usp_CheckMp", {"Item": "I1"}, {"Result": Decimal(0)})
    for missing, writes in ((None, True), ("BizDocEditor", False)):
        doc = document()
        run = runner(clean, procedures, references, missing_template=missing)
        run.load(doc)
        plan = run.save(doc)
        assert plan.check.may_save  # every rule decided and passed
        assert plan.may_write is writes


def test_a_changed_layout_changes_behaviour_with_no_code_change() -> None:
    edited = LAYOUT.replace(
        "<zResultDecimalRound>2</zResultDecimalRound>",
        "<zResultDecimalRound>0</zResultDecimalRound>",
    )
    doc, run = document(), runner(edited)
    run.load(doc)
    run.edit(doc, "Detail", 0, "Qty", Decimal(3))  # Amount 60, Usd 60/4 = 15
    run.edit(doc, "Detail", 0, "Price", Decimal(21))  # Amount 63, Usd 15.75 -> 16
    assert doc.children["Detail"][0].get("Usd") == Decimal(16)
    doc2, run2 = document(), runner()
    run2.load(doc2)
    run2.edit(doc2, "Detail", 0, "Qty", Decimal(3))
    run2.edit(doc2, "Detail", 0, "Price", Decimal(21))
    assert doc2.children["Detail"][0].get("Usd") == Decimal("15.75")


def test_table_orderer_numbers_rows_at_save() -> None:
    doc, run = document(), runner()
    run.load(doc)
    doc.children["Detail"].reverse()
    run.save(doc)
    assert [r.get("Ord") for r in doc.children["Detail"]] == [Decimal(1), Decimal(2)]


def test_a_layout_with_a_doctype_is_refused() -> None:
    read_layout(LAYOUT, "X")  # the same layout without one reads
    with pytest.raises(UnsupportedSyntaxError, match="DOCTYPE"):
        read_layout('<!DOCTYPE root [<!ENTITY a "b">]>' + LAYOUT, "X")


def test_two_different_definitions_of_one_rule_refuse_when_used() -> None:
    twice = LAYOUT.replace(
        "<Group><Eval_Mark /></Group>",
        "<Group><Eval_Mark /><Eval_Usd><DataMember>Usd</DataMember><Value>0</Value></Eval_Usd></Group>",
    )
    doc, run = document(), runner(twice)
    run.load(doc)
    with pytest.raises(RuleRefusedError, match="defined twice"):
        run.edit(doc, "Detail", 0, "Qty", Decimal(4))


# A line added to the grid (ticket 73): the relation key and the `RowAdded`
# rules come from the layout, as the SO screen's `ParentKey`/`ChildKey`
# (`BizDocId`) and `RowAdded` do.
ROWS_LAYOUT = LAYOUT.replace(
    "<Name>vLine_Edit</Name><Alias>Detail</Alias>",
    "<Name>vLine_Edit</Name><Alias>Detail</Alias><ParentKey>DocKey</ParentKey><ChildKey>DocKey</ChildKey>"
    "<RowAdded><Eval_Detail_DocDate_FromParent /><Eval_Flagged>Empty(Parent.Customer)</Eval_Flagged>"
    "<Eval_Fresh /></RowAdded>",
).replace(
    "<Eval_Order>",
    "<Eval_Flagged><DataMember>Flag</DataMember><Value>1</Value></Eval_Flagged>"
    "<Eval_Fresh><DataMember>Made</DataMember><Value>Qty</Value><Expr>Id &lt; 0</Expr></Eval_Fresh>"
    "<Eval_Order>",
)
# Every column the line's view holds, NULL: a new grid line knows nothing yet.
NEW_LINE: dict[str, object] = dict.fromkeys(
    ["Item", "Qty", "Price", "Amount", "Usd", "Made", "Eta", "Group", "Ord", "DocDate"]
)


def test_an_added_row_takes_the_parents_key_a_negative_id_and_its_rowadded_rules() -> None:
    doc, run = document(), runner(ROWS_LAYOUT)
    doc.parent.set("DocKey", "K1")
    run.load(doc)

    first = run.add_row(doc, "Detail", NEW_LINE, stored=[*NEW_LINE, "CreatedBy"])
    second = run.add_row(doc, "Detail", NEW_LINE, stored=NEW_LINE)
    run.edit(doc, "Detail", first, "Qty", Decimal(3))

    rows = doc.children["Detail"]
    assert (first, second) == (2, 3)
    assert [rows[i].get("Id") for i in (first, second)] == [Decimal(-1), Decimal(-2)]
    assert rows[first].get("DocKey") == "K1"
    assert rows[first].get("DocDate") == DAY  # RowAdded's rule
    assert not rows[first].has("Flag")  # its use's condition does not hold
    inserts = {c.row: dict(c.columns) for c in run.save(doc).commands if c.kind == "insert"}
    assert set(inserts) == {first, second}
    # The id is the client's own until Bravo gives one: never written.
    assert "Id" not in inserts[first] and inserts[first]["DocKey"] == "K1"
    assert inserts[first]["CreatedBy"] == Decimal(7)
    assert "CreatedBy" not in inserts[second]


def test_an_id_below_zero_is_what_a_new_rows_own_rules_read() -> None:
    doc, run = document(), runner(ROWS_LAYOUT.replace("<Eta>", "<Qty><Eval_Fresh /></Qty><Eta>", 1))
    doc.parent.set("DocKey", "K1")
    run.load(doc)
    index = run.add_row(doc, "Detail", NEW_LINE, stored=NEW_LINE)
    run.edit(doc, "Detail", index, "Qty", Decimal(4))
    run.edit(doc, "Detail", 0, "Qty", Decimal(9))
    assert doc.children["Detail"][index].get("Made") == Decimal(4)
    assert doc.children["Detail"][0].get("Made") == Decimal(0)  # a stored row: Id > 0


def test_a_row_cannot_be_added_where_the_layout_names_no_relation() -> None:
    doc, run = document(), runner()
    run.load(doc)
    with pytest.raises(RuleRefusedError, match="ParentKey"):
        run.add_row(doc, "Detail", NEW_LINE, stored=NEW_LINE)


# A lookup's `bindingMembers` (ticket 72), in 8212's shapes: a member renamed
# on the way (`<DocStatus_Ct>DocStatus</DocStatus_Ct>`: the lookup's column,
# then the row's) and a conditional one (`Eval_DocCode_BindingMembers`'
# `Ma_Gd_Ct`, which sets `TransCode` only while it is empty).
BINDING_LAYOUT = """<root><Tables><ParentTable><Name>vDoc_Edit</Name>
<ColumnChanged><DocCode><Eval_DocCode_Bind /></DocCode></ColumnChanged>
<Evaluators>
  <Eval_DocCode_Bind><ClassName>BravoBindingMember</ClassName><DataMember>DocCode</DataMember>
    <LookupKey>DmCt</LookupKey><bindingMembers><DocStatus_Ct>DocStatus</DocStatus_Ct>
    <Ma_Gd_Ct><Condition_0><DataMember>TransCode</DataMember><Expr>Empty(TransCode)</Expr></Condition_0></Ma_Gd_Ct>
    </bindingMembers></Eval_DocCode_Bind>
</Evaluators>
</ParentTable></Tables></root>"""


def _bound(trans_code: object) -> Row:
    references = RecordedReferences(
        rows={("dmct", "SO"): {"DocStatus_Ct": Decimal(4), "Ma_Gd_Ct": "3201"}}
    )
    parent = Row({"Id": 1, "DocCode": None, "DocStatus": None, "TransCode": trans_code})
    doc = Document(parent, {})
    runner(BINDING_LAYOUT, references=references).edit(doc, PARENT, 0, "DocCode", "SO")
    return doc.parent


def test_a_binding_sets_the_rows_column_from_the_lookups_column() -> None:
    assert _bound(None).get("DocStatus") == Decimal(4)


def test_a_conditional_binding_member_sets_its_column_only_where_its_condition_holds() -> None:
    assert _bound(None).get("TransCode") == "3201"
    assert _bound("3101").get("TransCode") == "3101"


def test_a_binding_shape_not_read_refuses_when_it_runs_and_not_before() -> None:
    two = BINDING_LAYOUT.replace(
        "</Condition_0></Ma_Gd_Ct>",
        "</Condition_0><Condition_1><DataMember>TransTypeCode</DataMember><Expr>1=1</Expr></Condition_1></Ma_Gd_Ct>",
    )
    run = runner(two)  # the layout reads
    doc = Document(Row({"Id": 1, "DocCode": None, "TransCode": None}), {})
    with pytest.raises(RuleRefusedError, match="Ma_Gd_Ct"):
        run.edit(doc, PARENT, 0, "DocCode", "SO")
