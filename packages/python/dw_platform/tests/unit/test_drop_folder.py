"""The drop folder a mail flow fills with `.eml` files (Sales ticket 43, lifted
by docs/adr/0013 so DW2 reads its own the same way): regular files in the
folder or one level below are listed, and a name that is not a plain file
name never reaches a read."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dw_platform.adapters.drop_folder import LocalDropFolder
from dw_platform.application.drop_folder import DroppedFile

pytestmark = pytest.mark.unit


async def test_files_in_the_folder_and_one_level_below_are_listed(tmp_path: Path) -> None:
    (tmp_path / "top.eml").write_bytes(b"a")
    (tmp_path / "pic").mkdir()
    (tmp_path / "pic" / "below.eml").write_bytes(b"bb")
    (tmp_path / "pic" / "deeper").mkdir()
    (tmp_path / "pic" / "deeper" / "too-deep.eml").write_bytes(b"c")

    listed = {(f.folder, f.name, f.size) for f in await LocalDropFolder(tmp_path).files()}

    assert listed == {("", "top.eml", 1), ("pic", "below.eml", 2)}


@pytest.mark.skipif(os.name == "nt", reason="a symlink needs a privilege on Windows")
async def test_a_link_is_not_listed(tmp_path: Path) -> None:
    outside = tmp_path / "outside.eml"
    outside.write_bytes(b"secret")
    drop = tmp_path / "drop"
    drop.mkdir()
    (drop / "link.eml").symlink_to(outside)

    assert await LocalDropFolder(drop).files() == []


async def test_a_read_is_bounded_one_past_the_limit(tmp_path: Path) -> None:
    (tmp_path / "big.eml").write_bytes(b"x" * 10)
    folder = LocalDropFolder(tmp_path)
    [dropped] = await folder.files()

    assert await folder.read(dropped, 4) == b"xxxxx"


@pytest.mark.parametrize(
    ("folder", "name"),
    [("", "../outside.eml"), ("..", "outside.eml"), ("pic/..", "x.eml"), ("", "..")],
)
async def test_a_name_that_climbs_out_is_never_read(tmp_path: Path, folder: str, name: str) -> None:
    (tmp_path / "outside.eml").write_bytes(b"secret")
    drop = tmp_path / "drop"
    (drop / "pic").mkdir(parents=True)
    dropped = DroppedFile(
        name=name, size=6, modified_at=datetime(2026, 11, 2, tzinfo=UTC), folder=folder
    )

    with pytest.raises(ValueError, match="not a file in the drop folder"):
        await LocalDropFolder(drop).read(dropped, 100)
