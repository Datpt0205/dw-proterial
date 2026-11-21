# 53 — SO adjustments written into Bravo under the PIC's user (phase 2)

Status: ready-for-agent (offline against the trace; UAT after ticket 52)
Blocked by: 63 (the gateway), 64 (identity; replaces the hand-made PIC ↔ Bravo user list)
Category: enhancement

## Why

After confirmation, PIC and PC change dates, split lines, cut quantities and
cancel lines (tickets 10 and 29). Typing those changes into Bravo is the
manual step left.

## Shape

- **Through the gateway (ADR 0027, 2026-11-21).** The 11-20 design's staging
  table and Agent job are dropped. Each change is one typed command to the
  gateway, carrying the approval token. The gateway then:
  - checks the PIC's right from Bravo's own permission rows;
  - refuses a line that sits on a CDO (`ufn_Prevent_Edit`);
  - runs the screen's rules (`dw_bravo`);
  - writes exactly what the client writes for that operation (as traced),
    under the PIC's user and the `timestamp` condition;
  - reads the result back.
- **Operations, in order.**
  - "XN giao hàng" (`EstimatedTimeDelivery`), keeping the first confirmed
    date (`OriginalConfirmedDate`).
  - Bulk dates.
  - Split, with `QuantityGroup`, `GroupDivi` and `Divide`.
  - Quantity.
  - Cancel with `IsCancel`; a partial cancel is a split, then a cancel.
- **Validators.** Each operation enforces the screen validators it touches:
  - split totals;
  - cancel quantity;
  - quantity not below what was produced;
  - no edit during approval;
  - no item change after PRS.
- Bravo is updated before the customer is told, in one mail (Đạt, 11-20).
- **Stop.** Any one of these halts writing:
  - IT disables the write login;
  - DW turns the write kind off;
  - the gateway's fingerprint changes.

## Acceptance

For each operation, on UAT:

- the row DW wrote equals the row a PIC typed, in every column but ids and times;
- the `_Log` entry names the PIC;
- a line changed since DW read it is refused;
- a repeated command is ignored;
- a PIC without the right is refused.

## Comments
