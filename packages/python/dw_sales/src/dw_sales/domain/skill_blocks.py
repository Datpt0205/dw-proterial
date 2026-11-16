"""The one way a skill names what it holds: a block per entry, read by code
(ticket 42, dw_sales ADR 0014).

A skill a fixed step reads (the mail kinds, the document forms, the
hand-offs, the reply drafts) names each entry in its instructions, one block
at the start of a line, its head first::

    - kind: invoice_question
      route: other
      label: Hỏi hoá đơn
      means: the customer asks about an invoice or a payment ...
        (a longer value goes on, indented)

`blocks_of` reads the blocks and refuses anything else in them: a key the
skill does not know, a key said twice, a line that belongs to nothing. What
each key may hold, and which are needed, is the reading skill's to check;
this module only says where a block starts and ends, so every such skill is
written, and read, one way.
"""

from __future__ import annotations

import re
from typing import Final

__all__ = ["blocks_of"]

_KEY: Final = re.compile(r"^[ \t]+([A-Za-z_]+):[ \t]*(.*)$")


def blocks_of(instructions: str, head: str, fields: frozenset[str]) -> list[dict[str, str]]:
    """Every block ``instructions`` holds, each its name under ``head`` and
    the values of ``fields`` it states; empty where it holds none. Raises
    ValueError, saying what is wrong in words, for a block that does not
    read."""
    start = re.compile(rf"^- {re.escape(head)}:[ \t]*(.*)$")
    blocks: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    last: str | None = None
    for raw in instructions.replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        if begun := start.match(line):
            current = {head: begun.group(1).strip()}
            blocks.append(current)
            last = None
            continue
        if current is None:
            continue
        if not line.strip() or not line[0].isspace():
            # A blank line or the next paragraph ends the block.
            current, last = None, None
            continue
        named = f"the {head} {current[head]}"
        field = _KEY.match(line)
        if field is not None and field.group(1) in fields:
            key = field.group(1)
            if key in current:
                raise ValueError(f"{named} says {key} twice")
            current[key] = field.group(2).strip()
            last = key
        elif field is not None:
            raise ValueError(f"{named} has an unknown line {field.group(1)}")
        elif last is not None:
            current[last] = f"{current[last]} {line.strip()}".strip()
        else:
            raise ValueError(f"{named} has a line that belongs to nothing")
    return blocks
