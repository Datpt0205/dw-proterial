"""Which values of a PO written in the mail may apply themselves (ticket 44;
Đạt, 2026-11-18, "1 theo đề xuất").

`po_body_extraction` reads every value of such a PO, each flagged
`model_read` and so a `value_uncertain` Sales settles. A value may apply
itself only where code's own checks leave nothing for a person to weigh:

- **The PO's own values** (`po_no`, `revision`, `po_date`, `currency`,
  `delivery_term`), where no open finding of the PO, other than its own
  `value_uncertain`, stands: a duplicate, a currency or a term the customer's
  master data disagrees with, and every other PO-level finding keeps all of
  them a person's.
- **A line's `unit_price`**, only where it equals the quotation the line was
  checked against, in its currency and unit; **its `quantity`**, only where
  the item master states both the MOQ and the pack multiple, so both checks
  ran; and either only where no open finding of the line, other than its
  `value_uncertain`, stands.
- **Everything else** (a line's code, description, unit, dates, amount; the
  total) stays a person's: fail closed until decided otherwise.

This says only whether a value may be put to the gate. Whether it then
applies itself is the gate's (`autonomy.gate_route`: its confidence against
the step's certified threshold, the audit sample).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Final

from dw_sales.domain.orders import FindingCode, OrderCase, RegionFlag

PO_VALUES: Final = frozenset({"po_no", "revision", "po_date", "currency", "delivery_term"})
LINE_VALUES: Final = frozenset({"unit_price", "quantity"})


def model_read_values(case: OrderCase) -> Iterator[tuple[int | None, str, float | None]]:
    """Each value a model read on ``case``: the line (None: the PO's own),
    the field and its confidence. The total is left out: it is never put to
    the gate."""
    for flag in case.header.flags:
        if flag.flag is RegionFlag.MODEL_READ:
            yield None, flag.field, flag.confidence
    for line in case.lines:
        for flag in line.po_line.flags:
            if flag.flag is RegionFlag.MODEL_READ:
                yield line.line_no, flag.field, flag.confidence


def _other_open(case: OrderCase, line_no: int | None) -> bool:
    """Whether a finding of ``line_no`` (None: the PO's own) other than a
    value read uncertainly is still open."""
    return any(
        f.is_open and f.line_no == line_no and f.code is not FindingCode.VALUE_UNCERTAIN
        for f in case.findings
    )


def may_apply_itself(case: OrderCase, line_no: int | None, field: str) -> bool:
    """Whether ``field`` (of line ``line_no``, None: of the PO) may be put to
    the gate (module docstring). Never for a PO a file was read from."""
    if not case.document.from_message:
        return False
    if line_no is None:
        return field in PO_VALUES and not _other_open(case, None)
    if field not in LINE_VALUES or _other_open(case, line_no):
        return False
    line = case.line(line_no)
    po_line = line.po_line
    if field == "unit_price":
        quoted = line.basis.quotation
        return (
            quoted is not None
            and quoted.unit_price == po_line.unit_price
            and quoted.currency == case.header.currency
            and (quoted.uom is None or quoted.uom == po_line.uom)
        )
    item = line.basis.item
    return item is not None and item.moq is not None and item.pack_multiple is not None
