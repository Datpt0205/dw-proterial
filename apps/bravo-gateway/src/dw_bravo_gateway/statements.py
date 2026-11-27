"""The client's own statements, rendered from the rule runner's save plan.

Measured on the 2026-11-20 UAT trace (`EDIT_BizDocSO` saves), and nothing
here goes beyond it:

- the client sets the connection's context before it writes:
  `CAST('<command>|<event>' padded to 50, '@<user id>@0@<branch>@<year>')`,
  which Bravo's triggers read the user from
  (`ufn_sys_GetUserIdFromContext_Info`); the `0` was 0 in every statement
  traced, its meaning unknown;
- an UPDATE sets the changed columns, then `[ModifiedAt]=DEFAULT`, holds
  `Id` and the row's `timestamp`, and reads the row back:
  `UPDATE TOP (1) <t> SET [c]=@_c,...,[ModifiedAt]=DEFAULT WHERE
  Id=@_Original_Id AND timestamp=@_Original_timestamp;SELECT TOP (1)
  Id,<key>,CreatedAt,ModifiedAt,timestamp FROM <t> WHERE Id=@_Id;`.

The order the client lists its SET columns in is its own: not the table's,
not its load view's, not the order the rules changed them (each tried on the
trace). An UPDATE's meaning does not depend on it (every value is a
parameter), so the gateway lists them in the table's order and the replay
compares the assignments as a set.

An INSERT, measured on the five the UAT traces hold (11-20 10:26:40 and
10:30:07, 11-25 16:53:33, 16:56:07 and 17:28:58):
`INSERT INTO <t> ([c],...) VALUES (@_c,...);SELECT TOP (1)
Id,<key>,CreatedAt,ModifiedAt,timestamp FROM <t> WHERE Id=SCOPE_IDENTITY();`,
listing in the table's order every column the client's row holds that is
not NULL, and every NULL one the table gives no default (passed as a NULL
parameter); the row's key column (`RowId`) is written '' and Bravo's own
trigger fills it. A save lists the header's UPDATE first, then the new
lines' INSERTs, then the lines' UPDATEs (11-20 10:30:07, 11-25 16:56:07 and
17:28:58).

What is not measured is refused (`UnmeasuredError`), never guessed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Final

from dw_bravo.runner import WriteCommand
from dw_bravo_gateway.ports import Batch, ProcedureStep, ReadBack, Statement

_CONTEXT_WIDTH: Final = 50
_CONTEXT_LIMIT: Final = 128  # varbinary(128)


class UnmeasuredError(Exception):
    """What the client would send here is not measured; nothing is sent."""


@dataclass(frozen=True)
class ScreenTables:
    """Where a screen's layout tables are stored, as the trace shows."""

    header: str
    lines: Mapping[str, str]  # layout table key -> stored table
    # The second column of each table's read-back SELECT (`Id,<key>,...`).
    read_back_key: Mapping[str, str]
    # The event word of the context for a save, by operation. Absent: not
    # measured, so refused.
    context_event: Mapping[str, str]
    # The document code the client passes the process step (`DocCode`).
    doc_code: str
    # What the client's new line holds before anything is typed, beyond
    # NULL: its key column '' in every traced INSERT, filled by Bravo's
    # trigger (`DML_B30BizDocDetailSO_InsertUpdate_RowId`).
    new_line: Mapping[str, object] = field(default_factory=dict)
    # What the client's new header holds beyond NULL and the layout's
    # DefaultValues: in both traced SO creates (11-20 10:26:40, 11-25
    # 16:53:33) `ParentId` -1 and `IsActive` 1, which no rule of 8212 sets.
    new_header: Mapping[str, object] = field(default_factory=dict)
    # Each line table's column holding its header's key: a new header's
    # lines carry the key its INSERT reads back (the layout's
    # `ParentKey`/`ChildKey`, `BizDocId`).
    relation: Mapping[str, str] = field(default_factory=dict)

    def table_for(self, layout_key: str) -> str:
        if layout_key == "Parent":
            return self.header
        try:
            return self.lines[layout_key]
        except KeyError:
            raise UnmeasuredError(f"where layout table {layout_key} is stored") from None


