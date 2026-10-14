"""`python -m dw_reader.health`: the container's healthcheck, over the socket.

Exit 0 when `/health` answers 200, 1 otherwise. The container has no network,
so the check speaks HTTP over the Unix socket itself.
"""

from __future__ import annotations

import http.client
import socket
import sys

from dw_reader.settings import get_settings


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: str) -> None:
        super().__init__("reader", timeout=5)
        self._path = path

    def connect(self) -> None:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(5)
        connection.connect(self._path)
        self.sock = connection


def main() -> int:
    connection = _UnixConnection(get_settings().socket_path)
    try:
        connection.request("GET", "/health")
        return 0 if connection.getresponse().status == 200 else 1
    except OSError:
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())
