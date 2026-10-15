"""A scanned page read as words with boxes (ticket 27,
ADRs 0009-parser-page-output-with-coordinates and
0010-document-intake-at-real-size-and-format): CPU OCR by Tesseract, Vietnamese
first.

Like the converter (`readers.legacy`), it runs in the reader sandbox's
one-use reading process: `pdftoppm` rasterises the one page, `tesseract`
reads it into TSV (every word with its box and confidence), and both are
that process's children, under its budget and its clock.

What comes back is a page in points, the PDF's own unit, with its words
grouped into lines as Tesseract grouped them, and a line split into cells
where the gap between two words is wider than a word space: the shape the PDF
reader already reads a text layer in (`readers.pdf`), so a scanned PO is read
by the same layout, with the same anchors (a page and a box).

**Nothing read by OCR is taken on trust**: the PDF reader flags every value of
a page it OCRed (`RegionFlag.OCR`), so each is `value_uncertain` until Sales
confirms it, whatever confidence the engine gave. Confidence is kept on the
word only to drop what the engine itself calls noise (below `MIN_CONFIDENCE`).

The engine and its language data are the image's (`tesseract-ocr`,
`tesseract-ocr-vie` from Debian); `tesseract --version` names it on every
reading (`Derivation.tool`). Which page segmentation mode reads the fixture
scans best, and how long and how much memory a page takes, are measured on
the image (ticket 27, "Post-reboot checks"), not assumed here.
"""

from __future__ import annotations

import csv
import io
import itertools
import statistics
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

# Rendering resolution: Tesseract's own advice for body text is 300 dpi.
DPI: Final = 300
POINTS_PER_INCH: Final = 72
# Vietnamese first, English for the labels a foreign customer prints.
LANGUAGES: Final = "vie+eng"
# Tesseract's page segmentation mode 6, "a single uniform block of text",
# keeps a table's row on one line; to be confirmed on the fixtures.
PAGE_SEGMENTATION: Final = "6"
# A word the engine gives less confidence than this is noise (a speck, a rule).
MIN_CONFIDENCE: Final = 30.0
# A gap wider than this many word heights ends a cell.
CELL_GAP: Final = 1.2


class OcrError(Exception):
    """The page could not be OCRed: why, as a code-written sentence."""


@dataclass(frozen=True, slots=True)
class OcrWord:
    text: str
    # The word's box in points from the page's top-left.
    left: float
    top: float
    width: float
    height: float
    line: tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class OcrCell:
    """Words of one line close enough to be one cell, in points."""

    text: str
    left: float
    top: float
    height: float


@dataclass(frozen=True, slots=True)
class OcrPage:
    width: float
    height: float
    # Each line's cells, top of the page first, each line left to right.
    lines: tuple[tuple[OcrCell, ...], ...]

    @property
    def empty(self) -> bool:
        return not self.lines


class PageOcrPort(Protocol):
    """One page of a PDF read by OCR; raises `OcrError` when it cannot be."""

    def tool(self) -> str:
        """The engine and its languages, as it names itself."""
        ...

    def page(self, pdf: bytes, number: int, size: tuple[float, float]) -> OcrPage:
        """Page ``number`` (1-based) of ``pdf``, whose size in points is ``size``."""
        ...


Run = Callable[..., subprocess.CompletedProcess[bytes]]


@dataclass(frozen=True)
class TesseractOcr:
    """`PageOcrPort` by `pdftoppm` and `tesseract` (module docstring). ``run``
    is `subprocess.run`, a test's stand-in otherwise."""

    tesseract: str = "tesseract"
    pdftoppm: str = "pdftoppm"
    seconds: int = 60
    run: Run = subprocess.run

    def tool(self) -> str:
        done = self._call([self.tesseract, "--version"])
        # Tesseract prints its version on stdout or stderr depending on the build.
        said = (done.stdout or done.stderr).decode("utf-8", errors="replace").strip()
        first = said.splitlines()[0] if said else ""
        if not first:
            raise OcrError("Tesseract did not say its version")
        return f"{first} {LANGUAGES}"[:200]

    def page(self, pdf: bytes, number: int, size: tuple[float, float]) -> OcrPage:
        # Under TMPDIR, which the sandbox points at the request's own directory.
        with tempfile.TemporaryDirectory(prefix="ocr-") as workdir:
            return self._page(Path(workdir), pdf, number, size)

    def _page(self, root: Path, pdf: bytes, number: int, size: tuple[float, float]) -> OcrPage:
        source = root / "in.pdf"
        source.write_bytes(pdf)
        image = root / "page"
        self._call(
            [
                self.pdftoppm,
                "-r",
                str(DPI),
                "-f",
                str(number),
                "-l",
                str(number),
                "-singlefile",
                "-gray",
                "-png",
                str(source),
                str(image),
            ]
        )
        done = self._call(
            [
                self.tesseract,
                str(image.with_suffix(".png")),
                "stdout",
                "-l",
                LANGUAGES,
                "--psm",
                PAGE_SEGMENTATION,
                "tsv",
            ]
        )
        return page_from_tsv(done.stdout.decode("utf-8", errors="replace"), size)

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
            raise OcrError("the OCR engine is not installed where this file was read") from missing
        except subprocess.TimeoutExpired as slow:
            raise OcrError(f"OCR of a page took longer than {self.seconds} s") from slow
        if done.returncode != 0:
            raise OcrError(f"{Path(command[0]).name} exited {done.returncode}")
        return done


def page_from_tsv(tsv: str, size: tuple[float, float], dpi: int = DPI) -> OcrPage:
    """Tesseract's TSV of one page rendered at ``dpi``, as a page in points
    of ``size``: its words (level 5) above `MIN_CONFIDENCE`, grouped by the
    line Tesseract put them on, each line split into cells."""
    scale = POINTS_PER_INCH / dpi
    words: list[OcrWord] = []
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        text = (row.get("text") or "").strip()
        if row.get("level") != "5" or not text:
            continue
        try:
            confidence = float(row["conf"])
            box = [float(row[k]) * scale for k in ("left", "top", "width", "height")]
            line = (int(row["block_num"]), int(row["par_num"]), int(row["line_num"]))
        except (KeyError, ValueError):
            continue
        if confidence < MIN_CONFIDENCE:
            continue
        words.append(OcrWord(text, box[0], box[1], box[2], box[3], line))
    by_line: dict[tuple[int, int, int], list[OcrWord]] = {}
    for word in words:
        by_line.setdefault(word.line, []).append(word)
    lines = [
        _cells(sorted(line, key=lambda w: w.left))
        for line in sorted(by_line.values(), key=lambda ws: min(w.top for w in ws))
    ]
    width, height = size
    return OcrPage(width=width, height=height, lines=tuple(lines))


def _cells(words: list[OcrWord]) -> tuple[OcrCell, ...]:
    """A line's words, a new cell wherever a gap is wider than a word space."""
    gap = CELL_GAP * statistics.median(w.height for w in words)
    cells: list[list[OcrWord]] = [[words[0]]]
    for previous, word in itertools.pairwise(words):
        if word.left - (previous.left + previous.width) > gap:
            cells.append([word])
        else:
            cells[-1].append(word)
    return tuple(
        OcrCell(
            text=" ".join(w.text for w in cell),
            left=cell[0].left,
            top=min(w.top for w in cell),
            height=max(w.height for w in cell),
        )
        for cell in cells
    )
