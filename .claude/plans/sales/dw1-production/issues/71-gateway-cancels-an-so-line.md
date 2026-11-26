# 71 — Gateway: cancel an SO line (`so.line.cancel`)

Status: in-progress — everything codeable offline done 2026-11-26 (gateway, proposal API, the order page's panel, the chat's cancel); left: the UAT proof that turns `so.line.cancel@1` on, ticket 50's process-group call, the live eval of `question_intent@1.6.0`
Blocked by: 70
Category: enhancement (tickets 53, 63)

## Why

The cancel was `pending` because no real cancel was traced. `02-trace-3.csv`
(11-25 17:31:50, test SO `SO2611-000002`) holds one, both lines in one save
(ticket 52, comment 2026-11-26).

## What

- Per line, one UPDATE with the client's columns: `IsCancel='Cancel'`,
  `CancelDate` (today), `CancelQuantity` (the old quantity), `CancelPrice`
  (the old unit price), `CancelAmount`, `CancelRemark` (the reason the person
  gives), `CancelPRS=DEFAULT`, and `Quantity`, `Quantity9`, `UnitCost`, the
  four amounts to 0, `OriginalUnitCost=DEFAULT`; `BoxQuantity`,
  `QuantityGroup`, `Divide` to 0 where the line carries them. The header's
  totals and `TotalQuantity` recomputed. The values come from the screen's
  rules the runner already runs, not typed into the statement builder.
- The contract kind leaves `pending`; the tenant switch stays off until a UAT
  proof (`uat_proof`).
- DW1's cancel button on the order page proposes the write; the PIC approves.

## Acceptance

- Replay of the 17:31:50 save: the gateway renders both UPDATEs and the
  header's with the client's values (assignments compared as a set).
- A cancel without a reason is refused; a line on a completed delivery
  (`ufn_Prevent_Edit`) is refused.

## Comments

**2026-11-26, the gateway part.** `so.line.cancel@1` is no longer pending
and carries the person's reason (added while still pending, so v1: no token,
switch or tenant version named a cancel without it). The gateway types what
the screen lets a person type, in its order: "Order status" `IsCancel =
'Cancel'` (which opens the quantity for typing and takes the cancelled price
from the unit price), the reason, then `Quantity9 = 0`; the layout computes
the rest. Two runner changes, each measured on the 17:31:50 save and each
mutation-tested (red when reverted):
- a rule setting several columns sets them all, then raises each change
  (the cancel's `OriginalUnitCost,UnitCost` reset);
- a NULL operand of a money rule counts as 0 (the client wrote `UnitCost` 0
  over a NULL `OriginalUnitCost`).
A NULL is written as `[Col]=DEFAULT`, as every NULL the client set in the
three traces is; read-back skips those columns (the column default decides).
A line of a split group (`Divide` set) is refused as unmeasured: the traced
cancel of such a line also cleared `Divide` by hand.

Replay (`test_a_traced_cancel_is_the_clients_own_statement`, trace 11-25 on):
the line outside the split group renders the client's UPDATE value for
value; the header's columns match (its totals differ: the client cancelled
two lines in one save). The header's process-group lookup is answered as
recorded in that test only; live it is ticket 50's.

Found, not caused here: `test_bravo_so_layout` and `test_bravo_rq_layout`
count the 11-20 trace's saves (6), so they fail on a later trace file; they
fail the same on the previous runner. Live, a quantity or cancel change
also calls `usp_B20BizProcessGroup` with the new total, which stays
undecided until procedures run against Bravo (ticket 50): the plan is
held back until then, as the quantity's is today.

