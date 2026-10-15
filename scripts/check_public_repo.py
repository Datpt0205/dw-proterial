"""No customer data in a tracked file: the public-repo guard (sales ticket 26).

The repository is public and names Proterial and its procedure codes on
purpose. What must never be tracked is Proterial's DATA: real customer names,
PIC names and emails, prices, survey content. The words to look for are that
data, so the list of them cannot live in git either. It lives in a file outside
the checkout, named by `DW_PUBLIC_REPO_DENYLIST`, and in CI it is the
`PUBLIC_REPO_DENYLIST` secret written to a temporary file.

    uv run python scripts/check_public_repo.py            every file git ls-files lists
    uv run python scripts/check_public_repo.py --staged   what the next commit holds

The deny-list is UTF-8, one term per line; blank lines and `#` lines are
skipped. A term matches as a SUBSTRING of a file's text after both are
lower-cased and stripped of diacritics (`Nguyễn` and `NGUYEN` are one word
here, `đ` is `d`), and whitespace inside a term matches any run of whitespace
or underscores, line breaks included. Substring rather than whole word, on
purpose: a name inside an XML run or glued to the next cell is still that name,
and a false alarm costs a minute while a miss is a disclosure. Write terms
specifically (a full name, an email, a price with its separators). A
spreadsheet stores a number without separators, so a price list's entries
belong on the deny-list in that bare form too.

A file's NAME is checked as well as its content: `PO_Nguyen_Van_A.xlsx`
publishes the name as surely as a cell does.

Tracked spreadsheets and PDFs are compressed, so reading their bytes would see
nothing. An Office file (any zip) is read member by member, and a member that
is itself a zip or a PDF (a workbook embedded in a document) the same way, with
XML tags removed; a PDF is read through its text layer. Character references
and `\\uXXXX` escapes (JSON written with `ensure_ascii`, a string literal in
code) are decoded, and a text file with a UTF-16 byte-order mark is read as
UTF-16. A file that cannot be opened and a legacy binary Office file (.xls,
.doc) are findings: an unchecked file is not a clean one. A PDF with no text
layer at all (a scan; the mock M16 is one on purpose, drawn from data in
`generate_attachments.py`, which is scanned) is reported as NOT CHECKED without
failing. Not seen at all: text inside an image, and Vietnamese typed in a
legacy 8-bit font (TCVN3, VNI), which reads as other letters until it is
converted (sales ticket 20, ADR 0010-document-intake-at-real-size-and-format).

A deny-list term that `scripts/public_repo_allowlist.txt` matches whole is a
deliberate public name and is not searched for.

Output never contains a term, only where it was found and which deny-list
line it was. The CI log of a public repository is public too.

It also checks that `.gitignore` covers where Proterial's documents land
locally, and that nothing there is tracked. That check needs no deny-list
and always runs.

Exit 0 clean (or no deny-list on a developer machine: skipped, and it says
so), 1 on a finding, on a deny-list that is missing in CI, unreadable, empty
or inside the checkout.
"""

from __future__ import annotations

import argparse
import html
import io
import os
import re
import subprocess
import sys
import unicodedata
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import chain
from pathlib import Path

DENYLIST_ENV = "DW_PUBLIC_REPO_DENYLIST"
ALLOWLIST = Path(__file__).resolve().parent / "public_repo_allowlist.txt"

# Where Proterial's documents land in a developer's checkout. Each probe must
# be ignored by `.gitignore`; no tracked path may match the paired test.
IGNORED_PROBES = ("docs/design/handoff.pdf", "docs/requirements.docx", "docs/sales/survey.docx")

_MARKS = re.compile(r"[̀-ͯ]")
_XML_TAG = re.compile(r"<[^>]*>")
_U_ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})")
_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # a legacy .xls/.doc/.msg, or an encrypted OOXML file


def normalise(text: str) -> str:
    """Lower-cased, diacritics removed, `đ` read as `d`: how both sides compare."""
    folded = text.casefold()
    if folded.isascii():
        return folded
    return _MARKS.sub("", unicodedata.normalize("NFKD", folded)).replace("đ", "d")


@dataclass(frozen=True)
class Term:
    entry: int  # its line in the deny-list, which is what a finding names
    pattern: re.Pattern[str]


class ConfigError(Exception):
    """The deny-list cannot be used; the check must not pass."""


class UnreadableError(Exception):
    """A file this script cannot turn into text. Its message is fixed wording, never content."""


class UnseenError(Exception):
    """A file that opens and holds no text to check: said out loud, not failed."""


