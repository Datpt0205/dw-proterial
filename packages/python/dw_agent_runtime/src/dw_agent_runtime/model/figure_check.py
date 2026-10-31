"""Every figure a model wrote is one its sources hold (sales' AI list, items
8 and 12; lifted here by docs/adr/0013 so every context checks prose alike).

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
from collections.abc import Collection
from typing import Final

# A number, a date or a code as it may be written: a run of digits, with the
# letters, separators and decimal marks that hold it together (`Q26-0104`,
# `0.712`, `31/12/2026`, `1,200`).
_FIGURE = re.compile(r"[A-Za-z]*\d[\w./,\-]*")
_PARTS = re.compile(r"[./,\-]")
# What an amount looks like in any of the customers' languages: a percent, a
# currency code or symbol. A mail to a customer no approval looked at carries
# none (sales items 11 and the customer reminder): a "5%" passes a figure check
# whenever a date holds a 5.
_AMOUNT: Final = re.compile(
    # `\uff05` is the full-width percent sign a Japanese mail may use.
    r"[%\uff05$¥€₫]|\b(?:USD|VND|JPY|EUR|SGD|THB|CNY|đồng)\b|円|ドル",
    re.IGNORECASE,
)


def names_amount(text: str) -> bool:
    """Whether ``text`` writes an amount of money or a percentage."""
    return _AMOUNT.search(text) is not None


def figures(text: str) -> set[str]:
    """Each figure in ``text``, its trailing punctuation dropped."""
    return {m.group(0).rstrip(".,-/") for m in _FIGURE.finditer(text)}


def _key(figure: str) -> str:
    return figure.lstrip("0") or "0" if figure.isdigit() else figure


def unsupported(written: str, sources: str, *, names: Collection[str] = ()) -> set[str]:
    """The figures ``written`` holds that ``sources`` do not. ``names`` hold a
    digit and are no figure (a context's Digital Workers, ``DW1``): the
    caller's, since which names a deployment has is not the platform's to say."""
    known = figures(sources)
    parts = {_key(p) for k in known for p in (k, *_PARTS.split(k)) if p}
    return {f for f in figures(written) - set(names) if f not in known and _key(f) not in parts}
