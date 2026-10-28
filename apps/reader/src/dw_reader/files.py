"""The two files a reading process exchanges with the service, in its own
directory. Apart from `reading` so the process imports two names, not the
service's runner and settings (2026-10-28: 0.6 s of every read)."""

from __future__ import annotations

from typing import Final

REQUEST: Final = "request.json"
RESULT: Final = "result.json"
