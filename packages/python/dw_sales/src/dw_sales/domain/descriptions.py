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
_SPEC_NO = re.compile(r"[A-Z0-9][A-Z0-9/-]{1,31}")


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

    @model_validator(mode="after")
    def _states_something(self) -> Self:
        # A description that states nothing would fit every item.
        if all(value is None for _, value in self):
            raise ValueError("a description states at least one attribute")
        return self

    def fits(self, item: Item) -> bool:
        """Every attribute stated is the item's own."""
        attributes = item.attributes
        known = {
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
        }
        return all(value is None or known[name] == value for name, value in self)


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
    """A one-word attribute: cores, gauge, stranding, colour, packaging, length."""
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
    if match := _PACK_LENGTH.fullmatch(word):
        return "pack_length_m", Decimal(match.group(1)), 1
    return None
