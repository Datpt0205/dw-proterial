"""Finding a span a model copied from a customer's text: one rule for every step.

dw_sales ADR 0005: a model gives span text, and code locates it in the text
it was read from before anything of it counts. Each step that reads through a
model (item descriptions, a request for quotation, the intent of a message)
locates its spans here, so "the span is there, exactly once" means the same
thing in all of them.

The text is NFKC-normalised by the caller and case folded here, with each
folded character's position in the unfolded text kept (folding can lengthen a
character: ``ß`` is ``ss``), so a located span is reported in the caller's
own offsets.

**Bounded** location also refuses an occurrence that is part of a longer
token: ``24`` inside ``AWG24``, ``200`` inside ``1,200``, ``m`` inside
``mm``. That is the field confusion a quantity or a date read from a line is
most exposed to, and it costs nothing where the span really is a token. A
number may be followed by its unit (``1200m``); a letter may not be followed
by a digit of the same token. Wide characters (CJK, kana) are not word
characters, so ``数量1200m`` holds ``1200``.
"""

from __future__ import annotations

import unicodedata
from typing import Literal

NotLocated = Literal["span_not_found", "span_repeated"]


class FoldedText:
    """``original`` case folded for finding spans, with positions mapped back."""

    def __init__(self, original: str) -> None:
        self.original = original
        folded: list[str] = []
        self._origin: list[int] = []
        for index, char in enumerate(original):
            for piece in char.casefold():
                folded.append(piece)
                self._origin.append(index)
        self.folded = "".join(folded)

    def locate(
        self, span: str, *, bounded: bool = False, within: tuple[int, int] | None = None
    ) -> tuple[int, int] | NotLocated:
        """Where ``span`` is in the original, when it is there exactly once.

        Overlapping occurrences count (``22`` is twice in ``222``). ``within``
        limits the search to a range of the original; ``bounded`` counts only
        occurrences that are whole tokens (module docstring).
        """
        found = self.occurrences(span, bounded=bounded, within=within)
        if not found:
            return "span_not_found"
        if len(found) > 1:
            return "span_repeated"
        return found[0]

    def occurrences(
        self, span: str, *, bounded: bool = False, within: tuple[int, int] | None = None
    ) -> list[tuple[int, int]]:
        """Every place ``span`` is, in original offsets."""
        wanted = span.casefold().strip()
        if not wanted:
            return []
        found: list[tuple[int, int]] = []
        at = self.folded.find(wanted)
        while at >= 0:
            start = self._origin[at]
            end = self._origin[at + len(wanted) - 1] + 1
            inside = within is None or (within[0] <= start and end <= within[1])
            if inside and (not bounded or self._is_token(start, end)):
                found.append((start, end))
            at = self.folded.find(wanted, at + 1)
        return found

    def _is_token(self, start: int, end: int) -> bool:
        text = self.original
        before = text[start - 1] if start > 0 else ""
        first, last = text[start], text[end - 1]
        after = text[end] if end < len(text) else ""
        return not _joined(text, start - 1, before, first) and not _joined(
            text, end - 1, last, after
        )


def _word(char: str) -> bool:
    return char.isalnum() and unicodedata.east_asian_width(char) not in ("W", "F")


def _joined(text: str, at: int, left: str, right: str) -> bool:
    """Whether ``left`` (at ``at``) and ``right`` belong to one token."""
    if not left or not right:
        return False
    if left.isdigit() and right.isdigit():
        return True
    # A separator between digits is inside a number: `1,200`, `0.5`.
    if left in ".," and right.isdigit():
        return at > 0 and text[at - 1].isdigit()
    if right in ".," and left.isdigit():
        return at + 2 < len(text) and text[at + 2].isdigit()
    # A letter run, or a letter run into its digits (`AWG24`); a number may be
    # followed by its unit (`1200m`).
    return _word(left) and _word(right) and not (left.isdigit() and not right.isdigit())
