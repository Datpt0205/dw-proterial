"""clamd's protocol against a fake clamd on a local socket (sales ticket 25);
the real one is the integration suite's, with EICAR (`test_clamd.py`)."""

from __future__ import annotations

import asyncio
import struct

import pytest

from dw_platform.adapters.clamd import ClamdScanner, SkippedScan, malware_scanner, verdict
from dw_platform.application.malware import ScanVerdict

pytestmark = pytest.mark.unit

EICAR = "Eicar-Test-Signature"


# ------------------------------------------------------ clamd's protocol --


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        (b"stream: OK\0", ScanVerdict.clean()),
        (b"stream: Eicar-Test-Signature FOUND\0", ScanVerdict.infected(EICAR)),
        (b"INSTREAM size limit exceeded. ERROR\0", ScanVerdict.unavailable("unexpected reply")),
        (b"stream: OK FOUND? no\0", ScanVerdict.unavailable("unexpected reply")),
        (b"stream:  FOUND\0", ScanVerdict.unavailable("unexpected reply")),
        (b"\0", ScanVerdict.unavailable("unexpected reply")),
    ],
)
def test_a_clamd_reply_is_read_strictly(reply: bytes, expected: ScanVerdict) -> None:
    assert verdict(reply) == expected


async def _fake_clamd(answer: bytes | None) -> tuple[asyncio.Server, list[bytes]]:
    """A clamd on a local port that records the stream it was sent and answers
    ``answer``, or never answers (None)."""
    received: list[bytes] = []

    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        command = await reader.readexactly(len(b"zINSTREAM\0"))
        received.append(command)
        while True:
            (size,) = struct.unpack("!I", await reader.readexactly(4))
            if size == 0:
                break
            received.append(await reader.readexactly(size))
        if answer is None:
            await asyncio.sleep(5)
        else:
            writer.write(answer)
            await writer.drain()
        writer.close()

    return await asyncio.start_server(serve, "127.0.0.1", 0), received


async def test_the_file_goes_to_clamd_as_an_instream_in_chunks_and_the_answer_is_read() -> None:
    server, received = await _fake_clamd(b"stream: Eicar-Test-Signature FOUND\0")
    data = bytes(range(256)) * 600  # 153,600 bytes: three chunks
    async with server:
        port = server.sockets[0].getsockname()[1]
        found = await ClamdScanner("127.0.0.1", port).scan(data)

    assert found == ScanVerdict.infected(EICAR)
    assert received[0] == b"zINSTREAM\0"
    assert b"".join(received[1:]) == data and len(received) == 4


async def test_a_clamd_that_does_not_answer_in_time_is_unavailable() -> None:
    server, _ = await _fake_clamd(None)
    async with server:
        port = server.sockets[0].getsockname()[1]
        found = await ClamdScanner("127.0.0.1", port, timeout_seconds=0.2).scan(b"x")

    assert found == ScanVerdict.unavailable("timeout")


async def test_no_clamd_at_all_is_unavailable() -> None:
    server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    server.close()
    await server.wait_closed()

    found = await ClamdScanner("127.0.0.1", port, timeout_seconds=2).scan(b"x")

    assert found.outcome == "unavailable"


def test_a_deployed_profile_cannot_skip_the_scan() -> None:
    assert isinstance(
        malware_scanner("clamd", host="clamav", port=3310, deployed=True), ClamdScanner
    )
    assert isinstance(
        malware_scanner("skip", host="clamav", port=3310, deployed=False), SkippedScan
    )
    with pytest.raises(ValueError, match="refused"):
        malware_scanner("skip", host="clamav", port=3310, deployed=True)
    with pytest.raises(ValueError, match="clamd or skip"):
        malware_scanner("off", host="clamav", port=3310, deployed=False)
