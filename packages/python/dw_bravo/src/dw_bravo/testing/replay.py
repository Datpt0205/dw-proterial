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
from dw_bravo.ports import ProcedurePort, Session
from dw_bravo.runner import Document, Finding, Row, RuleRunner, WriteCommand, _same
from dw_bravo.testing.sql_trace import ProcedureCall, Write

_AUDIT = {"modifiedat", "modifiedby", "createdby"}


@dataclass
class SaveGroup:
    at: datetime
    writes: list[Write]


@dataclass
class SaveState:
    save: SaveGroup
    header: dict[str, object]  # the header before the save
    lines: dict[object, dict[str, object]]  # BuiltinOrder -> the line before the save
    window: list[ProcedureCall]
    # The save's INSERTs of new lines (`states(with_inserts=True)`), kept out
    # of `before_after`: a new line has no "before".
    inserted: list[Write] = field(default_factory=list)


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
        answers: list[dict[str, object]] = []
        for row in rows:
            values = {k.lower(): v for k, v in row.items()}
            missing = [o for o in outputs if o.lower() not in values]
            if missing:
                raise UndecidableError(f"{command}: {', '.join(missing)} is not a written column")
            answer = {o: values[o.lower()] for o in outputs}
            if not any(_params_equal(answer, a) for a in answers):
                answers.append(answer)
        # Several rows may fit one call (a split's lines share an item and a
        # customer): their written values answer it only when they agree.
        if len(answers) != 1:
            raise UndecidableError(
                f"{command}: {len(rows)} rows fit its parameters, its result is not in hand"
            )
        return answers[0]

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
    # Columns the client passes as parameters with a line but its view does
    # not load, so the line it holds has none of them (the YCBG line's view
    # has no CreatedBy, ModifiedBy or timestamp).
    line_unloaded: frozenset[str] = frozenset()

    def replay(
        self, saves: Sequence[SaveGroup], calls: Sequence[ProcedureCall]
    ) -> list[ReplayResult]:
        return [
            self._replay_update(state.save, state.header, state.lines, state.window)
            for state in self.states(saves, calls)
        ]

    def states(
        self,
        saves: Sequence[SaveGroup],
        calls: Sequence[ProcedureCall],
        *,
        with_inserts: bool = False,
    ) -> list[SaveState]:
        """Each UPDATE save with the document as it stood before it and the
        procedure calls the client made since the previous save: what the
        Bravo gateway's replay (ticket 63) runs its own commands against.
        `with_inserts` also gives a save of a stored document that added
        lines (a split, ticket 73), its INSERTs on `SaveState.inserted`."""
        header: dict[str, object] | None = None
        lines: dict[object, dict[str, object]] = {}  # BuiltinOrder -> values
        states: list[SaveState] = []
        previous_at: datetime | None = None
        for position, save in enumerate(saves):
            window = [
                c
                for c in calls
                if (previous_at is None or c.statement.at > previous_at)
                and c.statement.at <= save.at
            ]
            inserts = [w for w in save.writes if w.kind == "insert"]
            new_document = any(w.table == self.header_table for w in inserts)
            if header is not None and (not inserts or (with_inserts and not new_document)):
                states.append(
                    SaveState(
                        save,
                        dict(header),
                        {k: dict(v) for k, v in lines.items()},
                        window,
                        inserts,
                    )
                )
            for write in save.writes:
                values = dict(write.values)
                if write.kind == "insert":
                    values = self._reloaded(write, saves[position + 1 :])
                if write.table == self.header_table:
                    header = values
                elif write.table == self.detail_table:
                    lines[write.values.get("BuiltinOrder")] = values
            previous_at = save.at
        return states

    def before_after(
        self, state: SaveState
    ) -> tuple[
        dict[str, object],
        list[dict[str, object]],
        dict[str, object],
        list[dict[str, object]],
        dict[str, Write],
    ]:
        return self._before_after(state.save, state.header, state.lines)

    def procedures(self, state: SaveState) -> ProcedurePort:
        """Answers only the calls the client made before this save."""
        _, _, after_h, after_l, _ = self.before_after(state)
        new_lines = [dict(w.values) for w in state.inserted]
        return _ReplayProcedures(
            self.layout, state.window, {PARENT: [after_h], self.detail_key: after_l + new_lines}
        )

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
            if write.kind == "insert":
                continue  # a new line: no before (`SaveState.inserted`)
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
        unloaded = {c.lower() for c in self.line_unloaded}
        rows = [
            Row(
                {**line, **self.derive_line(line)},
                stored=[c for c in line if c.lower() not in unloaded],
            )
            for line in lines
        ]
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
        # A written column no rule of the layout can set was typed (or picked
        # in a lookup, the same thing to the rules): it is a root for certain,
        # and only the columns a rule could also have set are searched.
        certain = [c for c in candidates if c[2].lower() not in self._settable(c[0])]
        searched = [c for c in candidates if c not in certain]
        last_error = "no edit set reproduces the save"
        for size in range(0 if certain else 1, min(self.max_roots, len(searched)) + 1):
            for extra in combinations(searched, size):
                roots = (*certain, *extra)
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

    def _settable(self, table: str) -> frozenset[str]:
        """The columns some rule of the layout, homed on `table`, can set."""
        columns: set[str] = set()
        for rule in self.layout.rules.values():
            if rule.home != table:
                continue
            columns.update(c.lower() for c in rule.data_members())
            columns.update(c.lower() for c in rule.maps.get("CopyValues", {}))
            columns.update(m.target.lower() for m in rule.bindings)
        return frozenset(columns)

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


