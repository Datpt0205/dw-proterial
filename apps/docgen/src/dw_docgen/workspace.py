"""Per-session directories and the containment rule for every path that crosses
the wire.

One container serves every session, so the only thing separating them is this
module: a session id maps to exactly one directory, and no path a caller sends
may resolve outside it. Symlinks are resolved before the check, so a script that
plants `out -> /etc` cannot turn a later download into an arbitrary file read.
"""

from __future__ import annotations

import re
import shutil
import time
from collections.abc import Container
from pathlib import Path

# Session ids come from the calling backend, not from the model, but they land
# in a filesystem path, so they are validated rather than trusted.
SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class InvalidSessionError(ValueError):
    """The session id could not be used as a directory name."""


class PathOutsideSessionError(ValueError):
    """A path resolved outside the session directory it was addressed to."""


class SessionWorkspace:
    """Resolves session ids and paths against a root directory."""

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    @property
    def scratch_dir(self) -> Path:
        """The service's own directory under the root, created on demand.

        Dot-prefixed, which no session id can be, so it can never be mistaken
        for one - by the sweep or by anything else.
        """
        path = self._root / ".service"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def session_dir(self, session_id: str, *, create: bool = True) -> Path:
        """The directory backing `session_id`, created on first use."""
        if not SESSION_ID.match(session_id):
            msg = (
                f"session id {session_id!r} is not usable as a directory name; "
                "use letters, digits, '-' and '_', up to 64 characters"
            )
            raise InvalidSessionError(msg)
        path = self._root / session_id
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def resolve(self, session_id: str, raw_path: str) -> Path:
        """Map a caller-supplied path onto a real path inside the session.

        Absolute paths are honoured when they already point inside the session
        directory; relative paths are taken against it. Anything else is refused
        rather than clamped, because silently relocating a write is how a script
        ends up believing it wrote a file it did not.
        """
        base = self.session_dir(session_id)
        candidate = Path(raw_path)
        target = candidate if candidate.is_absolute() else base / candidate
        # `resolve()` on a path that does not exist yet resolves the existing
        # prefix and appends the rest verbatim - what an upload to a new file
        # needs, and it still follows a symlinked parent, which is the escape
        # this check exists for.
        resolved = target.resolve()
        base_resolved = base.resolve()
        if resolved != base_resolved and base_resolved not in resolved.parents:
            msg = f"{raw_path!r} resolves outside the session workspace"
            raise PathOutsideSessionError(msg)
        return resolved

    def reset(self, session_id: str) -> None:
        """Delete everything the session wrote. Idempotent."""
        shutil.rmtree(self.session_dir(session_id, create=False), ignore_errors=True)

    def sweep(
        self,
        *,
        older_than_seconds: int,
        skip: Container[str] = (),
        now: float | None = None,
    ) -> list[str]:
        """Delete sessions untouched for `older_than_seconds`; return their ids.

        A run that crashes never calls `reset`, and the root is a tmpfs, so
        without this the container leaks RAM and keeps one customer's draft
        readable to the next session that goes looking. `skip` holds the sessions
        with a command in flight: a long run that only reads leaves its directory
        mtime untouched and would otherwise look abandoned.
        """
        if not self._root.exists():
            return []
        cutoff = (time.time() if now is None else now) - older_than_seconds
        swept: list[str] = []
        for child in self._root.iterdir():
            if child.name.startswith(".") or child.name in skip:
                continue
            if not child.is_dir() or child.stat().st_mtime >= cutoff:
                continue
            shutil.rmtree(child, ignore_errors=True)
            swept.append(child.name)
        return swept
