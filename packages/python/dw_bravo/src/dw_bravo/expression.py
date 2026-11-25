"""Bravo's expression language, read from a screen's layout and evaluated here.

Bravo stores a screen's rules as XML (`B00LayoutData`); its client evaluates
their expressions (sales ticket 59). The syntax is ADO.NET's DataColumn
expressions plus Bravo's own functions (EMPTY, VLOOKUP, SUMIF, UPDATEDCOLUMN,
USER, GETDATE...), with `{=expr}` substituted from the current row before the
text is parsed.

The rule here is the ticket's: **an expression this module cannot evaluate
without guessing refuses the run** (`RuleRefusedError`). That covers syntax it does
not know, a function whose behaviour has not been measured, and a value that is
not in hand (`UndecidableError`). A refusal is recoverable; a guessed rule acting on
Bravo is not.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, DivisionByZero, InvalidOperation
from functools import lru_cache
from typing import Protocol


class RuleRefusedError(Exception):
    """The rule cannot be evaluated without guessing; the run stops."""


class UnsupportedSyntaxError(RuleRefusedError):
    """Syntax or a function this evaluator does not know."""


class UndecidableError(RuleRefusedError):
    """A value the rule needs is not in hand (a column, a procedure's result)."""


class _Unknown:
    """A value that exists in Bravo but is not in hand here.

    Reading it raises `UndecidableError`; it is never treated as NULL, because a
    NULL is a value Bravo's rules act on and an unknown is not.
    """

    _instance: _Unknown | None = None

    def __new__(cls) -> _Unknown:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "UNKNOWN"


UNKNOWN = _Unknown()


# --------------------------------------------------------------------------- AST


@dataclass(frozen=True)
class Lit:
    value: object


@dataclass(frozen=True)
class Col:
    """A column: `Qty` on the current row, `Parent.Qty`, or `Detail.Qty`."""

    name: str
    table: str | None = None


@dataclass(frozen=True)
class Call:
    name: str  # upper-cased
    args: tuple[Node, ...]


@dataclass(frozen=True)
class Member:
    """`Child(Detail).OriginalAmount`: a column of a child table."""

    base: Node
    name: str


@dataclass(frozen=True)
class Unary:
    op: str
    operand: Node


@dataclass(frozen=True)
class Binary:
    op: str
    left: Node
    right: Node


@dataclass(frozen=True)
class InList:
    operand: Node
    items: tuple[Node, ...]
    negated: bool


@dataclass(frozen=True)
class Like:
    operand: Node
    pattern: Node
    negated: bool


@dataclass(frozen=True)
class IsNull:
    operand: Node
    negated: bool


Node = Lit | Col | Call | Member | Unary | Binary | InList | Like | IsNull


# ------------------------------------------------------------------ tokenizer

_TOKEN = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<num>\d+(?:\.\d+)?)
  | (?P<str>'(?:[^']|'')*')
  | (?P<op><>|!=|<=|>=|==|[=<>+\-*/%(),!.])
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    """,
    re.VERBOSE,
)

_KEYWORDS = {"AND", "OR", "NOT", "IN", "LIKE", "IS", "NULL", "TRUE", "FALSE"}


@dataclass(frozen=True)
class _Tok:
    kind: str  # num | str | op | name | kw | end
    text: str


def _tokenize(text: str) -> list[_Tok]:
    tokens: list[_Tok] = []
    pos = 0
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        if match is None:
            raise UnsupportedSyntaxError(f"unexpected character {text[pos]!r} in {text!r}")
        pos = match.end()
        kind = match.lastgroup or ""
        if kind == "ws":
            continue
        value = match.group(kind)
        if kind == "name" and value.upper() in _KEYWORDS:
            tokens.append(_Tok("kw", value.upper()))
        else:
            tokens.append(_Tok(kind, value))
    tokens.append(_Tok("end", ""))
    return tokens


# --------------------------------------------------------------------- parser


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.tokens = _tokenize(text)
        self.pos = 0

    def peek(self) -> _Tok:
        return self.tokens[self.pos]

    def take(self) -> _Tok:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def accept(self, kind: str, text: str | None = None) -> bool:
        tok = self.peek()
        if tok.kind == kind and (text is None or tok.text == text):
            self.pos += 1
            return True
        return False

    def expect(self, kind: str, text: str) -> None:
        if not self.accept(kind, text):
            raise UnsupportedSyntaxError(
                f"expected {text!r} at {self.peek().text!r} in {self.text!r}"
            )

    def parse(self) -> Node:
        node = self.or_()
        if self.peek().kind != "end":
            raise UnsupportedSyntaxError(f"unexpected {self.peek().text!r} in {self.text!r}")
        return node

    def or_(self) -> Node:
        node = self.and_()
        while self.accept("kw", "OR"):
            node = Binary("OR", node, self.and_())
        return node

    def and_(self) -> Node:
        node = self.not_()
        while self.accept("kw", "AND"):
            right = self.not_()
            # `X AND False` is false whatever X is: folded here so a disabled
            # rule (`... AND False`) never evaluates the part before it.
            node = Lit(False) if Lit(False) in (node, right) else Binary("AND", node, right)
        return node

    def not_(self) -> Node:
        if self.accept("kw", "NOT") or self.accept("op", "!"):
            return Unary("NOT", self.not_())
        return self.comparison()

    def comparison(self) -> Node:
        node = self.additive()
        tok = self.peek()
        if tok.kind == "op" and tok.text in ("=", "==", "<>", "!=", "<", "<=", ">", ">="):
            self.take()
            op = {"==": "=", "!=": "<>"}.get(tok.text, tok.text)
            return Binary(op, node, self.additive())
        negated = False
        if tok.kind == "kw" and tok.text == "NOT":
            nxt = self.tokens[self.pos + 1]
            if nxt.kind == "kw" and nxt.text in ("IN", "LIKE"):
                self.take()
                negated = True
        if self.accept("kw", "IN"):
            self.expect("op", "(")
            items = [self.additive()]
            while self.accept("op", ","):
                items.append(self.additive())
            self.expect("op", ")")
            return InList(node, tuple(items), negated)
        if self.accept("kw", "LIKE"):
            return Like(node, self.additive(), negated)
        if self.accept("kw", "IS"):
            is_not = self.accept("kw", "NOT")
            self.expect("kw", "NULL")
            return IsNull(node, is_not)
        return node

    def additive(self) -> Node:
        node = self.multiplicative()
        while self.peek().kind == "op" and self.peek().text in ("+", "-"):
            node = Binary(self.take().text, node, self.multiplicative())
        return node

    def multiplicative(self) -> Node:
        node = self.unary()
        while self.peek().kind == "op" and self.peek().text in ("*", "/", "%"):
            node = Binary(self.take().text, node, self.unary())
        return node

    def unary(self) -> Node:
        if self.accept("op", "-"):
            return Unary("-", self.unary())
        if self.accept("op", "!"):
            return Unary("NOT", self.unary())
        return self.primary()

    def primary(self) -> Node:
        tok = self.take()
        if tok.kind == "num":
            return Lit(Decimal(tok.text))
        if tok.kind == "str":
            return Lit(tok.text[1:-1].replace("''", "'"))
        if tok.kind == "kw" and tok.text in ("TRUE", "FALSE"):
            return Lit(tok.text == "TRUE")
        if tok.kind == "kw" and tok.text == "NULL":
            return Lit(None)
        if tok.kind == "op" and tok.text == "(":
            inner = self.or_()
            self.expect("op", ")")
            return inner
        if tok.kind == "name":
            if self.accept("op", "("):
                args: list[Node] = []
                if not self.accept("op", ")"):
                    args.append(self.or_())
                    while self.accept("op", ","):
                        args.append(self.or_())
                    self.expect("op", ")")
                node: Node = Call(tok.text.upper(), tuple(args))
                if self.accept("op", "."):
                    name = self.take()
                    if name.kind != "name":
                        raise UnsupportedSyntaxError(
                            f"expected a column after '.' in {self.text!r}"
                        )
                    node = Member(node, name.text)
                return node
            if self.accept("op", "."):
                name = self.take()
                if name.kind != "name":
                    raise UnsupportedSyntaxError(f"expected a column after '.' in {self.text!r}")
                return Col(name.text, tok.text)
            return Col(tok.text)
        raise UnsupportedSyntaxError(f"unexpected {tok.text!r} in {self.text!r}")


@lru_cache(maxsize=4096)
def parse(text: str) -> Node:
    """Parse an expression with no `{=...}` left in it."""
    return _Parser(text).parse()


# ------------------------------------------------------------- substitution


def _template_spans(text: str) -> list[tuple[int, int]]:
    """Where each `{=expr}` starts and ends, quotes inside it respected."""
    spans: list[tuple[int, int]] = []
    pos = 0
    while (start := text.find("{=", pos)) != -1:
        depth, i, quoted = 1, start + 2, False
        while i < len(text) and depth:
            ch = text[i]
            if ch == "'":
                quoted = not quoted
            elif not quoted and ch == "{":
                depth += 1
            elif not quoted and ch == "}":
                depth -= 1
            i += 1
        if depth:
            raise UnsupportedSyntaxError(f"unclosed {{= in {text!r}")
        spans.append((start, i))
        pos = i
    return spans


def _render(value: object, text: str) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, Decimal | int):
        return format(Decimal(value).normalize(), "f")
    if isinstance(value, str) and "'" not in value:
        return value
    raise RuleRefusedError(
        f"cannot substitute {value!r} into {text!r}: its rendering is unmeasured"
    )


# ----------------------------------------------------------------- evaluation


class Scope(Protocol):
    """What an expression reads: the row it runs on and its document."""

    def column(self, name: str) -> object: ...

    def parent_column(self, name: str) -> object: ...

    def table_rows(self, table: str) -> Sequence[Scope]: ...

    def updated_column(self) -> str | None: ...

    def session(self, function: str, argument: object) -> object: ...


@dataclass(frozen=True)
class _TableRef:
    name: str


def _check(value: object, what: str) -> object:
    if value is UNKNOWN:
        raise UndecidableError(f"{what} is not in hand")
    return value


def _number(value: object, text: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return Decimal(int(value))
    if isinstance(value, Decimal | int):
        return Decimal(value)
    raise RuleRefusedError(f"{value!r} is not a number in {text!r}")


def is_empty(value: object) -> bool:
    """Bravo's EMPTY: NULL, '', zero or False."""
    _check(value, "a value EMPTY() reads")
    if value is None or value == "" or value is False:
        return True
    if isinstance(value, Decimal | int) and not isinstance(value, bool):
        return Decimal(value) == 0
    return False


