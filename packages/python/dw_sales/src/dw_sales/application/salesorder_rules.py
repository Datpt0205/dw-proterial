"""A customer's SalesOrder rules: what each column of the Bravo upload file
holds for that customer, as data code applies (dw_sales ADR 0013, ticket 38).

The tenant's upload layout (`BravoUploadLayout`, ticket 02) says what every
customer's file holds: each column's source among a field the normal reading
gives, the customer's record, a fixed text or nothing. What differs per
customer (a date the PIC moves from the customer's ETA, a quantity in km
written in m, a column that joins two values, a code looked up in the
master data) is the customer's own rules: ``sales_salesorder_rules``, a
tenant rule version holding, per customer, the columns it overrides. A
column it does not name follows the layout.

A column's rule is a **source** (a field of the normal reading, or a value
of the customer's record) and an **ordered list of steps**, each from a
closed set code knows how to apply. Each is one sentence:

- ``copy``: keeps the value as it is.
- ``constant(value)``: the value is this fixed text.
- ``lookup(table, key)``: the value is what the master data's ``table``
  holds for it (or for the field ``key``): the customer's own convert list,
  or one of the item master's columns by PRV code. A table is master data
  imported with its own approval, never copied into a rule.
- ``unit_factor(from, to)``: multiplies the value by how many ``to`` make one
  ``from`` (km to m: 1000).
- ``shift_days(days)``: moves a date by whole calendar days.
- ``round(places, mode)``: rounds a number to ``places`` decimals, half up,
  down or up.
- ``cut(start, end)``: keeps the characters from ``start`` to before ``end``,
  counted from 0, a negative number from the end.
- ``concat(sources, separator)``: appends the values of other fields, each
  after the separator.
- ``multiply(source)``: multiplies the value by another field's.

Anything else is refused when the version is validated: a rule holds no
formula, no code and no value of a particular PO (a ``constant`` is checked
against the worked example when it is learned, `salesorder_learning`).

`filled_row` is the one place a row of the upload file is composed, for the
file a case draws (`order_artifacts.bravo_upload`) and for the replay of a
worked example alike: the same row, the same code.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, ROUND_UP, Decimal, InvalidOperation
from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dw_sales.application.artifact_content import (
    BravoUploadLayout,
    CustomerAttribute,
    UploadColumn,
    UploadField,
    Value,
)
from dw_sales.domain.catalog import ConvertEntry, Customer, CustomerCode, Item

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

# The longest fixed text a rule holds: what a layout's column holds.
CONSTANT_MAX: Final = 200
# How many steps one column takes, and how many columns one customer's rules.
STEPS_MAX: Final = 8
COLUMNS_MAX: Final = 120

# The master-data tables a lookup may name: the customer's own convert list
# (its code for an item to the PRV code), and the item master's columns by
# PRV code. Colour letters reach the PRV code through the convert list, which
# Bravo writes the colour into (ticket 04's comment of 2026-11-10).
LookupTable = Literal[
    "convert_list",
    "item_name",
    "item_specification",
    "item_standard_length",
    "item_unit",
    "item_category",
    "item_colour",
]
# The units a length is converted between, by how many metres each is.
LengthUnit = Literal["mm", "cm", "m", "km"]
_METRES: Final[Mapping[LengthUnit, Decimal]] = {
    "mm": Decimal("0.001"),
    "cm": Decimal("0.01"),
    "m": Decimal(1),
    "km": Decimal(1000),
}
RoundMode = Literal["half_up", "down", "up"]
_ROUNDING: Final[Mapping[RoundMode, str]] = {
    "half_up": ROUND_HALF_UP,
    "down": ROUND_DOWN,
    "up": ROUND_UP,
}
# What two joined values may be separated by: a closed set, so a separator
# cannot carry a value of its own.
Separator = Literal["", " ", "-", "/", "_", ".", ", "]

_Text = Annotated[str, Field(min_length=1, max_length=CONSTANT_MAX, pattern=r"^[^\x00-\x1f\x7f]+$")]
Letter = Annotated[str, Field(pattern=r"^[A-Z]{1,3}$")]


# ------------------------------------------------------------- the steps --


class Copy(BaseModel):
    """Keeps the value as it is."""

    model_config = _FROZEN
    step: Literal["copy"] = "copy"


class Constant(BaseModel):
    """The value is this fixed text."""

    model_config = _FROZEN
    step: Literal["constant"] = "constant"
    value: _Text


class Lookup(BaseModel):
    """The value is what the master data's table holds for it, or for the
    field ``key`` where one is named."""

    model_config = _FROZEN
    step: Literal["lookup"] = "lookup"
    table: LookupTable
    key: UploadField | None = None


class UnitFactor(BaseModel):
    """Multiplies the value by how many ``to`` make one ``from``."""

    model_config = ConfigDict(
        frozen=True, extra="forbid", hide_input_in_errors=True, populate_by_name=True
    )
    step: Literal["unit_factor"] = "unit_factor"
    from_: LengthUnit = Field(alias="from")
    to: LengthUnit

    @model_validator(mode="after")
    def _two_units(self) -> Self:
        if self.from_ == self.to:
            raise ValueError("a unit factor converts between two units")
        return self


class ShiftDays(BaseModel):
    """Moves a date by whole calendar days."""

    model_config = _FROZEN
    step: Literal["shift_days"] = "shift_days"
    days: int = Field(ge=-366, le=366)


class Round(BaseModel):
    """Rounds a number to ``places`` decimals."""

    model_config = _FROZEN
    step: Literal["round"] = "round"
    places: int = Field(ge=0, le=6)
    mode: RoundMode = "half_up"


class Cut(BaseModel):
    """Keeps the characters from ``start`` to before ``end`` (from 0; a
    negative number counts from the end; none: the start or the end)."""

    model_config = _FROZEN
    step: Literal["cut"] = "cut"
    start: int | None = Field(default=None, ge=-200, le=200)
    end: int | None = Field(default=None, ge=-200, le=200)


class Concat(BaseModel):
    """Appends the values of other fields, each after the separator."""

    model_config = _FROZEN
    step: Literal["concat"] = "concat"
    sources: tuple[UploadField, ...] = Field(min_length=1, max_length=4)
    separator: Separator = ""


class Multiply(BaseModel):
    """Multiplies the value by another field's."""

    model_config = _FROZEN
    step: Literal["multiply"] = "multiply"
    source: UploadField


