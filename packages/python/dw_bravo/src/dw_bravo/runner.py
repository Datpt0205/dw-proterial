"""Runs a Bravo screen's own rules on a document, as Bravo's client would.

Bravo's form logic is not executed by SQL Server: its client (`DataEditor`)
evaluates the layout's XML on each PC, and a write straight to the database
skips every rule (ticket 59). This module is that client's rule engine, fed
the layout read at run time (`dw_bravo.layout`), so the 404 rules of the SO
screen are run, never copied.

What it does, all of it read from the layout:

- `edit()` sets a column the way a person typing does: the column's
  `ColumnChanging` rules, the value, then its `ColumnChanged` rules, each
  assignment cascading through the same events;
- `add_row()` adds a line as a person adds one to the grid: the relation key
  from the parent, a negative `Id`, then the table's `RowAdded` rules;
- `check()` runs the validators and sorts them into blocking, warning and
  undecided;
- `save()` runs `ServerUpdating` and returns the columns the client would
  `INSERT` or `UPDATE`, with the check.

What it refuses (`RuleRefusedError`), rather than guess:

- a rule the layout names but does not define (the shared template
  `BizDocEditor` is not in hand until script 03c);
- a rule kind, function or syntax not yet measured;
- a value that is not in hand (`UNKNOWN`): a view's column nobody loaded, a
  procedure result nobody recorded;
- a case where two readings consistent with everything measured would act
  differently (rounding on the half, a money evaluator's NULL over a non-zero
  value, a rule's condition and its use's condition disagreeing).

Measured against the 2026-11-20 UAT trace (the client's `sp_executesql` writes):
an `UPDATE` carries only the columns whose value changed, plus `ModifiedBy`;
the header is updated on every save; an `INSERT` lists only non-NULL columns
plus `CreatedBy`. An assignment of the value a column already holds raises
no event. `ModifiedBy` and `CreatedBy` are written only where the row the
client loaded holds them: the YCBG line's view (`vB30BizDocDetailRQ_Edit`)
has neither, and the client passes both as parameters and sets neither.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from dw_bravo.expression import (
    UNKNOWN,
    RuleRefusedError,
    Scope,
    UndecidableError,
    UnsupportedSyntaxError,
    condition,
    evaluate,
    is_empty,
    round_decimal,
    substitute,
    truth,
)
from dw_bravo.layout import PARENT, CommandGuard, Invocation, Layout, Rule, Table
from dw_bravo.ports import ProcedurePort, ReferencePort, Session

USER = "<user>"


class Row:
    """One row of a document, columns case-blind as Bravo's DataTable is."""

    def __init__(
        self,
        values: Mapping[str, object],
        *,
        stored: Iterable[str] | None = None,
        new: bool = False,
    ) -> None:
        self._names = {k.lower(): k for k in values}
        self._values: dict[str, object] = {k.lower(): v for k, v in values.items()}
        self.stored = frozenset(c.lower() for c in (stored if stored is not None else values))
        for column in self.stored:
            self._names.setdefault(column, column)
        self.new = new
        self.original: dict[str, object] = {} if new else dict(self._values)

    def has(self, column: str) -> bool:
        return column.lower() in self._values

    def get(self, column: str) -> object:
        return self._values[column.lower()]

    def set(self, column: str, value: object) -> None:
        self._names.setdefault(column.lower(), column)
        self._values[column.lower()] = value

    def name(self, column: str) -> str:
        return self._names.get(column.lower(), column)

    def accept(self) -> None:
        """The loaded state becomes the baseline a save is compared with."""
        self.original = dict(self._values)

    def changed(self) -> list[str]:
        return [
            c for c in sorted(self.stored) if not _same(self.original.get(c), self._values.get(c))
        ]

    def values(self) -> dict[str, object]:
        return {self.name(k): v for k, v in self._values.items()}


