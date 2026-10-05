"""`SourceAnchor`: one place in one file, never a reading of it."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest
from pydantic import ValidationError

from dw_sales.domain.anchors import PageBox, SourceAnchor

pytestmark = pytest.mark.unit

SHA = hashlib.sha256(b"M01 VLX-PO-2609-0118.xlsx").hexdigest()


def _anchor(**fields: Any) -> dict[str, Any]:
    return {"attachment_id": "M01-A1", "attachment_sha256": SHA} | fields


@pytest.mark.parametrize(
    ("cell_ref", "sheet", "cell"),
    [
        ("PO!B10", "PO", "B10"),
        ("Page 1!D10", "Page 1", "D10"),
        ("注文書!AB1234", "注文書", "AB1234"),
        # Excel allows "!" inside a sheet name; the cell is what follows the last one.
        ("Q3!Notes!C2", "Q3!Notes", "C2"),
    ],
)
def test_a_cell_anchor_names_its_sheet_and_cell(cell_ref: str, sheet: str, cell: str) -> None:
    anchor = SourceAnchor.model_validate(_anchor(cell_ref=cell_ref))

    assert (anchor.sheet, anchor.cell) == (sheet, cell)


def test_a_page_anchor_carries_its_boxes() -> None:
    anchor = SourceAnchor.model_validate(
        _anchor(page=1, boxes=[{"x": 0.07, "y": 0.31, "w": 0.6, "h": 0.02}])
    )

    assert anchor.page == 1
    assert anchor.boxes == (PageBox(x=0.07, y=0.31, w=0.6, h=0.02),)
    assert (anchor.sheet, anchor.cell) == (None, None)


def test_a_quote_anchor_and_several_kinds_at_once_are_accepted() -> None:
    quoted = SourceAnchor.model_validate(_anchor(quote="Tổng cộng: 43.500.000 VND"))
    both = SourceAnchor.model_validate(_anchor(cell_ref="PO!G14", quote="TOTAL"))

    assert quoted.quote == "Tổng cộng: 43.500.000 VND"
    assert (both.cell_ref, both.quote) == ("PO!G14", "TOTAL")


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {"page": 1},
        {"boxes": [{"x": 0, "y": 0, "w": 1, "h": 1}]},
        {"quote": "   "},
    ],
    ids=["nothing", "page_without_boxes", "boxes_without_page", "blank_quote"],
)
def test_an_anchor_that_points_nowhere_is_refused(fields: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        SourceAnchor.model_validate(_anchor(**fields))


@pytest.mark.parametrize(
    "cell_ref",
    ["B10", "PO!", "!B10", "PO!b10", "PO!B0", "PO:1!B10", "'PO'!B10", "PO!B10:C12"],
)
def test_a_cell_ref_in_another_spelling_is_refused(cell_ref: str) -> None:
    with pytest.raises(ValidationError, match="cell_ref is not Sheet!A1") as refused:
        SourceAnchor.model_validate(_anchor(cell_ref=cell_ref))

    assert cell_ref not in str(refused.value)


@pytest.mark.parametrize(
    "box",
    [
        {"x": 0.5, "y": 0, "w": 0.6, "h": 0.1},
        {"x": 0, "y": 0.95, "w": 0.1, "h": 0.1},
        {"x": -0.1, "y": 0, "w": 0.1, "h": 0.1},
        {"x": 0, "y": 0, "w": 0, "h": 0.1},
    ],
    ids=["past_the_right_edge", "past_the_bottom", "negative", "empty"],
)
def test_a_box_outside_the_page_is_refused(box: dict[str, float]) -> None:
    with pytest.raises(ValidationError):
        PageBox.model_validate(box)


@pytest.mark.parametrize(
    "fields",
    [{"attachment_sha256": "ABC"}, {"attachment_sha256": SHA.upper()}, {"attachment_id": "M01 A1"}],
)
def test_an_anchor_names_one_file_by_its_digest(fields: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        SourceAnchor.model_validate(_anchor(cell_ref="PO!B10") | fields)


def test_an_anchor_cannot_be_moved_once_made() -> None:
    anchor = SourceAnchor.model_validate(_anchor(cell_ref="PO!B10"))

    with pytest.raises(ValidationError):
        anchor.cell_ref = "PO!B11"
