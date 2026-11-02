"""The drop folder a context's mail arrives in (Sales ticket 43, lifted by
docs/adr/0013): `DropFolderPort` over a directory this process mounts
read-only.

The directory is the share a PC in the plant syncs from OneDrive, one
subfolder per mailbox; compose mounts it into the worker alone. Only regular
files in it or one level below are listed: a link, a deeper folder or a name
that is not a plain file name is not a mail a flow wrote.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from dw_platform.application.drop_folder import DroppedFile


@dataclass(frozen=True)
class LocalDropFolder:
    path: Path

    async def files(self) -> Sequence[DroppedFile]:
        return await asyncio.to_thread(self._files)

    async def read(self, dropped: DroppedFile, limit: int) -> bytes:
        return await asyncio.to_thread(self._read, dropped, limit)

    def _files(self) -> list[DroppedFile]:
        found: list[DroppedFile] = []
        with os.scandir(self.path) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    found.extend(self._in(Path(entry.path), entry.name))
                elif entry.is_file(follow_symlinks=False):
                    found.append(_dropped(entry, ""))
        return found

    def _in(self, folder: Path, name: str) -> list[DroppedFile]:
        with os.scandir(folder) as entries:
            return [_dropped(e, name) for e in entries if e.is_file(follow_symlinks=False)]

    def _read(self, dropped: DroppedFile, limit: int) -> bytes:
        for part in (dropped.folder, dropped.name):
            if Path(part).name != part or part in {".", ".."}:
                raise ValueError("not a file in the drop folder")
        with (self.path / dropped.folder / dropped.name).open("rb") as file:
            return file.read(limit + 1)


def _dropped(entry: os.DirEntry[str], folder: str) -> DroppedFile:
    stat = entry.stat(follow_symlinks=False)
    return DroppedFile(
        name=entry.name,
        size=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
        folder=folder,
    )