@dataclass
class Document:
    """A header row and its child tables (`Detail`, ...)."""

    parent: Row
    children: dict[str, list[Row]]
    trail: list[Step] = field(default_factory=list)
    unknown: dict[str, str] = field(default_factory=dict)  # column -> why it is unknown

    def rows(self, table: str) -> list[Row]:
        if table == PARENT:
            return [self.parent]
        try:
            return self.children[table]
        except KeyError:
            raise UndecidableError(f"table {table} is not loaded") from None

    def index(self, table: str, row: Row) -> int:
        return next(i for i, r in enumerate(self.rows(table)) if r is row)


@dataclass(frozen=True)
class Step:
    """One value set: by a rule (`rule`) or by the person (`USER`)."""

    rule: str
    table: str
    row: int
    column: str
    before: object
    after: object
    trigger: str | None


Level = Literal["block", "warning"]
Status = Literal["fired", "passed", "undecided"]


@dataclass(frozen=True)
class Finding:
    rule: str
    table: str
    row: int
    level: Level
    status: Status
    message: str
    columns: tuple[str, ...]
    reason: str | None = None


@dataclass(frozen=True)
class Check:
    findings: tuple[Finding, ...]

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.status == "fired" and f.level == "block"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.status == "fired" and f.level == "warning"]

    @property
    def undecided(self) -> list[Finding]:
        return [f for f in self.findings if f.status == "undecided"]

    @property
    def may_save(self) -> bool:
        """Fail closed: a blocking rule that could not be decided blocks too."""
        return not self.blocking and not any(f.level == "block" for f in self.undecided)


@dataclass(frozen=True)
class WriteCommand:
    table: str
    row: int
    kind: Literal["insert", "update"]
    columns: Mapping[str, object]


@dataclass(frozen=True)
class SavePlan:
    commands: tuple[WriteCommand, ...]
    check: Check
    provisional: tuple[str, ...] = ()  # why the plan may be missing rules

    @property
    def may_write(self) -> bool:
        """Fail closed: a plan made without all of the screen's rules writes nothing."""
        return self.check.may_save and not self.provisional


def _guard_finding(guard: CommandGuard, status: Status, reason: str | None = None) -> Finding:
    """A template guard's finding: on the parent, always blocking."""
    return Finding(guard.name, PARENT, 0, "block", status, guard.message or guard.name, (), reason)


def _same(a: object, b: object) -> bool:
    if a is UNKNOWN or b is UNKNOWN:
        return a is b
    if isinstance(a, Decimal | int) and isinstance(b, Decimal | int):
        return Decimal(a) == Decimal(b)
    return type(a) is type(b) and a == b


class _RowScope:
    def __init__(
        self, runner: RuleRunner, doc: Document, table: str, row: Row, trigger: str | None
    ) -> None:
        self.runner, self.doc, self.table, self.row, self.trigger = runner, doc, table, row, trigger

    def column(self, name: str) -> object:
        if self.row.has(name):
            return self.row.get(name)
        spec = self.runner.layout.tables.get(self.table)
        lower = name.lower()
        if spec is not None and lower in spec.expressions:
            return evaluate(spec.expressions[lower], self)
        if spec is not None and lower in spec.temp_columns:
            default = spec.temp_columns[lower]
            return None if default is None else evaluate(default, self)
        raise UndecidableError(f"{self.table}.{name} is not in hand")

    def parent_column(self, name: str) -> object:
        return _RowScope(self.runner, self.doc, PARENT, self.doc.parent, self.trigger).column(name)

    def table_rows(self, table: str) -> Sequence[Scope]:
        key = PARENT if table.lower() == PARENT.lower() else table
        return [_RowScope(self.runner, self.doc, key, r, self.trigger) for r in self.doc.rows(key)]

    def updated_column(self) -> str | None:
        return self.trigger

    def session(self, function: str, argument: object) -> object:
        session = self.runner.session
        if function == "GETDATE":
            return session.now
        if function == "BRANCH":
            if argument is None:
                return session.branch
            return session.branch_info.get(str(argument), UNKNOWN)
        if function == "LANGID":
            return session.lang_id
        source = {"USER": session.user, "CURRENCY": session.currency, "CONFIG": session.config}.get(
            function
        )
        if source is None:
            return UNKNOWN
        return source.get(str(argument), UNKNOWN)


