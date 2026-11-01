"""A rule changed in words: what a model's answer may change, decided by code
(dw_sales ADR 0006 decision 3, where it was built; lifted by ADR 0013/0014).

A person who may propose a version of a key types what they want changed
("nhắc khách sau 3 ngày thôi"; "hạn mức bậc 1 lên 50 triệu"). The model
answers with **changes**, each a path of the document in force and the value
it should hold; this module decides whether the draft exists, whichever
context asks:

- every path is one that document already has, under the part the person
  asked about (``focus``), and the value has the type the field holds now;
- in a key whose texts are the company's copy (mails, sheets, hand-offs) a
  changed text keeps every ``${value}`` it had and names no other, so a fact
  the draft printed is still printed by code and none is made up; and it
  holds no digit that neither the text it replaces nor the person's words
  hold, so a number is never the model's;
- the whole document, changed, is then validated by the key's schema, as any
  proposal is.

What passes is a **draft**: the person reads the diff and sends it through
the one door every version takes (`rule_versions.RuleVersionEngine.propose`).
The model proposes; it never applies. The prompt that asks for the changes,
and the queue that carries a request to the worker, are each context's own
(ADR 0014).
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

MAX_REQUEST_CHARS: Final = 2000
MAX_CHANGES: Final = 20

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
_PATH = r"^[A-Za-z_][A-Za-z0-9_]*(\.([A-Za-z0-9_]+))*$"
_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_DIGITS = re.compile(r"\d+")

type Scalar = str | int | float | bool | None
_Value = Scalar | list[str]


class ModelRuleChange(BaseModel):
    """One change the model proposes: where, and what it should hold."""

    model_config = _FROZEN

    path: Annotated[str, Field(pattern=_PATH, max_length=200)]
    value: _Value


class ModelRuleChanges(BaseModel):
    """The model's whole answer. ``understood`` False: it could not tell what
    to change, and nothing is drafted."""

    model_config = _FROZEN

    understood: bool
    changes: tuple[ModelRuleChange, ...] = Field(default=(), max_length=MAX_CHANGES)


WordsProblemCode = Literal[
    "nothing_understood",
    "path_unknown",
    "type_changed",
    "placeholder_changed",
    "digit_invented",
    "document_invalid",
]


class WordsProblem(BaseModel):
    """Why a change was refused: a code and the path, never the value."""

    model_config = _FROZEN

    code: WordsProblemCode
    path: str | None = Field(default=None, max_length=200)

    def __str__(self) -> str:
        return self.code if self.path is None else f"{self.code}:{self.path}"


@dataclass(frozen=True, slots=True)
class WordsApplied:
    document: dict[str, Any]
    changed: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WordsRefused:
    problems: tuple[WordsProblem, ...]


def focus_of(base: Mapping[str, Any], focus: str | None) -> Any:
    """The part of the document a request is about: the whole of it, or the
    subtree at ``focus``; a KeyError for a focus the document does not have."""
    node: Any = base
    for part in () if focus is None else focus.split("."):
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def apply_changes(
    schema: type[BaseModel],
    base: Mapping[str, Any],
    answer: ModelRuleChanges,
    *,
    request: str,
    focus: str | None = None,
    copy_text: bool = False,
) -> WordsApplied | WordsRefused:
    """``base`` with the model's changes made, once each one and the whole
    document pass (module docstring); every refusal named otherwise.
    ``copy_text``: the key's texts are the company's copy (what a draft
    prints), so a changed text keeps its placeholders and invents no digit."""
    if not answer.understood or not answer.changes:
        return WordsRefused((WordsProblem(code="nothing_understood"),))
    document = copy.deepcopy(dict(base))
    problems: list[WordsProblem] = []
    changed: list[str] = []
    for change in answer.changes:
        path = _under(change.path, focus)
        found = _parent(document, path)
        if found is None:
            problems.append(WordsProblem(code="path_unknown", path=path))
            continue
        parent, leaf = found
        old = parent[leaf]
        new = _typed(old, change.value)
        if new is _REFUSED:
            problems.append(WordsProblem(code="type_changed", path=path))
            continue
        if copy_text and isinstance(old, str) and isinstance(new, str):
            problem = _copy_problem(old, new, request, path)
            if problem is not None:
                problems.append(problem)
                continue
        parent[leaf] = new
        changed.append(path)
    if problems:
        return WordsRefused(tuple(problems))
    try:
        schema.model_validate(document)
    except ValidationError as invalid:
        return WordsRefused(
            tuple(
                WordsProblem(code="document_invalid", path=".".join(str(p) for p in e["loc"]))
                for e in invalid.errors()[:10]
            )
        )
    return WordsApplied(document, tuple(changed))


def _under(path: str, focus: str | None) -> str:
    """``path`` under the part asked about: a path relative to it, or one
    that repeats it. Anything else lands under it too, where the document
    has no such leaf, so it is refused as unknown, never written elsewhere."""
    if focus is None or path == focus or path.startswith(f"{focus}."):
        return path
    return f"{focus}.{path}"


def placeholders(text: str) -> frozenset[str]:
    return frozenset(_PLACEHOLDER.findall(text))


def _copy_problem(old: str, new: str, request: str, path: str) -> WordsProblem | None:
    if placeholders(new) != placeholders(old):
        return WordsProblem(code="placeholder_changed", path=path)
    allowed = set(_DIGITS.findall(_PLACEHOLDER.sub("", old))) | set(_DIGITS.findall(request))
    if set(_DIGITS.findall(_PLACEHOLDER.sub("", new))) - allowed:
        return WordsProblem(code="digit_invented", path=path)
    return None


def _parent(document: dict[str, Any], path: str) -> tuple[Any, Any] | None:
    """The container holding ``path``'s leaf and the leaf's key, or None when
    the document has no such leaf (a path is never created)."""
    parts = path.split(".")
    node: Any = document
    for part in parts[:-1]:
        node = _child(node, part)
        if node is None:
            return None
    last = parts[-1]
    if isinstance(node, dict) and last in node:
        return node, last
    if isinstance(node, list) and last.isdigit() and int(last) < len(node):
        return node, int(last)
    return None


def _child(node: Any, part: str) -> Any:
    if isinstance(node, dict):
        return node.get(part)
    if isinstance(node, list) and part.isdigit() and int(part) < len(node):
        return node[int(part)]
    return None


class _Refused:
    pass


_REFUSED: Final = _Refused()


def _typed(old: Any, value: Any) -> Any:
    """``value`` as the type the field holds now, or `_REFUSED`: a text stays
    a text (a number written as text, as decimals are, takes a number), a
    flag a flag, a number a number, a list of texts a list of texts."""
    if isinstance(old, bool):
        return value if isinstance(value, bool) else _REFUSED
    if isinstance(old, int):
        return value if isinstance(value, int) and not isinstance(value, bool) else _REFUSED
    if isinstance(old, float):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        return _REFUSED
    if isinstance(old, str):
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool) and _decimal(old):
            return str(value)
        return _REFUSED
    if isinstance(old, list) and all(isinstance(v, str) for v in old):
        if isinstance(value, list) and all(isinstance(v, str) for v in value):
            return list(value)
        return _REFUSED
    if old is None:
        return value if isinstance(value, (str, int, float, bool)) else _REFUSED
    return _REFUSED


def _decimal(text: str) -> bool:
    try:
        Decimal(text)
    except InvalidOperation:
        return False
    return True


def leaf_paths(node: Any, prefix: str = "", limit: int = 400) -> Sequence[str]:
    """Every leaf path under ``node``, for the prompt: what may be changed."""
    found: list[str] = []

    def walk(value: Any, at: str) -> None:
        if len(found) >= limit:
            return
        if isinstance(value, dict):
            for k, v in value.items():
                walk(v, f"{at}.{k}" if at else str(k))
        elif isinstance(value, list) and value and not all(isinstance(v, str) for v in value):
            for i, v in enumerate(value):
                walk(v, f"{at}.{i}")
        else:
            found.append(at)

    walk(node, prefix)
    return found