def load_allowlist(path: Path = ALLOWLIST) -> list[re.Pattern[str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [re.compile(line.strip()) for line in lines if line.strip() and not line.startswith("#")]


def load_terms(path: Path, root: Path, allowed: list[re.Pattern[str]]) -> list[Term]:
    resolved = path.resolve()
    if resolved.is_relative_to(root.resolve()):
        raise ConfigError(
            f"the deny-list must live outside the checkout, not at {resolved}: "
            "a list of customer data inside the repo is one `git add` from being published"
        )
    try:
        raw = resolved.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ConfigError(f"{DENYLIST_ENV} names a file that cannot be read ({exc})") from exc
    terms: list[Term] = []
    skipped: list[int] = []
    for number, line in enumerate(raw.splitlines(), start=1):
        term = " ".join(normalise(line).split())
        if not term or term.startswith("#"):
            continue
        if any(allow.fullmatch(term) for allow in allowed):
            skipped.append(number)
            continue
        words = term.split()
        terms.append(Term(number, re.compile(r"[\s_]+".join(re.escape(word) for word in words))))
    for number in skipped:
        print(f"deny-list line {number} is a deliberate public name (allow-list); not searched for")
    if not terms:
        raise ConfigError("the deny-list holds no terms, and a scan for nothing passes everything")
    return terms


def _unescaped_char(match: re.Match[str]) -> str:
    code = int(match.group(1), 16)
    # A control character or half a surrogate pair is left as written.
    return chr(code) if code >= 0x20 and not 0xD800 <= code <= 0xDFFF else match.group(0)


def texts(where: str, data: bytes) -> Iterator[tuple[str, str]]:
    """Every readable text in one file or archive member, as (where, text)."""
    if data.startswith(b"PK\x03\x04"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for member in archive.namelist():
                yield from texts(f"{where}[{member}]", archive.read(member))
    elif data.startswith(b"%PDF"):
        from pypdf import PdfReader  # only when a PDF is scanned

        pages = [page.extract_text() for page in PdfReader(io.BytesIO(data)).pages]
        if not any(text.strip() for text in pages):
            raise UnseenError("a PDF with no text layer, a scan")
        for number, text in enumerate(pages, start=1):
            yield f"{where}[page {number}]", text
    elif data.startswith(_OLE):
        raise UnreadableError("a legacy binary Office file")
    else:
        utf16 = data.startswith((b"\xff\xfe", b"\xfe\xff"))
        text = data.decode("utf-16" if utf16 else "utf-8", errors="ignore")
        xml = where.removesuffix("]").endswith((".xml", ".rels"))
        if xml or text.lstrip("\ufeff").startswith("<?xml"):
            text = _XML_TAG.sub("", text)
        yield where, _U_ESCAPE.sub(_unescaped_char, html.unescape(text))


def scan_file(path: str, data: bytes, terms: list[Term]) -> list[str]:
    """One line per hit, naming the place and the deny-list line, never the term."""
    found: list[str] = []
    try:
        for where, text in chain([(f"{path} (its name)", path)], texts(path, data)):
            normalised = normalise(text)
            for term in terms:
                for match in term.pattern.finditer(normalised):
                    line = normalised.count("\n", 0, match.start()) + 1
                    found.append(f"{where}:{line}: deny-list line {term.entry}")
    except UnseenError as exc:
        print(f"{path}: NOT CHECKED ({exc}); this scan cannot see its content")
    except Exception as exc:  # any parser failure is the same answer: not checked
        why = str(exc) if isinstance(exc, UnreadableError) else type(exc).__name__
        found.append(f"{path}: cannot be read ({why}), so it was not checked")
    return found


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, check=True).stdout


def _paths(output: bytes) -> list[str]:
    return [part.decode("utf-8") for part in output.split(b"\0") if part]


def tracked_files(root: Path) -> Iterator[tuple[str, bytes]]:
    for path in _paths(_git(root, "ls-files", "-z")):
        file = root / path
        if file.is_file():  # deleted in the working tree, not yet in the index
            yield path, file.read_bytes()


def staged_files(root: Path) -> Iterator[tuple[str, bytes]]:
    """What the commit will hold: the index's copy, not the working tree's."""
    names = _git(root, "diff", "--cached", "--name-only", "--diff-filter=d", "-z")
    for path in _paths(names):
        yield path, _git(root, "show", f":{path}")


def gitignore_problems(root: Path) -> list[str]:
    problems = []
    for probe in IGNORED_PROBES:
        ignored = subprocess.run(
            ["git", "check-ignore", "--no-index", "-q", probe], cwd=root, check=False
        )
        if ignored.returncode != 0:
            problems.append(f".gitignore does not cover {probe}")
    for path in _paths(_git(root, "ls-files", "-z")):
        if path.startswith("docs/design/") or (
            path.startswith("docs/") and path.lower().endswith(".docx")
        ):
            problems.append(f"{path} is tracked, and Proterial's documents stay outside git")
    return problems


def run(root: Path, *, staged: bool, environ: dict[str, str]) -> int:
    problems = gitignore_problems(root)
    for problem in problems:
        print(problem)

    named = environ.get(DENYLIST_ENV, "").strip()
    if not named:
        if environ.get("CI", "").lower() in ("1", "true", "yes"):
            print(
                f"FAILED: no deny-list in CI. Set {DENYLIST_ENV}, from the "
                "PUBLIC_REPO_DENYLIST secret, to a file outside the checkout."
            )
            return 1
        print(
            "\n"
            "*** PUBLIC-REPO GUARD SKIPPED: no deny-list on this machine. ***\n"
            f"*** Customer data was NOT checked. Set {DENYLIST_ENV} to a file ***\n"
            "*** outside the checkout to run it here. CI only finds a term ***\n"
            "*** AFTER a push has published it (pull requests and main). ***\n",
            file=sys.stderr,
        )
        return 1 if problems else 0

    try:
        terms = load_terms(Path(named), root, load_allowlist())
    except ConfigError as exc:
        print(f"FAILED: {exc}")
        return 1

    files = staged_files(root) if staged else tracked_files(root)
    findings = [found for path, data in files for found in scan_file(path, data, terms)]
    for finding in findings:
        print(finding)
    scope = "staged" if staged else "tracked"
    print(f"{len(findings)} deny-list hit(s) in {scope} files, {len(terms)} term(s) checked.")
    return 1 if findings or problems else 0


def main() -> int:
    if isinstance(sys.stdout, io.TextIOWrapper) and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--staged", action="store_true", help="scan the index, for a commit")
    args = parser.parse_args()
    root = Path(_git(Path.cwd(), "rev-parse", "--show-toplevel").decode().strip())
    return run(root, staged=args.staged, environ=dict(os.environ))


if __name__ == "__main__":
    sys.exit(main())
