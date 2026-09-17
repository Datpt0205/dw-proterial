"""Fixtures shared by the sandbox service's tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from dw_docgen.settings import DocgenSettings


@pytest.fixture
def settings(tmp_path: Path) -> DocgenSettings:
    """A budget small enough that the tests can actually reach every limit."""
    return DocgenSettings(
        root=str(tmp_path / "work"),
        token="",
        default_timeout_seconds=5,
        max_timeout_seconds=10,
        max_output_bytes=256,
        max_upload_bytes=4096,
        max_download_bytes=4096,
        max_files_per_batch=3,
    )