class RuleRunner:
    """Bravo's rules for one screen, run on documents of that screen."""

    def __init__(
        self,
        layout: Layout,
        procedures: ProcedurePort,
        references: ReferencePort,
        session: Session,
        *,
        max_depth: int = 64,
    ) -> None:
        self.layout = layout
        self.procedures = procedures
        self.references = references
        self.session = session
        self.max_depth = max_depth
        self._loading = False

    # ------------------------------------------------------------- public

    def load(self, doc: Document) -> None:
        """Run `ServerLoaded`; what it cannot learn stays UNKNOWN, never guessed.

        A loaded (stored) column keeps the value Bravo gave it; only the
        columns the client computes at load become UNKNOWN when a result is
        missing. The state after load is the baseline of `save()`.
        """
        self._loading = True
        try:
            self._event(doc, PARENT, doc.parent, "ServerLoaded")
            for table in self.layout.children():
                for row in doc.children.get(table.key, []):
                    self._event(doc, table.key, row, "ServerLoaded")
        finally:
            self._loading = False
        for table_key in (PARENT, *doc.children):
            for row in doc.rows(table_key):
                row.accept()

    def edit(self, doc: Document, table: str, index: int, column: str, value: object) -> None:
        """Set a column as a person typing it would."""
        row = doc.rows(table)[index]
        self._assign(
            doc, table, row, column, value, rule=USER, trigger=column, suppress=False, depth=0
        )

    def add_row(
        self,
        doc: Document,
        table: str,
        values: Mapping[str, object],
        *,
        stored: Iterable[str],
    ) -> int:
        """Add a row to a child table as a person adding a grid line does,
        and return its index. ``values`` is every column the client's new row
        holds (NULL where nothing is known yet: a rule reading a column the
        row does not hold refuses); ``stored`` the ones an INSERT may list.
        The row then takes the parent's relation key (the layout's
        ``ParentKey``/``ChildKey``) and an ``Id`` below zero, as the client's
        rows hold before a save (the layout's ``Id < 0`` rules read it; it is
        never stored), and the table's ``RowAdded`` rules run."""
        spec = self.layout.tables.get(table)
        if table == PARENT or spec is None:
            raise RuleRefusedError(f"{table} is not a child table of {self.layout.form}")
        if spec.parent_key is None or spec.child_key is None:
            raise RuleRefusedError(f"{table} names no ParentKey/ChildKey in {self.layout.form}")
        if not doc.parent.has(spec.parent_key):
            raise UndecidableError(f"{PARENT}.{spec.parent_key} is not in hand")
        rows = doc.rows(table)
        initial = dict(values)
        initial[spec.child_key] = doc.parent.get(spec.parent_key)
        initial["Id"] = Decimal(-(sum(1 for r in rows if r.new) + 1))
        held = [c for c in stored if c.lower() not in ("id", spec.child_key.lower())]
        row = Row(initial, stored=[*held, spec.child_key], new=True)
        rows.append(row)
        self._event(doc, table, row, "RowAdded")
        return len(rows) - 1

    def check(self, doc: Document) -> Check:
        findings: list[Finding] = []
        for table in self.layout.tables.values():
            rows = doc.rows(table.key) if table.key == PARENT or table.key in doc.children else []
            for index, row in enumerate(rows):
                for rule in table.validators:
                    findings.append(self._validate(doc, table, index, row, rule))
        return Check(tuple(findings))

    def save(self, doc: Document, *, commands: Sequence[str] = ("Save",)) -> SavePlan:
        """The save the client would make, checked by the layout's validators
        and by each guard of the shared template on ``commands`` (the window's
        own: ``("Edit", "Save")`` for a stored document, ``("New", "Save")``
        for a new one). A guard that is not true, or cannot be decided,
        blocks: Bravo refuses the command."""
        self._event(doc, PARENT, doc.parent, "ServerUpdating")
        for table in self.layout.children():
            for row in doc.children.get(table.key, []):
                self._event(doc, table.key, row, "ServerUpdating")
        check = self.check(doc)
        guarded = Check(check.findings + tuple(self._guards(doc, commands)))
        provisional: tuple[str, ...] = ()
        if self.layout.missing_template:
            provisional = (f"template {self.layout.missing_template} is not in hand (script 03c)",)
        return SavePlan(tuple(self._commands(doc)), guarded, provisional)

    def _guards(self, doc: Document, commands: Sequence[str]) -> list[Finding]:
        template = self.layout.template
        if template is None:
            return []
        asked = {c.lower() for c in commands}
        found: list[Finding] = []
        for guard in template.guards:
            if not guard.commands & asked:
                continue
            scope = _RowScope(self, doc, PARENT, doc.parent, None)
            try:
                allowed = condition(guard.expr, scope)
            except (UndecidableError, RuleRefusedError, UnsupportedSyntaxError) as exc:
                found.append(_guard_finding(guard, "undecided", str(exc)[:200]))
                continue
            found.append(
                _guard_finding(guard, "passed")
                if allowed
                else _guard_finding(guard, "fired", guard.expr)
            )
        return found

    # ------------------------------------------------------------- events

    def _event(self, doc: Document, table: str, row: Row, event: str) -> None:
        spec = self.layout.tables[table]
        for invocation in spec.row_events.get(event, ()):
            self._invoke(doc, invocation, table, row, trigger=None, depth=0)

    def _column_event(
        self, doc: Document, table: str, row: Row, event: str, column: str, depth: int
    ) -> None:
        spec = self.layout.tables[table]
        for invocation in spec.column_events.get(event, {}).get(column.lower(), ()):
            self._invoke(doc, invocation, table, row, trigger=column, depth=depth + 1)

    def _invoke(
        self,
        doc: Document,
        invocation: Invocation,
        table: str,
        row: Row,
        trigger: str | None,
        depth: int,
    ) -> None:
        if depth > self.max_depth:
            raise RuleRefusedError(f"rules nest deeper than {self.max_depth} at {invocation.name}")
        if invocation.name in self.layout.ambiguous:
            raise RuleRefusedError(
                f"{invocation.name} is defined twice, differently, in {self.layout.form}"
            )
        rule = self.layout.rules.get(invocation.name)
        if rule is None:
            raise RuleRefusedError(
                f"{invocation.name} is used by {self.layout.form} "
                "but defined in a template not in hand"
            )
        invoking = _RowScope(self, doc, table, row, trigger)
        use_ok = condition(invocation.condition, invoking)
        if not use_ok:
            return
        for target_table, target in self._targets(doc, rule, table, row):
            scope = _RowScope(self, doc, target_table, target, trigger)
            if rule.is_group:
                for member in rule.members:
                    self._invoke(doc, member, target_table, target, trigger, depth + 1)
                continue
            own_ok = condition(rule.setting("Expr"), scope)
            if not own_ok:
                if invocation.condition is not None:
                    # Is a use's condition added to the rule's own, or does it
                    # replace it? Unmeasured; here the two readings differ.
                    raise RuleRefusedError(
                        f"{rule.name}: its use's condition holds and its own does not"
                    )
                continue
            try:
                self._apply(doc, rule, target_table, target, trigger, depth)
            except RuleRefusedError as exc:
                if self._loading:
                    # What the client computes at load and this runner cannot
                    # stays UNKNOWN; reading it later refuses that later rule.
                    self._mark_unknown(doc, rule, target, str(exc))
                    continue
                if str(exc).startswith(rule.name):
                    raise
                raise type(exc)(f"{rule.name}: {exc}") from exc

    def _targets(self, doc: Document, rule: Rule, table: str, row: Row) -> list[tuple[str, Row]]:
        if rule.home == table:
            return [(table, row)]
        if rule.home == PARENT:
            return [(PARENT, doc.parent)]
        if table == PARENT:
            return [(rule.home, r) for r in doc.children.get(rule.home, [])]
        raise RuleRefusedError(f"{rule.name} (on {rule.home}) used from {table}")

    def _mark_unknown(self, doc: Document, rule: Rule, row: Row, reason: str) -> None:
        for column in rule.data_members():
            if column.lower() not in row.stored:
                row.set(column, UNKNOWN)
                doc.unknown[column] = f"{rule.name}: {reason}"

    # -------------------------------------------------------------- rules

    def _apply(
        self, doc: Document, rule: Rule, table: str, row: Row, trigger: str | None, depth: int
    ) -> None:
        kind = rule.class_name
        scope = _RowScope(self, doc, table, row, trigger)
        suppress = rule.flag("bSuppressChangeEvents")
        if kind is None:
            self._value_rule(doc, rule, table, row, scope, suppress, depth)
        elif kind == "BravoMoneyEvaluator":
            self._money_rule(doc, rule, table, row, scope, suppress, depth)
        elif kind == "BravoServerConstraint":
            if rule.setting("CommandKey"):
                raise RuleRefusedError(f"{rule.name} opens a screen ({rule.setting('CommandKey')})")
            command = rule.setting("Command")
            if not command:
                raise RuleRefusedError(f"{rule.name} names no command")
            outputs = rule.data_members()
            params = self._parameters(rule, scope)
            result = self.procedures.call(command, params, outputs)
            for column in outputs:
                self._assign(
                    doc, table, row, column, result[column], rule.name, trigger, suppress, depth
                )
        elif kind == "BravoBindingMember":
            self._binding_rule(doc, rule, table, row, scope, trigger, suppress, depth)
        elif kind == "BravoCopyValue":
            values = {k: evaluate(v, scope) for k, v in rule.maps.get("CopyValues", {}).items()}
            for column, value in values.items():
                self._assign(doc, table, row, column, value, rule.name, trigger, suppress, depth)
        elif kind == "BravoTableOrderer":
            for column in rule.data_members():
                position = Decimal(doc.index(table, row) + 1)
                self._assign(doc, table, row, column, position, rule.name, trigger, True, depth)
        else:
            raise RuleRefusedError(f"{rule.name}: rule kind {kind} is not measured yet")

    def _parameters(self, rule: Rule, scope: _RowScope) -> dict[str, object]:
        params: dict[str, object] = {}
        for name, text in rule.maps.get("Parameters", {}).items():
            if not text:
                raise RuleRefusedError(
                    f"{rule.name}: parameter {name} is an output; its use is unmeasured"
                )
            params[name] = evaluate(text, scope)
        return params

    def _rounded(self, rule: Rule, value: object, scope: _RowScope) -> object:
        places = rule.setting("zResultDecimalRound")
        if not places:
            return value
        return round_decimal(value, evaluate(places, scope), places)

    def _value_rule(
        self,
        doc: Document,
        rule: Rule,
        table: str,
        row: Row,
        scope: _RowScope,
        suppress: bool,
        depth: int,
    ) -> None:
        text = rule.setting("Value")
        if text is None and "Controls" in rule.settings:
            return  # a control's look only: nothing is assigned
        if text is None:
            raise RuleRefusedError(f"{rule.name} has no Value")
        rows = [row]
        scope_text = rule.setting("zScopeExpr")
        if scope_text:
            narrowed = substitute(scope_text, scope)
            rows = [
                r
                for r in doc.rows(table)
                if condition(narrowed, _RowScope(self, doc, table, r, scope.trigger))
            ]
        members = rule.data_members()
        for target in rows:
            target_scope = _RowScope(self, doc, table, target, scope.trigger)
            value = self._rounded(rule, evaluate(text, target_scope), target_scope)
            if len(members) == 1 or suppress:
                for column in members:
                    self._assign(
                        doc, table, target, column, value, rule.name, scope.trigger, suppress, depth
                    )
                continue
            # A rule setting several columns sets them all, then each change
            # raises its events (UAT trace 11-25 17:31:50: the reset of
            # `OriginalUnitCost,UnitCost` on a cancel leaves `UnitCost` 0, the
            # money rule's, which only holds when both are set first).
            changed = [c for c in members if self._will_change(table, target, c, value)]
            for column in changed:
                self._column_event(doc, table, target, "ColumnChanging", column, depth)
            for column in members:
                self._assign(
                    doc, table, target, column, value, rule.name, scope.trigger, True, depth
                )
            for column in changed:
                self._column_event(doc, table, target, "ColumnChanged", column, depth)

    def _money_rule(
        self,
        doc: Document,
        rule: Rule,
        table: str,
        row: Row,
        scope: _RowScope,
        suppress: bool,
        depth: int,
    ) -> None:
        money, number = rule.setting("zMoneyValue"), rule.setting("zNumberValue")
        if not money or not number:
            raise RuleRefusedError(f"{rule.name} lacks zMoneyValue or zNumberValue")
        formula = rule.setting("zFormula") or "{0}*{1}"
        text = formula.replace("{0}", f"({money})").replace("{1}", f"({number})")
        swapped = formula.replace("{0}", f"({number})").replace("{1}", f"({money})")
        value = evaluate(text, scope)
        if formula != "{0}*{1}" and not _same(value, evaluate(swapped, scope)):
            # Which operand is {0} is not measured; only a formula that reads
            # the same both ways is evaluated.
            raise RuleRefusedError(f"{rule.name}: zFormula depends on operand order")
        (column,) = rule.data_members() or (None,)
        if column is None:
            raise RuleRefusedError(f"{rule.name} names no DataMember")
        current = scope.column(column) if row.has(column) else None
        if value is None:
            # A NULL operand counts as 0: on the 11-25 cancel the client wrote
            # `UnitCost` 0 over `OriginalUnitCost` NULL (UAT trace 17:31:50),
            # which "left alone" would have kept at 1100 or NULL.
            value = Decimal(0)
        value = self._rounded(rule, value, scope)
        margin_text = rule.setting("zResultMarginValue")
        if margin_text and not _same(current, value):
            margin = evaluate(margin_text, scope)
            if margin is not None and not is_empty(margin):
                raise RuleRefusedError(f"{rule.name}: a non-zero margin's effect is unmeasured")
        self._assign(doc, table, row, column, value, rule.name, scope.trigger, suppress, depth)

    def _binding_rule(
        self,
        doc: Document,
        rule: Rule,
        table: str,
        row: Row,
        scope: _RowScope,
        trigger: str | None,
        suppress: bool,
        depth: int,
    ) -> None:
        (column,) = rule.data_members() or (None,)
        lookup = rule.setting("LookupKey")
        if column is None or lookup is None:
            raise RuleRefusedError(f"{rule.name} lacks DataMember or LookupKey")
        code = scope.column(column)
        filter_key = rule.setting("FilterKey")
        found = self.references.find(
            lookup, code, substitute(filter_key, scope) if filter_key else None
        )
        if found is None:
            raise UndecidableError(f"{lookup} {code!r} not found")
        for target, source in rule.maps.get("bindingMembers", {}).items():
            if source not in found:
                raise UndecidableError(f"{lookup}.{source} not in hand")
            self._assign(
                doc, table, row, target, found[source], rule.name, trigger, suppress, depth
            )

    # --------------------------------------------------------- assignment

    def _will_change(self, table: str, row: Row, column: str, value: object) -> bool:
        """Whether setting ``column`` to ``value`` changes it; refuses, as
        `_assign` does, a column not in hand whose change would fire rules."""
        current = row.get(column) if row.has(column) else None
        spec = self.layout.tables[table]
        handled = any(
            column.lower() in spec.column_events.get(e, {})
            for e in ("ColumnChanging", "ColumnChanged")
        )
        if current is UNKNOWN and handled:
            raise UndecidableError(
                f"{table}.{column} was not in hand, "
                "so whether setting it fires its rules is not known"
            )
        return not _same(current, value)

    def _assign(
        self,
        doc: Document,
        table: str,
        row: Row,
        column: str,
        value: object,
        rule: str,
        trigger: str | None,
        suppress: bool,
        depth: int,
    ) -> None:
        current = row.get(column) if row.has(column) else None
        spec = self.layout.tables[table]
        handled = any(
            column.lower() in spec.column_events.get(e, {})
            for e in ("ColumnChanging", "ColumnChanged")
        )
        if current is UNKNOWN and handled and not suppress:
            raise UndecidableError(
                f"{table}.{column} was not in hand, "
                "so whether setting it fires its rules is not known"
            )
        if _same(current, value):
            return
        if not suppress:
            self._column_event(doc, table, row, "ColumnChanging", column, depth)
        row.set(column, value)
        doc.trail.append(
            Step(rule, table, doc.index(table, row), row.name(column), current, value, trigger)
        )
        if not suppress:
            self._column_event(doc, table, row, "ColumnChanged", column, depth)

    # --------------------------------------------------------- validators

    def _validate(self, doc: Document, table: Table, index: int, row: Row, rule: Rule) -> Finding:
        level: Level = "warning" if rule.flag("bValidateWarning") else "block"
        columns = tuple(
            c.strip() for c in (rule.setting("SourceColumn") or "").split(",") if c.strip()
        )

        def finding(status: Status, reason: str | None = None) -> Finding:
            return Finding(
                rule.name,
                table.key,
                index,
                level,
                status,
                rule.message or rule.name,
                columns,
                reason,
            )

        scope = _RowScope(self, doc, table.key, row, None)
        try:
            if not condition(rule.setting("Expr"), scope):
                return finding("passed", "does not apply")
            if rule.flag("bValidateIfModify") and not (row.new or row.changed()):
                return finding("passed", "row not modified")
            kind = rule.class_name
            if kind is None:
                return finding(
                    "undecided",
                    "no ClassName: its kind is not in the layout "
                    "(the shared template may name it, script 03c)",
                )
            if kind == "BravoValidator":
                text = rule.setting("zValidateExpr")
                if not text:
                    return finding("undecided", "no zValidateExpr")
                ok = truth(evaluate(text, scope), text)
                if ok is None:
                    return finding("undecided", "the check is NULL")
                return finding("passed" if ok else "fired")
            if kind == "BravoServerConstraintValidator":
                command = rule.setting("Command") or ""
                params = self._parameters(rule, scope)
                result = self.procedures.call(command, params, ("Result",))["Result"]
                # A non-zero result fires: usp_Item_CheckMP returns 1 exactly
                # when the item has no mass-production order, its message's case.
                return finding("passed" if is_empty(result) else "fired")
            if kind == "BravoUniqueKeyValidator":
                values = {c: scope.column(c) for c in columns}
                filter_key = rule.setting("FilterKey")
                taken = self.references.key_taken(
                    table.name,
                    values,
                    substitute(filter_key, scope) if filter_key else None,
                    scope.column("Id") if row.has("Id") else None,
                )
                return finding("fired" if taken else "passed")
            return finding("undecided", f"validator kind {kind} is not measured yet")
        except RuleRefusedError as exc:
            return finding("undecided", str(exc))

    # -------------------------------------------------------------- save

    def _commands(self, doc: Document) -> list[WriteCommand]:
        user_id = self.session.user.get("Id")
        commands: list[WriteCommand] = []
        child_writes: list[WriteCommand] = []
        for table_key, rows in doc.children.items():
            for index, row in enumerate(rows):
                command = self._command(table_key, index, row, user_id)
                if command is not None:
                    child_writes.append(command)
        header = self._command(PARENT, 0, doc.parent, user_id)
        if header is None and child_writes:
            header = WriteCommand(PARENT, 0, "update", {"ModifiedBy": user_id})
        if header is not None:
            commands.append(header)
        commands.extend(child_writes)
        return commands

    def _command(self, table: str, index: int, row: Row, user_id: object) -> WriteCommand | None:
        if row.new:
            values = {
                row.name(c): row.get(c)
                for c in sorted(row.stored)
                if row.has(c) and row.get(c) is not None
            }
            if "createdby" in row.stored:
                values["CreatedBy"] = user_id
            return WriteCommand(table, index, "insert", values)
        changed = row.changed()
        if not changed:
            return None
        values = {row.name(c): row.get(c) for c in changed}
        if "modifiedby" in row.stored:
            values[row.name("ModifiedBy")] = user_id
        return WriteCommand(table, index, "update", values)
