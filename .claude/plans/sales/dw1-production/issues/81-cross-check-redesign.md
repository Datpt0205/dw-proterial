# 81 — Cross-check (O9) without approving the same thing twice

Status: needs-info (Đạt and Proterial)
Blocked by: 51 (read-back)
Category: decision → enhancement

## Why

Today the PIC approves the Bravo write and another Sales then cross-checks the
same content; the cross-checker is not told (ticket 78).

## Options

- **A (recommended):** DW reads the SO back from Bravo and compares line by
  line (ticket 51). A match passes; the cross-checker gets only orders with a
  difference, an exception, or the audit sample.
- **B:** keep a person, but before the write: the second person approves the
  write itself, and no check after.

## Acceptance

- The decision recorded in `sales.md`; the chosen path tested (a mismatch
  reaches the cross-checker, a match does not under A).
