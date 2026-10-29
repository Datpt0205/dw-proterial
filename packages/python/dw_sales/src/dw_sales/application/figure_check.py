"""Every figure a model wrote is one its sources hold (the AI list, items 8
and 12).

A model's prose is shown only when each number, date and code in it appears
in what it was given: code cannot check that a sentence is right, but it can
check that no figure in it was invented. A figure counts when a source holds
it whole, or holds it as a whole part of a longer figure split at its
separators (``2026`` and ``9`` in ``2026-10-09``; leading zeros aside). Never
as any substring: ``15`` is not in ``2026-10-150``'s parts, and a ``9``
inside ``0.79`` is not a nine.
"""

from __future__ import annotations

import re
from typing import Final

# A number, a date or a code as it may be written: a run of digits, with the
# letters, separators and decimal marks that hold it together (`Q26-0104`,
# `0.712`, `31/12/2026`, `1,200`).
_FIGURE = re.compile(r"[A-Za-z]*\d[\w./,\-]*")
_PARTS = re.compile(r"[./,\-]")
# Names that hold a digit and are no figure: the Digital Workers' own.
_NAMES: Final = frozenset({"DW1", "DW2"})


def figures(text: str) -> set[str]:
    """Each figure in ``text``, its trailing punctuation dropped."""
    return {m.group(0).rstrip(".,-/") for m in _FIGURE.finditer(text)}


def _key(figure: str) -> str:
    return figure.lstrip("0") or "0" if figure.isdigit() else figure


def unsupported(written: str, sources: str) -> set[str]:
    """The figures ``written`` holds that ``sources`` do not."""
    known = figures(sources)
    parts = {_key(p) for k in known for p in (k, *_PARTS.split(k)) if p}
    return {f for f in figures(written) - _NAMES if f not in known and _key(f) not in parts}
