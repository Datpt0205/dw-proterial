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
from collections.abc import Mapping
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
_MAPS = ("Parameters", "CopyValues", "DefaultValues", "bindingMembers")
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
        for child in _elements(element):
            tag = child.tag
            if tag.startswith("_"):
                ignored.append(tag)
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


def with_template(layout: Layout, template: Template) -> Layout:
    """``layout`` with the shared template it names in hand: a plan made with
    it is no longer provisional for want of it."""
    if layout.missing_template != template.name:
        raise ValueError(
            f"{layout.form} loads {layout.missing_template!r}, not template {template.name!r}"
        )
    return replace(layout, missing_template=None, template=template)