Step = Annotated[
    Copy | Constant | Lookup | UnitFactor | ShiftDays | Round | Cut | Concat | Multiply,
    Field(discriminator="step"),
]


class ColumnRule(BaseModel):
    """One column of the upload file, by its letter in the tenant's layout:
    where its value starts (a field of the normal reading, or the customer's
    record; none only where the first step is a constant) and the steps it
    then goes through, in order."""

    model_config = _FROZEN

    column: Letter
    field: UploadField | None = None
    customer: CustomerAttribute | None = None
    steps: tuple[Step, ...] = Field(default=(), max_length=STEPS_MAX)

    @model_validator(mode="after")
    def _one_start(self) -> Self:
        if self.field is not None and self.customer is not None:
            raise ValueError("a column starts from one source: a field or a customer value")
        starts_fixed = bool(self.steps) and isinstance(self.steps[0], Constant)
        if (self.field is None and self.customer is None) != starts_fixed:
            raise ValueError("a column starts from a source, or from a constant and none")
        return self

    @property
    def index(self) -> int:
        """Its place in the layout's columns, from 0 (A)."""
        return column_index(self.column)


class CustomerSalesOrderRules(BaseModel):
    """One customer's columns: each named once."""

    model_config = _FROZEN

    columns: tuple[ColumnRule, ...] = Field(min_length=1, max_length=COLUMNS_MAX)

    @model_validator(mode="after")
    def _each_column_once(self) -> Self:
        letters = [rule.column for rule in self.columns]
        if len(letters) != len(set(letters)):
            raise ValueError("a column is named once")
        return self

    @property
    def looks_up(self) -> bool:
        """Whether any column reads the master data."""
        return any(isinstance(step, Lookup) for rule in self.columns for step in rule.steps)

    def by_index(self) -> dict[int, ColumnRule]:
        return {rule.index: rule for rule in self.columns}


