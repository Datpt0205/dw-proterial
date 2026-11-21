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

What is not measured is refused (`UnmeasuredError`), never guessed: the
context's event word for a save of an existing document (the trace holds a
save after `New` only), and an INSERT's shape before the shared template
(script 03c).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from dw_bravo.runner import WriteCommand
from dw_bravo_gateway.ports import Batch, Statement

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
        # Only `New` is traced, and only for a document created in the same
        # session; a save of an existing SO is ticket 52's to trace.
        context_event={},
    ),
}


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
    assignments = ",".join(f"[{n}]=@_{n}" for n in names)
    sql = (
        f"UPDATE TOP (1) {table} SET {assignments},[ModifiedAt]=DEFAULT"
        " WHERE Id=@_Original_Id AND timestamp=@_Original_timestamp;"
        f"SELECT TOP (1) Id,{read_back_key},CreatedAt,ModifiedAt,timestamp"
        f" FROM {table} WHERE Id=@_Id;"
    )
    parameters: dict[str, object] = {
        f"_{n}": columns[c] for n, c in zip(names, ordered, strict=True)
    }
    parameters |= {"_Original_Id": row_id, "_Original_timestamp": rowversion, "_Id": row_id}
    return Statement(table=table, row_id=row_id, sql=sql, parameters=parameters)


def render_save(
    screen: str,
    commands: Sequence[WriteCommand],
    rows: Mapping[tuple[str, int], tuple[object, str]],
    column_order: Mapping[str, Sequence[str]],
    *,
    context: str,
) -> Batch:
    """A plan's commands as one batch. `rows` gives each (layout table, row
    index) its stored `Id` and the rowversion the write must hold."""
    tables = SCREENS[screen]
    statements: list[Statement] = []
    for command in commands:
        if command.kind != "update":
            raise UnmeasuredError("an INSERT's statement waits on the shared template (03c)")
        table = tables.table_for(command.table)
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
