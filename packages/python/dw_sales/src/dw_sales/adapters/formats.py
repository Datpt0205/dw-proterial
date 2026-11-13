"""What a file is by its bytes, and whether it is what its name says.

The type is sniffed from the first bytes and the container's own table of
contents, never from the file name or the media type the sender declared: both
are the sender's claim.

**A file that is not what its name says is refused** before any reader opens
it (`refusal`, ticket 25): a ``.xlsx`` that is no workbook, a ``.pdf`` that is
no PDF (a renamed program among them). A name that claims no document type
(an image, a signature) is not checked: it is sniffed, as before.

**A file locked with a password is not refused** (`encrypted`, ticket 17): an
Office file encrypted as a whole (an OLE compound file holding an
``EncryptedPackage`` stream, what Excel writes for "Encrypt with Password")
or a PDF whose trailer names an ``/Encrypt`` dictionary. Its contents are not
scannable by ClamAV, so it is read only in the reader sandbox, opened there
with the passwords its own mail carries (`dw_sales.domain.file_passwords`).
An encrypted Office file sniffs as ``encrypted``, which is read as a workbook
once opened: the sandbox holds the opened bytes to that, as it holds every
file to what it is.

**A portal's export** (ticket 18) is text, not a container: what Excel saves
as "Unicode text", UTF-16 with its byte-order mark and one tab-separated row
per line. It sniffs as ``csv`` by those bytes alone (the mark, then a tab
before the first line ends), whatever it is named; it is read as rows of
text, and a cell is never evaluated as a formula.

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
_ENCRYPTED: Final = "EncryptedPackage"
# A PDF encrypted with a password names its encryption dictionary in its
# trailer (or its cross-reference stream's dictionary, which is never
# compressed), so the key is in the bytes as written.
_PDF_ENCRYPT: Final = b"/Encrypt"
# The streams that make an OLE compound file a legacy workbook or Word file
# (ticket 27): Excel 97-2003's `Workbook` (`Book` before it), Word's
# `WordDocument`.
_LEGACY: Final[tuple[tuple[str, FileType], ...]] = (
    ("Workbook", "xls"),
    ("Book", "xls"),
    ("WordDocument", "doc"),
)
# A UTF-16 byte-order mark, little- and big-endian: how Excel's "Unicode
# text" (a portal's export, ticket 18) begins.
_UTF16_LE: Final = b"\xff\xfe"
_UTF16: Final = (_UTF16_LE, b"\xfe\xff")
# How much of a text file is decoded to find its first line: a header row of
# titles, well under this.
_FIRST_LINE_BYTES: Final = 4096
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
    extension = name[name.rfind(".") :].casefold() if "." in name else ""
    claimed = _CLAIMS.get(extension)
    if claimed is None:
        return None
    is_claimed = {
        "pdf": data.startswith(_PDF),
        # An encrypted OOXML file is an OLE compound file (module docstring).
        "ooxml": data.startswith(_ZIP) or sniff(data) == "encrypted",
        "ole": data.startswith(_OLE),
    }[claimed]
    if is_claimed and extension in (".xlsx", ".xlsm") and sniff(data) not in ("xlsx", "encrypted"):
        is_claimed = False
    return None if is_claimed else f"named {extension} but its bytes are not one"


def encrypted(data: bytes) -> bool:
    """Whether the file is locked with a password (module docstring): an
    Office file encrypted as a whole, or a PDF naming an encryption
    dictionary. A PDF whose text merely says ``/Encrypt`` is let through as
    encrypted here and opened as it is by the reader, which asks pypdf."""
    if data.startswith(_PDF):
        return _PDF_ENCRYPT in data
    return data.startswith(_OLE) and _entry_named(data, _ENCRYPTED)


def sniff(data: bytes) -> FileType | None:
    """What the bytes are, as far as a PO goes.

    ``pdf`` and ``xlsx`` are read; ``xls`` and ``doc`` are read once the
    reader sandbox converted them (ticket 27), ``encrypted`` once it opened
    it with a password from its mail (ticket 17), ``csv`` with a layout of
    the customer's export (ticket 18). ``unsupported`` is a
    document DW1 does not read (an image, another legacy Office file, an
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
    if data.startswith(_UTF16) and _tab_separated(data[:_FIRST_LINE_BYTES]):
        return "csv"
    return None


def _tab_separated(head: bytes) -> bool:
    """Whether UTF-16 text's first line holds a tab: the first bytes only,
    decoded as far as they go, so nothing past them is read."""
    encoding = "utf-16-le" if head.startswith(_UTF16_LE) else "utf-16-be"
    text = head[2 : len(head) - len(head) % 2].decode(encoding, errors="replace")
    first = text.split("\n", 1)[0]
    return "\t" in first


def _legacy(data: bytes) -> FileType:
    """A compound file's kind by the streams its directory names: a name is
    taken only where a directory entry starts and its length field agrees, so
    the same words in a document's text name no stream."""
    if _entry_named(data, _ENCRYPTED):
        return "encrypted"
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
