"""`MalwareScanPort` for tests that run DW1 with no scanner service (ticket 25).

Each verdict is the test's to state: `NoMalware` finds nothing in any file,
`ScriptedScanner` answers per file by its bytes, and anything else it was not
told about is clean. The real scanner is `dw_sales.adapters.clamd`, tested
against clamd itself in the integration suite.
"""

from __future__ import annotations

from collections.abc import Mapping

from dw_sales.application.malware import ScanVerdict


class NoMalware:
    """Every file clean, every call counted."""

    def __init__(self) -> None:
        self.scanned = 0

    async def scan(self, data: bytes) -> ScanVerdict:
        self.scanned += 1
        return ScanVerdict.clean()


class ScriptedScanner:
    """The verdict scripted for a file's exact bytes; clean otherwise."""

    def __init__(self, verdicts: Mapping[bytes, ScanVerdict]) -> None:
        self._verdicts = dict(verdicts)

    async def scan(self, data: bytes) -> ScanVerdict:
        return self._verdicts.get(data, ScanVerdict.clean())
