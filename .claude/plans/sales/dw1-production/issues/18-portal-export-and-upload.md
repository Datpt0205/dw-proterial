# 18 — "Tải PO lên" for a file Sales downloaded, and a portal's CSV export

Status: ready-for-agent
Blocked by: none (which customers use portals: owed by Proterial)
Category: enhancement

## Why

Customer 2 sends no PO by mail: a notice says the PO is on its portal, and
Sales downloads a UTF-16, tab-separated CSV that mixes forecast lines with
firm ones, one PO number per line. DW never logs into a customer's portal
(Đạt, 11-13): a person downloads, then uploads to DW1. Today a file Sales
forwards to themselves arrives from an internal address, so DW1 cannot tell
the customer.

## Shape

- "Tải PO lên" on the inbox: a person picks the customer and drops one or
  more files. Each becomes a stored message whose sender is that person,
  whose customer is the one picked (the person's choice, audited), and
  whose files go through the same malware scan, sandbox and reading as
  mail.
- A PO reader for the portal's CSV layout (a layout like any other: the
  tenant's, learned or mapped), reading firm lines only; forecast lines are
  counted and shown, never ordered.
- The notice mail itself is routed "PO trên cổng khách" to the PIC.

## Acceptance

1. An upload as one person for customer 2 opens cases from the firm lines
   only; the forecast count is shown.
2. A person without the right to process the mailbox cannot upload
   (refused at the route, negative test).
3. The same file uploaded twice is stored once.
