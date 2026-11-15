"""Give a local `.env` a VAPID key for Web Push when it has none (Sales
ticket 48).

`scripts/dev.sh` runs this before it reads `.env`. It writes only a missing
or empty `DW_WEB_PUSH_VAPID_PRIVATE_KEY` (and a local subject beside it when
that is empty too), never replaces one, and never touches any other file:
`.env` is ignored by git, so the key never reaches the repository. A
deployment's key comes from its own secrets, never from here.

Usage: uv run python scripts/dev_web_push_key.py [path/to/.env]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from dw_platform.adapters.web_push import new_vapid_private_key

KEY = "DW_WEB_PUSH_VAPID_PRIVATE_KEY"
SUBJECT = "DW_WEB_PUSH_SUBJECT"
LOCAL_SUBJECT = "mailto:dev@localhost.invalid"


def _filled(text: str, name: str, value: str) -> tuple[str, bool]:
    """``text`` with ``name`` set to ``value`` when it is missing or empty."""
    line = re.compile(rf"^{name}=(.*)$", re.MULTILINE)
    found = line.search(text)
    if found is None:
        return text.rstrip("\n") + f"\n{name}={value}\n", True
    if found.group(1).strip().strip("\"'"):
        return text, False
    return text[: found.start()] + f"{name}={value}" + text[found.end() :], True


def main() -> int:
    env = Path(sys.argv[1] if len(sys.argv) > 1 else ".env")
    if not env.is_file():
        return 0
    text = env.read_text(encoding="utf-8")
    text, wrote_key = _filled(text, KEY, new_vapid_private_key())
    text, wrote_subject = _filled(text, SUBJECT, LOCAL_SUBJECT)
    if wrote_key or wrote_subject:
        with env.open("w", encoding="utf-8", newline="") as out:
            out.write(text)
        print(f">> {env}: wrote a local Web Push key (set DW_WEB_PUSH_ENABLED=true to use it)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
