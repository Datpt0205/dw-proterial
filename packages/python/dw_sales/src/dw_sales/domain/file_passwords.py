"""The passwords a locked attachment's own mail may carry (ticket 17).

A customer that locks its PO file with a password writes the password in the
same mail (Đạt, 2026-11-13: DW opens it with the password its own mail
carries). Which words of the mail are the password is not decided here, and
not by a model either: the file decides. These are the **candidates**, found
by the mail's structure alone, and the reader sandbox tries each against the
file until one opens it with its integrity checked
(`dw_sales.adapters.readers.operations`). No keyword table guesses which line
names a password: a line in any language that ends in ``: <value>`` is the
shape a password is written in, and a word of a plausible length is the rest.

**Only the one mail.** The candidates come from the text of the message the
file is attached to, never from another message of its thread or of the
customer. **Never kept.** They are derived again each time the file is
opened, and live as long as one reader request: no column, log line, audit
detail, error, cache key or span carries one (the ticket's acceptance 3,
`tests/unit/test_locked_files.py`).
"""

from __future__ import annotations

import unicodedata
from typing import Final

# How many candidates one opening tries. One wrong try of an Excel file under
# agile encryption (what Excel 2010 and later write, spinCount 100000)
# measured 0.32 s on the development machine (2026-11-13, msoffcrypto-tool
# 6.0.0, `load_key(verify_password=True)`); a PDF's try is milliseconds. 24
# tries are then about 8 s in the worst case, a quarter of the in-process
# reader's 30 s clock and a fifteenth of the sandbox's 120 s, and the opening
# repeats for each operation on the file (read, buyer, each sheet shown).
MAX_PASSWORDS: Final = 24
# The longest candidate: a password a person types from a mail is shorter.
MAX_PASSWORD_CHARS: Final = 64
# The shortest word taken as a candidate when no ``:`` introduces it.
_MIN_WORD_CHARS: Final = 4
# What introduces a value on a line: ASCII and full-width colons.
_COLONS: Final = (":", "\uff1a")


def password_candidates(mail_text: str) -> tuple[str, ...]:
    """The candidates, in the order they are tried, at most `MAX_PASSWORDS`:
    first, for every line, the text after its last colon (ASCII, or the
    full-width U+FF1A Japanese mail writes), stripped; then, for every line,
    each whitespace-separated word of 4 to 64 characters with its trailing
    punctuation stripped. Each once."""
    lines = mail_text.splitlines()
    after_colon = (_after_last_colon(line) for line in lines)
    words = (_word(token) for line in lines for token in line.split())
    found: dict[str, None] = {}
    for candidate in (*after_colon, *words):
        if candidate and len(candidate) <= MAX_PASSWORD_CHARS:
            found.setdefault(candidate)
            if len(found) == MAX_PASSWORDS:
                break
    return tuple(found)


def _after_last_colon(line: str) -> str:
    at = max(line.rfind(colon) for colon in _COLONS)
    return line[at + 1 :].strip() if at >= 0 else ""


def _word(token: str) -> str:
    """The token without its trailing punctuation (a full stop, a comma, a
    closing bracket, in any script), when 4 characters or more remain."""
    end = len(token)
    while end and unicodedata.category(token[end - 1]).startswith("P"):
        end -= 1
    word = token[:end]
    return word if len(word) >= _MIN_WORD_CHARS else ""
