"""Ticket 25, against clamd itself: the `clamav` compose service's image and
config, reached at ``DW_TEST_CLAMD`` (``host:port``).

CI runs clamd as a service container for this suite and sets the variable;
there, its absence fails the suite rather than skipping it, because a scanner
test that never runs is a guard nobody watches (failure-modes #1). Locally it
is skipped unless a clamd is started for it (`infra/compose/clamd.conf`).

The EICAR test file is assembled here at run time, so this source file is
not itself something a virus scanner on the machine quarantines.
"""

from __future__ import annotations

import os

import pytest

from dw_sales.adapters.clamd import ClamdScanner
from dw_sales.adapters.mock.fixtures import ATTACHMENTS_DIR
from dw_sales.application.malware import ScanVerdict

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


async def test_a_mock_po_is_clean() -> None:
    data = (ATTACHMENTS_DIR / "M01_VLX-PO-2609-0118.xlsx").read_bytes()

    assert await _scanner().scan(data) == ScanVerdict.clean()


async def test_a_file_past_the_stream_limit_is_unavailable_never_clean() -> None:
    """clamd answers ``INSTREAM size limit exceeded. ERROR`` past its
    ``StreamMaxLength`` (25M): a file it did not scan whole is not clean."""
    found = await _scanner().scan(b"\0" * (26 * 1024 * 1024))

    assert found.outcome == "unavailable"
