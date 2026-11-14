# 19 — One mail or one file with several POs opens one case per PO

Status: done (2026-11-14)
Blocked by: 24 (a reply in a multi-PO thread must still link: dw_sales ADR 0009)
Category: enhancement

## Why

Customer 1 sends nine POs in one mail; customer 3 sends two; customer 2's
CSV holds one PO number per line. Today a mail is one case.

## Shape

- Grouping by PO number after reading: each PO number's lines become one
  case, each linked to the same stored message and file, with the lines'
  sources kept.
- A PO number repeated across files of the mail is one PO; the
  disagreement rule is ticket 22.
- The inbox shows the mail once with its cases listed.

## Acceptance

1. A fixture mail with three POs opens three cases whose lines sum to the
   file's lines.
2. Reprocessing the mail opens no second set.

## Done

Built 2026-11-14, by the agent, with ticket 22.

- **Grouping** (`domain/po_groups.py`): after every file is read, lines are
  grouped by PO number, a line's own (`line_po`) or its file's. A file with
  several POs (a portal export) is split into one document per PO, its lines
  numbered 1..n within their PO (as the export numbers its rows), each part
  dated by its own first row (`LinePo.po_date`, export reader 1.1.0), its
  anchors as read; the file's printed total is dropped from a split part
  (it is the whole file's) and its forecast rows are counted on its first
  part only. Intake (`OrderIntake._several`) opens or joins one case per PO
  number, every one on the same stored message.
- **One message, several cases**: `MessageDisposition.more_cases` (the cases
  after the first, in the mail's order), stored in `sales.message_cases`
  (migration `3fcedec4e4f1`, FKs to the message's key and to the case, RLS,
  SELECT/INSERT only). `MessageLogPort.cases_of` returns every case of a
  message, so a reply in its thread reaches all of them (ticket 24's rules:
  named → attached, none named → `reply_to_case` with the cases offered).
  `talk_before`, thread summaries, the inbox's visibility (`_shown`) and the
  overview's ingest time read every case of a message.
- **Idempotency, in the database**: every case of the mail is written in the
  one transaction that records the message's disposition, whose
  (workspace, message_id) key refuses a second processing whole; and a
  message is one revision per PO number
  (`uq_order_revisions_tenant_id_workspace_id_message_id_po_no`, replacing
  "one revision per message", `po_no` a generated column).
- **Inbox**: the mail is one row; its disposition lists its cases by PO
  number (`order_cases`), each a link.
- **Fixture**: the mail `P3` in `tests/unit/test_several_pos.py` carries
  three of the sample set's fictional customer Velatrix's POs (M21, M33,
  M44's files); a synthetic portal export with three PO numbers too.

Decisions the ticket left open:

- **All or nothing.** When one PO of a mail would be routed to Sales (a late
  revision, a revision of a case that takes none, two files that are not one
  PO), the whole mail is routed with that PO named and no case of it opens:
  one message has one disposition, and a half-opened mail would hide the PO
  left out.
- The disposition names a case the mail *opened* first (so its ingest time
  is the message's), else the first in the mail's order.
- PO numbers are grouped as printed (exact text), as `check_history`
  compares them.
- At most 50 POs per message, else routed.
- The audit row of the processing lists the further cases (`more_case_ids`).