def round_decimal(value: object, places: object, text: str) -> object:
    """Round as Bravo does — or refuse where its rounding mode would matter.

    Half-up and half-even give the same answer unless the value sits on the
    half; Bravo's mode has not been measured, so a value on the half refuses.
    """
    if value is None:
        return None
    number = _number(value, text)
    digits = _number(places, text)
    if number is None or digits is None:
        raise RuleRefusedError(f"rounding {value!r} to {places!r} places in {text!r}")
    quantum = Decimal(1).scaleb(-int(digits))
    up = number.quantize(quantum, rounding=ROUND_HALF_UP)
    even = number.quantize(quantum, rounding=ROUND_HALF_EVEN)
    if up != even:
        raise RuleRefusedError(
            f"{number} sits on the half at {int(digits)} places; Bravo's mode is unmeasured"
        )
    return up


def _compare(op: str, left: object, right: object, text: str) -> bool | None:
    if left is None or right is None:
        return None
    if isinstance(left, str) and isinstance(right, str):
        if left != right and left.casefold() == right.casefold():
            # Bravo compares through .NET and SQL Server, both case-blind by
            # default here; which one applies is unmeasured, so a case-only
            # difference refuses rather than decides.
            raise RuleRefusedError(f"{left!r} and {right!r} differ only in case in {text!r}")
        a: object = left
        b: object = right
    elif isinstance(left, datetime) and isinstance(right, datetime):
        a, b = left, right
    else:
        a, b = _number(left, text), _number(right, text)
    if op == "=":
        return a == b
    if op == "<>":
        return a != b
    try:
        if op == "<":
            return bool(a < b)  # type: ignore[operator]
        if op == "<=":
            return bool(a <= b)  # type: ignore[operator]
        if op == ">":
            return bool(a > b)  # type: ignore[operator]
        return bool(a >= b)  # type: ignore[operator]
    except TypeError as exc:
        raise RuleRefusedError(f"cannot order {left!r} and {right!r} in {text!r}") from exc


