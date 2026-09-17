"""Fails on rules that lint and mypy cannot see, for added lines only.

Inherited code carries plenty of what this forbids; requiring a repo-wide
cleanup would block every PR. Checking the diff stops new violations instead.
"""

from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
import unicodedata

# Horn, hook above and dot below are Vietnamese-only; stacking two marks on one
# vowel is too. Single acute or umlaut is not, so French and German pass.
VIETNAMESE_MARKS = {"̛", "̉", "̣"}
EMOJI_RANGES = ((0x1F300, 0x1FAFF), (0x2600, 0x27BF), (0x2B00, 0x2BFF), (0xFE0F, 0xFE0F))
SOURCE_SUFFIXES = (".py", ".yaml", ".yml", ".sh", ".ts", ".tsx", ".md")
# Prose may reference its own sections with the mark; code may not, because
# there the mark only ever pointed into the deleted blueprint.
CODE_SUFFIXES = (".py", ".yaml", ".yml", ".sh", ".ts", ".tsx")
SELF = "scripts/check_hygiene.py"
# Vendored upstream source. These rules are about what THIS team writes; holding
# a third-party tree to them would mean rewriting it on every re-vendor, and the
# rewrite is what makes the next upgrade a merge conflict.
VENDORED = ("vendor/",)


# A quoted span inside a comment is evidence, not prose: the rule is that
# comments are *written* in English, and the measured example a comment cites is
# routinely a Vietnamese name, address or headline. Stripping quoted spans
# before the test keeps the rule and stops it firing on the data that makes a
# comment worth reading.
#
# Backticks count for the same reason and are this repo's inline-code mark: a
# docstring saying which glyph a test asserts on writes it as `ế`, and that is
# the evidence, not a lapse into Vietnamese.
_QUOTED_SPAN = re.compile(r"\"[^\"]*\"|'[^']*'|`[^`]*`")


def _prose(text: str) -> str:
    """The comment with its quoted evidence removed.

    Docstring delimiters are stripped first. A triple quote is three quote
    characters, so the span regex would pair the first two with each other and
    mis-pair every real quote after them.
    """
    without_delimiters = text.replace('"' * 3, " ").replace("'" * 3, " ")
    return _QUOTED_SPAN.sub(" ", without_delimiters)


def is_vietnamese(text: str) -> bool:
    if any(char in "đĐ" for char in text):
        return True
    stacked = 0
    for char in unicodedata.normalize("NFD", text):
        if not unicodedata.combining(char):
            stacked = 0
            continue
        stacked += 1
        if char in VIETNAMESE_MARKS or stacked >= 2:
            return True
    return False


def has_emoji(text: str) -> bool:
    return any(any(low <= ord(c) <= high for low, high in EMOJI_RANGES) for c in text)


def added_lines(base: str) -> list[tuple[str, str]]:
    diff = subprocess.run(
        ["git", "diff", "--unified=0", f"{base}...HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    path = ""
    found: list[tuple[str, str]] = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]
        elif line.startswith("+") and not line.startswith("+++"):
            found.append((path, line[1:]))
    return found


def violations(base: str) -> list[str]:
    problems = []
    for path, line in added_lines(base):
        if not path.endswith(SOURCE_SUFFIXES) or path == SELF:
            continue
        if path.startswith(VENDORED):
            continue
        stripped = line.strip()
        if has_emoji(line):
            problems.append(f"{path}: emoji in file content: {stripped[:60]}")
        if "§" in line and path.endswith(CODE_SUFFIXES):
            problems.append(f"{path}: pointer into a deleted document: {stripped[:60]}")
        is_comment = stripped.startswith("#") or stripped.startswith('"""')
        if path.endswith(".py") and is_comment and is_vietnamese(_prose(line)):
            problems.append(f"{path}: comment must be English: {stripped[:60]}")
    return problems


def main() -> int:
    # Windows consoles default to cp1252, which cannot print the very text
    # this check exists to catch.
    if isinstance(sys.stdout, io.TextIOWrapper) and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/main")
    problems = violations(parser.parse_args().base)
    for problem in problems:
        print(problem)
    print(f"{len(problems)} hygiene violation(s) in added lines.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
