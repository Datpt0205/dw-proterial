---
status: Proposed
date: 2026-11-27
decided: 2026-11-26 by recommendation (Đạt, unattended run): build tickets 80 and 81 only behind a tenant switch that is off by default
owed: Đạt's word to turn it on for a tenant; Proterial's owner of WIV-03-012 step 9
amends: 0004-checker-decisions-on-the-runtime.md, 0015-reversible-steps-apply-themselves-and-corrections-teach.md
---

# A matching read-back from Bravo may pass the cross-check, measured and off by default

## Context

WIV-03-012 step 9 has a second Sales member cross-check the Bravo entry
against the order as approved. Since ticket 51 DW reads the sales order back
from Bravo through the gateway and compares it with the paste sheet, row by
row, confirmed dates included. For an order where nothing else needed a
person, the cross-checker repeats what the comparison already showed (ticket
81, option A). Option B (the second person approves before the write) needs
no switch and is not built.

A read-back proves transcription (sheet to Bravo), not judgement (PO to
sheet). The judgement survives only through the exceptions below, the audit
sample, and a measure taken on the people's own cross-checks first.

## Decision

1. **A tenant switch, off.** `sales_order_rules.cross_check_on_match`
   (1.18.0), false on the platform and in every earlier version, refused
   true without `cross_check_required`, stamped on each case when checked
   (`OrderCase.cross_check_on_match`; None reads as off).
2. **What may pass** (`OrderCase.on_match_exceptions`, each fact read
   directly, never through `makers`): the rules stamped say so; the order
   awaits its cross-check with no decision left unapplied; the read-back is
   Bravo's own (`source = gateway`, never an export a person uploaded), at
   this case version, with no difference; no finding at all, whatever was
   decided; nothing a person typed (a value, a PRV code, PC's dates, a
   customer's change); nothing DW applied by itself (a value or a code under
   ADR 0015, or a password file's values under ticket 80, so the two never
   stack into an order nobody looked at); no revision and no update loop.
   The transition (`cross_checked_on_match`) asks again, where the effect
   happens.
3. **Measured as ADR 0015 measures a step**, carved out of T2 for this one
   approval at T1's target (`autonomy.hand_off_error`, 2%) and audit share:
   `measured_route` over what people decided on the same basis
   (`cross_check_on_match@1.0.0`, a new basis restarting from none). Until
   the people's cross-checks of eligible orders certify the target (149 at
   2%, none wrong), every order stays the cross-checker's; certified, a
   sample still goes to them unannounced; an audit that finds the error
   above target stops it (shadow).
4. **The lane, not a route** (amends ADR 0004, whose "the steps a run takes
   are given only to the graph" holds for every person's decision): the
   worker's `sales_cross_check_on_match` reads each eligible case version
   once, as itself (`system:sales_cross_check_on_match`), stores the
   read-back with its audit row, records the route
   (`sales.order_cross_check_routes`), and on "applied" withdraws the
   pending approval first, then saves the pass with the case version it
   read. A person deciding meanwhile wins; a failed save leaves the order
   awaiting a cross-check with none raised, recovered by "Gửi kiểm chéo lại"
   (ticket 14).
5. **A pass never reads as a person's check**: `cross_checked_by` holds the
   lane's system actor and `cross_checked_on_read_back` the gateway answer's
   hash; the line trail says DW decided it, the confirmation and the portal
   checklist print the copy's "checked automatically" words instead of a
   name, and the reply facts name nobody.
6. **Taken back by a non-maker** with the cross-check scope, before the
   confirmation leaves (`reopen_cross_check`, cross_checked ->
   uploaded_to_bravo): counted as an error, and the order's check is a
   person's from then on (the stamp turns false). It is raised again by
   whoever recorded the Bravo entry, or the head, as any stalled cross-check.

## Consequences

- Nothing changes for any tenant until its own order rules say so.
- Turning it on needs Đạt's word, Proterial's owner of step 9 (whether an
  automated comparison may stand for the second person when nothing is an
  exception, and what the cross-checker checks beyond transcription), and
  ticket 51's acceptance on Bravo UAT (a DWTEST PO read back field by field).
- `compare` covers item code, quantity, unit price, requested date and
  confirmed date per row. The SO header (currency, delivery term, payment
  terms, DocDate) is not compared: before a tenant turns this on, either it
  is compared or the pass names what it covered.
- The PIC is not yet told of a pass by a notice of its own; the order page
  and the trail say it.
