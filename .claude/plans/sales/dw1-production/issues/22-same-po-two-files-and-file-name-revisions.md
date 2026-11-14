# 22 — The same PO in two files that disagree; a revision named by the file name

Status: ready-for-agent
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
