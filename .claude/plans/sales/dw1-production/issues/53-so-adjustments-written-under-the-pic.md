# 53 — SO adjustments written into Bravo under the PIC's user (phase 2)

Status: needs-info (the Bravo vendor approves the procedure; Proterial confirms in writing)
Blocked by: 49, 52, the PIC ↔ Bravo user list
Category: enhancement

## Why

After confirmation, PIC and PC change dates, split lines, cut quantities and
cancel lines (tickets 10 and 29). Typing those changes into Bravo is the
manual step left.

## Shape

- **Staging.** DW stages one approved command per change. The login
  `dw_write` holds INSERT on `GetData.dw.lenh_ghi`, SELECT on `dw.ket_qua`,
  and nothing on Bravo. Each command carries:
  - an idempotency key;
  - the line's `timestamp` when DW read it;
  - the PIC's Bravo user id;
  - the approval id and the content hash.
- **The job.** An Agent job runs `dw.usp_ApDungLenhGhi` every minute. For each
  command it:
  - checks the PIC's right with `usp_sys_GetControlPermission`;
  - refuses a line that sits on a CDO (`ufn_Prevent_Edit`);
  - sets `Context_Info` in the client's format, with the PIC's id;
  - writes exactly what the client writes for that operation (as traced),
    under the `timestamp` condition;
  - records the result.
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
- **Stop.** Any one of these halts writing: IT disables the job, DW turns its
  flag off, or `dw_write` is revoked.

## Acceptance

For each operation, on UAT:

- the row DW wrote equals the row a PIC typed, in every column but ids and times;
- the `_Log` entry names the PIC;
- a line changed since DW read it is refused;
- a repeated command is ignored;
- a PIC without the right is refused.

## Comments
