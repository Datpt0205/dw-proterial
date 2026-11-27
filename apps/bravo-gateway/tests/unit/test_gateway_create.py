"""A new SO's statements (ticket 72), as the client sends a create: the
header's INSERT first, read back by `SCOPE_IDENTITY()`, its lines carrying
the `BizDocId` Bravo's trigger filled, and the process step after them with
that key too (UAT trace 11-25 16:53:33: `@_BizDocId=N''` on the header,
`'100000925895SO'` on the line and on `usp_B30BizDocProcess_CreateProcess`).
`so.create@1` stays `pending`; these tests drive the statements and the
writer's contract directly, never past the kind check."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal

import pytest
from gateway_fakes import SET_DATE, gateway, token

from dw_bravo.runner import WriteCommand
from dw_bravo_gateway.adapters.sqlserver import Login, SqlServerBravo, bind, bind_step
from dw_bravo_gateway.ports import Batch, ReadBack, Statement, WriteRejectedError
from dw_bravo_gateway.statements import UnmeasuredError, process_step, render_save

pytestmark = pytest.mark.unit

HEADER_COLUMNS = ["BizDocId", "DocCode", "DocNo", "BranchCode", "ParentId", "IsActive", "CreatedBy"]
LINE_COLUMNS = ["BizDocId", "RowId", "BuiltinOrder", "ItemCode", "Quantity9", "CreatedBy"]


def _create(
    *, line_columns: dict[str, object] | None = None, stored_line: bool = False
) -> list[Statement]:
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
    if stored_line:
        commands.append(WriteCommand("Detail", 1, "update", {"Quantity9": Decimal(5)}))
    batch = render_save(
        "EDIT_BizDocSO",
        commands,
        {("Detail", 1): (11, "0x00000000000007D1")},
        {"B30BizDocDetailSO": LINE_COLUMNS},
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


def test_a_stored_row_in_a_new_documents_save_is_refused() -> None:
    """A create writes its own rows only: an UPDATE of a stored row beside
    the new header's INSERT is a save no trace holds."""
    with pytest.raises(UnmeasuredError, match="stored row written in a new document's save"):
        _create(stored_line=True)


# The header INSERT's read-back as the driver hands it over: each result set
# the statement produced, None for a row count (its trigger's, without SET
# NOCOUNT ON), else its rows.
READ_BACK = ("Id", "BizDocId", "CreatedAt", "ModifiedAt", "timestamp")
ROW = (9, "100000925895SO", None, None, bytes(8))


class _Cursor:
    def __init__(self, header_sets: Sequence[Sequence[tuple[object, ...]] | None]) -> None:
        self.header_sets = header_sets
        self.sets: list[Sequence[tuple[object, ...]] | None] = []
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.rowcount = 1

    def execute(self, sql: str, values: tuple[object, ...] = ()) -> None:
        self.executed.append((sql, values))
        self.sets = list(self.header_sets) if sql.startswith("INSERT INTO B30BizDoc ") else [None]

    @property
    def description(self) -> list[tuple[str]] | None:
        rows = self.sets[0] if self.sets else None
        return None if rows is None else [(n,) for n in READ_BACK]

    def nextset(self) -> bool:
        if self.sets:
            self.sets.pop(0)
        return bool(self.sets)

    def fetchall(self) -> Sequence[tuple[object, ...]]:
        rows = self.sets[0]
        assert rows is not None
        return rows


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self.the_cursor = cursor
        self.events: list[str] = []

    def cursor(self) -> _Cursor:
        return self.the_cursor

    def commit(self) -> None:
        self.events.append("commit")

    def rollback(self) -> None:
        self.events.append("rollback")

    def close(self) -> None:
        self.events.append("close")


def _writer(header_sets: Sequence[Sequence[tuple[object, ...]] | None]) -> _Connection:
    return _Connection(_Cursor(header_sets))


async def _execute(connection: _Connection) -> None:
    login = Login("db", 1433, "bravo", "dw", "secret")
    bravo = SqlServerBravo(login, login, connect=lambda _cs, _auto: connection)
    await bravo.execute(Batch(context="EDIT_BizDocSO|New", statements=_create()))


async def test_the_writer_keys_a_new_line_by_the_one_row_its_header_reads_back() -> None:
    connection = _writer([None, [ROW]])  # the trigger's count, then the SELECT
    await _execute(connection)
    inserts = [v for sql, v in connection.the_cursor.executed if sql.startswith("INSERT")]
    assert inserts[1][0] == "100000925895SO"
    assert connection.events[0] == "commit"


@pytest.mark.parametrize(
    "header_sets",
    [[None], [None, []], [[ROW, (10, "100000925896SO", None, None, bytes(8))]]],
    ids=["no_select", "no_row", "two_rows"],
)
async def test_a_header_insert_that_reads_back_no_one_row_is_rejected_and_rolled_back(
    header_sets: Sequence[Sequence[tuple[object, ...]] | None],
) -> None:
    connection = _writer(header_sets)
    with pytest.raises(WriteRejectedError, match="B30BizDoc: no row read back"):
        await _execute(connection)
    executed = [sql for sql, _ in connection.the_cursor.executed]
    assert not any(sql.startswith("INSERT INTO B30BizDocDetailSO") for sql in executed)
    assert connection.events[0] == "rollback"
