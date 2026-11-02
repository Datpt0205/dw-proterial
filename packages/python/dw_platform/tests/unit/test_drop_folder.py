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
from dw_platform.application.drop_folder import DroppedFile, OwnedFolders

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


class _Owners:
    def __init__(self, *addresses: str) -> None:
        self.held = frozenset(addresses)

    async def addresses(self) -> frozenset[str]:
        return self.held


async def test_a_lane_sees_only_the_folders_of_those_holding_its_scope(tmp_path: Path) -> None:
    """One drop folder for every DW, a subfolder per mailbox address: a lane
    lists the files of the addresses its owners name, case aside, and
    nothing in the root or in anyone else's folder."""
    for name in ("an@proterial.example", "Binh@Proterial.example", "khoa@proterial.example"):
        (tmp_path / name).mkdir()
        (tmp_path / name / f"{name.lower()}.eml").write_bytes(b"x")
    (tmp_path / "stray.eml").write_bytes(b"x")
    folder = OwnedFolders(
        LocalDropFolder(tmp_path), _Owners("an@proterial.example", "binh@proterial.example")
    )

    listed = {(f.folder, f.name) for f in await folder.files()}

    assert listed == {
        ("an@proterial.example", "an@proterial.example.eml"),
        ("Binh@Proterial.example", "binh@proterial.example.eml"),
    }


async def test_a_lane_whose_scope_nobody_holds_sees_nothing(tmp_path: Path) -> None:
    (tmp_path / "an@proterial.example").mkdir()
    (tmp_path / "an@proterial.example" / "1.eml").write_bytes(b"x")
    assert await OwnedFolders(LocalDropFolder(tmp_path), _Owners()).files() == []


async def test_a_file_outside_the_owners_folders_is_never_read(tmp_path: Path) -> None:
    """Listing is not the only door: a read of another person's file is refused."""
    (tmp_path / "khoa@proterial.example").mkdir()
    (tmp_path / "khoa@proterial.example" / "1.eml").write_bytes(b"secret")
    folder = OwnedFolders(LocalDropFolder(tmp_path), _Owners("an@proterial.example"))
    theirs = DroppedFile(
        name="1.eml",
        size=6,
        modified_at=datetime(2026, 11, 2, tzinfo=UTC),
        folder="khoa@proterial.example",
    )
    with pytest.raises(ValueError, match="not a folder this lane reads"):
        await folder.read(theirs, 100)
