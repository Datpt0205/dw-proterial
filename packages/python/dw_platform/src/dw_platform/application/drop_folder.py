"""A folder mail arrives in as `.eml` files: the port (Sales' mail drop,
ticket 43, lifted by docs/adr/0013 when Purchasing read its own mail the
same way; each context keeps the lane that reads it, ADR 0014).

A flow exports every mail reaching a mailbox into the folder, and a PC in the
plant syncs it to the host (`dw_platform.adapters.drop_folder`).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class DroppedFile:
    """A file in the drop folder: its name, the subfolder it sits in ("" for
    the folder itself), its size and when it last changed. The flow names a
    file by the time and a fresh guid, so a name is the file's identity
    across the mailboxes' folders."""

    name: str
    size: int
    modified_at: datetime
    folder: str = ""


class DropFolderPort(Protocol):
    """The folder the flows' files arrive in, read only."""

    async def files(self) -> Sequence[DroppedFile]:
        """Every regular file in the folder or one level below it."""
        ...

    async def read(self, dropped: DroppedFile, limit: int) -> bytes:
        """At most ``limit`` + 1 bytes of the file: one more than the limit
        says it is over."""
        ...
