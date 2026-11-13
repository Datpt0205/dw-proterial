"""A file locked with a password, opened in memory (ticket 17).

Runs where reading is contained, the reader sandbox (`readers.operations`),
on the bytes of one request and the candidates its file's own mail carries
(`ReaderArgs.passwords`, `dw_sales.domain.file_passwords`). The file decides
which candidate is its password: an Office file is opened only when a
candidate verifies against its key and the decrypted package passes its
integrity check (msoffcrypto-tool, ``verify_password`` and
``verify_integrity``); a PDF when pypdf takes a candidate as its user or
owner password. The opened bytes are returned and read as any file is; they
leave the sandbox only as a reading.

**Nothing here names a password.** Which candidate opened the file is not
returned, and a file none opens raises `LockedError` with a sentence code
wrote. A candidate a library refuses with an exception is a candidate that
did not open the file: the exception is dropped unread, since its text is
the library's and might quote what it was given.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Sequence
from typing import Final

import msoffcrypto
from pypdf import PasswordType, PdfReader, PdfWriter

from dw_sales.adapters.formats import encrypted, sniff
from dw_sales.domain.file_passwords import MAX_PASSWORDS

# Why a locked file was not opened, as the routed message and the audit say
# it: the attachment's id goes before it, never a candidate.
NO_PASSWORD: Final = "the file has a password, and its mail carries none to try"
NONE_OPENS: Final = "the file has a password, and none its mail carries opens it"


class LockedError(Exception):
    """The file is locked with a password and no candidate opened it."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def opened(data: bytes, passwords: Sequence[str]) -> bytes | None:
    """The file's bytes, opened with the first candidate that opens it; None
    when the file is not locked. `LockedError` when it is and none does."""
    if not encrypted(data):
        return None
    if sniff(data) == "pdf":
        try:
            if not PdfReader(io.BytesIO(data)).is_encrypted:
                return None  # "/Encrypt" in its text, no encryption: as it is
        except Exception:  # not a PDF pypdf can open: the reader says so
            return None
        open_one: Callable[[bytes, str], bytes | None] = _pdf
    else:
        open_one = _office
    if not passwords:
        raise LockedError(NO_PASSWORD)
    for password in passwords[:MAX_PASSWORDS]:
        try:
            plain = open_one(data, password)
        except Exception:  # this candidate did not open it (module docstring)
            continue
        if plain is not None:
            return plain
    raise LockedError(NONE_OPENS)


def _office(data: bytes, password: str) -> bytes:
    """An Office file opened with ``password``, its key verified and its
    package's integrity checked; raises when it is not the password."""
    office = msoffcrypto.OfficeFile(io.BytesIO(data))
    office.load_key(password=password, verify_password=True)
    plain = io.BytesIO()
    office.decrypt(plain, verify_integrity=True)
    return plain.getvalue()


def _pdf(data: bytes, password: str) -> bytes | None:
    """A PDF opened with ``password``, written out again without its
    encryption; None when it is not the password."""
    reader = PdfReader(io.BytesIO(data))
    if reader.decrypt(password) is PasswordType.NOT_DECRYPTED:
        return None
    plain = io.BytesIO()
    PdfWriter(clone_from=reader).write(plain)
    return plain.getvalue()
