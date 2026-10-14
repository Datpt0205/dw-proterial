"""`python -m dw_reader`: the service on its Unix socket.

A socket left by an earlier start is removed first (a container restarted on
the same volume), and uvicorn makes the new one readable and writable by the
volume's users; the volume's directory belongs to the one uid the api, the
worker and the reader share.
"""

from __future__ import annotations

from pathlib import Path

import uvicorn

from dw_reader.main import create_app
from dw_reader.settings import get_settings


def main() -> None:
    settings = get_settings()
    socket = Path(settings.socket_path)
    socket.parent.mkdir(parents=True, exist_ok=True)
    socket.unlink(missing_ok=True)
    uvicorn.run(create_app(settings), uds=str(socket), log_level="info")


if __name__ == "__main__":
    main()
