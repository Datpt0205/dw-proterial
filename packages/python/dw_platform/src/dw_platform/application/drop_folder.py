"""A folder mail arrives in as `.eml` files: the port (Sales' mail drop,
ticket 43, lifted by docs/adr/0013 when Purchasing read its own mail the
same way; each context keeps the lane that reads it, ADR 0014).

A flow exports every mail reaching a mailbox into the folder, and a PC in the
plant syncs it to the host (`dw_platform.adapters.drop_folder`).

**One folder for every DW** (Đạt, 2026-11-02): every person runs the same
flow, into a subfolder named by their own mailbox address. Which DW reads a
person's mail is not a list anyone types: a context's lane reads the folders
of the members holding the scope it acts on (`OwnedFolders` over
`FolderOwnersPort`), and its model sorts what each mail is. A file in the
root, or in a folder nobody holding the scope owns, is read by no one.
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


class FolderOwnersPort(Protocol):
    async def addresses(self) -> frozenset[str]:
        """The mailbox addresses, lowercase, whose folders a lane reads."""
        ...


@dataclass(frozen=True)
class OwnedFolders:
    """`DropFolderPort` over ``inner``, cut to the subfolders ``owners``
    names (the folder name compared lowercase). A read outside them is
    refused, not only left unlisted."""

    inner: DropFolderPort
    owners: FolderOwnersPort

    async def files(self) -> Sequence[DroppedFile]:
        mine = await self.owners.addresses()
        return [f for f in await self.inner.files() if f.folder and f.folder.lower() in mine]

    async def read(self, dropped: DroppedFile, limit: int) -> bytes:
        if not dropped.folder or dropped.folder.lower() not in await self.owners.addresses():
            raise ValueError("not a folder this lane reads")
        return await self.inner.read(dropped, limit)
