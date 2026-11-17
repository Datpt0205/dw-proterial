"""The revision a PO file's name suggests (ticket 22): a hint, never a decision.

Some customers mark a revised PO only in the file's name: ``PO123-R1.xlsx``
after ``PO123.xlsx``, or ``R``, ``-2``, ``-RE11``, ``RV`` (Box B10's
correction thread, 11-14). DW1 reads that suffix and shows it beside the PO
number, the printed revision and the line comparison, which still decide
whether the file is a revision (`order_checks.check_history`, "PO sửa"). A
file named ``-R1`` that prints revision 0 and the same lines is still a
duplicate; one with no suffix that prints revision 1 is still a revision.

**The rule, small on purpose.** The suffix is read only from what follows
the PO number in the file's name (its last occurrence, compared without case
or spaces), so a name that does not carry the PO number suggests nothing,
and a word that happens to end in ``R`` ("ORDER") is never read as one.
After separators (``-``, ``_``, ``.``, space), the rest must be one of:

- a revision mark, then optionally separators and 1-3 digits (``R1``,
  ``-RE11``, ``_rev 2``, ``RV``);
- 1-2 digits alone (``-2``), so a date or another long number is not one.

Anything else after the PO number (``-signed``, ``(copy)``) suggests nothing.

**The marks are the tenant's** (ticket 42 family 6): which letters a
company's customers write for "revised" is a fact about those customers, not
language for a model to read, so it is a list in the order rules
(`OrderRules.revision_marks`), approved like any rule, and `REVISION_MARKS`
(today's four) where a version does not say. The rule above stays code: a
mark is only ever letters (`is_revision_mark`), read only after the PO
number, and the hint still decides nothing.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from functools import cache
from pathlib import PurePosixPath
from typing import Final

# The marks read where the tenant's order rules name none of their own.
REVISION_MARKS: Final = ("R", "RV", "RE", "REV")
# A mark is 1-5 capital letters (`PoDocument.name_revision` holds 8: a mark
# and its 1-3 digits).
_MARK: Final = re.compile(r"^[A-Z]{1,5}$")


def is_revision_mark(text: str) -> bool:
    """Whether ``text`` may be a revision mark: 1-5 capital ASCII letters."""
    return _MARK.fullmatch(text) is not None


@cache
def _suffix(marks: tuple[str, ...]) -> re.Pattern[str]:
    """What may follow the PO number, for ``marks`` (module docstring); the
    longest mark tried first, so ``REV2`` is never ``RE`` and ``V2``."""
    if not all(is_revision_mark(mark) for mark in marks):
        raise ValueError("a revision mark is 1-5 capital letters")
    alternatives = "|".join(sorted(marks, key=len, reverse=True))
    marked = rf"(?P<mark>{alternatives})[\s_.\-]*(?P<number>\d{{1,3}})?|" if marks else ""
    return re.compile(rf"[\s_.\-]*(?:{marked}(?P<bare>\d{{1,2}}))", re.IGNORECASE)


def _squeezed(text: str) -> str:
    return "".join(char.lower() for char in text if not char.isspace())


def name_revision(file_name: str, po_no: str, marks: Sequence[str] = REVISION_MARKS) -> str | None:
    """The revision ``file_name`` suggests after ``po_no`` with ``marks``
    (module docstring), upper-cased without separators (``R1``, ``RE11``,
    ``2``); None when the name suggests none."""
    stem = PurePosixPath(file_name).stem
    wanted = _squeezed(po_no)
    if not wanted:
        return None
    # Where the PO number ends in the stem, compared without case or spaces.
    squeezed, ends = "", []
    for index, char in enumerate(stem):
        if char.isspace():
            continue
        lowered = char.lower()
        squeezed += lowered
        ends.extend([index + 1] * len(lowered))
    at = squeezed.rfind(wanted)
    if at < 0:
        return None
    rest = stem[ends[at + len(wanted) - 1] :]
    match = _suffix(tuple(marks)).fullmatch(rest)
    if match is None or not rest.strip(" _.-"):
        return None
    if match.group("bare") is not None:
        return match.group("bare")
    return (match.group("mark") + (match.group("number") or "")).upper()