class SalesOrderRules(BaseModel):
    """``sales_salesorder_rules``: the tenant's customers' rules, by customer
    code. The platform ships none; every customer's arrives as a tenant
    version learned from a worked example and approved."""

    model_config = _FROZEN

    schema_version: Literal["1.0"]
    policy_id: Literal["sales_salesorder_rules"]
    policy_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    mock: bool
    description: str = ""
    customers: Mapping[CustomerCode, CustomerSalesOrderRules] = Field(default_factory=dict)

    @property
    def version(self) -> str:
        return f"{self.policy_id}@{self.policy_version}"

    @property
    def ref(self) -> str:
        return self.version

    def of(self, customer_code: str) -> CustomerSalesOrderRules | None:
        return self.customers.get(customer_code)


def column_index(letter: str) -> int:
    """``A`` as 0, ``AA`` as 26."""
    number = 0
    for char in letter:
        number = number * 26 + ord(char) - ord("A") + 1
    return number - 1


def column_letter(index: int) -> str:
    """0 as ``A``, 26 as ``AA``."""
    letters = ""
    number = index + 1
    while number:
        number, rest = divmod(number - 1, 26)
        letters = chr(ord("A") + rest) + letters
    return letters


def outside(layout: BravoUploadLayout, rules: CustomerSalesOrderRules) -> list[str]:
    """The columns ``rules`` names that the layout does not have."""
    return [rule.column for rule in rules.columns if rule.index >= len(layout.columns)]


# --------------------------------------------------------- the lookups --


@dataclass(frozen=True, slots=True)
class Lookups:
    """The master data a lookup reads, for one customer: its own convert
    list (never another customer's), matched on the code as printed, as the
    catalogue matches a PO line, and the item master by PRV code."""

    convert: Mapping[str, str] = field(default_factory=dict)
    items: Mapping[str, Item] = field(default_factory=dict)

    @classmethod
    def of(
        cls, customer_code: str, entries: Sequence[ConvertEntry], items: Sequence[Item]
    ) -> Lookups:
        return cls(
            convert={
                e.customer_item_code: e.prv_code
                for e in entries
                if e.customer_code == customer_code
            },
            items={item.prv_code: item for item in items},
        )

    def find(self, table: LookupTable, key: str) -> Value:
        if table == "convert_list":
            return self.convert.get(key)
        item = self.items.get(key)
        if item is None:
            return None
        found: object = {
            "item_name": item.name,
            "item_specification": item.specification,
            "item_standard_length": item.pack_multiple,
            "item_unit": item.unit,
            "item_category": item.category,
            "item_colour": item.attributes.colour,
        }[table]
        return found if isinstance(found, str | Decimal) else None


# ----------------------------------------------------------- comparing --
# How a cell is compared, by the replay of a worked example (ticket 38) and by
# the trace of a model's fill (ticket 41): one rule, here.

_DAY: Final = re.compile(
    r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?$"
)
_NUMBER: Final = re.compile(r"^-?\d+(\.\d+)?$")


def canonical(value: Value) -> date | Decimal | str | None:
    """A cell as the replay compares it: a date by its day (a text written
    ``yyyy-mm-dd``, ``yyyy/mm/dd`` or ``yyyy.mm.dd``, with a time of day or
    not, as the reader hands a date cell over, is that day), a number
    by its value (a text of plain digits too), any other text NFKC and
    trimmed, an empty cell as None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, int | Decimal):
        return Decimal(value)
    text = unicodedata.normalize("NFKC", value).strip()
    if not text:
        return None
    if day := _DAY.match(text):
        try:
            return date(int(day.group(1)), int(day.group(2)), int(day.group(3)))
        except ValueError:
            return text
    if _NUMBER.match(text):
        try:
            return Decimal(text)
        except InvalidOperation:
            return text
    return text


def shown(value: Value) -> str | None:
    """A value as a difference names it."""
    found = canonical(value)
    if found is None:
        return None
    if isinstance(found, date):
        return found.isoformat()
    if isinstance(found, Decimal):
        return format(found, "f")
    return found[:200]


# ------------------------------------------------------------ applying --

# Why a step could not be applied, named on the replay's difference and on
# the refusal to draw a file.
StepProblem = Literal[
    "value_missing",
    "not_text",
    "not_a_number",
    "not_a_date",
    "lookup_missing",
]


class StepRefusedError(ValueError):
    """A step that cannot be applied to the value it was given."""

    def __init__(self, column: str, step: int, problem: StepProblem) -> None:
        super().__init__(f"column {column}, step {step}: {problem}")
        self.column = column
        self.step = step
        self.problem = problem


def layout_cell(
    column: UploadColumn, values: Mapping[UploadField, Value], customer: Customer
) -> Value:
    """What one column of the layout holds in one row: the field's value, the
    customer's own value, the fixed text, or nothing in a blank column."""
    if column.field is not None:
        return values[column.field]
    if column.customer is not None:
        value: Value = getattr(customer, column.customer)
        return value
    return column.constant