SCREENS: Final[Mapping[str, ScreenTables]] = {
    "EDIT_BizDocSO": ScreenTables(
        header="B30BizDoc",
        lines={"Detail": "B30BizDocDetailSO"},
        read_back_key={"B30BizDoc": "BizDocId", "B30BizDocDetailSO": "RowId"},
        # The client's word for a save (ticket 70): `Edit` for an SO opened
        # from the list (UAT trace 11-25, the date and quantity saves, and
        # 11-26's cancel and split), `New` for a document created in the
        # same window (11-20, 11-25 16:53). The gateway only ever writes a
        # stored SO, so an update is `Edit`; `New` is the create's.
        context_event={"update": "Edit", "insert": "New"},
        doc_code="SO",
        new_line={"RowId": ""},
        new_header={"ParentId": Decimal(-1), "IsActive": True},
        relation={"B30BizDocDetailSO": "BizDocId"},
    ),
}

# The procedure every save of a document ends with in the UAT traces (11-20
# to 11-26): Bravo's business-process rows for the document. The gateway
# runs it after its statements, in the same transaction (ticket 74, ADR
# 0027 amendment); the write login holds EXECUTE on it and nothing else.
PROCESS_PROCEDURE: Final = "usp_B30BizDocProcess_CreateProcess"


def process_step(screen: str, header: Mapping[str, object]) -> ProcedureStep:
    """The process step after a save, with the client's arguments: the
    document's `BizDocId` and `BranchCode`, no process group, the screen's
    document code (`exec dbo.usp_B30BizDocProcess_CreateProcess
    @_BizDocId='…SO',@_BizProcessGroupUnique=NULL,@_BranchCode='A01',
    @_DocCode='SO'` in every traced save)."""
    biz_doc_id, branch = header.get("BizDocId"), header.get("BranchCode")
    if not biz_doc_id or not branch:
        raise UnmeasuredError("the document's BizDocId or BranchCode for its process step")
    return ProcedureStep(
        name=PROCESS_PROCEDURE,
        parameters={
            # A new document's is the one its INSERT reads back.
            "_BizDocId": biz_doc_id if isinstance(biz_doc_id, ReadBack) else str(biz_doc_id),
            "_BizProcessGroupUnique": None,
            "_BranchCode": str(branch),
            "_DocCode": SCREENS[screen].doc_code,
        },
    )


def context_line(command: str, event: str | None, user_id: int, branch: str, year: int) -> str:
    """The text the client casts to varbinary and sets as Context_Info."""
    head = command if event is None else f"{command}|{event}"
    if len(head) > _CONTEXT_WIDTH or "@" in head or "'" in head:
        raise ValueError(f"cannot write {head!r} into the context")
    if "@" in branch or "'" in branch or not branch:
        raise ValueError("a branch code holds no '@' or quote")
    text = f"{head.ljust(_CONTEXT_WIDTH)}@{user_id}@0@{branch}@{year}"
    if len(text.encode("ascii")) > _CONTEXT_LIMIT:
        raise ValueError("the context is longer than varbinary(128)")
    return text


def render_update(
    table: str,
    columns: Mapping[str, object],
    column_order: Sequence[str],
    *,
    row_id: object,
    rowversion: str,
    read_back_key: str,
) -> Statement:
    """One UPDATE as the client writes it. `columns` is the runner's set,
    `ModifiedBy` included; each must be one of the table's own columns
    (`column_order`, spelled as the table does); `ModifiedAt` is the
    database's default."""
    position = {c.lower(): i for i, c in enumerate(column_order)}
    unknown = [c for c in columns if c.lower() not in position]
    if unknown:
        raise UnmeasuredError(f"{table} has no column {', '.join(sorted(unknown))}")
    ordered = sorted(columns, key=lambda c: position[c.lower()])
    names = [column_order[position[c.lower()]] for c in ordered]
    for name in names:
        if not name.replace("_", "").isalnum():
            raise ValueError(f"{name!r} is not a column name the client writes")
    if not table.isalnum() or not read_back_key.isalnum():
        raise ValueError("table and key are Bravo's own names")
    # A NULL is written as the column's DEFAULT, never as a NULL parameter:
    # every NULL the client set in the UAT traces (11-20 to 11-26) reads so.
    nulls = {n for n, c in zip(names, ordered, strict=True) if columns[c] is None}
    assignments = ",".join(f"[{n}]=DEFAULT" if n in nulls else f"[{n}]=@_{n}" for n in names)
    sql = (
        f"UPDATE TOP (1) {table} SET {assignments},[ModifiedAt]=DEFAULT"
        " WHERE Id=@_Original_Id AND timestamp=@_Original_timestamp;"
        f"SELECT TOP (1) Id,{read_back_key},CreatedAt,ModifiedAt,timestamp"
        f" FROM {table} WHERE Id=@_Id;"
    )
    parameters: dict[str, object] = {
        f"_{n}": columns[c] for n, c in zip(names, ordered, strict=True) if n not in nulls
    }
    parameters |= {"_Original_Id": row_id, "_Original_timestamp": rowversion, "_Id": row_id}
    return Statement(table=table, row_id=row_id, sql=sql, parameters=parameters)


