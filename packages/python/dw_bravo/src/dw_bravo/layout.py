"""A Bravo screen's layout (`B00LayoutData`, the `<DataSource>` kind), read as data.

The XML names tables (`ParentTable`, `ChildTable_<alias>`), and for each one:

- events (`ColumnChanging`/`ColumnChanged` per column, `RowAdded`,
  `ServerLoaded`, `ServerUpdating`...), each a list of rule names, some with
  a condition as their text;
- rule definitions, in `Evaluators`/`EvaluatorGroups` or inline inside an
  event the first time they are used;
- `Validators`, `DefaultValues`, `Expressions` (computed columns) and
  `TempColumns`.

Nothing here knows a particular screen: the SO screen's 404 rules are read,
not copied (ticket 59). A layout that changes in Bravo changes what the
runner does with no code change.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from types import MappingProxyType

from dw_bravo.expression import UnsupportedSyntaxError

PARENT = "Parent"

# Child elements of a rule that carry its settings; any other child element is
# a rule reference (inside a group) or an inline definition.
_SETTINGS = frozenset(
    {
        "ClassName",
        "DataMember",
        "Value",
        "Expr",
        "zScopeExpr",
        "zResultDecimalRound",
        "zMoneyValue",
        "zNumberValue",
        "zFormula",
        "zResultMarginValue",
        "bSuppressChangeEvents",
        "Command",
        "CommandKey",
        "zCtorArgs",
        "LookupKey",
        "FilterKey",
        "zValidateExpr",
        "SourceColumn",
        "TargetColumn",
        "bValidateWarning",
        "bValidateIfModify",
        "Text",
        "Parameters",
        "CopyValues",
        "DefaultValues",
        "bindingMembers",
        "Controls",  # a control's look (Visible, Enabled, Format): no value is set
        "autoOutputMember",
    }
)
_MAPS = ("Parameters", "CopyValues", "DefaultValues")
_ROW_EVENTS = (
    "RowAdded",
    "RowCopied",
    "RowDeleting",
    "RowDeleted",
    "ServerLoaded",
    "ServerUpdating",
)
_COLUMN_EVENTS = ("ColumnChanging", "ColumnChanged")


@dataclass(frozen=True)
class Invocation:
    """One use of a rule in an event: its name and, if any, its own condition."""

    name: str
    condition: str | None = None


@dataclass(frozen=True)
class BindingMember:
    """One of a lookup's `bindingMembers`, `<source>target</source>`: the row's
    column `target` takes the looked-up row's column `source` (8213's item
    lookup: `<Name>Description</Name>`, the item's name into the line's
    description; the client's own lookup SELECT reads `Name`, and its INSERT
    writes it as `Description`, UAT trace 11-25 16:53:33). A conditional one,
    `<source><Condition_0><DataMember>target</DataMember><Expr>...</Expr>
    </Condition_0></source>` (8212's `Eval_DocCode_BindingMembers`), sets
    `target` only where `condition` holds on the row."""

    source: str
    target: str
    condition: str | None = None


def _binding_members(element: ET.Element) -> tuple[tuple[BindingMember, ...], tuple[str, ...]]:
    """A `bindingMembers` block: its members in the layout's order, and what
    in it is not read (refused when the rule runs, so one shape not yet
    measured does not stop the whole layout from being read)."""
    members: list[BindingMember] = []
    unread: list[str] = []
    entries = _elements(element)
    if not entries and _text(element):
        # The short form `<bindingMembers>A,B</bindingMembers>`: same names.
        names = [n.strip() for n in (_text(element) or "").split(",") if n.strip()]
        return tuple(BindingMember(n, n) for n in names), ()
    for entry in entries:
        parts = _elements(entry)
        if not parts:
            target = _text(entry)
            if target is None:
                unread.append(f"{entry.tag} binds to no column")
            else:
                members.append(BindingMember(entry.tag, target))
            continue
        first, rest = parts[0], parts[1:]
        settings = {e.tag for e in _elements(first)}
        target, expr = _text(first.find("DataMember")), _text(first.find("Expr"))
        if (
            rest
            or not first.tag.startswith("Condition_")
            or settings != {"DataMember", "Expr"}
            or target is None
            or expr is None
        ):
            # Several conditions on one member (which wins?), or another shape.
            unread.append(f"{entry.tag}: {[p.tag for p in parts]} is not read")
            continue
        members.append(BindingMember(entry.tag, target, expr))
    return tuple(members), tuple(unread)


@dataclass(frozen=True)
class Rule:
    """A rule definition, an evaluator, a group or a validator."""

    name: str
    home: str  # the table it is defined on: "Parent" or a child alias
    class_name: str | None
    settings: Mapping[str, str]
    maps: Mapping[str, Mapping[str, str]]
    members: tuple[Invocation, ...]  # a group's rules, in order
    message: str | None  # the Vietnamese text a validator shows
    ignored: tuple[str, ...]  # settings switched off by a leading '_' in Bravo
    bindings: tuple[BindingMember, ...] = ()  # a lookup's bindingMembers, in order
    unread_bindings: tuple[str, ...] = ()  # what of them is not read: refused when run

    def setting(self, key: str) -> str | None:
        return self.settings.get(key)

    def flag(self, key: str) -> bool:
        return (self.settings.get(key) or "").strip().lower() == "true"

    def data_members(self) -> tuple[str, ...]:
        raw = self.settings.get("DataMember") or ""
        return tuple(m.strip() for m in raw.split(",") if m.strip())

    @property
    def is_group(self) -> bool:
        return bool(self.members) and not self.settings


@dataclass(frozen=True)
class Table:
    key: str  # "Parent" or the child's alias
    name: str  # the view or table Bravo loads it from
    row_events: Mapping[str, tuple[Invocation, ...]]
    column_events: Mapping[str, Mapping[str, tuple[Invocation, ...]]]  # event -> lower col -> rules
    validators: tuple[Rule, ...]
    default_values: Mapping[str, str]
    expressions: Mapping[str, str]  # lower col -> expression
    temp_columns: Mapping[str, str | None]  # lower col -> default expression
    # A child table's relation to its parent (`<ParentKey>`/`<ChildKey>`): the
    # parent's column whose value a new row of this table takes in its own.
    parent_key: str | None = None
    child_key: str | None = None


@dataclass(frozen=True)
class CommandGuard:
    """One of a template's `CommandValidators`: the commands it guards
    (lower case), the condition each needs to be true, and its message."""

    name: str
    commands: frozenset[str]
    expr: str
    message: str | None


@dataclass(frozen=True)
class Template:
    """A shared template a screen loads beside its own layout, as far as it
    sets or checks anything: its command guards. Everything else in it is the
    window's menus and toolbars."""

    name: str
    guards: tuple[CommandGuard, ...]


@dataclass(frozen=True)
class WindowLookup:
    """A lookup box of the screen's window (its form layout, `IsTemplate` 0:
    8213 for `EDIT_BizDocSO`) that binds: when ``column`` of ``table`` takes a
    value, the lookup's row for it is read and its members set on the row.
    It acts on the data, not only on a person's typing: the client read the
    unit lookup (`vB20ItemUnit_Lookup`) right after the item lookup set the
    line's unit through 8212's `Eval_Detail_Unit_DefaultValue` (UAT trace
    11-25 16:50:01). The client's read applies the `FilterKey` and the
    `SelectKey` (16:50:38: the customer's `IsGroup=0 AND ISNULL(Property,'')
    =1 ...`). ``editable`` is the editor's `Expr`, when a person may type
    the column; ``unread`` what is not read, refused when it binds."""

    name: str
    table: str  # "Parent" or the grid's DataMember (a child alias)
    column: str
    lookup_key: str
    filter_key: str | None
    select_key: str | None
    editable: str | None
    members: tuple[BindingMember, ...]
    unread: tuple[str, ...] = ()


@dataclass(frozen=True)
class Window:
    """What of a screen's window sets values: its binding lookups, by (table,
    lower column)."""

    lookups: Mapping[tuple[str, str], WindowLookup]

    def lookup(self, table: str, column: str) -> WindowLookup | None:
        return self.lookups.get((table, column.lower()))


@dataclass(frozen=True)
class Layout:
    form: str
    tables: Mapping[str, Table]
    rules: Mapping[str, Rule]
    ambiguous: frozenset[str] = field(default_factory=frozenset)
    # The shared template the screen also loads (`B00Command`'s TemplateName,
    # `BizDocEditor` for the SO screen) when it is not in hand: its events and
    # rules are invisible here, so nothing the runner returns is complete.
    missing_template: str | None = None
    # The template, read, once it is in hand (`with_template`).
    template: Template | None = None
    # The screen's window (`read_window`), once in hand (`with_window`); and
    # why it is not, when the screen's window was asked for and could not be
    # read: which columns bind is then unknown, so no plan is complete.
    window: Window | None = None
    missing_window: str | None = None

    @property
    def parent(self) -> Table:
        return self.tables[PARENT]

    def children(self) -> list[Table]:
        return [t for k, t in self.tables.items() if k != PARENT]


def _text(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    value = (element.text or "").strip()
    return value or None


def _elements(element: ET.Element) -> list[ET.Element]:
    return [c for c in element if isinstance(c.tag, str)]


def _message(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    return _text(element.find("Vietnamese")) or _text(element.find("English")) or _text(element)


class _Reader:
    def __init__(self, form: str) -> None:
        self.form = form
        self.rules: dict[str, Rule] = {}
        self.ambiguous: set[str] = set()

    def define(self, element: ET.Element, home: str) -> Rule:
        settings: dict[str, str] = {}
        maps: dict[str, Mapping[str, str]] = {}
        members: list[Invocation] = []
        ignored: list[str] = []
        bindings: tuple[BindingMember, ...] = ()
        unread: tuple[str, ...] = ()
        for child in _elements(element):
            tag = child.tag
            if tag.startswith("_"):
                ignored.append(tag)
            elif tag == "bindingMembers":
                bindings, unread = _binding_members(child)
            elif tag in _MAPS:
                entries = {c.tag: (c.text or "").strip() for c in _elements(child)}
                if not entries and _text(child):
                    # The short form `<Parameters>CurrencyCode,BranchCode</Parameters>`:
                    # each parameter takes the column of the same name.
                    entries = {
                        n.strip(): n.strip() for n in (_text(child) or "").split(",") if n.strip()
                    }
                maps[tag] = MappingProxyType(entries)
            elif tag == "Text":
                continue
            elif tag in _SETTINGS:
                settings[tag] = (child.text or "").strip()
            else:
                members.append(self.invocation(child, home))
        rule = Rule(
            name=element.tag,
            home=home,
            class_name=settings.pop("ClassName", None) or None,
            settings=MappingProxyType(settings),
            maps=MappingProxyType(maps),
            members=tuple(members),
            message=_message(element.find("Text")),
            ignored=tuple(ignored),
            bindings=bindings,
            unread_bindings=unread,
        )
        return rule

    def register(self, rule: Rule) -> None:
        known = self.rules.get(rule.name)
        if known is not None and known != rule:
            self.ambiguous.add(rule.name)
        self.rules.setdefault(rule.name, rule)

    def invocation(self, element: ET.Element, home: str) -> Invocation:
        if _elements(element):
            self.register(self.define(element, home))
            return Invocation(element.tag)
        return Invocation(element.tag, _text(element))

    def table(self, element: ET.Element, key: str) -> Table:
        row_events: dict[str, tuple[Invocation, ...]] = {}
        column_events: dict[str, Mapping[str, tuple[Invocation, ...]]] = {}
        for section in ("Evaluators", "EvaluatorGroups"):
            block = element.find(section)
            if block is not None:
                for rule_el in _elements(block):
                    self.register(self.define(rule_el, key))
        for event in _ROW_EVENTS:
            block = element.find(event)
            if block is not None:
                row_events[event] = tuple(self.invocation(e, key) for e in _elements(block))
        for event in _COLUMN_EVENTS:
            block = element.find(event)
            per_column: dict[str, tuple[Invocation, ...]] = {}
            if block is not None:
                for column in _elements(block):
                    per_column[column.tag.lower()] = tuple(
                        self.invocation(e, key) for e in _elements(column)
                    )
            column_events[event] = MappingProxyType(per_column)
        validators = element.find("Validators")
        defaults = element.find("DefaultValues")
        expressions = element.find("Expressions")
        temps = element.find("TempColumns")
        return Table(
            key=key,
            name=_text(element.find("Name")) or key,
            row_events=MappingProxyType(row_events),
            column_events=MappingProxyType(column_events),
            validators=tuple(self.define(v, key) for v in _elements(validators))
            if validators is not None
            else (),
            default_values=MappingProxyType(
                {c.tag.lower(): (c.text or "").strip() for c in _elements(defaults)}
                if defaults is not None
                else {}
            ),
            expressions=MappingProxyType(
                {c.tag.lower(): (c.text or "").strip() for c in _elements(expressions)}
                if expressions is not None
                else {}
            ),
            temp_columns=MappingProxyType(
                {c.tag.lower(): _text(c.find("DefaultValue")) for c in _elements(temps)}
                if temps is not None
                else {}
            ),
            parent_key=_text(element.find("ParentKey")),
            child_key=_text(element.find("ChildKey")),
        )


def read_layout(xml_text: str, form: str, *, missing_template: str | None = None) -> Layout:
    """Read a `<DataSource>` layout; refuse one that declares a DOCTYPE.

    `missing_template` names the shared template the screen loads beside its
    own layout when that template is not in hand (script 03c brings
    `BizDocEditor`); how the two merge is not measured yet.
    """
    root = _parse(xml_text, "a layout")
    tables_el = root.find("Tables")
    if tables_el is None:
        raise UnsupportedSyntaxError(f"{form}: no <Tables> in the layout")
    reader = _Reader(form)
    tables: dict[str, Table] = {}
    for element in _elements(tables_el):
        if element.tag == "ParentTable":
            key = PARENT
        elif element.tag.startswith("ChildTable_"):
            key = _text(element.find("Alias")) or element.tag.removeprefix("ChildTable_")
        else:
            raise UnsupportedSyntaxError(f"{form}: unknown table element {element.tag}")
        tables[key] = reader.table(element, key)
    if PARENT not in tables:
        raise UnsupportedSyntaxError(f"{form}: no ParentTable")
    return Layout(
        form=form,
        tables=MappingProxyType(tables),
        rules=MappingProxyType(dict(reader.rules)),
        ambiguous=frozenset(reader.ambiguous),
        missing_template=missing_template,
    )


# The parts of a template's parent table that set or check nothing: the
# columns the window fetches. Any other part refuses the template whole.
_TEMPLATE_INERT = frozenset({"FetchingColumnList"})


def _parse(xml_text: str, what: str) -> ET.Element:
    if "<!DOCTYPE" in xml_text[:4096].upper():
        raise UnsupportedSyntaxError(f"{what} with a DOCTYPE is refused (entities are not read)")
    # DOCTYPE refused above; expat also refuses entity amplification
    # (measured 2.7.4, 2026-11-23); ElementTree fetches no external entity.
    return ET.fromstring(xml_text)  # nosec B314


def read_template(xml_text: str, name: str) -> Template:
    """Read a shared template (`B00Layout.IsTemplate`): its parent table's
    `CommandValidators`, each a guard on the commands it names. A template
    that sets or checks anything else (an event, a rule, a validator, a
    child table) is refused whole: what it would do is not read, so a plan
    made with it would not be complete (ticket 59, script 03c)."""
    root = _parse(xml_text, f"template {name}")
    source = root.find("DataSource")
    if source is None:
        return Template(name, ())
    tables = source.find("Tables")
    parts = _elements(source)
    if any(p.tag != "Tables" for p in parts):
        raise UnsupportedSyntaxError(f"template {name}: {[p.tag for p in parts]} is not read")
    guards: list[CommandGuard] = []
    for table in [] if tables is None else _elements(tables):
        if table.tag != "ParentTable":
            raise UnsupportedSyntaxError(f"template {name}: {table.tag} is not read")
        for part in _elements(table):
            if part.tag in _TEMPLATE_INERT:
                continue
            if part.tag != "CommandValidators":
                raise UnsupportedSyntaxError(f"template {name}: {part.tag} is not read")
            for guard in _elements(part):
                commands = _text(guard.find("CommandName")) or ""
                expr = _text(guard.find("Expr"))
                if not commands or expr is None:
                    raise UnsupportedSyntaxError(
                        f"template {name}: guard {guard.tag} names no command or condition"
                    )
                guards.append(
                    CommandGuard(
                        name=guard.tag,
                        commands=frozenset(
                            c.strip().lower() for c in commands.split(",") if c.strip()
                        ),
                        expr=expr,
                        message=_message(guard.find("Text")),
                    )
                )
    return Template(name, tuple(guards))


def _lookup(
    element: ET.Element, name: str, table: str, column: str, editable: str | None
) -> WindowLookup:
    members, unread = _binding_members(element.find("bindingMembers"))  # type: ignore[arg-type]
    lookup_key = _text(element.find("LookupKey"))
    if (_text(element.find("ClassName")) or "") != "BravoLookupBox" or lookup_key is None:
        unread = (*unread, f"{name}: a binding that is not a BravoLookupBox with a LookupKey")
    return WindowLookup(
        name=name,
        table=table,
        column=column,
        lookup_key=lookup_key or "",
        filter_key=_text(element.find("FilterKey")),
        select_key=_text(element.find("SelectKey")),
        editable=editable,
        members=members,
        unread=unread,
    )


def read_window(xml_text: str, form: str) -> Window:
    """Read a screen's window (its form layout): every lookup box that binds
    (`bindingMembers`), on the header (a control naming its `DataMember`) or
    on a grid's column (`BravoGridContainer`/`Items`/`Item_N`, whose
    `DataMember` is the child table).
    A binding whose column cannot be placed, or two on one column, refuse
    the window whole: which columns bind would not be known."""
    root = _parse(xml_text, f"{form} window")
    if root.find("Tables") is not None:
        raise UnsupportedSyntaxError(f"{form}: a DataSource, not a window")
    lookups: dict[tuple[str, str], WindowLookup] = {}
    placed: set[int] = set()

    def add(lookup: WindowLookup) -> None:
        key = (lookup.table, lookup.column.lower())
        if key in lookups:
            raise UnsupportedSyntaxError(f"{form}: two lookups bind {lookup.table}.{lookup.column}")
        lookups[key] = lookup

    for container in root.iter():
        if _text(container.find("ClassName")) != "BravoGridContainer":
            continue
        items = container.find("Items")
        for item in [] if items is None else _elements(items):
            alias = _text(item.find("DataMember"))
            cols = item.find("Cols")
            if alias is None or cols is None:
                raise UnsupportedSyntaxError(f"{form}: grid {item.tag} names no table or columns")
            for col in _elements(cols):
                editor = col.find("Editor")
                if editor is None:
                    continue
                placed.add(id(editor))
                if editor.find("bindingMembers") is not None:
                    add(
                        _lookup(
                            editor,
                            f"{alias}.{col.tag}",
                            alias,
                            col.tag,
                            _text(editor.find("Expr")),
                        )
                    )
    for element in root.iter():
        if element.find("bindingMembers") is None or id(element) in placed:
            continue
        column = _text(element.find("DataMember"))
        if column is None:
            raise UnsupportedSyntaxError(f"{form}: {element.tag} binds but names no column")
        add(_lookup(element, element.tag, PARENT, column, _text(element.find("Expr"))))
    return Window(MappingProxyType(lookups))


def merge_windows(base: Window, variants: Sequence[Window], why: str) -> Window:
    """The window as far as ``base`` and its ``variants`` (a user's or a
    role's own copy, `B00LayoutDataEdit`) agree: a lookup they bind
    differently stays, marked unread with ``why``, so it refuses when it
    binds and nothing else does."""
    lookups = dict(base.lookups)
    for variant in variants:
        for key in base.lookups.keys() | variant.lookups.keys():
            mine, theirs = base.lookups.get(key), variant.lookups.get(key)
            if mine == theirs:
                continue
            kept = mine or theirs
            assert kept is not None
            lookups[key] = replace(lookups.get(key, kept), unread=(*kept.unread, why))
    return Window(MappingProxyType(lookups))


def with_window(layout: Layout, window: Window) -> Layout:
    """``layout`` with its screen's window in hand: its lookups bind."""
    return replace(layout, window=window, missing_window=None)


def with_template(layout: Layout, template: Template) -> Layout:
    """``layout`` with the shared template it names in hand: a plan made with
    it is no longer provisional for want of it."""
    if layout.missing_template != template.name:
        raise ValueError(
            f"{layout.form} loads {layout.missing_template!r}, not template {template.name!r}"
        )
    return replace(layout, missing_template=None, template=template)