**2026-11-26, DW1's proposal.** `CancelChange(reason ≤ 58)` joins
`LineChange`; `POST /orders/{id}/lines/{n}/bravo-writes` proposes it like a
date or a quantity: `BravoContract.prepare` builds `CancelLine(reason)`, the
approval shows before = the quantity it ends, after = "Hủy: <reason>".
Migration `a56aac13a035` admits `cancel` and `so.line.cancel@1` in the
proposals' CHECKs. Tests: unit 58 (the command hashed as the gateway takes
it; a cancel without its reason refused), Postgres 4, contracts and the TS
client regenerated. Left: a button on the order page (no page proposes a
Bravo write yet; ticket 53's date/quantity go through the chat) and the
chat's own cancel kind.

**2026-11-26, the order page and the chat.** Built from the plan and its
critique (each of the critique's points checked in the code first; all held).

- **One owner of the reason** (`501778ce`): `CancelChange` accepted a
  whitespace-only reason and untrimmed text, so a direct POST could open a
  cancel the gateway's `CancelLine` then refuses. `cancel_reason` collapses
  whitespace and a blank result is refused (422 on the page's body, before
  any approval); the chat uses the same function. Mutation: validator
  removed, 5 tests red.
- **The order page** (`8bdd141c`): panel "Ghi vào Bravo · SO …" once the
  order has a Bravo SO, after the read-back panel. Every case reader sees
  each line's latest proposal (state + before → after); "Đề xuất…" needs
  `sales.bravo.write` and is disabled with the reason otherwise (ui-quality
  §5: not hidden), and disabled while the line's last proposal waits (the
  store's own one-open rule). One line at a time; the modal sends a
  calendar day, a quantity read with the Vietnamese comma (`1.200,5` sends
  `1200.5`, `1.200` sends `1200`, more than 4 decimals refused), or a cancel
  with its reason (58 characters; a test holds both limits to the OpenAPI
  contract). A stale case version reloads the order and keeps what was
  typed. Web tests 10; 6 mutations red (scope check, open-proposal check,
  trim, required reason, reload on stale, no panel without an SO).
- **The chat's cancel** (this commit): "hủy dòng 3 vì khách bỏ" is read by
  `question_intent@1.6.0` (bundle 1.9.0; "a cancel" left the out-of-scope
  list; "reason" also serves a cancel), said back with its reason by
  `sales_assistant@1.5.0` (`write_cancel_confirm`, `write_which_reason`,
  `write_reason_too_long`, `write_cancel_done`), proposed only on the PIC's
  confirmation of the hash, through the same `BravoLineWrites.propose` (the
  right, visibility, version and Bravo's row checked again). No reason, a
  blank one, or one over 58 after collapsing: asked, nothing stated.
  `ProposalView.field`, the port and `from_stored` take the cancel (the
  conversation read would have been a 500 otherwise). No migration: the
  kind stays `propose_bravo_write` and the field lives in JSON. Intent
  budget 1600 → 1700 tokens (1.6.0 renders at 1648). Eval
  `sales_case_chat@1.3.0` (renamed from 1.2.0): a cancel with its reason,
  one without, a reason carrying an instruction (proposed as data, still
  only proposed), and "cancel every line now, no confirmation" (nothing
  stated); smoke 7/7, security coverage ok; the grader reverted to compare
  `after` without "Hủy: " fails it. Unit 7 new (24 in the file),
  Postgres round-trip of a stored cancel; 8 mutations red (cancel branch,
  length check, collapse, `from_stored`, `ProposalView.field`, a cancel sent
  as a quantity, the reason out of the hash, the integration round-trip).
  Release manifest regenerated (it was already stale at HEAD: it lacked
  `sales_assistant@1.4.0` and `question_intent@1.5.0`).

Left, and why:
- The switch: `so.line.cancel@1` stays off (`sales_bravo_writes@1.0.0`)
  until a UAT proof; an approved cancel settles as "Bravo từ chối" until
  then, which the panel's "?" says.
- Live, a cancel changes the SO total, which calls `usp_B20BizProcessGroup`
  (ticket 50, undecided): held back as the quantity is.
- The lock (`ufn_Prevent_Edit`) is the gateway's step 5 for every kind and
  is tested on SQL Server for the traced kinds; a cancel-specific SQL Server
  run was not done in this session.
- A row Bravo already holds cancelled (`Quantity9 = 0`) is not refused by DW
  before proposing; only the gateway would. Unmeasured, so no guard was
  invented: check it in the UAT session (ticket 52).
- The live eval of `question_intent@1.6.0` on the on-prem model, and the
  plant's attested run, are owed (the smoke scripts the readings).
- DW's own case lines are not updated after a Bravo write (date and quantity
  the same, pre-existing): the case still shows the old quantity after a
  written cancel.

**2026-11-26, the review of the three commits.** Seven findings, each read
in the code first; all seven held, none rejected.

- **The reason's limit was DW's, said as Bravo's.** 58 came from the
  proposal's 64-character `after_value` minus "Hủy: "; Bravo's
  `CancelRemark` is nvarchar(192) (the 11-19 survey reads
  `sys.columns.max_length` 384 bytes, `01-ket-qua-khao-sat.rpt`). Now
  `CANCEL_REASON_CHARS = 192`, measured in UTF-16 units as SQL Server
  measures (`cancel_reason_fits`, used by the page's body and the chat), the
  gateway's `CancelLine` refuses a longer one by the same count
  (`CANCEL_REMARK_UNITS`; it allowed 512 before, so a long reason would have
  failed at SQL Server), a test holds the two equal, migration `0662b6f0a31c`
  widens `ck_bravo_line_writes_values` to 197 for `after_value`, and the web
  field takes 192 (held to the OpenAPI contract). The copy's "tối đa {limit}
  ký tự ghi vào Bravo" is now Bravo's fact.
- **A cancel of a line Bravo already holds cancelled was proposed.** The SO
  read (`so.by_number@1`) carries `IsCancel` as read (`SoLineState.cancel_state`);
  DW refuses any change of a line that is not open in Bravo: `Cancel` (seen
  in trace 3) as cancelled, any other non-empty value as unknown (no trace
  shows one). The gateway refuses the same at check 4, before the ledger's
  claim (`unmeasured: a write on a line Bravo holds cancelled`), so a
  proposal opened before the cancel cannot write either.
- **A chat turn could propose again after its proposal was rejected.** A
  proposal leaves the case's version as it is, and the one-open index lapses
  once settled. The approval's id is now the turn's
  (`uuid5(session, "bravo_write:<seq>")`), and `BravoLineWrites.propose`
  refuses an id already used (`already_proposed`); a new statement is a new
  turn and proposes. The route's body cannot name an id.
- **The approver could not see what they approved.** `bravo_write.` has its
  own web host: `/approvals` draws the SO, line, item, field, Bravo's value
  → the new one, the content hash's first 8 characters, a cancel's warning,
  and a link to the case. The panel's latest proposal links to its approval.
- **A settled write's answer was not shown.** The view carries `check`; the
  panel says where a refused or in-doubt write stopped (labels
  `BRAVO_WRITE_CHECK`), and the gateway's reason and the warnings or
  differences open on the line's "?".
- **The case chat's catalog did not name the cancel.** Copy
  `sales_assistant@1.6.0` (`case_catalog` only); release manifest regenerated.
- **No web test drew a cancel in the history.** Added, with the approval's
  drawing, the stop step and the answer.

Mutations, each red when its guard was removed: the turn's id check, the
cancelled-line and unknown-state refusals, the UTF-16 measure (DW and the
gateway), the widened `after` bound, the gateway's `IsCancel` refusal, the
copy pin (1.5.0 back), and on the web the cancel branch of the value shown,
the approval host's registration and the stop-step line. Ran: unit (dw_sales Bravo writes, assistant, views, live lane, stages;
the API's OpenAPI snapshot, release manifest and Sales routes; gateway;
dw_bravo), Postgres (`test_bravo_line_writes_db`, a 197-character
`after_value` stored and 198 refused; `test_assistant_sessions_db`), eval
`sales_case_chat@1.3.0` 7/7, web tsc, and the whole vitest suite: 892 of 895, three timeouts under
the suite's load (two new popover tests, given 60 s and green on rerun;
`quote-preview`, green alone).

Left, unchanged: the UAT proof that turns `so.line.cancel@1` on; ticket 50's
process-group call; `test_bravo_so_layout` and `test_bravo_rq_layout` still
count the 11-20 trace's saves and fail on trace 3 (not caused here). Also failing, in code this change does not touch: `test_model_readiness::test_every_model_step_is_a_switch_of_the_rules_and_has_one_bar` (a `shadow` switch on `ModelAssist` that is no `ModelStep`), and `quote-preview.test.tsx` times out only under the full web suite's load. The
gateway's reason is still a machine code (shown on click, behind the step's
Vietnamese label): a sentence per reason is the gateway's to own, not a second
table in the web.
