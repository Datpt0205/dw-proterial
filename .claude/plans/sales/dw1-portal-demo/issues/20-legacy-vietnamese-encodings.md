# 20 — Legacy Vietnamese encodings are detected, never read as text (G37)

Status: ready-for-agent
Blocked by: —
Category: enhancement

Split from ticket 12 on 2026-10-12.

## What

Vietnamese documents typed in TCVN3 (ABC) or VNI fonts store bytes that read
as garbage in Unicode ("Cña hµng" for "Cửa hàng"). DW1 today would read such
a PO as text and match attributes against garbage. Nothing detects it
(verified 2026-10-12: no `legacy_encoding` anywhere in `dw_sales`).

## Acceptance

1. The Excel reader detects TCVN3/VNI font names in the cell styles of the
   cells it reads (`.VnTime`, `.VnArial`, `VNI-Times`, … — one list, in one
   place); the PDF reader detects them in the fonts of the pages it reads.
2. A detected document raises a blocking `legacy_encoding` finding (PO
   level), with the anchor of the first affected cell or page. No attribute
   matching runs on text from affected cells.
3. The finding's only dispositions are `ask_customer` or re-upload; there is
   no free-text override. Conversion to Unicode is ADR 0010 decision 3 and
   lands later.
4. One fictional fixture (an xlsx with a `.VnTime` cell) and its eval case;
   the existing fixtures raise no `legacy_encoding`.
5. Removing the detection turns the fixture's test red.

## Out of scope

- Converting the text (ADR 0010 decision 3; a later ticket).
- `.doc`/`.xls` binary formats (ticket 27).

## Sources (as of 2026-10-12)

- `dw_sales/adapters/readers/` (`excel.py`, the PDF reader),
  `domain/order_checks.py`, `domain/orders.py` (finding kinds).
- `docs/adr/0010-document-intake-at-real-size-and-format.md` decision 3
  (Proposed).

## Comments
