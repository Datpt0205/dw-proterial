"""Which line of an order some words name: one answer for every reader
(ticket 42 family 6; failure-modes #2).

A model copies the words a mail names a line with (a customer's change
request, ticket 27; a customer's mail handed off to PC, ticket 33; PC's own
mail Sales pastes, ticket 10), and code decides which line they name, here
and nowhere else. The order is given as its lines, each by its number and
the codes it is known by (`LineNames`): a DW1 case's line by the customer's
code and the PRV code its checks ran against (`names_of`), a sales order in
the ERP by its PRV code.

- **A code of the order written whole in the words** names its line
  (``Dòng 1 (mã VX-C4B22)``, ``品番CVG-0005``, ``cáp VX-C2F05``); a code
  only begun (``NV-CB4-22`` of ``NV-CB4-22-GY``) is no code of it.
- **Else the one number the words state** names the line of that number
  (``Dòng 2``, ``Line 2``, ``2行目``, ``#3``, ``No.2``): a number of its own,
  not part of a code (``AWG24``, ``KMH-21-0077``) or of a decimal or grouped
  number (``1.5``, ``1,200``). No word list says which words announce a line
  number: the model chose the words, code only reads the number in them.
- **Where both are there they must agree**: among lines sharing a code, the
  one whose number the words state; a code of one line beside the number of
  another line of the order names neither.

None when the words name no line, or more than one; the number may name no
line of the order, which the caller refuses. Never the nearest line.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from dw_sales.domain.orders import OrderCase, OrderLine
from dw_sales.domain.spans import FoldedText, word_char


@dataclass(frozen=True, slots=True)
class LineNames:
    """A line of an order by its number and every code it is known by."""

    line_no: int
    codes: frozenset[str]


def names_of(line: OrderLine) -> LineNames:
    """A case's line: the customer's code as entered and the PRV code its
    checks ran against (`LineMapping.checked_against`)."""
    codes = (line.effective.customer_item_code, line.mapping.checked_against)
    return LineNames(line.line_no, frozenset(code for code in codes if code))


def case_lines(case: OrderCase) -> tuple[LineNames, ...]:
    return tuple(names_of(line) for line in case.lines)


def _nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


_DIGITS: Final = re.compile(r"\d+")


def _numbers_in(span: str) -> list[int]:
    """The whole numbers ``span`` writes as tokens of their own: not part of
    a word or code (``AWG24``, ``CB-2007``, ``KMH-21-0077``), a decimal
    (``1.5``) or a grouped number (``1,200``)."""
    found: list[int] = []
    for match in _DIGITS.finditer(span):
        start, end = match.span()
        before = span[start - 1] if start else ""
        ahead = span[start - 2] if start > 1 else ""
        after = span[end] if end < len(span) else ""
        beyond = span[end + 1] if end + 1 < len(span) else ""
        if (
            (before and word_char(before))
            or (before in ".," and ahead.isdigit())
            or (before == "-" and ahead and word_char(ahead))
            or (after and word_char(after))
            or (after in ".," and beyond.isdigit())
            or (after == "-" and beyond and word_char(beyond))
        ):
            continue
        found.append(int(match.group()))
    return found


def named_line(lines: Iterable[LineNames], span: str) -> int | None:
    """The line ``span`` names among ``lines`` (module docstring)."""
    text = _nfkc(span)
    folded = FoldedText(text)
    known = tuple(lines)
    coded = {
        line.line_no
        for line in known
        if any(folded.occurrences(_nfkc(code), bounded=True) for code in line.codes)
    }
    numbers = _numbers_in(text)
    if coded:
        stated = set(numbers) & {line.line_no for line in known}
        found = coded & stated if stated else coded
        return next(iter(found)) if len(found) == 1 else None
    return numbers[0] if len(numbers) == 1 else None


__all__ = ["LineNames", "case_lines", "named_line", "names_of"]
