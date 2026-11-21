"""Replays the client's saves of one screen from a trace, through the runner.

For each save the client made (one `UPDATE` of the header plus the rows it
wrote, at one instant), the document is rebuilt as it stood before the save,
the person's edits are applied through `RuleRunner.edit`, and the runner's
`save()` is compared with what the client wrote, column by column.

The person's edits are not in a trace; only the columns the client wrote
are. They are found by search: the smallest set of written columns which, typed
in, makes the runner write exactly the rest. Every other written column is the
runner's own work, and a save where the runner adds or misses one column fails.

Procedure results come from the trace too: the call must have been made by the
client with exactly the parameters the runner passes, and its result is the
value the client then wrote (ticket 59: "proc Bravo tạm dùng kết quả ghi
trong trace").

Values this module infers, each from the trace and stated where it is done:
`GETDATE()` is the save's date (the client writes `OriginalInputDate` as the
date at midnight); the base currency rounds to the places its amounts are
written with; a header's exchange-rate operator is "not multiply" when
`UnitCost` = `OriginalUnitCost` / `ExchangeRate`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from itertools import combinations

from dw_bravo.expression import UNKNOWN, RuleRefusedError, UndecidableError
from dw_bravo.layout import PARENT, Layout
from dw_bravo.ports import Session
from dw_bravo.runner import Document, Finding, Row, RuleRunner, WriteCommand, _same
from dw_bravo.testing.sql_trace import ProcedureCall, Write

_AUDIT = {"modifiedat", "modifiedby", "createdby"}


@dataclass
class SaveGroup:
    at: datetime
    writes: list[Write]


@dataclass
class ReplayResult:
    save: SaveGroup
    roots: dict[str, list[str]] = field(default_factory=dict)  # row label -> columns typed
    computed: dict[str, list[str]] = field(
        default_factory=dict
    )  # row label -> columns the rules wrote
    matched: bool = False
    mismatch: str | None = None
    fired: list[Finding] = field(default_factory=list)
    undecided: list[Finding] = field(default_factory=list)


def group_saves(writes: Iterable[Write], screen: str) -> list[SaveGroup]:
    groups: list[SaveGroup] = []
    for write in writes:
        if write.statement.screen != screen:
            continue
        if groups and groups[-1].at == write.statement.at:
            groups[-1].writes.append(write)
        else:
            groups.append(SaveGroup(write.statement.at, [write]))
    return groups


class _ReplayProcedures:
    """Answers a call only if the client made it, from the value it wrote."""

    def __init__(
        self,
        layout: Layout,
        calls: Sequence[ProcedureCall],
        after: Mapping[str, list[dict[str, object]]],
    ):
        self.layout = layout
        self.calls = calls
        self.after = after  # table key -> rows' values after the save
        self.made: list[tuple[str, dict[str, object]]] = []

    def call(
        self, command: str, parameters: Mapping[str, object], outputs: Sequence[str]
    ) -> Mapping[str, object]:
        self.made.append((command, dict(parameters)))
        if not any(
            c.command.lower() == command.lower() and _params_equal(c.parameters, parameters)
            for c in self.calls
        ):
            raise UndecidableError(
                f"the client did not call {command}{dict(parameters)} before this save"
            )
        rows = self._rows_for(command, parameters)
        if len(rows) != 1:
            raise UndecidableError(
                f"{command}: {len(rows)} rows fit its parameters, its result is not in hand"
            )
        values = {k.lower(): v for k, v in rows[0].items()}
        missing = [o for o in outputs if o.lower() not in values]
        if missing:
            raise UndecidableError(f"{command}: {', '.join(missing)} is not a written column")
        return {o: values[o.lower()] for o in outputs}

    def _rows_for(self, command: str, parameters: Mapping[str, object]) -> list[dict[str, object]]:
        rules = [
            r
            for r in self.layout.rules.values()
            if (r.setting("Command") or "").lower() == command.lower()
        ]
        fits: list[dict[str, object]] = []
        for rule in rules:
            for row in self.after.get(rule.home, []):
                lowered = {k.lower(): v for k, v in row.items()}
                parent = {k.lower(): v for k, v in self.after[PARENT][0].items()}
                ok = True
                for name, expr in rule.maps.get("Parameters", {}).items():
                    text = expr.strip()
                    source = parent if text.lower().startswith("parent.") else lowered
                    column = text.split(".", 1)[-1].lower()
                    if not column.replace("_", "").isalnum() or column not in source:
                        continue
                    given = next(
                        (v for k, v in parameters.items() if k.lower() == name.lower()), None
                    )
                    if not _value_equal(source[column], given):
                        ok = False
                        break
                if ok and row not in fits:
                    fits.append(row)
        return fits


def _value_equal(a: object, b: object) -> bool:
    if a in (None, "") and b in (None, ""):
        return True
    return _same(a, b) or (
        isinstance(a, Decimal | int) and isinstance(b, Decimal | int) and Decimal(a) == Decimal(b)
    )


def _params_equal(traced: Mapping[str, object], ours: Mapping[str, object]) -> bool:
    t = {k.lower(): v for k, v in traced.items()}
    o = {k.lower(): v for k, v in ours.items()}
    return t.keys() == o.keys() and all(_value_equal(t[k], o[k]) for k in t)


@dataclass
class ScreenReplay:
    """Replays one document's saves on one screen (EDIT_BizDocSO first)."""

    layout: Layout
    header_table: str  # the table Bravo writes the header to, e.g. B30BizDoc
    detail_table: str  # e.g. B30BizDocDetailSO
    detail_key: str  # the layout's alias, e.g. Detail
    session_for: Callable[[SaveGroup], Session]
    # The view's own columns (joined, not stored) of a header and of a line,
    # derived from the stored row: what the client's load would have read.
    derive_header: Callable[[dict[str, object]], dict[str, object]]
    derive_line: Callable[[dict[str, object]], dict[str, object]]
    max_roots: int = 3

    def replay(
        self, saves: Sequence[SaveGroup], calls: Sequence[ProcedureCall]
    ) -> list[ReplayResult]:
        header: dict[str, object] | None = None
        lines: dict[object, dict[str, object]] = {}  # BuiltinOrder -> values
        results: list[ReplayResult] = []
        previous_at: datetime | None = None
        for position, save in enumerate(saves):
            window = [
                c
                for c in calls
                if (previous_at is None or c.statement.at > previous_at)
                and c.statement.at <= save.at
            ]
            inserts = [w for w in save.writes if w.kind == "insert"]
            if not inserts and header is not None:
                results.append(self._replay_update(save, header, lines, window))
            for write in save.writes:
                values = dict(write.values)
                if write.kind == "insert":
                    values = self._reloaded(write, saves[position + 1 :])
                if write.table == self.header_table:
                    header = values
                elif write.table == self.detail_table:
                    lines[write.values.get("BuiltinOrder")] = values
            previous_at = save.at
        return results

    def _reloaded(self, insert: Write, later: Sequence[SaveGroup]) -> dict[str, object]:
        """An inserted row as the client reloads it: its Id and the database's
        defaults, read from the row's next write, whose own changes are undone
        with the inserted values."""
        order = insert.values.get("BuiltinOrder")
        for save in later:
            for write in save.writes:
                same_row = write.table == insert.table and (
                    insert.table == self.header_table or write.values.get("BuiltinOrder") == order
                )
                if write.kind == "update" and same_row:
                    values = dict(write.values)
                    for column in write.columns:
                        if column.lower() not in _AUDIT:
                            values[column] = insert.values.get(column)
                    return values
        return {**insert.values, "Id": UNKNOWN}

    def _before_after(
        self, save: SaveGroup, header: dict[str, object], lines: dict[object, dict[str, object]]
    ) -> tuple[
        dict[str, object],
        list[dict[str, object]],
        dict[str, object],
        list[dict[str, object]],
        dict[str, Write],
    ]:
        written: dict[str, Write] = {}
        after_header, before_header = dict(header), dict(header)
        after_lines = {k: dict(v) for k, v in lines.items()}
        before_lines = {k: dict(v) for k, v in lines.items()}
        for write in save.writes:
            if write.table == self.header_table:
                previous = header
                after_header = dict(write.values)
                before_header = dict(write.values)
                for column in write.columns:
                    if column.lower() not in _AUDIT:
                        before_header[column] = previous.get(column)
                written[PARENT] = write
            else:
                order = write.values.get("BuiltinOrder")
                previous = lines[order]
                after_lines[order] = dict(write.values)
                before_lines[order] = dict(write.values)
                for column in write.columns:
                    if column.lower() not in _AUDIT:
                        before_lines[order][column] = previous.get(column)
                written[f"{self.detail_key}#{order}"] = write
        order_keys = sorted(lines, key=lambda k: Decimal(str(k)))
        return (
            before_header,
            [before_lines[k] for k in order_keys],
            after_header,
            [after_lines[k] for k in order_keys],
            written,
        )

    def _document(self, header: dict[str, object], lines: list[dict[str, object]]) -> Document:
        parent = Row({**header, **self.derive_header(header)}, stored=header.keys())
        rows = [Row({**line, **self.derive_line(line)}, stored=line.keys()) for line in lines]
        return Document(parent, {self.detail_key: rows})

    def _replay_update(
        self,
        save: SaveGroup,
        header: dict[str, object],
        lines: dict[object, dict[str, object]],
        window: Sequence[ProcedureCall],
    ) -> ReplayResult:
        before_h, before_l, after_h, after_l, written = self._before_after(save, header, lines)
        result = ReplayResult(save)
        candidates: list[tuple[str, int, str]] = []  # (table, index, column)
        for label, write in written.items():
            table = PARENT if label == PARENT else self.detail_key
            index = (
                0
                if label == PARENT
                else [Decimal(str(x.get("BuiltinOrder"))) for x in before_l].index(
                    Decimal(str(write.values.get("BuiltinOrder")))
                )
            )
            for column in write.columns:
                if column.lower() not in _AUDIT:
                    candidates.append((table, index, column))
        after_rows = {PARENT: [after_h], self.detail_key: after_l}
        last_error = "no edit set reproduces the save"
        for size in range(1, min(self.max_roots, len(candidates)) + 1):
            for roots in combinations(candidates, size):
                doc = self._document(before_h, before_l)
                procedures = _ReplayProcedures(self.layout, window, after_rows)
                runner = RuleRunner(
                    self.layout, procedures, _NoReferences(), self.session_for(save)
                )
                try:
                    runner.load(doc)
                    for table, index, column in roots:
                        source = after_h if table == PARENT else after_l[index]
                        runner.edit(doc, table, index, column, source[column])
                    plan = runner.save(doc)
                except RuleRefusedError as exc:
                    last_error = f"{[r[2] for r in roots]}: {exc}"
                    continue
                problem = self._compare(plan.commands, written, before_l)
                if problem is None:
                    result.matched = True
                    for table, index, column in roots:
                        result.roots.setdefault(f"{table}#{index}", []).append(column)
                    for command in plan.commands:
                        label = f"{command.table}#{command.row}"
                        typed = set(result.roots.get(label, []))
                        result.computed[label] = [
                            c for c in command.columns if c.lower() not in _AUDIT and c not in typed
                        ]
                    result.fired = plan.check.blocking + plan.check.warnings
                    result.undecided = plan.check.undecided
                    return result
                last_error = f"{[r[2] for r in roots]}: {problem}"
        result.mismatch = last_error
        return result

    def _compare(
        self,
        commands: Sequence[WriteCommand],
        written: Mapping[str, Write],
        before_lines: list[dict[str, object]],
    ) -> str | None:
        ours: dict[str, WriteCommand] = {}
        for command in commands:
            if command.table == PARENT:
                ours[PARENT] = command
            else:
                order = before_lines[command.row].get("BuiltinOrder")
                ours[f"{self.detail_key}#{order}"] = command
        if set(ours) != set(written):
            return f"rows written: ours {sorted(ours)} vs client {sorted(written)}"
        for label, write in written.items():
            command = ours[label]
            theirs = {c for c in write.columns if c.lower() != "modifiedat"}
            mine = set(command.columns)
            if {c.lower() for c in theirs} != {c.lower() for c in mine}:
                return f"{label} columns: ours {sorted(mine)} vs client {sorted(theirs)}"
            lowered = {k.lower(): v for k, v in command.columns.items()}
            for column in theirs:
                if not _value_equal(lowered[column.lower()], write.values.get(column)):
                    mine_v, theirs_v = lowered[column.lower()], write.values.get(column)
                    return f"{label}.{column}: ours {mine_v!r} vs client {theirs_v!r}"
        return None


class _NoReferences:
    def find(
        self, lookup_key: str, code: object, filter_key: str | None
    ) -> Mapping[str, object] | None:
        raise UndecidableError(f"lookup {lookup_key} {code!r} is not in the trace")

    def key_taken(
        self, table: str, values: Mapping[str, object], filter_key: str | None, own_id: object
    ) -> bool:
        raise UndecidableError(f"whether {dict(values)} is taken in {table} is not in the trace")


def unknown_columns(names: Iterable[str]) -> dict[str, object]:
    return dict.fromkeys(names, UNKNOWN)


def session_from(
    save: SaveGroup, user_id: int, branch: str, currency: Mapping[str, object]
) -> Session:
    day = save.at.replace(hour=0, minute=0, second=0, microsecond=0)
    return Session(user={"Id": Decimal(user_id)}, branch=branch, now=day, currency=currency)
