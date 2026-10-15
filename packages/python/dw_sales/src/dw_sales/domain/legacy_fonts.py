"""Vietnamese typed in a legacy 8-bit font: TCVN3 (ABC) or VNI.

Before Unicode, Vietnamese was typed with fonts that draw its letters at the
code points of other characters. A cell typed "Cửa hàng" in `.VnTime` holds
"Cña hµng": the file is right on screen, in that font, and wrong as text. A
reader that took the text would match attributes against garbage, so such a
value is detected by the font it was typed in and never read as text
(ticket 20). Converting it to Unicode is ADR 0010-document-intake-at-real-size-and-format decision 3
(`docs/adr/0010-document-intake-at-real-size-and-format.md`), later.

The font's name says which encoding its bytes are in. This is the one list
of them; both PO readers and the RFQ reader ask it (`legacy_encoding`).
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Final


class LegacyEncoding(StrEnum):
    TCVN3 = "tcvn3"
    VNI = "vni"


# A family's name by its prefix, casefolded. TCVN3 (ABC) fonts are named
# `.Vn<face>` (`.VnTime`, `.VnTimeH`, `.VnArial`, `.VnArialH`, …), VNI fonts
# `VNI-<face>` (`VNI-Times`, `VNI-Helve`, `VNI-Aptima`, …): a prefix covers
# every face and its bold, italic and capitals cuts, which a list of names
# would have to enumerate and would miss one of.
_PREFIXES: Final[Mapping[str, LegacyEncoding]] = MappingProxyType(
    {".vn": LegacyEncoding.TCVN3, "vni-": LegacyEncoding.VNI}
)


def legacy_encoding(font_name: str | None) -> LegacyEncoding | None:
    """The legacy encoding a font draws Vietnamese in, or None for any other font.

    ``font_name`` is the family as the file names it (a cell's font, a PDF
    font's base name without its subset tag).
    """
    if not font_name:
        return None
    name = font_name.strip().casefold()
    return next((enc for prefix, enc in _PREFIXES.items() if name.startswith(prefix)), None)
