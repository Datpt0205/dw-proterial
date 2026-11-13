# 25 — Sales' sent mail joins its thread

Status: ready-for-agent (with a fake flow; the real export waits on 23)
Blocked by: 23 for the real link field
Category: enhancement

## Why

dw_sales ADR 0009 decision 3: DW must see what Sales asked and when a
confirmation left, also when Sales answered from Outlook.

## Shape

- A message is outgoing when its sender is the member's own sign-in
  address (resolved by the server), never by the folder name.
- An outgoing message is stored and threaded, never processed into a case,
  never routed, never read for values. Its thread intents may be read
  (ticket 26).
- The mail drop lane reads it like any file; the inbox lists it under its
  thread, marked "Sales gửi".

## Acceptance

1. A sent copy from a PIC's folder is stored, threaded and has no
   disposition of its own.
2. A file whose sender is NOT the member is treated as incoming (the
   folder decides nothing).
