"""Where a value was read: the one anchor type orders and quotes share.

Every value DW1 reads from a customer's file is shown to the person checking
it beside the original it came from (`.claude/rules/ui-quality.md`, ADR 0009).
A `SourceAnchor` says where that is, in terms the review screen draws on the
original itself: a cell on the sheet grid, boxes on the rendered page, or the
words quoted from it. Never a line of extracted text, which is the parser's
reading and not the customer's file.

The anchor carries the file's sha256. A file that changed, or was parsed again
into different bytes, no longer matches, so an anchor can never point into a
file other than the one its value was read from. dw_sales ADR 0002 records why
the type lives here until a second context needs it.
"""

from __future__ import annotations

import re
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dw_sales.domain.messages import AttachmentId, Sha256Hex

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

# Excel's own rule for a sheet name: 1-31 characters, none of []:*?/\ . An
# apostrophe may not open or close one, which is what lets ``Page 1!B10`` be
# read without Excel's quoting.
_SHEET = r"[^\[\]:*?/\\']|[^\[\]:*?/\\'][^\[\]:*?/\\]{0,29}[^\[\]:*?/\\']"
_CELL = r"[A-Z]{1,3}[1-9][0-9]{0,6}"
_CELL_REF = re.compile(rf"(?P<sheet>{_SHEET})!(?P<cell>{_CELL})")

Fraction = Annotated[float, Field(ge=0, le=1)]


class PageBox(BaseModel):
    """A rectangle on a rendered page, as fractions of the page.

    ``x`` and ``y`` are the top-left corner measured from the page's top-left,
    so the box draws the same at any zoom and on any renderer.
    """

    model_config = _FROZEN

    x: Fraction
    y: Fraction
    w: Annotated[float, Field(gt=0, le=1)]
    h: Annotated[float, Field(gt=0, le=1)]

    @model_validator(mode="after")
    def _inside_the_page(self) -> Self:
        if self.x + self.w > 1 or self.y + self.h > 1:
            raise ValueError("a page box ends outside the page")
        return self


class SourceAnchor(BaseModel):
    """The place in one attachment a value was read from.

    At least one of: ``cell_ref`` (``Sheet!B10``), ``page`` with its
    ``boxes``, or ``quote``, the words as the file prints them. More than one
    may be given when the reader knows more than one.
    """

    model_config = _FROZEN

    # The `Attachment` it points into, held to that attachment's own rules.
    attachment_id: AttachmentId
    attachment_sha256: Sha256Hex
    cell_ref: str | None = Field(default=None, max_length=64)
    page: int | None = Field(default=None, ge=1)
    boxes: tuple[PageBox, ...] = ()
    quote: str | None = Field(default=None, min_length=1, max_length=500, pattern=r"\S")

    @model_validator(mode="after")
    def _points_somewhere(self) -> Self:
        if self.cell_ref is not None and _CELL_REF.fullmatch(self.cell_ref) is None:
            raise ValueError("cell_ref is not Sheet!A1")
        if (self.page is None) != (not self.boxes):
            raise ValueError("page and boxes go together")
        if self.cell_ref is None and self.page is None and self.quote is None:
            raise ValueError("an anchor needs a cell_ref, a page with boxes, or a quote")
        return self

    @property
    def sheet(self) -> str | None:
        """The sheet ``cell_ref`` names, or None for an anchor without one."""
        return self._cell_ref_part("sheet")

    @property
    def cell(self) -> str | None:
        """The cell ``cell_ref`` names (``B10``), or None for an anchor without one."""
        return self._cell_ref_part("cell")

    def _cell_ref_part(self, part: str) -> str | None:
        if self.cell_ref is None:
            return None
        match = _CELL_REF.fullmatch(self.cell_ref)
        assert match is not None  # refused in the constructor otherwise
        return match.group(part)
