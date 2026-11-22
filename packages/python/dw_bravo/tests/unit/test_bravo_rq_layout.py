"""Bravo's real YCBG screen (`EDIT_BizDocRQ`), run from its own layout.

Like the SO screen's tests (`test_bravo_so_layout.py`), these read Proterial's
decoded layouts from `DW_BRAVO_LAYOUTS` and the UAT trace from
`DW_BRAVO_TRACE`, and skip where they are absent; no customer value is
written here.

The screen is read with no missing template: its `B00Command` row names none
(the SO, quotation, PR and PO screens name `BizDocEditor`), and its layout
uses no rule it does not define (each of those four uses 3 to 10).
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from dw_bravo.adapters.recorded import RecordedProcedures, RecordedReferences, call_key
from dw_bravo.layout import Layout, read_layout
from dw_bravo.ports import Session
from dw_bravo.runner import Check, Document, Row, RuleRunner

LAYOUTS = os.environ.get("DW_BRAVO_LAYOUTS")
TRACE = os.environ.get("DW_BRAVO_TRACE")
RQ_LAYOUT = "layout_11766_EDIT_BizDocRQ__Xml"

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(
        not LAYOUTS or not (Path(LAYOUTS) / RQ_LAYOUT).is_file(),
        reason="Proterial's decoded layouts are not on this machine (DW_BRAVO_LAYOUTS)",
    ),
]

DAY = datetime(2026, 1, 10)
SESSION = Session(user={"Id": Decimal(7)}, branch="B1", now=DAY)


def layout_text() -> str:
    return (Path(LAYOUTS or "") / RQ_LAYOUT).read_text(encoding="utf-8")


def rq_layout(text: str | None = None) -> Layout:
    return read_layout(text or layout_text(), "EDIT_BizDocRQ")


def header(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "Id": Decimal(1),
        "BizDocId": "D1",
        "DocCode": "RQ",
        "BranchCode": "B1",
        "DocNo": "RQ-1",
        "DocDate": DAY,
        "CustomerCode": "C1",
        "DocStatus": Decimal(4),
        "CreatedBy": Decimal(7),
        "ModifiedBy": Decimal(7),
        "UserId": Decimal(7),
        "AutoNumbering": Decimal(1),
        "BizProcessGroupUnique": None,
        "BizProcessId": None,
        "BizProcess_UserIdList": None,
    }
    return {**base, **over}


def line(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "Id": Decimal(11),
        "BizDocId": "D1",
        "BuiltinOrder": Decimal(1),
        "CustomerCode": "C1",
        "BasePriceCode": None,
        "DesignCheck": None,
        "DeclineReason": None,
        "Status": "PENDING",
        "NewItem": "Y",
        "Priority": "High",
        "DesignerEmployeeId": None,
        "EstimatedCompletionDesign": None,
    }
    return {**base, **over}


def runner(text: str | None = None, *, taken: bool = False) -> RuleRunner:
    procedures = RecordedProcedures()
    # A save asks for the document's approval process (ServerUpdating); none.
    procedures.record(
        "usp_B20BizProcessGroup",
        {
            "LastBizProcessGroupUnique": None,
            "BizProcessId": None,
            "Stt": "D1",
            "DocStatus": Decimal(4),
            "DocDate": DAY,
            "CustomerCode": "C1",
            "DocCode": "RQ",
            "BranchCode": "B1",
            "UserId": Decimal(7),
            "LangId": Decimal(0),
        },
        {"BizProcessGroupUnique": None, "BizProcessId": None},
    )
    references = RecordedReferences()
    references.taken[call_key("vB30BizDoc_Edit", {"DocNo": "RQ-1"})] = taken
    return RuleRunner(rq_layout(text), procedures, references, SESSION)


def document(head: dict[str, object], lines: list[dict[str, object]]) -> Document:
    # The line's view has no audit column: the line holds none.
    rows = [Row(values) for values in lines]
    for loaded in rows:
        loaded.accept()
    return Document(Row(head), {"Detail": rows})


def check(head: dict[str, object], lines: list[dict[str, object]], *, taken: bool = False) -> Check:
    return runner(taken=taken).check(document(head, lines))


def fired(result: Check) -> set[str]:
    return {f.rule for f in result.blocking + result.warnings}


def test_the_screen_has_the_5_validators_measured_on_11_20() -> None:
    validators = [v for t in rq_layout().tables.values() for v in t.validators]
    levels = [("warning" if v.flag("bValidateWarning") else "block") for v in validators]
    assert len(validators) == 5
    assert (levels.count("block"), levels.count("warning")) == (4, 1)


def test_the_layout_uses_no_rule_it_does_not_define() -> None:
    layout = rq_layout()
    used = {
        i.name
        for t in layout.tables.values()
        for event in (
            *t.row_events.values(),
            *(e for c in t.column_events.values() for e in c.values()),
        )
        for i in event
    }
    assert used and used <= set(layout.rules)


def test_a_base_price_code_typed_by_design_quotes_and_closes_the_line() -> None:
    doc, run = document(header(), [line()]), runner()
    run.load(doc)
    run.edit(doc, "Detail", 0, "BasePriceCode", "BP1")
    row = doc.children["Detail"][0]
    assert row.get("DesignCheck") == "QUOTE"
    assert row.get("Status") == "CLOSE"
    assert row.get("DesignerEmployeeId") == Decimal(7)
    assert row.get("EstimatedCompletionDesign") == DAY
    assert row.get("NewItem") is None and row.get("Priority") is None
    plan = run.save(doc)
    written = {(c.table, c.row): dict(c.columns) for c in plan.commands}
    assert "ModifiedBy" not in written[("Detail", 0)]
    assert written[("Parent", 0)] == {"ModifiedBy": Decimal(7)}


def test_a_line_designed_by_someone_keeps_its_designer() -> None:
    doc, run = document(header(), [line(DesignerEmployeeId=Decimal(9))]), runner()
    run.load(doc)
    run.edit(doc, "Detail", 0, "BasePriceCode", "BP1")
    assert doc.children["Detail"][0].get("DesignerEmployeeId") == Decimal(9)


def test_an_edited_copy_of_the_layout_changes_what_a_typed_code_sets() -> None:
    original = "IIF(ISNULL(BasePriceCode,'')&lt;&gt;'','QUOTE','')"
    edited = layout_text().replace(original, original.replace("'QUOTE'", "'NOINFO'"))
    assert edited != layout_text()
    doc, run = document(header(), [line()]), runner(edited)
    run.load(doc)
    run.edit(doc, "Detail", 0, "BasePriceCode", "BP1")
    assert doc.children["Detail"][0].get("DesignCheck") == "NOINFO"


def test_a_plain_document_fires_nothing_it_can_decide() -> None:
    assert fired(check(header(), [line()])) == set()


def test_check_row_on_detail_fires_with_no_lines() -> None:
    assert "CheckRowOnDetail" in {f.rule for f in check(header(), []).blocking}


def test_a_doc_no_already_taken_warns_on_a_changed_header() -> None:
    run = runner(taken=True)
    doc = document(header(DocNo="RQ-0"), [line()])
    doc.parent.accept()
    doc.parent.set("DocNo", "RQ-1")
    result = run.check(doc)
    assert "DocNo" in {f.rule for f in result.warnings}
    unchanged = check(header(), [line()], taken=True)
    assert "DocNo" not in fired(unchanged)


def test_check_biz_process_passes_for_its_creator_and_is_undecided_otherwise() -> None:
    in_process = {"BizProcessGroupUnique": "G1", "BizProcess_UserIdList": ",9,"}
    assert "CheckBizProcess" not in fired(check(header(**in_process), [line()]))
    other = check(header(**in_process, CreatedBy=Decimal(9)), [line()])
    finding = next(f for f in other.undecided if f.rule == "CheckBizProcess")
    assert "CHARINDEX" in (finding.reason or "")
    assert not other.may_save


@pytest.mark.parametrize(("rule", "table"), [("NotNull_DocNo", "Parent"), ("NotNull", "Detail")])
def test_validators_without_a_class_name_are_undecided_and_block(rule: str, table: str) -> None:
    result = check(header(AutoNumbering=Decimal(0)), [line()])
    findings = [f for f in result.findings if f.rule == rule]
    assert findings and all(f.status == "undecided" and f.table == table for f in findings)
    assert all("ClassName" in (f.reason or "") for f in findings)
    assert not result.may_save


# --------------------------------------------------------------- the trace


@pytest.mark.skipif(
    not TRACE or not Path(TRACE).is_file(),
    reason="the UAT trace is not on this machine (DW_BRAVO_TRACE)",
)
def test_designs_saved_result_in_the_uat_trace_is_reproduced_column_for_column() -> None:
    from dw_bravo.testing import sql_trace
    from dw_bravo.testing.replay import group_saves, rq_screen_replay

    statements = sql_trace.read(Path(TRACE or ""))
    saves = group_saves(sql_trace.writes(statements), "EDIT_BizDocRQ")
    calls = [
        c for c in sql_trace.procedure_calls(statements) if c.statement.screen == "EDIT_BizDocRQ"
    ]
    context = re.search(r"@(\d+)@\d+@(\w+)@", saves[0].writes[0].statement.sql)
    assert context is not None

    replay = rq_screen_replay(rq_layout(), int(context.group(1)), context.group(2))
    [result] = replay.replay(saves, calls)  # the one UPDATE; the creation is an INSERT
    assert result.matched, result.mismatch
    assert not [f for f in result.fired if f.level == "block"], result.fired
    # What Design typed is written as typed; these four the layout computed.
    assert sorted(result.computed["Detail#0"]) == [
        "DesignCheck",
        "DesignerEmployeeId",
        "EstimatedCompletionDesign",
        "Status",
    ]
