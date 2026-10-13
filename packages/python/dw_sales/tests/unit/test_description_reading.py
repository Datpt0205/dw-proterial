"""What code accepts of a model's reading of a description (ticket 28, ADR 0005).

One test per guard in `domain.description_reading`: each span found exactly
once, every number parsed by code from its span, every word covered, no
number hidden in a label, and a model-read line never exact. Each guard's
mutation (remove it, watch a test here go red) is recorded in ticket 28.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from dw_sales.adapters.mock.fixtures import DATA_DIR, read_records
from dw_sales.domain.anchors import SourceAnchor
from dw_sales.domain.catalog import Item
from dw_sales.domain.description_reading import (
    DescriptionReading,
    ModelDescriptionLine,
    Verified,
    parse_cores,
    parse_gauge,
    parse_pack_length,
    parse_spec_no,
    verify_reading,
)
from dw_sales.domain.order_checks import map_read_line
from dw_sales.domain.orders import (
    LineBasis,
    LineMapping,
    MappingStatus,
    OrderLine,
    PoLine,
    PoLineAnchors,
)

pytestmark = pytest.mark.unit

ITEMS = read_records(DATA_DIR / "items.json", Item)
JA = "2芯 AWG24 黒 撚線 305M リール"


def _line(**spans: Any) -> ModelDescriptionLine:
    """A model's answer for line 1: only what the test names, the rest null."""
    fields = {name: None for name in ModelDescriptionLine.model_fields if name != "line_no"}
    fields.update(spans)
    return ModelDescriptionLine(line_no=1, **fields)


def _ja() -> ModelDescriptionLine:
    return _line(
        cores_span="2芯",
        gauge_span="AWG24",
        colour="black",
        colour_span="黒",
        stranding="stranded",
        stranding_span="撚線",
        pack_length_span="305M",
        packaging="reel",
        packaging_span="リール",
    )


def _verified(description: str, line: ModelDescriptionLine) -> Verified:
    verdict = verify_reading(description, line)
    assert isinstance(verdict, Verified), verdict
    return verdict


def test_a_reading_that_holds_states_what_code_parsed_and_flags_the_labels() -> None:
    verified = _verified(JA, _ja())

    assert verified.stated.model_dump(exclude_none=True) == {
        "cores": 2,
        "gauge": "AWG24",
        "stranding": "stranded",
        "colour": "black",
        "packaging": "reel",
        "pack_length_m": Decimal(305),
    }
    by = {span.attribute: span.read_by for span in verified.spans}
    assert by == {
        "cores": "code",
        "gauge": "code",
        "colour": "model",
        "stranding": "model",
        "pack_length_m": "code",
        "packaging": "model",
    }
    # Each span is where the text is, in the normalised description.
    for span in verified.spans:
        assert JA[span.start : span.end] == span.span


# ------------------------------------------------- 1. located exactly once --


def test_a_span_the_description_does_not_hold_is_refused() -> None:
    line = _ja().model_copy(update={"gauge_span": "AWG26"})
    assert verify_reading(JA, line) == "span_not_found"


def test_a_span_found_twice_proves_nothing_and_is_refused() -> None:
    # "2" is in "2芯" and in "AWG24": a short token is no evidence.
    line = _ja().model_copy(update={"cores_span": "2"})
    assert verify_reading(JA, line) == "span_repeated"


def test_two_attributes_read_from_overlapping_text_are_refused() -> None:
    line = _ja().model_copy(update={"colour_span": "黒 撚線"})
    assert verify_reading(JA, line) == "spans_overlap"


def test_a_span_is_found_whatever_its_case_and_width() -> None:
    # NFKC folds the full-width digits; case folding lets `blk` find `BLK`.
    description = "２芯 AWG２４ BLK"  # noqa: RUF001 (full-width on purpose)
    line = _line(cores_span="2芯", gauge_span="awg24", colour="black", colour_span="blk")
    verified = _verified(description, line)
    assert verified.stated.cores == 2 and verified.stated.gauge == "AWG24"


# ----------------------------------------- 2. every number parsed by code --


@pytest.mark.parametrize(
    ("parse", "span", "value"),
    [
        (parse_cores, "2芯", "2"),
        (parse_cores, "4 lõi", "4"),
        (parse_cores, "6C", "6"),
        (parse_cores, "2x", "2"),
        (parse_cores, "0C", None),
        # A bare number is no core count: the unit says which attribute it is.
        (parse_cores, "2", None),
        (parse_gauge, "AWG24", "AWG24"),
        (parse_gauge, "24 AWG", "AWG24"),
        (parse_gauge, "0,5mm2", "0.5mm2"),
        (parse_gauge, "0.50 sq", "0.5mm2"),
        (parse_gauge, "1.25MM2", "1.25mm2"),
        (parse_gauge, "AWG", None),
        (parse_pack_length, "305M", "305"),
        (parse_pack_length, "1000 mét", "1000"),
        (parse_pack_length, "500メートル", "500"),
        (parse_pack_length, "1 KM", None),
        (parse_pack_length, "100 FT", None),
        (parse_pack_length, "305", None),
        (parse_spec_no, "SPEC SP-5201", "SP-5201"),
        (parse_spec_no, "sp-1124", "SP-1124"),
        (parse_spec_no, "SPEC", None),
    ],
)
def test_each_number_is_parsed_from_its_span(parse: Any, span: str, value: str | None) -> None:
    assert parse(span) == value