def apply_rule(
    rule: ColumnRule, values: Mapping[UploadField, Value], customer: Customer, lookups: Lookups
) -> Value:
    """``rule`` applied to one row's values: its source, then each step."""
    value: Value
    if rule.field is not None:
        value = values.get(rule.field)
    elif rule.customer is not None:
        value = getattr(customer, rule.customer)
    else:
        value = None
    return apply_steps(rule.column, value, rule.steps, values, lookups)


def apply_steps(
    column: str,
    value: Value,
    steps: Sequence[Step],
    values: Mapping[UploadField, Value],
    lookups: Lookups,
) -> Value:
    """``steps`` applied in order to ``value``, one row's ``values`` naming
    the fields a step reads: a rule's, and a computation a model named for a
    cell (`salesorder_fill`), redone by the same code. Raises
    `StepRefusedError` naming ``column`` where a step cannot be applied."""
    for number, step in enumerate(steps, start=1):
        try:
            value = _step(step, value, values, lookups)
        except _StepError as refused:
            raise StepRefusedError(column, number, refused.problem) from None
    return value


class _StepError(Exception):
    def __init__(self, problem: StepProblem) -> None:
        self.problem = problem


def _number(value: Value) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise _StepError("value_missing" if value is None else "not_a_number")
    if isinstance(value, int | Decimal):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except InvalidOperation:
            raise _StepError("not_a_number") from None
    raise _StepError("not_a_number")


def _text(value: Value) -> str:
    if value is None:
        raise _StepError("value_missing")
    if isinstance(value, date):
        raise _StepError("not_text")
    return str(value)


def _step(step: Step, value: Value, values: Mapping[UploadField, Value], lookups: Lookups) -> Value:
    match step:
        case Copy():
            return value
        case Constant(value=fixed):
            return fixed
        case Lookup(table=table, key=key):
            found = lookups.find(table, _text(values.get(key) if key is not None else value))
            if found is None:
                raise _StepError("lookup_missing")
            return found
        case UnitFactor(from_=source, to=target):
            return _number(value) * _METRES[source] / _METRES[target]
        case ShiftDays(days=days):
            if not isinstance(value, date):
                raise _StepError("value_missing" if value is None else "not_a_date")
            return value + timedelta(days=days)
        case Round(places=places, mode=mode):
            exponent = Decimal(1).scaleb(-places)
            return _number(value).quantize(exponent, rounding=_ROUNDING[mode])
        case Cut(start=start, end=end):
            return _text(value)[start:end]
        case Concat(sources=sources, separator=separator):
            return separator.join([_text(value), *(_text(values.get(s)) for s in sources)])
        case Multiply(source=source):
            return _number(value) * _number(values.get(source))


def filled_row(
    layout: BravoUploadLayout,
    rules: CustomerSalesOrderRules | None,
    values: Mapping[UploadField, Value],
    customer: Customer,
    lookups: Lookups,
) -> tuple[Value, ...]:
    """One row of the upload file: each column the customer's rules name by
    its rule, every other one as the layout says. Raises `StepRefusedError`
    where a rule's step cannot be applied."""
    named = rules.by_index() if rules is not None else {}
    return tuple(
        apply_rule(named[index], values, customer, lookups)
        if index in named
        else layout_cell(column, values, customer)
        for index, column in enumerate(layout.columns)
    )
