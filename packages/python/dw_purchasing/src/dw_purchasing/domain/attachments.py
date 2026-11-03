"""What DW2 read of one attachment, kept beside it when its mail was stored.

The worker's `purchasing_mail_drop` lane reads each attachment once, as it
stores the mail: scanned for malware first, then, when it is a document (an
Excel form, a PDF, a scanned page, a legacy `.xls`/`.doc` converted first),
its text taken in the reader sandbox, a page with no text layer read by OCR.
Nothing else ever parses the file: the API and every service read this.

**Not read** carries a code, never a word of the file: ``infected`` (the
scanner found something; the bytes are not kept), ``not_a_document`` (an
image, an archive, anything that is not a form), ``too_many`` (past the
documents one mail is read for), ``unreadable`` (a document the reader could
not open: encrypted, broken, a scan with no word OCR could read, too large,
or too slow).
"""

from __future__ import annotations

from typing import Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

# The most text kept of one page or sheet; a form's is far smaller.
MAX_PAGE_CHARS: Final = 50_000
# The most pages or sheets kept of one file (a request is a page or two).
MAX_PAGES: Final = 20

NotRead = Literal["infected", "not_a_document", "too_many", "unreadable"]


class AttachmentPage(BaseModel):
    """One page's or one sheet's text, and whether OCR read it."""

    model_config = _FROZEN

    text: str = Field(min_length=1, max_length=MAX_PAGE_CHARS)
    ocr: bool = False


class AttachmentReading(BaseModel):
    """The text of one attachment, or why there is none (module docstring)."""

    model_config = _FROZEN

    pages: tuple[AttachmentPage, ...] = Field(default=(), max_length=MAX_PAGES)
    not_read: NotRead | None = None

    @model_validator(mode="after")
    def _text_or_a_reason(self) -> Self:
        if bool(self.pages) == (self.not_read is not None):
            raise ValueError("an attachment has its text or a reason it has none, not both")
        return self

    @classmethod
    def refused(cls, reason: NotRead) -> AttachmentReading:
        return cls(not_read=reason)

    @property
    def read(self) -> bool:
        return self.not_read is None

    @property
    def scanned(self) -> bool:
        return any(page.ocr for page in self.pages)

    @property
    def text(self) -> str:
        """The pages one after another, as the model is shown them."""
        return "\n".join(page.text for page in self.pages)
