# ruff: noqa: E501 - the XML below is kept on the lines Bravo would write it
"""A screen's shared template (`B00Command`'s TemplateName, `BizDocEditor`
for the SO, quotation, PR and PO screens; script 03c, 2026-11-25), read and
applied by the rule runner (ticket 59).

What the production template holds was measured: menus and three command
guards (`CommandValidators`) on the parent table, nothing else that sets or
checks a value. The template below has the same shape and no Bravo data.
"""

from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from dw_bravo.adapters.recorded import RecordedProcedures, RecordedReferences
from dw_bravo.expression import UnsupportedSyntaxError
from dw_bravo.layout import read_layout, read_template, with_template
from dw_bravo.ports import Session
from dw_bravo.runner import Document, Row, RuleRunner

pytestmark = pytest.mark.unit

DAY = datetime(2026, 1, 10)
CLEAN = """<root><Tables>
<ParentTable><Name>vDoc_Edit</Name></ParentTable>
<ChildTable_Detail><Name>vLine_Edit</Name><Alias>Detail</Alias>
  <ColumnChanged><Qty><Eval_Amount /></Qty></ColumnChanged>
  <Evaluators><Eval_Amount><DataMember>Amount</DataMember><Value>Qty * Price</Value></Eval_Amount></Evaluators>
</ChildTable_Detail>
</Tables></root>"""


def document() -> Document:
    parent = Row(
        {"Id": 1, "BranchCode": "B1", "Active": 1, "ModifiedBy": Decimal(3)},
        stored=["Id", "BranchCode", "Active", "ModifiedBy"],
    )
    line = Row(
        {
            "Id": 11,
            "Qty": Decimal(2),
            "Price": Decimal(20),
            "Amount": Decimal(40),
            "ModifiedBy": Decimal(3),
        },
        stored=["Id", "Qty", "Price", "Amount", "ModifiedBy"],
    )
    return Document(parent, {"Detail": [line]})


TEMPLATE = """<root><toolStrip1><Items><Save /></Items></toolStrip1>
<DataSource><Tables><ParentTable><CommandValidators>
  <ModifyInactiveData><CommandName>Edit</CommandName><Expr>ISNULL(Active,1)=1</Expr>
    <Text><Vietnamese>Dữ liệu đang ở trạng thái không sử dụng.</Vietnamese></Text></ModifyInactiveData>
  <CreateData><CommandName>New,NewAsCopy,Edit</CommandName><Expr>BRANCH('IsGroup')=0</Expr>
    <Text><Vietnamese>Không được sửa dữ liệu tại đơn vị tổng hợp.</Vietnamese></Text></CreateData>
  <ModifyCurrentData><CommandName>Edit,Save,SaveAndNew,SaveAndClose</CommandName><Expr>BranchCode=BRANCH()</Expr>
    <Text><Vietnamese>Dữ liệu không thuộc đơn vị hiện tại.</Vietnamese></Text></ModifyCurrentData>
</CommandValidators></ParentTable></Tables></DataSource></root>"""


def _runner(
    branch: str = "B1", *, is_group: object = Decimal(0), template: str = TEMPLATE
) -> RuleRunner:
    layout = with_template(
        read_layout(CLEAN, "EDIT_Test", missing_template="BizDocEditor"),
        read_template(template, "BizDocEditor"),
    )
    session = Session(
        user={"Id": Decimal(7)},
        branch=branch,
        now=DAY,
        branch_info={} if is_group is None else {"IsGroup": is_group},
    )
    return RuleRunner(layout, RecordedProcedures(), RecordedReferences(), session)


def _doc(**parent: object) -> Document:
    doc = document()
    for column, value in parent.items():
        doc.parent.set(column, value)
    doc.parent.accept()
    return doc


def test_the_template_is_read_as_its_command_guards_and_nothing_else() -> None:
    template = read_template(TEMPLATE, "BizDocEditor")
    assert [(g.name, sorted(g.commands)) for g in template.guards] == [
        ("ModifyInactiveData", ["edit"]),
        ("CreateData", ["edit", "new", "newascopy"]),
        ("ModifyCurrentData", ["edit", "save", "saveandclose", "saveandnew"]),
    ]


def test_a_template_that_sets_or_checks_a_value_is_refused_whole() -> None:
    """Fail closed: a template part the reader does not know is never skipped."""
    with_events = TEMPLATE.replace(
        "</CommandValidators>",
        "</CommandValidators><ColumnChanged><Qty><Eval_X /></Qty></ColumnChanged>",
    )
    with pytest.raises(UnsupportedSyntaxError, match="ColumnChanged"):
        read_template(with_events, "BizDocEditor")
    with pytest.raises(UnsupportedSyntaxError, match="DOCTYPE"):
        read_template("<!DOCTYPE x>" + TEMPLATE, "BizDocEditor")


