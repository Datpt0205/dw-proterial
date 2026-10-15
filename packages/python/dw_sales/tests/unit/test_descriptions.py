"""Reading an item description: what it states, and when it is not understood."""

from __future__ import annotations

from decimal import Decimal
from typing import get_args

import pytest
from pydantic import ValidationError

from dw_sales.adapters.mock.fixtures import DATA_DIR, read_records
from dw_sales.adapters.mock.generate_attachments import StatedAttributes as PrintedAttributes
from dw_sales.domain.catalog import Conductor, Item, ItemFamily, Shield
from dw_sales.domain.descriptions import (
    CONDUCTOR_WORDS,
    FAMILY_WORDS,
    SHIELD_WORDS,
    StatedAttributes,
    candidates,
    read_description,
)

pytestmark = pytest.mark.unit

ITEMS = read_records(DATA_DIR / "items.json", Item)


@pytest.mark.parametrize("item", ITEMS, ids=lambda item: item.prv_code)
def test_every_item_is_read_back_from_its_printed_description(item: Item) -> None:
    """The mock customers print descriptions with the generator's words; this
    reads them with the domain's. Two vocabularies, held together here: a word
    added to one and not the other fails this, not a mapping in production."""
    printed = PrintedAttributes.of_item(item)

    stated = read_description(printed.describe())

    assert stated is not None
    assert stated.model_dump() == printed.model_dump()
    assert candidates(stated, ITEMS) == (item,)


def test_a_partial_description_fits_every_item_it_does_not_contradict() -> None:
    # M05 line 1: no packaging, so the reel and the drum of one cable both fit.
    stated = read_description(
        "MULTI-CORE CABLE 2C 0.5mm2 STRANDED TINNED CU FOIL SHIELD BLACK SPEC SP-5201"
    )

    assert stated is not None
    assert [item.prv_code for item in candidates(stated, ITEMS)] == ["CB-2001", "CB-2002"]


def test_words_are_read_whatever_their_case_or_width() -> None:
    # Full-width digit and letter, as a Japanese input method types them.
    full_width_2c = chr(0xFF12) + chr(0xFF23)
    stated = read_description(f"multi-core cable {full_width_2c} 0.5MM2 braid shield")

    assert stated == StatedAttributes(
        family="multi_core_cable", cores=2, gauge="0.5mm2", shield="braid"
    )


@pytest.mark.parametrize(
    "text",
    [
        # One unknown word: matching on the rest would find every black wire.
        "HOOK-UP WIRE BLACK HALOGEN-FREE",
        # The same attribute twice: which one the customer means is a guess.
        "MULTI-CORE CABLE 2C 4C",
        "BLACK RED",
        # Half of a two-word attribute.
        "MULTI-CORE",
        "SPEC",
        # A value no item has: a customer's text, so not understood, never raised.
        "0C BLACK",
        "REEL 0M",
        "",
        "   ",
    ],
)
def test_a_description_with_anything_unread_is_not_understood(text: str) -> None:
    assert read_description(text) is None


def test_a_length_is_the_pack_length_and_compared_as_a_number() -> None:
    stated = read_description("REEL 300M")

    assert stated is not None
    assert stated.pack_length_m == Decimal(300)
    fitting = candidates(stated, ITEMS)
    assert "CB-2001" in {item.prv_code for item in fitting}
    assert all(i.pack_multiple == 300 and i.attributes.packaging == "reel" for i in fitting)


def test_stating_nothing_is_refused_by_the_model() -> None:
    """A description that states nothing would fit every item."""
    with pytest.raises(ValidationError):
        StatedAttributes()


def test_every_family_conductor_and_shield_has_a_printed_word() -> None:
    assert set(FAMILY_WORDS) == set(get_args(ItemFamily))
    assert set(CONDUCTOR_WORDS) == set(get_args(Conductor))
    assert set(SHIELD_WORDS) == set(get_args(Shield))


def _another_spelling(value: object) -> object:
    if isinstance(value, str):
        return value.lower() if value != value.lower() else value.upper()
    if isinstance(value, int):
        return value + 1
    raise AssertionError(f"no other spelling for {value!r}")


@pytest.mark.parametrize("field", ["spec_no", "family", "cores", "gauge"])
def test_the_picker_attributes_fit_by_exact_equality(field: str) -> None:
    """The candidate picker in apps/web (candidate-picker.tsx, `against`) marks
    spec, family, cores and gauge khớp/lệch with `===` beside what DW1 read.
    That is a copy of this rule, held to it here: if `fits` starts to forgive
    a spelling (case, a gauge written another way), this fails, and the picker
    must take the server's verdict instead of saying lệch where DW1 matched."""
    item = ITEMS[0]
    own = {
        "spec_no": item.attributes.spec_no,
        "family": item.family,
        "cores": item.attributes.cores,
        "gauge": item.attributes.gauge,
    }[field]
    other = (
        next(f for f in get_args(ItemFamily) if f != own)
        if field == "family"
        else _another_spelling(own)
    )

    assert StatedAttributes.model_validate({field: own}).fits(item)
    assert not StatedAttributes.model_validate({field: other}).fits(item)