def render_insert(
    table: str,
    columns: Mapping[str, object],
    insertable: Sequence[str],
    no_default: frozenset[str],
    *,
    read_back_key: str,
) -> Statement:
    """One INSERT as the client writes it. `columns` is the runner's set for
    the new row (its non-NULL columns, `CreatedBy` included); `insertable`
    the columns the client's row holds that the table stores, in the
    table's order (its load view's columns that are the table's, less the
    identity and the rowversion); `no_default` (lower case) the table's
    columns without a default, which are listed NULL when the row has none.
    INSERT is granted on the whole table (SQL Server has no column INSERT
    grant), so this list is the only column guard the write login has."""
    if not insertable:
        raise UnmeasuredError(f"the columns a new row of {table} holds are not read")
    position = {c.lower(): c for c in insertable}
    unknown = [c for c in columns if c.lower() not in position]
    if unknown:
        raise UnmeasuredError(f"a new row of {table} holds no column {', '.join(sorted(unknown))}")
    given = {c.lower(): v for c, v in columns.items()}
    names = [c for c in insertable if given.get(c.lower()) is not None or c.lower() in no_default]
    for name in names:
        if not name.replace("_", "").isalnum():
            raise ValueError(f"{name!r} is not a column name the client writes")
    if not table.isalnum() or not read_back_key.isalnum():
        raise ValueError("table and key are Bravo's own names")
    sql = (
        f"INSERT INTO {table} ({','.join(f'[{n}]' for n in names)})"
        f" VALUES ({','.join(f'@_{n}' for n in names)});"
        f"SELECT TOP (1) Id,{read_back_key},CreatedAt,ModifiedAt,timestamp"
        f" FROM {table} WHERE Id=SCOPE_IDENTITY();"
    )
    parameters = {f"_{n}": given.get(n.lower()) for n in names}
    return Statement(table=table, row_id=None, sql=sql, parameters=parameters)


def render_save(
    screen: str,
    commands: Sequence[WriteCommand],
    rows: Mapping[tuple[str, int], tuple[object, str]],
    column_order: Mapping[str, Sequence[str]],
    *,
    context: str,
    insertable: Mapping[str, Sequence[str]] | None = None,
    no_default: Mapping[str, frozenset[str]] | None = None,
) -> Batch:
    """A plan's commands as one batch, in the client's order: the header,
    the new rows, the stored rows. `rows` gives each stored (layout table,
    row index) its `Id` and the rowversion the write must hold; a new row
    has neither, and its columns are checked against `insertable`. A new
    header (a create) is INSERTed first, and its lines carry the key it
    reads back (`ReadBack`), never the '' the client's row held."""
    tables = SCREENS[screen]
    rank = {"header": 0, "insert": 1, "update": 2}
    ordered = sorted(
        commands,
        key=lambda c: rank["header" if c.table == "Parent" else c.kind],
    )
    new_header = any(c.table == "Parent" and c.kind == "insert" for c in commands)
    header_key = ReadBack(tables.header, tables.read_back_key[tables.header])
    statements: list[Statement] = []
    for command in ordered:
        table = tables.table_for(command.table)
        if command.kind == "insert":
            columns = dict(command.columns)
            if new_header and command.table != "Parent":
                relation = tables.relation.get(table)
                if relation is None or relation.lower() not in {c.lower() for c in columns}:
                    raise UnmeasuredError(f"which column of {table} holds its new header's key")
                columns = {
                    c: header_key if c.lower() == relation.lower() else v
                    for c, v in columns.items()
                }
            statements.append(
                render_insert(
                    table,
                    columns,
                    (insertable or {}).get(table, ()),
                    (no_default or {}).get(table, frozenset()),
                    read_back_key=tables.read_back_key[table],
                )
            )
            continue
        if new_header:
            raise UnmeasuredError("a stored row written in a new document's save")
        row_id, rowversion = rows[(command.table, command.row)]
        statements.append(
            render_update(
                table,
                command.columns,
                column_order[table],
                row_id=row_id,
                rowversion=rowversion,
                read_back_key=tables.read_back_key[table],
            )
        )
    return Batch(context=context, statements=statements)
