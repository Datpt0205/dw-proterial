"""A new SO's statements (ticket 72), as the client sends a create: the
header's INSERT first, read back by `SCOPE_IDENTITY()`, its lines carrying
the `BizDocId` Bravo's trigger filled, and the process step after them with
that key too (UAT trace 11-25 16:53:33: `@_BizDocId=N''` on the header,
`'100000925895SO'` on the line and on `usp_B30BizDocProcess_CreateProcess`).
`so.create@1` stays `pending`; these tests drive the statements and the
writer's contract directly, never past the kind check."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from gateway_fakes import SET_DATE, gateway, token

from dw_bravo.runner import WriteCommand
from dw_bravo_gateway.adapters.sqlserver import bind, bind_step
from dw_bravo_gateway.ports import ReadBack, Statement, WriteRejectedError
from dw_bravo_gateway.statements import UnmeasuredError, process_step, render_save

pytestmark = pytest.mark.unit

HEADER_COLUMNS = ["BizDocId", "DocCode", "DocNo", "BranchCode", "ParentId", "IsActive", "CreatedBy"]
LINE_COLUMNS = ["BizDocId", "RowId", "BuiltinOrder", "ItemCode", "Quantity9", "CreatedBy"]


def _create(*, line_columns: dict[str, object] | None = None) -> list[Statement]:
    commands = [
        WriteCommand(
            "Parent",
            0,
            "insert",
            {
                "BizDocId": "",
                "DocCode": "SO",
                "DocNo": "SO2611-000003",
                "BranchCode": "A01",
                "ParentId": Decimal(-1),
                "IsActive": True,
                "CreatedBy": Decimal(2413),
            },
        ),
        WriteCommand(
            "Detail",
            0,
            "insert",
            line_columns
            if line_columns is not None
            else {
                "BizDocId": "",
                "RowId": "",
                "BuiltinOrder": Decimal(1),
                "ItemCode": "01-01-0213",
                "CreatedBy": Decimal(2413),
            },
        ),
    ]
    batch = render_save(
        "EDIT_BizDocSO",
        commands,
        {},
        {},
        context="EDIT_BizDocSO|New",
        insertable={"B30BizDoc": HEADER_COLUMNS, "B30BizDocDetailSO": LINE_COLUMNS},
        no_default={"B30BizDoc": frozenset(), "B30BizDocDetailSO": frozenset({"quantity9"})},
    )
    return list(batch.statements)


def test_a_new_so_is_its_headers_insert_then_its_lines_keyed_by_what_the_header_reads_back() -> (
    None
):
    header, line = _create()
    assert header.table == "B30BizDoc" and header.sql.startswith(
        "INSERT INTO B30BizDoc ([BizDocId],[DocCode],[DocNo],[BranchCode],[ParentId],[IsActive],"
        "[CreatedBy])"
    )
    assert header.sql.endswith(
        "SELECT TOP (1) Id,BizDocId,CreatedAt,ModifiedAt,timestamp"
        " FROM B30BizDoc WHERE Id=SCOPE_IDENTITY();"
    )
    assert header.parameters["_BizDocId"] == ""  # Bravo's trigger fills it
    assert line.table == "B30BizDocDetailSO"
    assert line.parameters["_BizDocId"] == ReadBack("B30BizDoc", "BizDocId")
    assert line.parameters["_Quantity9"] is None  # no default: listed NULL


def test_a_new_documents_process_step_carries_the_key_its_insert_reads_back() -> None:
    step = process_step(
        "EDIT_BizDocSO", {"BizDocId": ReadBack("B30BizDoc", "BizDocId"), "BranchCode": "A01"}
    )
    read = {"b30bizdoc": {"Id": 9, "BizDocId": "100000925895SO"}}
    _, values = bind_step(step, read)
    assert values == ("100000925895SO", None, "A01", "SO")


def test_a_read_back_value_is_resolved_from_the_earlier_inserts_row() -> None:
    _, line = _create()
    sql, values = bind(line, {"b30bizdoc": {"BizDocId": "100000925895SO"}})
    assert values[0] == "100000925895SO" and "SCOPE_IDENTITY" not in sql
    with pytest.raises(WriteRejectedError, match="not read back"):
        bind(line, {})
    with pytest.raises(WriteRejectedError, match="read back empty"):
        bind(line, {"b30bizdoc": {"BizDocId": ""}})


def test_a_header_insert_whose_read_back_is_needed_keeps_its_select_in_the_same_batch() -> None:
    header, _ = _create()
    sql, _ = bind(header, keep_read_back=True)
    assert sql.endswith("WHERE Id=SCOPE_IDENTITY();")
    assert "SCOPE_IDENTITY" not in bind(header)[0]


def test_a_new_documents_line_that_names_no_header_key_is_refused() -> None:
    with pytest.raises(UnmeasuredError, match="new header's key"):
        _create(line_columns={"RowId": "", "BuiltinOrder": Decimal(1)})


async def test_a_write_bravo_rejected_and_rolled_back_is_refused_not_in_doubt() -> None:
    gw = gateway()
    gw.bravo.fail_with = WriteRejectedError("B30BizDoc: no row read back")
    approval = uuid.uuid4()

    result = await gw.pipeline.execute(SET_DATE, token(approval=approval))

    assert (result.outcome, result.check, result.reason) == (
        "refused",
        "write",
        "rejected_and_rolled_back",
    )
    assert gw.ledger.entries[approval].status == "refused"
