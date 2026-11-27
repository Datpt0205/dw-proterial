# 53 — SO adjustments written into Bravo under the PIC's user (phase 2)

Status: in-progress — the date and the quantity built end to end offline (2026-11-21): proposed against Bravo's row, approved by the one person whose Bravo user writes it, signed in the decision, sent by the worker through the gateway. pending: split and creation (script 03c), the existing SO's save context word and the command right (ticket 52), and every UAT acceptance item. Done since: the cancel (ticket 71, 2026-11-26) and the order page's panel "Ghi vào Bravo" (date, quantity, cancel; 2026-11-26), beside the case chat (since 2026-11-22)
Blocked by: 63 (the gateway), 64 (identity; replaces the hand-made PIC ↔ Bravo user list)
Category: enhancement

## Why

After confirmation, PIC and PC change dates, split lines, cut quantities and
cancel lines (tickets 10 and 29). Typing those changes into Bravo is the
manual step left.

## Shape

- **Through the gateway (ADR 0027, 2026-11-21).** The 11-20 design's staging
  table and Agent job are dropped. Each change is one typed command to the
  gateway, carrying the approval token. The gateway then:
  - checks the PIC's right from Bravo's own permission rows;
  - refuses a line that sits on a CDO (`ufn_Prevent_Edit`);
  - runs the screen's rules (`dw_bravo`);
  - writes exactly what the client writes for that operation (as traced),
    under the PIC's user and the `timestamp` condition;
  - reads the result back.
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
- **Stop.** Any one of these halts writing:
  - IT disables the write login;
  - DW turns the write kind off;
  - the gateway's fingerprint changes.

## Acceptance

For each operation, on UAT:

- the row DW wrote equals the row a PIC typed, in every column but ids and times;
- the `_Log` entry names the PIC;
- a line changed since DW read it is refused;
- a repeated command is ignored;
- a PIC without the right is refused.

## Done (2026-11-21, offline)

- **Proposed** (`dw_sales.application.bravo_line_writes.BravoLineWrites.propose`,
  `POST /sales/orders/{case}/lines/{line}/bravo-writes`): the change of one
  line's confirmed date or quantity. DW reads the SO through the gateway
  (`so.by_number`: `B30BizDoc` with `DocCode = 'SO'`, as the client's SO list
  filters in the 11-20 trace; lines by `BizDocId`, with `POLine`, `Quantity9`,
  `EstimatedTimeDelivery`, `timestamp`), takes the one row of the PO line, and
  builds the typed command with that row's rowversion. Refused, opening
  nothing: no right (`sales.bravo.write`), no SO number on the case, the SO
  not in Bravo or under two headers, a PO line Bravo holds as several rows
  (split), a value Bravo already holds, a kind the gateway does not run yet,
  Bravo not answering, a second open proposal for the line.
- **Decided by one person** (approval type `bravo_write.sales_order`,
  required scope `sales.bravo.write`, `makers` empty). **Decision taken here,
  confirmed by Đạt 2026-11-23:** the type is not under `sales.`, whose approvals want a
  second person who made none of the case; ADR 0027 has "the PIC approves the
  exact content", and the write is the approver's own, under their own Bravo
  user, as when they type it into Bravo today. What stops a wrong write is
  the approver's own Bravo user and rights (checked by the gateway), the
  kind's switch (off until UAT proof), and the rules runner.
- **Signed in the decision** (`BravoWriteStamp`, `decision_stamps`): the
  decider's live employee-code link (ticket 64), exactly one active Bravo user
  for it (`user.by_employee_code`), the token over the stored command's hash.
  No signing key, no link, no or two Bravo users, Bravo not answering, or a
  payload whose command no longer hashes as proposed: the decision is
  refused and nothing is recorded.
- **Carried out** (`BravoWriteSettlement`, worker handler for
  `bravo_write.sales_order.decided`): the stored command and the token to the
  gateway; its answer kept on the row (written, refused with the check and
  reason, in doubt, written with differences), audited, and the decider told.
  A gateway error is retried (5xx and no answer); a refusal after a lost
  answer is recorded **in doubt**, since the gateway may have written then.
  A redelivered decision sends nothing again; a rejection and an approval
  without its token send nothing.
- **Store** (migration `af89f3f5d27d`, `sales.bravo_line_writes`): keyed by
  the approval (composite FK, same tenant and workspace), one open proposal
  per line (partial unique index), a settled row names who and when (CHECK),
  kinds a fixed set; RLS forced in the one `sales` shape.
- **Contract**: the application never imports `dw_bravo` (import-linter); the
  adapters `bravo_contract` (build, hash, sign) and `bravo_gateway_client`
  (HTTP) do. The client is tested against the gateway's real HTTP face
  in-process: a write arrives as the very command DW hashed.
- **One tenant's Bravo** (found by the security review of this ticket): the
  gateway reaches one tenant's Bravo, and Sales' client was first built for
  every tenant, so another tenant's case could have read this Bravo's SO
  lines, prices or users. The client is now built for the gateway's tenant
  (`DW_SALES_BRAVO_TENANT_ID`, compose maps the gateway's own) and answers
  "not connected" to any other, sending nothing; every port takes the tenant
  (identity's `BravoPeoplePort` too). Tested, and red when the pin is removed.
- **Every POST names the case version it was made on** (the routes' rule):
  a proposal on an older version is refused.
- **Not connected**: no gateway URL or no signing key (`DW_SALES_BRAVO_GATEWAY_URL`,
  `DW_BRAVO_APPROVAL_SIGNING_KEY`) and every proposal and decision is refused;
  a decided write with no gateway in the worker is recorded refused with that
  reason. A malformed key stops the API at startup.
- **Proven by trace replay**: the gateway's replay (ticket 63) renders the
  client's own UPDATE for the two traced saves of these kinds; the write from
  DW's side arrives as the same typed command.
- Tests: unit 27 (proposal, decision, stamp, settlement), client 6, worker
  handler 6, API key 4, gateway reads 12 + SQL Server 1, PostgreSQL 4; 22
  mutations red (one found a real hole: a 503 on a write was recorded as
  refused instead of retried).

## Comments

**2026-11-26 (ticket 71).** The order page proposes a line's date, quantity
or cancel: panel "Ghi vào Bravo" once the order has a Bravo SO, history for
every case reader, "Đề xuất…" behind `sales.bravo.write` (disabled with the
reason otherwise), one open proposal per line. The chat proposes a cancel
too. Details and what is left: ticket 71's comment of the same day.
