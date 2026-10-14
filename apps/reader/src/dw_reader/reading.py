"""One request, read by one throwaway process under the containment budget.

The service process never parses a file. It writes the request into a fresh
directory, starts `python -m dw_reader.child` there through the docgen
sandbox's runner (`dw_docgen.runner.run_command`: `ulimit` before the
command, a wall clock that SIGKILLs the whole process group, a capped output,
a bare environment whose HOME and TMPDIR are that directory), reads the
answer the child wrote, and deletes the directory. Whatever a hostile file
does to the parser, it does it in a process that dies with the request.

The answer is the child's `result.json`, passed through as written: the
caller validates it against the operation's type (`reader_wire`). Without
one, the reply says why, by kind: the clock ran out (``timed_out``), the
process died (``crashed``) or wrote more than an answer may hold
(``refused``). What the process printed is never returned or logged: it may
quote the file. A child that could not apply its limits is an outage, not a
file's outcome (`LimitsUnavailableError`).
"""

from __future__ import annotations

import logging
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Final

from dw_docgen.runner import LIMITS_UNAVAILABLE_EXIT_CODE, run_command
from dw_reader.settings import ReaderSettings
from dw_sales.adapters.reader_wire import Failure, ReaderReply

logger = logging.getLogger("dw_reader")

REQUEST: Final = "request.json"
RESULT: Final = "result.json"


class LimitsUnavailableError(RuntimeError):
    """The reading process refused to start without its limits."""


def child_command() -> str:
    """The command that reads one request, in the interpreter running this
    service (the image's venv). `exec` on POSIX, so the shell that applied the
    limits becomes the reader and nothing sits between it and the clock."""
    if sys.platform == "win32":
        # Tests only: no limits, no `exec`, cmd.exe quoting.
        return f"{subprocess.list2cmdline([sys.executable])} -m dw_reader.child"
    return f"exec {shlex.quote(sys.executable)} -m dw_reader.child"


def read_once(body: bytes, settings: ReaderSettings) -> bytes:
    """The reply to one request (module docstring), as JSON bytes."""
    root = Path(settings.root)
    sink = root / ".service"
    sink.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="read-", dir=root))
    try:
        (work / REQUEST).write_bytes(body)
        ran = run_command(
            child_command(),
            cwd=work,
            sink_dir=sink,
            settings=settings,
            timeout_seconds=settings.read_seconds,
        )
        if ran.timed_out:
            return _failed("timed_out", f"reading took longer than {settings.read_seconds} s")
        if ran.exit_code == LIMITS_UNAVAILABLE_EXIT_CODE:
            raise LimitsUnavailableError("the reading process could not apply its limits")
        answer = work / RESULT
        if ran.exit_code != 0 or not answer.is_file():
            # The length of what it printed, never the text: it may quote the file.
            logger.warning(
                "reading process exited %s, %d characters of output",
                ran.exit_code,
                len(ran.output),
            )
            return _failed("crashed", f"the reading process exited {ran.exit_code}")
        if answer.stat().st_size > settings.max_result_bytes:
            return _failed("refused", "the answer is over the size a reply may hold")
        return answer.read_bytes()
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _failed(failure: Failure, detail: str) -> bytes:
    return ReaderReply.failed(failure, detail).model_dump_json().encode("utf-8")