def test_a_span_that_does_not_parse_is_refused_whatever_the_model_meant() -> None:
    description = "HOOK-UP WIRE AWG24 BLACK 1 KM"
    line = _line(
        family="hook_up_wire",
        family_span="HOOK-UP WIRE",
        gauge_span="AWG24",
        colour="black",
        colour_span="BLACK",
        pack_length_span="1 KM",
    )
    # Read as metres, "1 KM" would be a 1 m pack: refused instead.
    assert verify_reading(description, line) == "value_unparsed"


def test_full_width_japanese_digits_are_parsed_by_code() -> None:
    description = "３芯 ０．７５ｍｍ２ 灰色 ３００ｍ"  # noqa: RUF001 (full-width on purpose)
    line = _line(
        cores_span="3芯",
        gauge_span="0.75mm2",
        colour="grey",
        colour_span="灰色",
        pack_length_span="300m",
    )
    stated = _verified(description, line).stated
    assert (stated.cores, stated.gauge, stated.pack_length_m) == (3, "0.75mm2", Decimal(300))


# --------------------------------------------- 3. every word is covered --


def test_a_word_no_span_covers_leaves_the_line_unmapped() -> None:
    # "PVC" is in no vocabulary. Reading the rest would match every black
    # AWG24 wire, and one of them would look like a confident candidate.
    description = "AWG24 PVC BLACK"
    line = _line(gauge_span="AWG24", colour="black", colour_span="BLACK")
    assert verify_reading(description, line) == "text_uncovered"


def test_punctuation_and_spaces_need_no_span() -> None:
    description = "AWG24, (BLACK) / REEL."
    line = _line(
        gauge_span="AWG24",
        colour="black",
        colour_span="BLACK",
        packaging="reel",
        packaging_span="REEL",
    )
    assert isinstance(verify_reading(description, line), Verified)


# ------------------------------------------ 4. no number inside a label --


def test_a_label_span_that_holds_a_number_is_refused() -> None:
    # Stretching the colour over "3C" would hide a core count from code.
    description = "AWG22 BLACK 3C"
    line = _line(gauge_span="AWG22", colour="black", colour_span="BLACK 3C")
    assert verify_reading(description, line) == "digit_in_label"


# ------------------------------------------------- the answer as a whole --


def test_no_attribute_at_all_is_missing_evidence() -> None:
    assert verify_reading("Hàng như lần trước", _line()) == "no_attribute"


def test_a_line_the_answer_leaves_out_is_not_understood() -> None:
    assert verify_reading(JA, None) == "line_missing"


def test_a_label_without_its_text_is_dropped_and_coverage_decides() -> None:
    # The colour's text is left out, so "黒" is a word no span covers.
    line = _ja().model_copy(update={"colour_span": None})
    assert verify_reading(JA, line) == "text_uncovered"


def test_a_label_the_words_do_not_state_is_not_taken() -> None:
    """Measured on the local model: a conductor "read" from a description
    that names none. With no text it is a guess, so it narrows nothing."""
    line = _line(gauge_span="AWG24", conductor="bare_copper", colour="black", colour_span="BLK")
    stated = _verified("AWG24 BLK", line).stated
    assert stated.conductor is None
    assert (stated.gauge, stated.colour) == ("AWG24", "black")


# ---------------------------- 5. a mislabel passes, flagged, never exact --


def _read(verified: Verified) -> DescriptionReading:
    return DescriptionReading(
        prompt="sales.description_attributes@1.0.0",
        model_profile="onprem",
        route="structured_extraction",
        outcome="read",
        spans=verified.spans,
    )


def test_a_mislabelled_colour_passes_the_checks_and_is_flagged_as_the_models() -> None:
    """`BLK` read as red: no check can tell, so it is marked as the model's
    judgement and the PRV code it narrows to stays a candidate to confirm."""
    description = "HOOK-UP WIRE AWG24 TINNED CU BLK REEL 610M"
    line = _line(
        family="hook_up_wire",
        family_span="HOOK-UP WIRE",
        gauge_span="AWG24",
        conductor="tinned_copper",
        conductor_span="TINNED CU",
        colour="red",
        colour_span="BLK",
        packaging="reel",
        packaging_span="REEL",
        pack_length_span="610M",
    )
    verified = _verified(description, line)
    reading = _read(verified)
    assert "colour" in reading.model_read

    mapped = map_read_line(verified, reading, ITEMS)
    # The wrong item, as a candidate: Sales sees "red" beside "BLK".
    assert (mapped.mapping.status, mapped.mapping.candidates) == (
        MappingStatus.CANDIDATE,
        ("HW-1002",),
    )


def test_a_model_read_line_can_never_be_exact() -> None:
    verified = _verified(JA, _ja())
    basis = LineBasis(checks_run=("read", "mapping"), description_reading=_read(verified))
    exact = LineMapping(status=MappingStatus.EXACT, prv_code="HW-1001")
    po_line = _po_line()

    with pytest.raises(ValueError, match="never exact"):
        OrderLine(po_line=po_line, mapping=exact, basis=basis)


def _po_line() -> PoLine:
    anchor = SourceAnchor(attachment_id="A1", attachment_sha256="b" * 64, cell_ref="PO!B10")
    return PoLine(
        line_no=1,
        customer_item_code="KMH-21-0300",
        description=JA,
        quantity=Decimal(3050),
        uom="m",
        unit_price=Decimal("0.0510"),
        amount=Decimal("155.55"),
        requested_date=date(2026, 12, 4),
        anchors=PoLineAnchors(**dict.fromkeys(PoLineAnchors.model_fields, anchor)),
    )
