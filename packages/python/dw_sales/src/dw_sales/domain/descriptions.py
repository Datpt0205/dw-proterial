"""What a customer's item description states, read word by word.

A PO or RFQ line whose code is not in the convert list is matched to the
catalogue by the attributes its description states (requirements step 2:
shield, cores, gauge, stranding, conductor, colour, packaging, spec). The words
are the ones the customers' documents print, in the order documented in
`adapters/mock/README.md`, every part optional.

**A word outside the vocabulary means the description is not understood**, and
the line matches nothing. Ignoring it would match on the words that were
understood: "BLACK HALOGEN-FREE" would match every black cable, and one such
cable would look like a confident candidate. Not understood is an answer Sales
acts on; a near match is a guess.

The vocabulary is built from the `Literal` types in `catalog.py`, so a colour or
packaging added there is read here without a second list.

A near match never maps a line: `nearest` only names the codes a request to
Design shows beside a line no item fits (ticket 06), for Design to compare.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from decimal import Decimal
from typing import Self, get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from dw_sales.domain.catalog import (
    Colour,
    Conductor,
    Item,
    ItemFamily,
    Packaging,
    Shield,
    Stranding,
)

_FROZEN = ConfigDict(frozen=True, extra="forbid")

# The printed words for the values whose spelling is not the value itself.
FAMILY_WORDS: dict[ItemFamily, str] = {
    "hook_up_wire": "HOOK-UP WIRE",
    "multi_core_cable": "MULTI-CORE CABLE",
}
CONDUCTOR_WORDS: dict[Conductor, str] = {
    "bare_copper": "BARE CU",
    "tinned_copper": "TINNED CU",
}
SHIELD_WORDS: dict[Shield, str] = {
    "none": "NO SHIELD",
    "foil": "FOIL SHIELD",
    "braid": "BRAID SHIELD",
}

_CORES = re.compile(r"(\d{1,3})C")
_AWG = re.compile(r"AWG(\d{1,2})")
_SECTION = re.compile(r"(\d{1,2}\.\d{1,2})MM2")
_PACK_LENGTH = re.compile(r"(\d{1,6})M")
# A length per reel and a count of reels, as a PO's packing prints it
# ("610X12": twelve reels of 610 m). The length is the attribute; the count is
# the quantity's, which `pack_multiple` checks.
_REELS = re.compile(r"(\d{1,6})X\d{1,4}")
_SPEC_NO = re.compile(r"[A-Z0-9][A-Z0-9/-]{1,31}")
_STANDARD = re.compile(r"UL\d{3,5}")


class StatedAttributes(BaseModel):
    """The attributes one description states. Unset means not stated."""

    model_config = _FROZEN

    family: ItemFamily | None = None
    cores: int | None = Field(default=None, ge=1)
    gauge: str | None = None
    stranding: Stranding | None = None
    conductor: Conductor | None = None
    shield: Shield | None = None
    colour: Colour | None = None
    packaging: Packaging | None = None
    pack_length_m: Decimal | None = Field(default=None, gt=0)
    spec_no: str | None = None
    # The wire standard (``UL1007``): what a real item's name states first
    # (`item_names`).
    standard: str | None = None

    @model_validator(mode="after")
    def _states_something(self) -> Self:
        # A description that states nothing would fit every item.
        if all(value is None for _, value in self):
            raise ValueError("a description states at least one attribute")
        return self

    def fits(self, item: Item) -> bool:
        """Every attribute stated is the item's own."""
        known = _known(item)
        return all(value is None or known[name] == value for name, value in self)

    def held_by(self, item: Item) -> int:
        """How many of the attributes stated are the item's own: by the same
        equality `fits` asks of every one (ticket 06's nearest codes)."""
        known = _known(item)
        return sum(value is not None and known[name] == value for name, value in self)


def _known(item: Item) -> dict[str, object]:
    """The item's value of each attribute a description may state."""
    attributes = item.attributes
    return {
        "family": item.family,
        "cores": attributes.cores,
        "gauge": attributes.gauge,
        "stranding": attributes.stranding,
        "conductor": attributes.conductor,
        "shield": attributes.shield,
        "colour": attributes.colour,
        "packaging": attributes.packaging,
        "pack_length_m": item.pack_multiple,
        "spec_no": attributes.spec_no,
        "standard": attributes.standard,
    }


