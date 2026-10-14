"""A legacy Office file converted to one the readers read (ticket 27, ADR 0010
decision 2): `.xls` to `.xlsx`, `.doc` to PDF, by LibreOffice headless.

It runs where every reader runs, in the reader sandbox's one-use reading
process (`apps/reader`), so LibreOffice is that process's child: the same
`ulimit` budget, the same process group the wall clock kills, the same
directory that is deleted with the request, no network. On top of that:

- **one throwaway profile per conversion** (`-env:UserInstallation` in the
  request's own directory), so nothing one file leaves in a profile is there
  for the next, and no shared profile lock serialises or wedges them;
- **macros never run**: the profile is written before LibreOffice starts with
  macro execution disabled outright (`DisableMacrosExecution`) and macro
  security at its highest level, and the command adds no filter option that
  could lower either;
- `--norestore --nologo --nodefault --nolockcheck`: no recovery of an earlier
  session, nothing on screen, no document opened but the one given, no lock
  file honoured or left;
- its own clock (`seconds`), under the sandbox's: a conversion that hangs is
  `ConversionError`, which the reader turns into an unreadable file with the
  reason, never a failed run (acceptance 5).

The copy is named by its own sha256 and the converter by its own words
(`soffice --version`), both stamped on what is read from it (`Derivation`).
"""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, Protocol

Legacy = Literal["xls", "doc"]

# What each legacy kind becomes, and LibreOffice's name for that filter.
TARGETS: Final[dict[Legacy, tuple[Literal["xlsx", "pdf"], str]]] = {
    "xls": ("xlsx", "xlsx"),
    "doc": ("pdf", "pdf"),
}

# The profile written before LibreOffice starts: macros disabled outright,
# and macro security "very high" (only trusted, signed macros) should the
# first ever be ignored.
PROFILE: Final = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry"
           xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <item oor:path="/org.openoffice.Office.Common/Security/Scripting">
    <prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop>
  </item>
  <item oor:path="/org.openoffice.Office.Common/Security/Scripting">
    <prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>
  </item>
</oor:items>
"""


class ConversionError(Exception):
    """The file could not be converted: why, as a code-written sentence."""


@dataclass(frozen=True, slots=True)
class Converted:
    """The copy, what it is, and what made it."""

    data: bytes
    kind: Literal["xlsx", "pdf"]
    tool: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


class ConverterPort(Protocol):
    """Converts one legacy file; raises `ConversionError` when it cannot."""

    def convert(self, data: bytes, kind: Legacy) -> Converted: ...


Run = Callable[..., subprocess.CompletedProcess[bytes]]


@dataclass(frozen=True)
class LibreOfficeConverter:
    """`ConverterPort` by LibreOffice headless (module docstring). ``run`` is
    `subprocess.run`, a test's stand-in otherwise."""

    soffice: str = "soffice"
    seconds: int = 90
    run: Run = subprocess.run

    def convert(self, data: bytes, kind: Legacy) -> Converted:
        # Under TMPDIR, which the sandbox points at the request's own directory:
        # the profile and the copy go with the request.
        with tempfile.TemporaryDirectory(prefix="convert-") as workdir:
            return self._convert(Path(workdir), data, kind)

    def _convert(self, root: Path, data: bytes, kind: Legacy) -> Converted:
        target, filter_name = TARGETS[kind]
        profile = root / "profile"
        out = root / "out"
        (profile / "user").mkdir(parents=True, exist_ok=True)
        out.mkdir(parents=True, exist_ok=True)
        (profile / "user" / "registrymodifications.xcu").write_text(PROFILE, encoding="utf-8")
        source = root / f"in.{kind}"
        source.write_bytes(data)
        self._call(self.command(profile, out, source, filter_name))
        made = out / f"in.{target}"
        if not made.is_file() or made.stat().st_size == 0:
            raise ConversionError(f"LibreOffice made no {target} of the {kind} file")
        return Converted(made.read_bytes(), target, self.version())

    def command(self, profile: Path, out: Path, source: Path, filter_name: str) -> list[str]:
        """The conversion's command line: nothing in it lowers macro security."""
        return [
            self.soffice,
            f"-env:UserInstallation={profile.resolve().as_uri()}",
            "--headless",
            "--norestore",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            "--convert-to",
            filter_name,
            "--outdir",
            str(out),
            str(source),
        ]

    def version(self) -> str:
        """`soffice --version`'s first line: the converter, as it names itself."""
        done = self._call([self.soffice, "--version"])
        line = done.stdout.decode("utf-8", errors="replace").strip().splitlines()
        if not line:
            raise ConversionError("LibreOffice did not say its version")
        return line[0][:200]

    def _call(self, command: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
        try:
            done = self.run(
                list(command),
                capture_output=True,
                timeout=self.seconds,
                check=False,
                stdin=subprocess.DEVNULL,
            )
        except FileNotFoundError as missing:
            raise ConversionError(
                "LibreOffice is not installed where this file was read"
            ) from missing
        except subprocess.TimeoutExpired as slow:
            raise ConversionError(f"the conversion took longer than {self.seconds} s") from slow
        if done.returncode != 0:
            raise ConversionError(f"LibreOffice exited {done.returncode}")
        return done
