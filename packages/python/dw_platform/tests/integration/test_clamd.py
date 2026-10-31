"""Sales ticket 25, against clamd itself: the `clamav` compose service's image and
config, reached at ``DW_TEST_CLAMD`` (``host:port``).

CI runs clamd as a service container for this suite and sets the variable;
there, its absence fails the suite rather than skipping it, because a scanner
test that never runs is a guard nobody watches (failure-modes #1). Locally it
is skipped unless a clamd is started for it (`infra/compose/clamd.conf`).

The EICAR test file is assembled here at run time, so this source file is
not itself something a virus scanner on the machine quarantines.
"""

from __future__ import annotations

import io
import os
import zipfile

import pytest

from dw_platform.adapters.clamd import ClamdScanner
from dw_platform.application.malware import ScanVerdict

pytestmark = pytest.mark.integration

_EICAR = ("X5O!P%@AP[4\\PZX54(P^)7CC)7}$" + "EICAR-STANDARD-ANTIVIRUS-" + "TEST-FILE!$H+H*").encode(
    "ascii"
)


def _scanner() -> ClamdScanner:
    address = os.environ.get("DW_TEST_CLAMD", "")
    if not address:
        if os.environ.get("CI"):
            pytest.fail("DW_TEST_CLAMD is not set: CI runs clamd for this suite")
        pytest.skip("no clamd for this run (set DW_TEST_CLAMD=host:port)")
    host, _, port = address.rpartition(":")
    return ClamdScanner(host, int(port), timeout_seconds=60)


async def test_the_eicar_test_file_is_found_by_its_signature() -> None:
    assert await _scanner().scan(_EICAR) == ScanVerdict.infected("Eicar-Test-Signature")


async def test_an_ordinary_office_file_is_clean() -> None:
    # An Office file is a zip: one built here, so the suite needs no context's fixtures.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/workbook.xml", "<workbook/>")
    data = buffer.getvalue()

    assert await _scanner().scan(data) == ScanVerdict.clean()


async def test_a_file_past_the_stream_limit_is_unavailable_never_clean() -> None:
    """clamd answers ``INSTREAM size limit exceeded. ERROR`` past its
    ``StreamMaxLength`` (25M): a file it did not scan whole is not clean."""
    found = await _scanner().scan(b"\0" * (26 * 1024 * 1024))

    assert found.outcome == "unavailable"