def test_with_the_template_in_hand_a_clean_edit_may_write() -> None:
    doc, run = _doc(), _runner()
    run.load(doc)
    run.edit(doc, "Detail", 0, "Qty", Decimal(3))
    plan = run.save(doc, commands=("Edit", "Save"))
    assert plan.provisional == ()
    assert plan.may_write
    guards = {
        f.rule: f.status
        for f in plan.check.findings
        if f.rule in {"ModifyInactiveData", "CreateData", "ModifyCurrentData"}
    }
    assert guards == {
        "ModifyInactiveData": "passed",
        "CreateData": "passed",
        "ModifyCurrentData": "passed",
    }


@pytest.mark.parametrize(
    ("parent", "branch", "is_group", "fired"),
    [
        ({"Active": 0}, "B1", Decimal(0), "ModifyInactiveData"),
        ({}, "B1", Decimal(1), "CreateData"),
        ({"BranchCode": "B2"}, "B1", Decimal(0), "ModifyCurrentData"),
    ],
)
def test_each_guard_blocks_the_command_it_names(
    parent: dict[str, object], branch: str, is_group: Decimal, fired: str
) -> None:
    doc, run = _doc(**parent), _runner(branch, is_group=is_group)
    run.load(doc)
    plan = run.save(doc, commands=("Edit", "Save"))
    blocking = {f.rule for f in plan.check.blocking}
    assert blocking == {fired}
    assert not plan.may_write
    (finding,) = [f for f in plan.check.blocking if f.rule == fired]
    assert finding.message and finding.level == "block"


def test_a_guard_on_a_command_not_asked_is_not_applied() -> None:
    """Editing an inactive record is Edit's guard; a New document is not edited."""
    doc, run = _doc(Active=0), _runner()
    run.load(doc)
    plan = run.save(doc, commands=("New", "Save"))
    assert "ModifyInactiveData" not in {f.rule for f in plan.check.findings}
    assert plan.may_write


def test_a_branch_attribute_not_in_hand_is_undecided_and_blocks() -> None:
    doc, run = _doc(), _runner(is_group=None)
    run.load(doc)
    plan = run.save(doc, commands=("Edit", "Save"))
    (undecided,) = [f for f in plan.check.findings if f.rule == "CreateData"]
    assert undecided.status == "undecided"
    assert not plan.may_write


def test_the_template_must_be_the_one_the_screen_names() -> None:
    layout = read_layout(CLEAN, "EDIT_Test", missing_template="BizDocEditor")
    with pytest.raises(ValueError, match="BizDocEditor"):
        with_template(layout, read_template(TEMPLATE, "BizDocVoucher"))


LAYOUTS = os.environ.get("DW_BRAVO_LAYOUTS")


@pytest.mark.skipif(
    not LAYOUTS or not (Path(LAYOUTS) / "layout_11463_BizDocEditor__Xml").is_file(),
    reason="Proterial's decoded template is not on this machine (DW_BRAVO_LAYOUTS)",
)
def test_proterials_bizdoceditor_is_three_guards_and_completes_the_so_screen() -> None:
    """Script 03c (production, 2026-11-25): the SO screen's template holds the
    three guards and nothing that sets or checks a value; with it, the SO
    layout is no longer missing anything a template would give."""
    folder = Path(LAYOUTS or "")
    template = read_template(
        (folder / "layout_11463_BizDocEditor__Xml").read_text(encoding="utf-8"), "BizDocEditor"
    )
    assert {g.name for g in template.guards} == {
        "ModifyInactiveData",
        "CreateData",
        "ModifyCurrentData",
    }
    so = read_layout(
        (folder / "layout_8212_EDIT_BizDocSO__Xml").read_text(encoding="utf-8"),
        "EDIT_BizDocSO",
        missing_template="BizDocEditor",
    )
    completed = with_template(so, template)
    assert completed.missing_template is None and completed.template is template


@pytest.mark.parametrize(("active", "fired"), [(True, set()), (False, {"ModifyInactiveData"})])
def test_a_bit_column_as_the_driver_gives_it_is_compared_as_bravo_does(
    active: bool, fired: set[str]
) -> None:
    """`B30BizDoc.IsActive` is a bit: the driver hands a bool, which
    `ISNULL(IsActive,1)=1` compares as 1 or 0."""
    doc, run = _doc(Active=active), _runner()
    run.load(doc)
    plan = run.save(doc, commands=("Edit", "Save"))
    assert {f.rule for f in plan.check.blocking} == fired
