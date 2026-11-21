"""Reads what Bravo's client sent SQL Server, from an Extended Events CSV.

The trace (`sql_batch_completed`/`rpc_completed`, one statement a line:
sequence, time, event, login, application, host, session, statement) is how
ticket 59's runner is proven: replayed, it must produce the columns the client
wrote. This module only parses; it holds no trace. A trace of Proterial's
UAT is customer data and stays out of git (`docs/proterial/` and the
operator's own folder), so tests that read one skip where it is absent.

Two statement shapes are read:

- the client's writes, `sp_executesql` of `INSERT INTO <table> (...)` or
  `UPDATE TOP (1) <table> SET [Col]=@_Col,... WHERE Id=...`, with every
  parameter's value (the whole row, not only what changed);
- a procedure or function a rule ran: `exec dbo.<name> @_P=...`.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

_PARAM = re.compile(r"@_(\w+)=(N'(?:[^']|'')*'|'(?:[^']|'')*'|DEFAULT|NULL|@\w+ output|[^,]*)")
_WRITE = re.compile(
    r"(INSERT INTO (\w+) \((.*?)\) VALUES|UPDATE TOP \(1\) (\w+) SET (.*?) WHERE)", re.S
)
_EXEC = re.compile(r"exec (?:dbo\.)?\[?(\w+)\]? (@_.*)$", re.S)


@dataclass(frozen=True)
class Statement:
    seq: int
    at: datetime
    application: str  # B8.x$<host>\<user>/<screen>|<rule>
    session: int
    sql: str

    @property
    def screen(self) -> str:
        return self.application.rsplit("/", 1)[-1].split("|", 1)[0]


@dataclass(frozen=True)
class Write:
    statement: Statement
    kind: str  # insert | update
    table: str
    columns: tuple[str, ...]  # the INSERT's column list or the UPDATE's SET list
    values: dict[str, object]  # every parameter: the whole row after the write

    @property
    def row_id(self) -> object:
        return self.values.get("Id")


@dataclass(frozen=True)
class ProcedureCall:
    statement: Statement
    command: str
    parameters: dict[str, object]


def literal(text: str) -> object:
    """A T-SQL literal as the client wrote it."""
    text = text.strip()
    if text in ("NULL", "DEFAULT"):
        return None
    if text.startswith("N'") or text.startswith("'"):
        body = text[2:-1] if text.startswith("N'") else text[1:-1]
        body = body.replace("''", "'")
        if not text.startswith("N'") and re.fullmatch(
            r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d(\.\d+)?", body
        ):
            return datetime.fromisoformat(body)
        return body
    if text.startswith("0x"):
        return text
    if re.fullmatch(r"-?\d+(\.\d+)?", text):
        return Decimal(text)
    raise ValueError(f"unread literal {text!r}")


def read(path: Path) -> list[Statement]:
    statements: list[Statement] = []
    csv.field_size_limit(1 << 26)  # one statement carries a whole layout's XML
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) < 8:
                continue
            statements.append(
                Statement(
                    seq=int(row[0]),
                    at=datetime.fromisoformat(row[1]),
                    application=row[4],
                    session=int(row[6]),
                    sql=row[7],
                )
            )
    statements.sort(key=lambda s: (s.at, s.session, s.seq))
    return statements


def _values(sql: str) -> dict[str, object]:
    declared = sql.find(",N'@_")
    if declared == -1:
        return {}
    start = sql.find("',@_", declared + 3)
    if start == -1:
        return {}
    out: dict[str, object] = {}
    for match in _PARAM.finditer(sql[start + 2 :]):
        name, raw = match.group(1), match.group(2)
        if raw.endswith(" output"):
            continue
        out[name] = literal(raw)
    return out


def writes(statements: list[Statement]) -> Iterator[Write]:
    for statement in statements:
        if "sp_executesql" not in statement.sql:
            continue
        match = _WRITE.search(statement.sql)
        if match is None:
            continue
        values = _values(statement.sql)
        if match.group(2):
            columns = tuple(c.strip(" []") for c in match.group(3).split(","))
            yield Write(statement, "insert", match.group(2), columns, values)
        else:
            columns = tuple(re.findall(r"\[(\w+)\]=", match.group(5)))
            yield Write(statement, "update", match.group(4), columns, values)


def procedure_calls(statements: list[Statement]) -> Iterator[ProcedureCall]:
    for statement in statements:
        sql = statement.sql.strip()
        if sql.startswith("declare "):
            sql = sql[sql.find("exec ") :]
        match = _EXEC.match(sql)
        if match is None or match.group(1).startswith("sp_"):
            continue
        parameters: dict[str, object] = {}
        for param in _PARAM.finditer(match.group(2)):
            raw = param.group(2)
            if raw.endswith(" output") or raw == "default":
                continue
            parameters[param.group(1)] = literal(raw)
        yield ProcedureCall(statement, match.group(1), parameters)