def truth(value: object, text: str) -> bool | None:
    """A condition's value: True, False or None (NULL)."""
    if value is None or isinstance(value, bool):
        return value
    raise RuleRefusedError(f"{value!r} is not a condition in {text!r}")


def _like(value: str, pattern: str) -> bool:
    regex = "".join(".*" if ch == "%" else "." if ch == "_" else re.escape(ch) for ch in pattern)
    blind = bool(re.fullmatch(regex, value, re.DOTALL | re.IGNORECASE))
    if blind != bool(re.fullmatch(regex, value, re.DOTALL)):
        raise RuleRefusedError(f"LIKE {pattern!r} on {value!r} depends on case")
    return bool(re.fullmatch(regex, value, re.DOTALL))


class Evaluator:
    """Evaluates one expression text against a `Scope`."""

    def __init__(self, text: str, scope: Scope) -> None:
        self.text = text
        self.scope = scope

    def run(self) -> object:
        return self.eval(parse(substitute(self.text, self.scope)), self.scope)

    # -- nodes

    def eval(self, node: Node, scope: Scope) -> object:
        if isinstance(node, Lit):
            return node.value
        if isinstance(node, Col):
            return self.column(node, scope)
        if isinstance(node, Unary):
            value = self.eval(node.operand, scope)
            if node.op == "NOT":
                cond = truth(value, self.text)
                return None if cond is None else not cond
            number = _number(value, self.text)
            return None if number is None else -number
        if isinstance(node, Binary):
            return self.binary(node, scope)
        if isinstance(node, InList):
            value = self.eval(node.operand, scope)
            if value is None:
                return None
            found = any(
                _compare("=", value, self.eval(item, scope), self.text) for item in node.items
            )
            return found != node.negated
        if isinstance(node, Like):
            value = self.eval(node.operand, scope)
            pattern = self.eval(node.pattern, scope)
            if value is None or pattern is None:
                return None
            if not isinstance(value, str) or not isinstance(pattern, str):
                raise RuleRefusedError(f"LIKE on a non-string in {self.text!r}")
            return _like(value, pattern) != node.negated
        if isinstance(node, IsNull):
            value = _check(self.eval(node.operand, scope), self.text)
            return (value is None) != node.negated
        if isinstance(node, Call):
            return self.call(node, scope)
        if isinstance(node, Member):
            raise UnsupportedSyntaxError(
                f"a child table's column outside SUM/SUMIF in {self.text!r}"
            )
        raise UnsupportedSyntaxError(f"{node!r} in {self.text!r}")

    def column(self, node: Col, scope: Scope) -> object:
        if node.table is None:
            return _check(scope.column(node.name), node.name)
        if node.table.upper() == "PARENT":
            return _check(scope.parent_column(node.name), f"Parent.{node.name}")
        raise UnsupportedSyntaxError(
            f"{node.table}.{node.name} outside an aggregate in {self.text!r}"
        )

    def binary(self, node: Binary, scope: Scope) -> object:
        if node.op in ("AND", "OR"):
            lcond = truth(self.eval(node.left, scope), self.text)
            if node.op == "AND" and lcond is False:
                return False
            if node.op == "OR" and lcond is True:
                return True
            rcond = truth(self.eval(node.right, scope), self.text)
            if node.op == "AND":
                if rcond is False:
                    return False
                return None if None in (lcond, rcond) else True
            if rcond is True:
                return True
            return None if None in (lcond, rcond) else False
        left = self.eval(node.left, scope)
        right = self.eval(node.right, scope)
        if node.op in ("=", "<>", "<", "<=", ">", ">="):
            return _compare(node.op, left, right, self.text)
        if left is None or right is None:
            return None
        if node.op == "+" and (isinstance(left, str) or isinstance(right, str)):
            if isinstance(left, str) and isinstance(right, str):
                return left + right
            raise RuleRefusedError(f"'+' between {left!r} and {right!r} in {self.text!r}")
        a, b = _number(left, self.text), _number(right, self.text)
        assert a is not None and b is not None
        try:
            if node.op == "+":
                return a + b
            if node.op == "-":
                return a - b
            if node.op == "*":
                return a * b
            if node.op == "/":
                return a / b
            return a % b
        except (DivisionByZero, InvalidOperation) as exc:
            raise RuleRefusedError(f"{a} {node.op} {b} in {self.text!r}") from exc

    # -- functions

    def table(self, node: Node) -> _TableRef:
        if isinstance(node, Col) and node.table is None:
            return _TableRef(node.name)
        if isinstance(node, Call) and node.name == "CHILD" and len(node.args) == 1:
            return self.table(node.args[0])
        raise UnsupportedSyntaxError(f"expected a table in {self.text!r}")

    def table_column(self, node: Node) -> tuple[str, str]:
        if isinstance(node, Col) and node.table is not None and node.table.upper() != "PARENT":
            return node.table, node.name
        if isinstance(node, Member):
            return self.table(node.base).name, node.name
        raise UnsupportedSyntaxError(f"expected Table.Column in {self.text!r}")

    def call(self, node: Call, scope: Scope) -> object:
        name, args = node.name, node.args
        handler = _SIMPLE.get(name)
        if handler is not None:
            arity, fn = handler
            if len(args) != arity:
                raise UnsupportedSyntaxError(f"{name} with {len(args)} arguments in {self.text!r}")
            return fn(self, [self.eval(a, scope) for a in args])
        if name == "IIF" and len(args) == 3:
            cond = truth(self.eval(args[0], scope), self.text)
            if cond is None:
                raise RuleRefusedError(f"IIF on a NULL condition in {self.text!r}")
            return self.eval(args[1] if cond else args[2], scope)
        if name == "ISNULL" and len(args) == 2:
            value = self.eval(args[0], scope)
            return self.eval(args[1], scope) if value is None else value
        if name == "EXISTS" and len(args) == 1:
            return bool(scope.table_rows(self.table(args[0]).name))
        if name in ("SUM", "SUMIF") and len(args) == (1 if name == "SUM" else 2):
            table_name, column = self.table_column(args[0])
            rows = scope.table_rows(table_name)
            if name == "SUMIF":
                rows = [r for r in rows if truth(self.eval(args[1], r), self.text)]
            values = [_number(_check(r.column(column), column), self.text) for r in rows]
            present = [v for v in values if v is not None]
            if not rows:
                raise RuleRefusedError(
                    f"{name} over no rows in {self.text!r}: Bravo's result unmeasured"
                )
            return sum(present, Decimal(0)) if present else None
        if name == "VLOOKUP" and len(args) == 3:
            looked = args[1]
            if not isinstance(looked, Col) or looked.table is not None:
                raise UnsupportedSyntaxError(f"VLOOKUP column in {self.text!r}")
            rows = scope.table_rows(self.table(args[0]).name)
            for row in rows:
                hit = truth(self.eval(args[2], _Aggregating(row, rows)), self.text)
                if hit:
                    return _check(row.column(looked.name), looked.name)
            return None
        if name == "MAX" and len(args) == 1 and isinstance(scope, _Aggregating):
            maxed = args[0]
            if not isinstance(maxed, Col) or maxed.table is not None:
                raise UnsupportedSyntaxError(f"MAX argument in {self.text!r}")
            values = [
                _number(_check(r.column(maxed.name), maxed.name), self.text) for r in scope.rows
            ]
            present = [v for v in values if v is not None]
            return max(present) if present else None
        if name == "DATEADD" and len(args) == 3:
            unit = args[0]
            if not (isinstance(unit, Col) and unit.table is None and unit.name.lower() == "day"):
                raise UnsupportedSyntaxError(f"DATEADD unit in {self.text!r}")
            days = _number(self.eval(args[1], scope), self.text)
            when = self.eval(args[2], scope)
            if days is None or when is None:
                return None
            if not isinstance(when, datetime) or days != days.to_integral_value():
                raise RuleRefusedError(f"DATEADD({days}, {when!r}) in {self.text!r}")
            return when + timedelta(days=int(days))
        if name in ("USER", "CURRENCY", "CONFIG") and len(args) == 1:
            return _check(scope.session(name, self.eval(args[0], scope)), f"{name}()")
        if name == "BRANCH" and len(args) == 1:
            return _check(scope.session(name, self.eval(args[0], scope)), f"{name}()")
        if name in ("GETDATE", "BRANCH", "LANGID") and not args:
            return _check(scope.session(name, None), f"{name}()")
        if name == "UPDATEDCOLUMN" and not args:
            return scope.updated_column()
        if name == "CHARINDEX":
            # 1-based-and-0 (SQL) or 0-based-and--1 (.NET)? The SO layout tests
            # its result with `>= 0`, which only one of the two makes useful.
            raise RuleRefusedError(f"CHARINDEX's semantics are unmeasured in {self.text!r}")
        raise UnsupportedSyntaxError(f"{name} with {len(args)} arguments in {self.text!r}")


