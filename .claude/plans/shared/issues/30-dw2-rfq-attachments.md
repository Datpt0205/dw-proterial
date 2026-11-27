# 30 — DW2: an RFQ goes with the PR's drawing and spec

Status: ready-for-agent
Blocked by: none
Category: mail / DW2

## What

§5: "DW2: RFQ kèm bản vẽ, spec". Checked 2026-11-27: not built. The RFQ
job is written with no files (`dw_purchasing/application/rfq_mail.py:349`,
`attachments=()`, and `self.outbox.write(..., ())`), though the outbox port
and the flow take attachments (DW1 sends its drafts with files).

## Design

- The buyer picks, per RFQ, among the PR's stored attachments that were
  scanned clean (`purchasing.mailbox_attachments`, stored with the PR's mail),
  default none; the choice is saved on the RFQ mail row (migration: the
  attachment ids) when it is queued, so the job sends exactly what was shown.
- The lane reads the bytes from object storage and writes them with the job;
  the total is bounded below the flow's 49 MB mail limit (the doc's §5) and
  refused at queue time over it, with the reason.
- An attachment of another case cannot be named (checked at the API).

## Acceptance

- API: an id of another PR, an unscanned or refused file, over the total:
  each refused; another tenant's id 404 (PostgreSQL).
- Lane: the job lists the files and the folder holds them, job last.
- Web: the RFQ panel's file pick and the sent list naming the files.

## Owed

- Đạt: whether a buyer may also upload a file that is not in the PR (a
  second slice: scan and store first).