def read_description(text: str) -> StatedAttributes | None:
    """The attributes ``text`` states, or None when it is not understood.

    Not understood: a word outside the vocabulary, an attribute stated twice,
    a value no item can have (``0C``, ``0M``), or nothing stated at all. The
    text is the customer's, so none of these may raise: a line whose
    description cannot be read is unmapped, not a PO that cannot be processed.
    """
    words = unicodedata.normalize("NFKC", text).upper().split()
    stated: dict[str, object] = {}
    position = 0
    while position < len(words):
        found = _phrase(words, position) or _word(words[position])
        if found is None:
            return None
        name, value, length = found
        if name in stated:
            return None
        stated[name] = value
        position += length
    if not stated:
        return None
    try:
        return StatedAttributes.model_validate(stated)
    except ValidationError:
        return None


def candidates(stated: StatedAttributes, items: Iterable[Item]) -> tuple[Item, ...]:
    """Every item the stated attributes fit, by PRV code."""
    return tuple(sorted((i for i in items if stated.fits(i)), key=lambda i: i.prv_code))


def nearest(stated: StatedAttributes, items: Iterable[Item], limit: int) -> tuple[Item, ...]:
    """The ``limit`` items holding the most of the stated attributes, most
    first, then by PRV code; never one holding none of them (ticket 06).

    What a line no item fits is closest to, for the request to Design to
    create a code: `candidates` asks every attribute, this counts them. Only
    the items given, which the caller takes from its tenant's item master,
    so a code no item holds is never one of them."""
    held = ((stated.held_by(item), item) for item in items)
    ranked = sorted(
        ((count, item) for count, item in held if count), key=lambda x: (-x[0], x[1].prv_code)
    )
    return tuple(item for _, item in ranked[:limit])


def described(item: Item) -> str:
    """The item in words for a person: Bravo's name where the item master
    has one, else its attributes in DW1's own vocabulary, the words
    `read_description` reads back to the same attributes."""
    if item.name:
        return item.name
    a = item.attributes
    words = (
        FAMILY_WORDS[item.family] if item.family else None,
        f"{a.cores}C" if a.cores else None,
        a.gauge.upper() if a.gauge else None,
        a.stranding.upper() if a.stranding else None,
        CONDUCTOR_WORDS[a.conductor] if a.conductor else None,
        SHIELD_WORDS[a.shield] if a.shield else None,
        a.colour.upper() if a.colour else None,
        a.packaging.upper() if a.packaging else None,
        f"{item.pack_multiple.normalize():f}M" if item.pack_multiple else None,
        f"SPEC {a.spec_no}" if a.spec_no else None,
        a.standard,
    )
    return " ".join(word for word in words if word)


def _phrase(words: list[str], position: int) -> tuple[str, object, int] | None:
    """A two-word attribute: family, conductor, shield, or ``SPEC <no>``."""
    if position + 1 >= len(words):
        return None
    first, second = words[position], words[position + 1]
    pair = f"{first} {second}"
    for name, table in (
        ("family", FAMILY_WORDS),
        ("conductor", CONDUCTOR_WORDS),
        ("shield", SHIELD_WORDS),
    ):
        for value, printed in table.items():
            if pair == printed:
                return name, value, 2
    if first == "SPEC" and _SPEC_NO.fullmatch(second):
        return "spec_no", second, 2
    return None


def _word(word: str) -> tuple[str, object, int] | None:
    """A one-word attribute: cores, gauge, stranding, colour, packaging,
    length, standard."""
    for name, values in (
        ("stranding", get_args(Stranding)),
        ("colour", get_args(Colour)),
        ("packaging", get_args(Packaging)),
    ):
        for value in values:
            if word == value.upper():
                return name, value, 1
    if match := _CORES.fullmatch(word):
        return "cores", int(match.group(1)), 1
    if match := _AWG.fullmatch(word):
        return "gauge", f"AWG{match.group(1)}", 1
    if match := _SECTION.fullmatch(word):
        return "gauge", f"{match.group(1)}mm2", 1
    if match := _PACK_LENGTH.fullmatch(word) or _REELS.fullmatch(word):
        return "pack_length_m", Decimal(match.group(1)), 1
    if _STANDARD.fullmatch(word):
        return "standard", word, 1
    return None
