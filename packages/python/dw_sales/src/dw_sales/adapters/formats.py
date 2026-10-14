"""What a file is by its bytes, and whether it is what its name says.

The type is sniffed from the first bytes and the container's own table of
contents, never from the file name or the media type the sender declared: both
are the sender's claim.

**A file that is not what its name says is refused** before any reader opens
it (`refusal`, ticket 25): a ``.xlsx`` that is no workbook, a ``.pdf`` that is
no PDF (a renamed program among them), and an encrypted Office file, which no
reader can open and whose name says nothing of that. A name that claims no
document type (an image, a signature) is not checked: it is sniffed, as
before.

This module stays in every process that holds an attachment, the API among
them, while every parser of a file's content runs in the reader sandbox
(ticket 25, `dw_sales.adapters.reader_client`). What it does to a file of the
sender's choosing is bounded on purpose: it compares magic numbers, and for a
zip it reads the central directory's names (`zipfile.ZipFile.namelist`), which
decompresses nothing. Stdlib only, so the import-linter contract that keeps the
parsers out of the API can name every module that does more.
"""

from __future__ import annotations

import io
import zipfile
from typing import Final

from dw_sales.application.order_ports import FileType

_PDF: Final = b"%PDF-"
_ZIP: Final = b"PK\x03\x04"
# An OLE compound file: a legacy .xls/.doc, or an encrypted OOXML workbook.
_OLE: Final = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_IMAGES: Final = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"II*\x00", b"MM\x00*", b"GIF8")
_WORKBOOK: Final = "xl/workbook.xml"
# An encrypted OOXML file is an OLE compound file holding this stream.
_ENCRYPTED: Final = "EncryptedPackage".encode("utf-16-le")
# The streams that make an OLE compound file a legacy workbook or Word file
# (ticket 27): Excel 97-2003's `Workbook` (`Book` before it), Word's
# `WordDocument`.
_LEGACY: Final[tuple[tuple[str, FileType], ...]] = (
    ("Workbook", "xls"),
    ("Book", "xls"),
    ("WordDocument", "doc"),
)
# A compound file's directory entry: 128 bytes, the name first (UTF-16LE,
# NUL-terminated, at most 64 bytes), its length in bytes at offset 64.
_ENTRY: Final = 128
_NAME_LENGTH_AT: Final = 64
# What a name claims: the container its bytes must be.
_CLAIMS: Final = {
    ".pdf": "pdf",
    ".xlsx": "ooxml",
    ".xlsm": "ooxml",
    ".docx": "ooxml",
    ".pptx": "ooxml",
    ".xls": "ole",
    ".doc": "ole",
    ".ppt": "ole",
}


def refusal(name: str, data: bytes) -> str | None:
    """Why a file is refused before anything reads it, or None (module
    docstring). The reason names the claim and what the bytes are, never a
    byte of the file."""
    if data.startswith(_OLE) and _ENCRYPTED in data:
        return "an encrypted Office file: a password-protected file is not read"
    extension = name[name.rfind(".") :].casefold() if "." in name else ""
    claimed = _CLAIMS.get(extension)
    if claimed is None:
        return None
    is_claimed = {
        "pdf": data.startswith(_PDF),
        "ooxml": data.startswith(_ZIP),
        "ole": data.startswith(_OLE),
    }[claimed]
    if is_claimed and extension in (".xlsx", ".xlsm") and sniff(data) != "xlsx":
        is_claimed = False
    return None if is_claimed else f"named {extension} but its bytes are not one"


def sniff(data: bytes) -> FileType | None:
    """What the bytes are, as far as a PO goes.

    ``pdf`` and ``xlsx`` are read; ``xls`` and ``doc`` are read once the
    reader sandbox converted them (ticket 27). ``unsupported`` is a document
    DW1 does not read (an image, an encrypted or other legacy Office file, an
    archive), which routes the message to Sales with the reason. None is
    anything else.
    """
    if data.startswith(_PDF):
        return "pdf"
    if data.startswith(_ZIP):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile:
            return "unsupported"
        return "xlsx" if _WORKBOOK in names else "unsupported"
    if data.startswith(_OLE):
        return _legacy(data)
    if data.startswith(_IMAGES):
        return "unsupported"
    return None


def _legacy(data: bytes) -> FileType:
    """A compound file's kind by the streams its directory names: a name is
    taken only where a directory entry starts and its length field agrees, so
    the same words in a document's text name no stream."""
    if _ENCRYPTED in data:
        return "unsupported"
    for name, kind in _LEGACY:
        if _entry_named(data, name):
            return kind
    return "unsupported"


def _entry_named(data: bytes, name: str) -> bool:
    encoded = name.encode("utf-16-le") + b"\x00\x00"
    length = len(encoded).to_bytes(2, "little")
    at = data.find(encoded)
    while at != -1:
        field = at + _NAME_LENGTH_AT
        if at % _ENTRY == 0 and data[field : field + 2] == length:
            return True
        at = data.find(encoded, at + 1)
    return False
