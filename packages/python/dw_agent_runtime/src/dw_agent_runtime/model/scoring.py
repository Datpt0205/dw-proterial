"""How sure a model was of each value it wrote, from its token probabilities.

dw_sales ADR 0015 (method: `docs/research/2026-11-16-less-human-review.md`
section 2.3a): a step's result may apply itself when its confidence clears a
threshold set on the tenant's labelled cases. The cheapest confidence is the
probability the model gave the tokens of the value it wrote, in the same call:
no extra call, and a server decoding against a JSON schema (Strata, measured
2026-11-16) returns each token's log-probability beside the answer.

`value_confidences` turns a call's tokens into one probability per JSON value,
keyed by the value's path (``lines.0.family``): the product of the
probabilities of the tokens the value's text lies in. A token that also holds
JSON punctuation counts with it; under a schema that punctuation is forced, so
its probability is about 1 and changes nothing.

The guarantee the threshold gives does not need these numbers to be well
calibrated (a weak score only lowers the share that applies itself), so this
module makes no claim that they are; it only reads them faithfully. A call
whose tokens are missing, or do not spell the answer, gives no confidences,
and nothing it produced applies itself.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class TokenLogprob:
    """One token the model wrote, and the natural log of its probability."""

    text: str
    logprob: float


@dataclass(frozen=True, slots=True)
class Scored[T]:
    """An answer, and how sure the model was of each of its values (by path),
    or None when the call gave no token probabilities."""

    answer: T
    confidences: Mapping[str, float] | None


class _UnparsedError(Exception):
    """The text is not one JSON object."""


_WHITESPACE: Final = " \t\r\n"
_LITERALS: Final = ("true", "false", "null")


def value_spans(text: str) -> dict[str, tuple[int, int]]:
    """Where each scalar value of the JSON object in ``text`` lies, by path:
    a string's characters between its quotes, any other value's literal. The
    object may be preceded or followed by other text (a fence), as the
    adapters accept it. Raises `ValueError` when there is no object."""
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object")
    spans: dict[str, tuple[int, int]] = {}
    try:
        _value(text, start, "", spans)
    except (_UnparsedError, IndexError) as exc:
        raise ValueError("not a JSON object") from exc
    return spans


def _skip(text: str, at: int) -> int:
    while at < len(text) and text[at] in _WHITESPACE:
        at += 1
    return at


def _string(text: str, at: int) -> int:
    """The index just past the closing quote of the string opening at ``at``."""
    if text[at] != '"':
        raise _UnparsedError
    at += 1
    while text[at] != '"':
        at += 2 if text[at] == "\\" else 1
    return at + 1


def _value(text: str, at: int, path: str, spans: dict[str, tuple[int, int]]) -> int:
    at = _skip(text, at)
    char = text[at]
    if char == "{":
        at = _skip(text, at + 1)
        if text[at] == "}":
            return at + 1
        while True:
            key_end = _string(text, _skip(text, at))
            key = text[_skip(text, at) + 1 : key_end - 1]
            at = _skip(text, key_end)
            if text[at] != ":":
                raise _UnparsedError
            at = _skip(text, _value(text, at + 1, f"{path}.{key}" if path else key, spans))
            if text[at] == "}":
                return at + 1
            if text[at] != ",":
                raise _UnparsedError
            at += 1
    if char == "[":
        at = _skip(text, at + 1)
        if text[at] == "]":
            return at + 1
        index = 0
        while True:
            at = _skip(text, _value(text, at, f"{path}.{index}" if path else str(index), spans))
            index += 1
            if text[at] == "]":
                return at + 1
            if text[at] != ",":
                raise _UnparsedError
            at += 1
    if char == '"':
        end = _string(text, at)
        spans[path] = (at + 1, end - 1)
        return end
    for literal in _LITERALS:
        if text.startswith(literal, at):
            spans[path] = (at, at + len(literal))
            return at + len(literal)
    end = at
    while end < len(text) and text[end] in "+-0123456789.eE":
        end += 1
    if end == at:
        raise _UnparsedError
    spans[path] = (at, end)
    return end


def value_confidences(tokens: Sequence[TokenLogprob]) -> dict[str, float]:
    """Each value's probability, by path (module docstring); empty when the
    tokens do not spell one JSON object. An empty string is scored by the
    tokens of its two quotes."""
    text = "".join(t.text for t in tokens)
    try:
        spans = value_spans(text)
    except ValueError:
        return {}
    bounds: list[tuple[int, int, float]] = []
    offset = 0
    for token in tokens:
        bounds.append((offset, offset + len(token.text), token.logprob))
        offset += len(token.text)
    confidences: dict[str, float] = {}
    for path, (start, end) in spans.items():
        low, high = (start - 1, end + 1) if start == end else (start, end)
        total = sum(lp for t_start, t_end, lp in bounds if t_start < high and t_end > low)
        confidences[path] = min(1.0, math.exp(total))
    return confidences
