"""What a PRV item name states, read from its spec string (ticket 36).

Bravo's item master (B06) holds none of the attributes a PO description is
matched on; it holds the item's name, "<kind> - <spec>", the spec written in
the wire trade's own shorthand::

    Hook up wire - UL1007 1X24AWG(11/0.16) LF WHITE P-30K
    Cabling - UL2464 3x17AWG(50/0.18TA) LF BK C200

which reads: the standard (UL style 1007), cores times gauge (one core of
24 AWG, or ``0.5SQ`` for a cross-section in mm²), the strands of each core
times their diameter in mm (11 of 0.16, a plating suffix such as ``TA`` after
it), then suffixes: lead-free (``LF``), a colour, a packing code. Code reads
these into `ItemAttributes`, so `descriptions.candidates` compares a real
item as it compares the mock's.

**Lenient by design, on our own names only.** A part this grammar does not
know (a packing code, a Design spec in brackets, a colour outside DW1's
words such as ``LIGHT BLUE``) is left unread, and the attribute it would give
stays None, which no stated value ever fits. So an unread part makes an item
a candidate for fewer lines, never for a wrong one. A customer's description
is not read here: the convert list, DW1's vocabulary
(`descriptions.read_description`) or a model reading it into the same
attributes (dw_sales ADR 0005) does that.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal
from typing import Final, get_args

from pydantic import BaseModel, ConfigDict, Field

from dw_sales.domain.catalog import Colour, Stranding

_FROZEN = ConfigDict(frozen=True, extra="forbid")

# "<kind> - <spec>": the spec is after the first spaced dash.
_KIND_SEPARATOR: Final = " - "
_STANDARD: Final = re.compile(r"\bUL(\d{3,5})(?!\d)")
# Cores times a size: ``1X24AWG``, ``3 x 17AWG``, ``24x0.3SQ``.
_CORES_AWG: Final = re.compile(r"(?<![\d.])(\d{1,3})\s*X\s*(\d{1,2})\s*AWG\b")
_CORES_SQ: Final = re.compile(r"(?<![\d.])(\d{1,3})\s*X\s*(\d{1,2}(?:\.\d{1,2})?)\s*SQ\b")
# A size alone: ``16AWG`` or ``AWG24`` (a single wire whose cores are not written).
_AWG_ALONE: Final = re.compile(r"(?<![\dX.])(\d{1,2})\s*AWG\b|\bAWG\s*(\d{1,2})\b")
_SQ_ALONE: Final = re.compile(r"(?<![\dX.])(\d{1,2}(?:\.\d{1,2})?)\s*SQ\b")
# Strands times diameter (a plating suffix such as ``TA`` may follow, not
# read): ``(50/0.18TA)``, ``7/0.16``.
_STRANDS: Final = re.compile(r"(?<![\d./])(\d{1,3})\s*/\s*(\d\.\d{1,3})(?![\d/])")
_WORD: Final = re.compile(r"[A-Z0-9][A-Z0-9./()-]*")
_LEAD_FREE: Final = "LF"
# DW1's colour words as names print them; GRAY is GREY spelled the other way.
_COLOURS: Final[dict[str, Colour]] = {c.upper(): c for c in get_args(Colour)} | {"GRAY": "grey"}


class NameAttributes(BaseModel):
    """What one name's spec string states; None where it does not say."""

    model_config = _FROZEN

    standard: str | None = None
    cores: int | None = Field(default=None, ge=1, le=100)
    gauge: str | None = None
    strands: int | None = Field(default=None, ge=1)
    strand_mm: Decimal | None = Field(default=None, gt=0)
    colour: Colour | None = None

    @property
    def stranding(self) -> Stranding | None:
        """One strand is a solid core; more are stranded."""
        if self.strands is None:
            return None
        return "single" if self.strands == 1 else "stranded"

    @property
    def stated(self) -> int:
        """How many attributes the matcher can compare were read."""
        return sum(
            value is not None
            for value in (self.standard, self.cores, self.gauge, self.stranding, self.colour)
        )


def _section(size: str) -> str | None:
    """A cross-section as DW1 spells one (``0.5mm2``), or None past its range."""
    whole, _, fraction = size.partition(".")
    if len(whole) > 2:
        return None
    return f"{whole}.{fraction or '0'}mm2"


def spec_of(name: str) -> str:
    """The spec string of a name: after its first spaced dash, else all of it."""
    _, separator, spec = name.partition(_KIND_SEPARATOR)
    return spec if separator else name


def read_name(name: str) -> NameAttributes:
    """The attributes ``name``'s spec string states (module docstring). Never
    raises: a name that states nothing reads as nothing."""
    spec = unicodedata.normalize("NFKC", spec_of(name)).upper()
    found: dict[str, object] = {}
    if standard := _STANDARD.search(spec):
        found["standard"] = f"UL{standard.group(1)}"
    if pair := _CORES_AWG.search(spec):
        found["cores"], found["gauge"] = int(pair.group(1)), f"AWG{int(pair.group(2))}"
    elif pair := _CORES_SQ.search(spec):
        found["cores"], found["gauge"] = int(pair.group(1)), _section(pair.group(2))
    elif alone := _AWG_ALONE.search(spec):
        found["gauge"] = f"AWG{int(alone.group(1) or alone.group(2))}"
    elif alone := _SQ_ALONE.search(spec):
        found["gauge"] = _section(alone.group(1))
    strands = _STRANDS.search(spec)
    if strands is not None and int(strands.group(1)) > 0 and Decimal(strands.group(2)) > 0:
        found["strands"] = int(strands.group(1))
        found["strand_mm"] = Decimal(strands.group(2))
    found["colour"] = _colour(_WORD.findall(spec))
    cores = found.get("cores")
    if isinstance(cores, int) and not 1 <= cores <= 100:
        del found["cores"]
    return NameAttributes.model_validate(found)


def _colour(words: list[str]) -> Colour | None:
    """The one colour word the spec prints, standing after a part of the
    grammar or a number, never after another word: "LIGHT BLUE" is not blue.
    Two colours (a twisted pair's) state none."""
    seen: set[Colour] = set()
    for index, word in enumerate(words):
        colour = _COLOURS.get(word)
        if colour is None:
            continue
        before = words[index - 1] if index else ""
        if before.isalpha() and before != _LEAD_FREE and before not in _COLOURS:
            return None
        seen.add(colour)
    return seen.pop() if len(seen) == 1 else None
