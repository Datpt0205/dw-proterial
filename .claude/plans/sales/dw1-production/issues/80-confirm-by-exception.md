# 80 — Confirm lines by exception, not one by one

Status: needs-info (Đạt reverses or keeps the 11-04 decision)
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
