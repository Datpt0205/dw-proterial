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
from dw_bravo.layout import read_layout
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


def test_money_evaluator_null_operand_over_a_value_refuses() -> None:
    doc, run = document(), runner()
    run.load(doc)
    with pytest.raises(RuleRefusedError, match="NULL operand"):
        run.edit(doc, "Detail", 0, "Price", None)


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
