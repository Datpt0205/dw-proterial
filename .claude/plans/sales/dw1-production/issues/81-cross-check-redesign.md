# 81 — Cross-check (O9) without approving the same thing twice

Status: option A built behind a tenant switch, off (2026-11-27); turning it on is Đạt's and Proterial's word (needs-info)
Blocked by: 51 (read-back)
Category: decision → enhancement

## Why

Today the PIC approves the Bravo write and another Sales then cross-checks the
same content; the cross-checker is not told (ticket 78).

## Options

- **A (recommended):** DW reads the SO back from Bravo and compares line by
  line (ticket 51). A match passes; the cross-checker gets only orders with a
  difference, an exception, or the audit sample.
- **B:** keep a person, but before the write: the second person approves the
  write itself, and no check after.

## Acceptance

- The decision recorded in `sales.md`; the chosen path tested (a mismatch
  reaches the cross-checker, a match does not under A).

## Comments

**2026-11-27, option A built off by default.** Decided by recommendation
(Đạt 11-26: 80 and 81 only behind a tenant switch that is off). dw_sales
ADR 0016 (Proposed), with amendments to ADR 0004 and ADR 0015 (one approval
carved out of T2). Option B is not built.

- Switch `sales_order_rules@1.18.0` `cross_check_on_match` (false; refused
  true without `cross_check_required`), stamped on the case when checked
  (`order_cases.cross_check_on_match`, NULL = off), placed on step O9.
- Verdict `OrderCase.on_match_exceptions` reads each fact directly (not
  `makers`, which cannot see a preparer who typed a value): rules stamped
  on; awaiting the cross-check with no unapplied decision; a read-back from
  the gateway (`order_bravo_read_backs.source`; every older row reads
  `export` and never passes) at this version with no difference; no finding
  of any disposition; nothing typed (value, PRV code, PC's dates, customer
  change); nothing DW applied (a gated value or code, a ticket-80 password
  file), so 80 and 81 never stack; no revision or update loop. The
  transition `cross_checked_on_match` asks it again (409 naming the
  exceptions).
- Measured as ADR 0015 (`measured_route`): a person's until the people's
  cross-checks of eligible orders certify `autonomy.hand_off_error` (149 at
  2%), then applied, an unannounced audit sample, or shadow when its audits
  stop it. Counted per basis `cross_check_on_match@1.0.0` in
  `sales.order_cross_check_routes` (migration `d533225350dd`: one row per
  case version, decided once, dw_app without DELETE, RLS in the workspace
  shape, FKs CASCADE with the case), the cross-checker's decision recorded
  `kept`/`returned` in its transaction (`CaseDecisions`), an undo `undone`.
- Worker lane `sales_cross_check_on_match` (every 5 min; built only where
  the worker has a gateway, `cross_check_gateway`): reads each eligible
  version once, through the gateway, as itself; stores the read-back with a
  lane audit row (`system:sales_cross_check_on_match`); on applied withdraws
  the pending approval first, then saves the pass with the version it read.
- A pass never reads as a person's: the trail says `dw`, the confirmation
  mail (`sales_emails@1.7.0`) and the portal checklist
  (`sales_documents@1.4.0`) print "đối chiếu tự động" words, the reply
  facts name nobody, the order page says "DW đối chiếu khớp với Bravo, không
  có người kiểm".
- Undo `POST /orders/{id}/cross-check/reopen` ("Mở lại kiểm chéo"), by a
  holder of `sales.order.cross_check` who made none of the order, before the
  confirmation left: back to `uploaded_to_bravo`, stamps cleared, the case's
  switch off for good, counted as an error; raised again by the recorder or
  the head with "Gửi kiểm chéo lại" (the run needs `sales.order.prepare`
  and the resend's recorder-or-head rule, so the reopener cannot raise it).
- Tests: `test_cross_check_on_match.py` (verdict, transition, stamps,
  reopen, route, rules; 15), `test_cross_check_on_match_lane.py` (match
  passes and never reaches the checker; uncertified stays a person's and is
  measured; sampled and differing go to the checker; switch off reads
  nothing; one read per version, an unanswered read retried; undo counted;
  trail and mail never name a person; 8), `test_cross_check_routes_db.py`
  (Postgres: once, decided once, other workspace/tenant see nothing,
  grants, CHECKs, stamp round-trip; 4), the worker consumer (2),
  `test_privileges.py`. Mutation: each verdict condition, the re-ask in
  the transition, None read as on, the validator, the maker check on
  reopen, the gate's three branches, read-once, lane audit, withdraw,
  gateway source, eligibility, outcome recording (person and undo), the
  trail's `dw`, the mail's words, the worker wiring: each turned a test red.

Owed before a tenant turns it on: Đạt's word; Proterial's owner of WIV-03-012
step 9 (may an automated comparison stand for the second person when nothing
is an exception; what the cross-checker checks beyond transcription); ticket
51's read-back on Bravo UAT and ticket 52's session; the SO header
(currency, delivery term, payment terms, DocDate) compared, or the pass
saying it did not cover it (`compare` covers item, quantity, price, dates per
row); the customer-facing words of `checked_on_read_back` checked by
Proterial (vi/en/ja drafted). Left: a notice to the PIC of a pass (today the
page and the trail say it); the process map draws the
`uploaded_to_bravo -> cross_checked` edge as Sales' only.
