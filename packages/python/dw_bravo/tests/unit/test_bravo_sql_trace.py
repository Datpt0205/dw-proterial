"""Reading a trace's deletes, replay states for a save that adds lines, and
the replay's answer to a procedure several lines fit (ticket 73), on
statements written for these tests (no Bravo data)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from dw_bravo.expression import UndecidableError
from dw_bravo.layout import PARENT, read_layout
from dw_bravo.ports import Session
from dw_bravo.testing import sql_trace
from dw_bravo.testing.replay import SaveGroup, ScreenReplay, _ReplayProcedures

pytestmark = pytest.mark.unit

AT = datetime(2026, 11, 25, 17, 28, 58)


def _statement(sql: str, at: datetime = AT) -> sql_trace.Statement:
    return sql_trace.Statement(1, at, "B8$PC\\PIC/EDIT_BizDocSO", 66, sql)


def test_a_deleted_row_is_read_with_its_id() -> None:
    sql = (
        "exec sp_executesql N'SET LOCK_TIMEOUT 1800000; DELETE TOP (1) FROM B30BizDocDetailSO"
        " WHERE Id=@_Original_Id AND timestamp=@_Original_timestamp;SET LOCK_TIMEOUT -1;',"
        "N'@_Original_Id int,@_Original_timestamp timestamp',@_Original_Id=381390,"
        "@_Original_timestamp=0x0000000080978695"
    )
    update = (
        "exec sp_executesql N'UPDATE TOP (1) B30BizDoc SET [A]=@_A WHERE Id=@_Id;',N'@_A int',@_A=1"
    )

    [deleted] = sql_trace.deletes([_statement(sql), _statement(update)])

    assert (deleted.table, deleted.row_id) == ("B30BizDocDetailSO", Decimal(381390))


def _write(kind: str, table: str, at: datetime, **values: object) -> sql_trace.Write:
    columns = tuple(c for c in values if c != "Id")
    return sql_trace.Write(_statement("", at), kind, table, columns, dict(values))


def _replay() -> ScreenReplay:
    layout = read_layout("<root><Tables><ParentTable /></Tables></root>", "EDIT_BizDocSO")
    return ScreenReplay(
        layout,
        "B30BizDoc",
        "B30BizDocDetailSO",
        "Detail",
        session_for=lambda save: Session(user={}, branch="A01", now=save.at),
        derive_header=lambda row: {},
        derive_line=lambda row: {},
    )


def test_a_save_that_adds_lines_is_a_state_only_when_asked_and_its_inserts_stay_apart() -> None:
    t0, t1, t2 = (datetime(2026, 11, 25, 17, m) for m in (0, 10, 20))
    created = SaveGroup(
        t0,
        [
            _write("insert", "B30BizDoc", t0, BizDocId="D1", Total=Decimal(1)),
            _write(
                "insert", "B30BizDocDetailSO", t0, BuiltinOrder=Decimal(1), Quantity9=Decimal(1)
            ),
        ],
    )
    edited = SaveGroup(
        t1,
        [
            _write("update", "B30BizDoc", t1, Id=Decimal(9), Total=Decimal(4)),
            _write(
                "update",
                "B30BizDocDetailSO",
                t1,
                Id=Decimal(5),
                BuiltinOrder=Decimal(1),
                Quantity9=Decimal(4),
            ),
        ],
    )
    split = SaveGroup(
        t2,
        [
            _write("update", "B30BizDoc", t2, Id=Decimal(9), Total=Decimal(4)),
            _write(
                "insert", "B30BizDocDetailSO", t2, BuiltinOrder=Decimal(2), Quantity9=Decimal(1)
            ),
            _write(
                "update",
                "B30BizDocDetailSO",
                t2,
                Id=Decimal(5),
                BuiltinOrder=Decimal(1),
                Quantity9=Decimal(3),
            ),
        ],
    )
    replay = _replay()

    assert [s.save.at for s in replay.states([created, edited, split], [])] == [t1]
    states = replay.states([created, edited, split], [], with_inserts=True)

    assert [s.save.at for s in states] == [t1, t2]  # a new document is never one
    assert [w.values["BuiltinOrder"] for w in states[1].inserted] == [Decimal(2)]
    _, before_l, _, after_l, written = replay.before_after(states[1])
    assert set(written) == {"Parent", "Detail#1"}
    assert [line["Quantity9"] for line in before_l] == [Decimal(4)]
    assert [line["Quantity9"] for line in after_l] == [Decimal(3)]


PROCEDURE_LAYOUT = """<root><Tables>
<ParentTable><Name>vDoc_Edit</Name></ParentTable>
<ChildTable_Detail>
  <Name>vLine_Edit</Name><Alias>Detail</Alias>
  <ColumnChanged><Eta>
    <Eval_Cd><ClassName>BravoServerConstraint</ClassName><Command>ufn_Cd</Command>
      <Parameters><Customer>Parent.Customer</Customer><Eta>Eta</Eta></Parameters>
      <DataMember>CdDate</DataMember></Eval_Cd>
  </Eta></ColumnChanged>
</ChildTable_Detail></Tables></root>"""
ETA = datetime(2026, 12, 1)


def _procedures(*cd_dates: datetime) -> _ReplayProcedures:
    """Lines that all fit one traced `ufn_Cd` call (a split's lines share an
    item and a customer), each holding the `CdDate` given."""
    call = sql_trace.ProcedureCall(
        _statement("exec ufn_Cd"), "ufn_Cd", {"Customer": "C1", "Eta": ETA}
    )
    after: dict[str, list[dict[str, object]]] = {
        PARENT: [{"Customer": "C1"}],
        "Detail": [{"Eta": ETA, "CdDate": cd} for cd in cd_dates],
    }
    return _ReplayProcedures(
        read_layout(PROCEDURE_LAYOUT, "EDIT_X", missing_template=None), [call], after
    )


def test_lines_that_agree_answer_a_procedure_they_all_fit() -> None:
    answer = _procedures(datetime(2026, 11, 28), datetime(2026, 11, 28)).call(
        "ufn_Cd", {"Customer": "C1", "Eta": ETA}, ["CdDate"]
    )

    assert answer == {"CdDate": datetime(2026, 11, 28)}


def test_lines_that_disagree_leave_the_procedures_result_undecided() -> None:
    procedures = _procedures(datetime(2026, 11, 28), datetime(2026, 11, 29))

    with pytest.raises(UndecidableError, match="2 rows fit its parameters"):
        procedures.call("ufn_Cd", {"Customer": "C1", "Eta": ETA}, ["CdDate"])
