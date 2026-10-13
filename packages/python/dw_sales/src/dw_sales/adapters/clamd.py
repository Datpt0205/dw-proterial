"""`MalwareScanPort` over clamd's ``INSTREAM`` command, on TCP (ticket 25).

The protocol, as clamd documents it: send ``zINSTREAM\\0``, then the file in
chunks, each a 4-byte big-endian length and that many bytes, then a zero
length; clamd answers one NUL-terminated line, ``stream: OK``,
``stream: <signature> FOUND``, or ``... ERROR``.

Everything that is not one of the first two is "unavailable", and the caller
fails closed on it: a refused or reset connection, a deadline passed, a reply
too long or cut short, an ``ERROR`` (a stream past clamd's ``StreamMaxLength``
among them), or words this adapter does not know. A scanner that answers
nonsense is a scanner that did not scan.
"""

from __future__ import annotations

import asyncio
import logging
import re
import struct
from contextlib import suppress
from typing import Final

from dw_sales.application.malware import MalwareScanPort, ScanVerdict

_LOG = logging.getLogger(__name__)

_CHUNK: Final = 64 * 1024
# clamd's whole answer is one short line; anything longer is not clamd.
_REPLY_LIMIT: Final = 1024
_FOUND = re.compile(r"stream: (?P<signature>[!-~][ -~]{0,199}) FOUND")


class ClamdScanner:
    """Scans each file with one connection to clamd at ``host:port``."""

    def __init__(self, host: str, port: int, *, timeout_seconds: float = 30.0) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout_seconds

    async def scan(self, data: bytes) -> ScanVerdict:
        try:
            async with asyncio.timeout(self._timeout):
                reply = await self._instream(data)
        except TimeoutError:
            return ScanVerdict.unavailable("timeout")
        except (OSError, asyncio.IncompleteReadError, asyncio.LimitOverrunError) as exc:
            return ScanVerdict.unavailable(type(exc).__name__)
        return verdict(reply)

    async def _instream(self, data: bytes) -> bytes:
        reader, writer = await asyncio.open_connection(self._host, self._port, limit=_REPLY_LIMIT)
        try:
            writer.write(b"zINSTREAM\0")
            for start in range(0, len(data), _CHUNK):
                chunk = data[start : start + _CHUNK]
                writer.write(struct.pack("!I", len(chunk)) + chunk)
                await writer.drain()
            writer.write(struct.pack("!I", 0))
            await writer.drain()
            return await reader.readuntil(b"\0")
        finally:
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()


def verdict(reply: bytes) -> ScanVerdict:
    """What one clamd reply says, read strictly (module docstring)."""
    text = reply.removesuffix(b"\0").decode("ascii", errors="replace")
    if text == "stream: OK":
        return ScanVerdict.clean()
    if (found := _FOUND.fullmatch(text)) is not None:
        return ScanVerdict.infected(found["signature"])
    return ScanVerdict.unavailable("unexpected reply")


class SkippedScan:
    """Hands every file over unscanned: a host-run local API, which cannot
    reach a scanner that publishes no port. `malware_scanner` refuses it in a
    deployed profile; anywhere else it says so in the log, once."""

    def __init__(self) -> None:
        self._warned = False

    async def scan(self, data: bytes) -> ScanVerdict:
        if not self._warned:
            _LOG.warning(
                "sales: attachments are NOT scanned for malware (DW_SALES_MALWARE_SCAN=skip)"
            )
            self._warned = True
        return ScanVerdict.clean()


def malware_scanner(mode: str, *, host: str, port: int, deployed: bool) -> MalwareScanPort:
    """The scanner a process's settings name: clamd, or none where that is
    allowed. One function for the API and the worker, so the two cannot
    disagree on what ``skip`` may do."""
    if mode == "clamd":
        return ClamdScanner(host, port)
    if mode == "skip" and not deployed:
        return SkippedScan()
    if mode == "skip":
        raise ValueError(
            "a deployed profile scans every attachment: DW_SALES_MALWARE_SCAN=skip is refused"
        )
    raise ValueError(f"DW_SALES_MALWARE_SCAN is clamd or skip, not {mode!r}")
