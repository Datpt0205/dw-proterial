"""A TCP forwarder: the only way anything reaches the sandbox.

The sandbox lives alone on `dw-sandbox`, declared `internal: true`. Two
distinct properties, and it is worth keeping them apart because an earlier
version of this file ran them together:

* `internal: true` denies a route off the machine, so an injected instruction
  can read data and has nowhere to send it.
* Being ALONE on that network denies the lateral hop. `internal: true` says
  nothing about containers sharing a bridge, and `dw-internal` carries Qdrant
  and Valkey, unauthenticated in the base stack. Model-written code that could
  open a socket to them would read every tenant's chunks or flush the cache,
  under no AccessContext and past RLS.

Docker builds no DNAT for a container on an internal network, so the sandbox
cannot publish a port, and giving it a routable one to fix that would trade the
first property away. This process takes the trade instead: it sits on both
networks, accepts on the published port and forwards. It runs no submitted
code, reads no files and parses nothing — it copies bytes in two directions.

It forwards to ONE address, read from its own environment and never from the
request. That is what makes it safe to be the single container bridging the two
networks: the sandbox can open a socket to it and get the sandbox's own API
back, not an onward hop.

Both the host and the chat container come through here — the host for the
development loop where the chat runs outside compose, the chat container
because it no longer shares a network with the sandbox.
"""

from __future__ import annotations

import asyncio
import os

GATEWAY_LISTEN_PORT = int(os.environ.get("GATEWAY_LISTEN_PORT", "8110"))
GATEWAY_TARGET_HOST = os.environ.get("GATEWAY_TARGET_HOST", "docgen")
GATEWAY_TARGET_PORT = int(os.environ.get("GATEWAY_TARGET_PORT", "8110"))


async def _pump(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while chunk := await reader.read(65536):
            writer.write(chunk)
            await writer.drain()
    except (ConnectionError, asyncio.IncompleteReadError):
        pass
    finally:
        writer.close()


async def _handle(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
    try:
        upstream_reader, upstream_writer = await asyncio.open_connection(
            GATEWAY_TARGET_HOST, GATEWAY_TARGET_PORT
        )
    except OSError:
        client_writer.close()
        return
    await asyncio.gather(
        _pump(client_reader, upstream_writer),
        _pump(upstream_reader, client_writer),
        return_exceptions=True,
    )


async def main() -> None:
    # Every interface inside the container; the published port binds it to
    # loopback on the host, which is where the exposure is actually decided.
    server = await asyncio.start_server(_handle, "0.0.0.0", GATEWAY_LISTEN_PORT)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