class _Aggregating:
    """A row being scanned by VLOOKUP, with the table it belongs to (for MAX)."""

    def __init__(self, row: Scope, rows: Sequence[Scope]) -> None:
        self.row = row
        self.rows = rows

    def column(self, name: str) -> object:
        return self.row.column(name)

    def parent_column(self, name: str) -> object:
        return self.row.parent_column(name)

    def table_rows(self, table: str) -> Sequence[Scope]:
        return self.row.table_rows(table)

    def updated_column(self) -> str | None:
        return self.row.updated_column()

    def session(self, function: str, argument: object) -> object:
        return self.row.session(function, argument)


def _empty(ev: Evaluator, args: list[object]) -> object:
    return is_empty(args[0])


def _date(ev: Evaluator, args: list[object]) -> object:
    value = args[0]
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise RuleRefusedError(f"DATE({value!r}) in {ev.text!r}")
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def _convert(ev: Evaluator, args: list[object]) -> object:
    value, target = args
    if target != "String":
        raise UnsupportedSyntaxError(f"CONVERT to {target!r} in {ev.text!r}")
    if value is None:
        return None
    return _render(value, ev.text)


_SIMPLE: Mapping[str, tuple[int, Callable[[Evaluator, list[object]], object]]] = {
    "EMPTY": (1, _empty),
    "DATE": (1, _date),
    "CONVERT": (2, _convert),
}


def substitute(text: str, scope: Scope) -> str:
    """Replace each `{=expr}` with its value on the current row."""
    spans = _template_spans(text)
    if not spans:
        return text
    out: list[str] = []
    last = 0
    for start, end in spans:
        inner = text[start + 2 : end - 1]
        out.append(text[last:start])
        out.append(_render(Evaluator(inner, scope).run(), text))
        last = end
    out.append(text[last:])
    return "".join(out)


def evaluate(text: str, scope: Scope) -> object:
    """The value of `text` on `scope`; `RuleRefusedError` where it cannot be had."""
    return Evaluator(text, scope).run()


def condition(text: str | None, scope: Scope) -> bool:
    """Whether a rule runs: an absent condition is true, a NULL one is not.

    NULL reads as "not true" because that is ADO.NET's rule for an expression
    filter, and Bravo's syntax is ADO.NET's DataColumn expressions. The SO
    layout relies on it: `PriceIncludeTax=1` guards a tax rule on every line
    with no tax code, where the client does not fail. A validator's NULL is
    not a condition and stays undecided (`RuleRunner.check`).
    """
    if text is None or not text.strip():
        return True
    return truth(evaluate(text, scope), text) is True