def rq_screen_replay(layout: Layout, user_id: int, branch: str) -> ScreenReplay:
    """The YCBG screen's replay (`EDIT_BizDocRQ`, layout 11766).

    Its header loads through the SO's view, `vB30BizDoc_Edit`
    (`ModifiedBy AS UserId`); its line's view, `vB30BizDocDetailRQ_Edit`,
    loads no audit column. What its view joins in (`Name_Item`, `ItemName`)
    is not derived: no rule the trace's saves run reads it.
    """

    def derive_header(row: dict[str, object]) -> dict[str, object]:
        out = unknown_columns(["MoneyDiffValue", "AutoNumbering"])
        out["UserId"] = row.get("ModifiedBy")
        return out

    def derive_line(row: dict[str, object]) -> dict[str, object]:
        return unknown_columns(["Name_Item", "ItemName"])

    return ScreenReplay(
        layout,
        "B30BizDoc",
        "B30BizDocDetailRQ",
        "Detail",
        session_for=lambda save: session_from(save, user_id, branch, {}),
        derive_header=derive_header,
        derive_line=derive_line,
        line_unloaded=frozenset(
            {"CreatedBy", "CreatedAt", "ModifiedBy", "ModifiedAt", "timestamp"}
        ),
    )


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


def so_screen_replay(layout: Layout, user_id: int, branch: str) -> ScreenReplay:
    """The SO screen's replay, with what its load view adds to a stored row.

    Shared by the runner's own replay test and the gateway's (ticket 63), so
    the two replay one reading of the trace, not two.
    """

    def derive_header(row: dict[str, object]) -> dict[str, object]:
        out = unknown_columns(
            ["MoneyDiffValue", "VATDiffValue", "MoneyDiffValue0", "VATDiffValue0", "AutoNumbering"]
        )
        out["UserId"] = row.get("ModifiedBy")  # the view: ModifiedBy AS UserId
        # Inferred from the trace, not read from Bravo: UnitCost is written as
        # OriginalUnitCost / ExchangeRate, so the operator is "not multiply"
        # (any value but 1 takes that branch), and the document currency's
        # amounts are written as integers.
        out["ExchangeRateOperator"] = Decimal(2)
        out["DecimalRound"] = Decimal(0)
        return out

    def derive_line(row: dict[str, object]) -> dict[str, object]:
        # The view's own columns: `Quantity9 AS Quantity_Edit`,
        # `OriginalUnitCost AS UnitPrice_price`; the tax joined on TaxCode,
        # NULL for an empty code (assumed: no tax is coded '').
        out = unknown_columns(["Name_Item", "Unit_Item", "PackingNote", "CoilBox", "Forwarder"])
        out.update(Quantity_Edit=row.get("Quantity9"), UnitPrice_price=row.get("OriginalUnitCost"))
        out["ItemName"] = row.get("Description")
        if row.get("TaxCode") in (None, ""):
            out.update(TaxRate=None, TaxType=None, PriceIncludeTax=None)
        return out

    return ScreenReplay(
        layout,
        "B30BizDoc",
        "B30BizDocDetailSO",
        "Detail",
        # Amount9 = Quantity9 x UnitCost is written with 2 places.
        session_for=lambda save: session_from(save, user_id, branch, {"DecimalRound": Decimal(2)}),
        derive_header=derive_header,
        derive_line=derive_line,
    )
