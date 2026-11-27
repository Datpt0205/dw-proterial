# 23 — Attach a file in the chat: scanned, read in the sandbox, shown as a file

Status: ready-for-agent
Blocked by: 17 (the `file` block)
Category: chat / files

## What

§1: "Đính kèm file trong chat (qua quét virus và sandbox đọc file)" (L) and
§7 "Đọc file khách trong sandbox: đường đính kèm từ chat". Checked
2026-11-27: not built. The pieces exist: the malware port and ClamAV
(`dw_platform/application/malware.py`, `adapters/clamd.py`), the `reader`
container (`apps/reader`), the queued-file pattern (Sales ticket 25: a file is
read by the worker, never awaited by a request). Slice 1 of 2; ticket 24
lets the answer use the text.

## Design

- **Upload:** `POST /api/v1/sales/{kind}/{id}/chat/files` (multipart, case
  readers) stores the bytes under an object key with tenant and workspace,
  limits from `attachment_ingest` (size, types), and records
  `sales.chat_files` (case, turn, uploader, name, size, state
  `scanning|ready|refused`, reason; migration, RLS forced, workspace shape).
- **Worker:** a lane scans (ClamAV first), then reads it in `reader` and keeps
  the text beside the row; a refusal keeps its reason. The API never parses.
- **The `file` block** (in `chat_blocks`): name, size, state, a download link
  that re-checks access, the refusal reason in words.

## Acceptance

- API: over the limit or a refused type is 422 before storage; a case the
  caller cannot read is 404; another tenant's file id 404 (PostgreSQL).
- Worker: an EICAR test file ends `refused` with its reason and is never sent
  to `reader`; a PDF ends `ready` with its text.
- Vitest: the file block's three states.
- import-linter: no parser imported into `dw_api` (the existing contract).

## Owed

- none.
