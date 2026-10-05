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
