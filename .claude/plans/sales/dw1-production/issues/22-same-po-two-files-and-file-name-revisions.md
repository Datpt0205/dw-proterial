# 22 — The same PO in two files that disagree; a revision named by the file name

Status: done (2026-11-14); which file wins is still owed by Proterial (built: neither)
Blocked by: Proterial: which file wins when they disagree (default: neither)
Category: enhancement

## Why

Customer 3 sends a signed PDF and an Excel of the same PO, and their
delivery dates differ. Revisions are marked only by a suffix on the file
name (R, R1, -2, -RE11; "RV" in Box B10's correction thread, 11-14).

## Shape

- Two files of one PO in one mail: both read, compared value by value; a
  difference is a blocking finding naming both values and both sources.
  Neither file wins until Proterial says which does.
- A file-name suffix is a hint for "PO sửa", shown to the person beside the
  PO number, the printed revision and the line comparison, which still
  decide (`check_history`).

## Acceptance

1. The fixture pair with different dates opens one case with a blocking
   finding citing both.
2. `PO123-R1.xlsx` after `PO123.xlsx` is flagged as a likely revision.

## Done

Built 2026-11-14, by the agent, with ticket 19.

- **One case for the same PO in two files** (`po_groups.one_per_po`,
  `print_pairs.one_po` generalised from ticket 34's workbook + print to any
  two files of one PO number): compared value by value, **lines matched by
  line number** (each file's own, or its reading order), the header's date
  and currency, and the total where both print one. Text is compared in one
  Unicode form, single-spaced and casefolded, as ticket 34 did.
- **Neither file wins.** The case holds its lines on the first file (the
  workbook beside a PDF, else the first attached), but each differing value
  is flagged `print_differs` → `value_uncertain`, which is never accepted as
  read: Sales types the value or asks the customer. A new PO-level finding
  `files_disagree` (error; order rules 1.12.0; migration `3fcedec4e4f1`
  admits the code) names both files and, per value, where each prints it and
  what (`M45-A1: line 1 requested_date 2026-11-16 [PO!H10]` /
  `M45-A2: line 1 requested_date 2026-11-23 [p1]`); an amount is cited by
  field and place only, since the finding is shown to readers who may not
  see prices. Allowed: accepted (with a reason, once Sales settled the
  values) or ask the customer. Both values are also kept on each difference
  (`PrintDifference.ours`/`theirs`) and shown on the case's second-file
  notice.
- Two files of one PO number that print other revisions or other line
  numbers, or three files of one PO number, route the mail to Sales with why.
- **File-name revision hint** (`domain/revision_hints.py`,
  `PoDocument.name_revision`, shown as "Tên tệp gợi ý PO sửa: R1" beside
  Rev. on the case): read only from what follows the PO number in the file's
  name: `R`/`RV`/`RE`/`REV` with up to three digits, or one or two digits
  alone; anything else suggests nothing. It decides nothing: acceptance 2's
  `…-R1.xlsx` with the same printed revision and lines is still a
  `duplicate_po`, shown with the hint.
- Labels: `files_disagree` in CONTEXT.md and `labels.ts`; the
  `print_differs` flag now reads "Tệp thứ hai của PO ghi khác".

Owed: Proterial's answer on which file wins (then a tenant rule, not code).
