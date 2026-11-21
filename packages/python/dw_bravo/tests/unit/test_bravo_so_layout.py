"""Bravo's real SO screen (`EDIT_BizDocSO`), run from its own layout.

The layout and the UAT trace are Proterial's and stay out of git
(`docs/proterial/`, gitignored, and the operator's own folder). These tests
read them from `DW_BRAVO_LAYOUTS` (the folder of decoded layouts) and
`DW_BRAVO_TRACE` (`02-trace-uat-bo-sung.csv`) and skip where they are absent,
so CI runs the runner's mechanics (`test_bravo_runner.py`) and a machine that
holds the data runs these too. The rows below are made up for each rule; no
customer value is written here.

Each of the screen's 27 validators has a test that fires it, or, where the
screen's own definition cannot be decided here, one that shows it undecided
with the reason (the shared template, CHARINDEX).
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
from dw_bravo.runner import Document, Row, RuleRunner

LAYOUTS = os.environ.get("DW_BRAVO_LAYOUTS")
TRACE = os.environ.get("DW_BRAVO_TRACE")
SO_LAYOUT = "layout_8212_EDIT_BizDocSO__Xml"

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(
        not LAYOUTS or not (Path(LAYOUTS) / SO_LAYOUT).is_file(),
        reason="Proterial's decoded layouts are not on this machine (DW_BRAVO_LAYOUTS)",
    ),
]

DAY = datetime(2026, 1, 10)


def layout_text() -> str:
    return (Path(LAYOUTS or "") / SO_LAYOUT).read_text(encoding="utf-8")


def so_layout(text: str | None = None) -> Layout:
    return read_layout(text or layout_text(), "EDIT_BizDocSO", missing_template="BizDocEditor")


def header(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "Id": Decimal(1),
        "BizDocId": "D1",
        "DocCode": "SO",
        "BranchCode": "B1",
        "DocNo": "SO-1",
        "DocDate": DAY,
        "Type": "Mass",
        "CurrencyCode": "USD",
        "CustomerCode": "C1",
        "IndirectCustomerCode": "",
        "POCustomer": "PO-1",
        "CreatedBy": Decimal(7),
        "BizProcessGroupUnique": None,
        "BizProcessId": None,
        "CheckEmptyECP_C2": Decimal(0),
        "C2CheckCustomer": "",
        "ReceiptDate": DAY,
    }
    return {**base, **over}


def line(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "Id": Decimal(11),
        "ItemCode": "I1",
        "ItemCodeTmp": "I1",
        "PRSNo": None,
        "Quantity9": Decimal(10),
        "Quantity": Decimal(10),
        "Quantity_RW": Decimal(0),
        "Quantity_RP": Decimal(0),
        "Quantity_Edit": Decimal(10),
        "Quantity9YC": Decimal(0),
        "QuantityPRS": Decimal(0),
        "TypeSO": "Mass",
        "QuantityGroup": Decimal(0),
        "QuantityGroupBeforeDivi": Decimal(0),
        "Divide": Decimal(0),
        "SalesSpecialNote": None,
        "EstimatedTimeDelivery": datetime(2026, 2, 1),
        "PORequestDate": datetime(2026, 3, 1),
        "LeadTime": Decimal(5),
        "BoxQuantity": Decimal(1),
        "QuantityBox": Decimal(1),
        "Length": Decimal(10),
        "PackingNote": None,
        "IsCancel": None,
        "CancelQuantity": Decimal(0),
        "CheckEmptyECP": Decimal(0),
        "CheckEmptyECP_Indir": Decimal(0),
        "UnitCost": Decimal(1),
        "BasePrice": Decimal(1000),
        "OriginalAmount9": Decimal(10),
        "OriginalAmount9_Check": Decimal(10),
        "CheckDate": Decimal(1),
        "Catalogry": "HK",
        "SalesAccountingDate": datetime(2026, 2, 1),
    }
    return {**base, **over}


def check(
    head: dict[str, object],
    lines: list[dict[str, object]],
    *,
    mp: Decimal = Decimal(0),
    taken: bool = False,
):
    procedures = RecordedProcedures()
    for row in lines:
        procedures.record("usp_Item_CheckMP", {"ItemCode": row["ItemCode"]}, {"Result": mp})
    references = RecordedReferences()
    references.taken[
        call_key(
            "vB30BizDoc_Edit",
            {"POCustomer": head["POCustomer"], "CustomerCode": head["CustomerCode"]},
        )
    ] = taken
    references.taken[call_key("vB30BizDoc_Edit", {"DocNo": head["DocNo"]})] = taken
    session = Session(user={"Id": Decimal(7)}, branch="B1", now=DAY)
    runner = RuleRunner(so_layout(), procedures, references, session)
    rows = [Row(values) for values in lines]
    for loaded in rows:
        loaded.accept()
    return runner.check(Document(Row(head), {"Detail": rows}))


def fired(result) -> set[str]:
    return {f.rule for f in result.blocking + result.warnings}


def test_the_screen_has_the_27_validators_measured_on_11_20() -> None:
    layout = so_layout()
    validators = [v for t in layout.tables.values() for v in t.validators]
    levels = [("warning" if v.flag("bValidateWarning") else "block") for v in validators]
    assert len(validators) == 27
    assert (levels.count("block"), levels.count("warning")) == (17, 10)


def test_a_plain_document_fires_nothing_it_can_decide() -> None:
    result = check(header(), [line()])
    assert fired(result) == set()


@pytest.mark.parametrize(
    ("rule", "head", "row", "kwargs"),
    [
        ("POCustomerValidator", {}, {}, {"taken": True}),
        ("DocNo", {}, {}, {"taken": True}),
        ("CheckC2", {"CheckEmptyECP_C2": Decimal(1)}, {}, {}),
        (
            "CheckQuantityReword",
            {"Type": "Returned"},
            {"Quantity_RW": Decimal(3), "Quantity_RP": Decimal(4)},
            {},
        ),
        ("SepcialNoteWarmning", {}, {"SalesSpecialNote": "note"}, {}),
        ("EstimatedTimeDeliveryCheckDate", {}, {"EstimatedTimeDelivery": datetime(2026, 1, 1)}, {}),
        ("BoxQuantity", {}, {"Quantity9": Decimal(15)}, {}),
        ("ShortLeadTime", {}, {"PORequestDate": datetime(2026, 1, 12)}, {}),
        ("QuantityPRSCheck", {}, {"QuantityPRS": Decimal(20)}, {}),
        ("PackingNoteCheck", {}, {"PackingNote": "please check con lan"}, {}),
        (
            "CheckDivide",
            {},
            {
                "Divide": Decimal(1),
                "QuantityGroup": Decimal(10),
                "QuantityGroupBeforeDivi": Decimal(9),
            },
            {},
        ),
        ("CheckQuanity", {}, {"Quantity": Decimal(0)}, {}),
        ("CheckMP", {}, {}, {"mp": Decimal(1)}),
        ("CheckEmptyECP", {}, {"CheckEmptyECP": Decimal(1)}, {}),
        ("CheckEmptyECP_Indir", {}, {"CheckEmptyECP_Indir": Decimal(1)}, {}),
        ("CheckUnitUSD", {}, {"UnitCost": Decimal(2)}, {}),
        ("CheckJPY", {"CurrencyCode": "JPY"}, {"OriginalAmount9_Check": Decimal(9)}, {}),
        ("CheckDate", {}, {"CheckDate": Decimal(0)}, {}),
    ],
)
def test_each_decidable_validator_fires(
    rule: str, head: dict[str, object], row: dict[str, object], kwargs: dict[str, Decimal | bool]
) -> None:
    result = check(header(**head), [line(**row)], **kwargs)  # type: ignore[arg-type]
    assert rule in fired(result)


def test_check_row_on_detail_fires_with_no_lines() -> None:
    assert "CheckRowOnDetail" in fired(check(header(), []))


def test_check_is_cancel_fires_only_on_a_modified_row() -> None:
    cancelled = line(IsCancel="Cancel", CancelQuantity=Decimal(10))
    assert "CheckIsCancel" not in fired(check(header(), [cancelled]))
    procedures = RecordedProcedures()
    procedures.record("usp_Item_CheckMP", {"ItemCode": "I1"}, {"Result": Decimal(0)})
    references = RecordedReferences()
    references.taken[call_key("vB30BizDoc_Edit", {"POCustomer": "PO-1", "CustomerCode": "C1"})] = (
        False
    )
    references.taken[call_key("vB30BizDoc_Edit", {"DocNo": "SO-1"})] = False
    runner = RuleRunner(
        so_layout(), procedures, references, Session(user={"Id": Decimal(7)}, branch="B1", now=DAY)
    )
    row = Row({**cancelled, "CancelQuantity": Decimal(0)})
    row.accept()
    row.set("CancelQuantity", Decimal(10))  # the person cancels but leaves the quantity
    doc = Document(Row(header()), {"Detail": [row]})
    assert "CheckIsCancel" in fired(runner.check(doc))


def test_check_biz_process_passes_for_its_creator_and_is_undecided_otherwise() -> None:
    in_process = {
        "BizProcessGroupUnique": "G1",
        "BizProcessId": None,
        "BizProcess_UserIdList": ",9,",
    }
    assert "CheckBizProcess" not in fired(check(header(**in_process), [line()]))
    other = check(header(**in_process, CreatedBy=Decimal(9)), [line()])
    finding = next(f for f in other.undecided if f.rule == "CheckBizProcess")
    assert "CHARINDEX" in (finding.reason or "")


@pytest.mark.parametrize(
    "rule", ["NotNull", "NotNull_DocNo", "LME", "ItemCodeTmp_CheckEdit", "NotnullCatalogry"]
)
def test_validators_whose_kind_lives_in_the_template_are_undecided(rule: str) -> None:
    result = check(header(AutoNumbering=Decimal(0)), [line(Id=Decimal(1), PRSNo="P1")])
    findings = [f for f in result.findings if f.rule == rule]
    assert findings and all(f.status == "undecided" for f in findings)
    assert all("template" in (f.reason or "") for f in findings)
    if rule == "NotNull":
        assert {f.table for f in findings} == {"Parent", "Detail"}


def test_an_edited_copy_of_the_layout_changes_the_check() -> None:
    edited = layout_text().replace("* 100 &gt; 150", "* 100 &gt; 250")
    assert edited != layout_text()
    head, row = header(), line(UnitCost=Decimal(2))  # 200% of BasePrice/1000
    procedures = RecordedProcedures()
    procedures.record("usp_Item_CheckMP", {"ItemCode": "I1"}, {"Result": Decimal(0)})
    references = RecordedReferences()
    references.taken[call_key("vB30BizDoc_Edit", {"POCustomer": "PO-1", "CustomerCode": "C1"})] = (
        False
    )
    references.taken[call_key("vB30BizDoc_Edit", {"DocNo": "SO-1"})] = False
    session = Session(user={"Id": Decimal(7)}, branch="B1", now=DAY)
    original = RuleRunner(so_layout(), procedures, references, session).check(
        Document(Row(head), {"Detail": [Row(row)]})
    )
    changed = RuleRunner(so_layout(edited), procedures, references, session).check(
        Document(Row(head), {"Detail": [Row(row)]})
    )
    assert "CheckUnitUSD" in fired(original)
    assert "CheckUnitUSD" not in fired(changed)


# --------------------------------------------------------------- the trace


@pytest.mark.skipif(
    not TRACE or not Path(TRACE).is_file(),
    reason="the UAT trace is not on this machine (DW_BRAVO_TRACE)",
)
def test_every_saved_so_update_in_the_uat_trace_is_reproduced_column_for_column() -> None:
    from dw_bravo.testing import sql_trace
    from dw_bravo.testing.replay import group_saves, so_screen_replay

    statements = sql_trace.read(Path(TRACE or ""))
    saves = group_saves(sql_trace.writes(statements), "EDIT_BizDocSO")
    calls = [
        c for c in sql_trace.procedure_calls(statements) if c.statement.screen == "EDIT_BizDocSO"
    ]
    context = re.search(r"@(\d+)@\d+@(\w+)@", saves[0].writes[0].statement.sql)
    assert context is not None
    user_id, branch = int(context.group(1)), context.group(2)

    replay = so_screen_replay(so_layout(), user_id, branch)
    results = replay.replay(saves, calls)
    updates = [s for s in saves if all(w.kind == "update" for w in s.writes)]
    assert len(results) == len(updates) == 6
    for result in results:
        assert result.matched, f"{result.save.at}: {result.mismatch}"
        assert not [f for f in result.fired if f.level == "block"], result.fired
    # The rules, not the search, wrote most columns: one or a few typed values
    # each, the rest computed by the layout.
    computed = sum(len(c) for r in results for c in r.computed.values())
    typed = sum(len(c) for r in results for c in r.roots.values())
    assert computed > typed
