# 80 — Confirm lines by exception, not one by one

Status: built behind a tenant switch, off (2026-11-27); turning it on is Đạt's word (needs-info)
Blocked by: none
Category: enhancement (UX, ADR 0015)

## Why

A password-protected PO flags every value; ticket 17 leaves 225 lines to
confirm one by one. Most lines pass every check.

## Proposal

- Only a line failing a check needs the PIC's click; the rest are confirmed
  with one "Xác nhận phần còn lại", recorded per line with the check results.
- A sample (the tenant's audit rate, 3% by ADR 0015) is still shown line by
  line; a correction becomes an example.

## Acceptance

- A PO of 225 lines with 4 failing: 4 clicks plus one; the audit trail names
  every line and the checks it passed.

## Comments

**2026-11-27, built off by default.** Decided by recommendation (Đạt 11-26:
80 and 81 only behind a tenant switch that is off). dw_sales ADR 0015
addendum "a password file's values, by exception" (Proposed).

- What was built is not the proposal's "Xác nhận phần còn lại": that press
  records a person's check on lines nobody looked at, a bulk verification
  ui-quality section 7 forbids. Instead the flag itself is the switch. The
  `opened_with_password` flag exists because ClamAV cannot scan inside the
  file (orders.py, ticket 17), not because the reading is less sure: the
  sandbox reads it with the same layout as any file. So
  `sales_order_rules@1.17.0` adds `password_file`: `every_value` (platform
  value, and what every earlier version reads) keeps Đạt's 11-13 rule;
  `failed_checks_only` takes the flag off every value when the case is opened
  (`PoDocument.with_password_values_as_read`, `OrderIntake._case`), stamps
  `password_values_as_read`, and each value then waits only on a check it
  failed or another flag, as the same file sent without a password. The
  acceptance's "4 clicks" holds; the "plus one" is not needed.
- The case still says the file was opened with a password: the audit's
  `encrypted_file` as before, and the order page's facts row "Tệp có mật khẩu"
  (`OrderView.password_file`). Placed on step O3 (/sales/rules, process
  settings), with Vietnamese words for the field and both values.
- No sample of the passing lines: a sample measures reading accuracy, which
  is not what the flag guards, and a file sent without a password has none.
- Tested (`test_locked_files.py`): under a tenant version saying
  `failed_checks_only`, the locked M01 workbook and M03 PDF raise exactly the
  findings the same files raise sent without a password, carry no
  password flag, and are still named opened with a password on the PO and in
  the audit; a PO stamped taken-as-read refuses a password flag left on a
  value. `test_order_rules.py`: 1.17.0 and 1.16.0 both read `every_value`.
  Mutation: the intake ignoring the switch turns the new test red; the
  intake always applying it turns the existing ticket-17 test red.

Owed (Đạt): the word that the unscanned decrypted bytes may be read with no
person on each value, or a scan of the decrypted bytes in the reader
sandbox first. Until then no tenant version should say `failed_checks_only`.
