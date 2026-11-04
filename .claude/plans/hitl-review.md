# Human-in-the-loop review (2026-11-04)

Đạt asked to reduce where a person must act. An audit of DW1 and DW2
(agent, read-only) found 47 such points. Classes: **A** hard rule (money,
approval authority, mail leaving the company, recording in Bravo,
human-in-command): keep. **B** waiting on a live measurement. **C** a
design choice or conservative default code could relax. **D** no
integration (Bravo). The full table is in the session transcript; what to
decide is below. Nothing here is built yet: each line is Đạt's choice.

## Found, not intended (verified in code on 11-04)

1. **DW2's automation lane never runs where deployed.**
   `apps/worker/src/dw_worker/main.py` `build_purchasing_automation` returns
   None when `settings.is_deployed` ("DW2's mocks are refused there"), and it
   is bound to the demo scope. The stored mailbox and the master-data import
   have shipped since, so on UAT or production every DW2 switch, "AI tự làm"
   included, does nothing and a person presses each step. Fix: build the
   lane per tenant with the stored mailbox, deployed or not.
2. **A supplier's order confirmation is announced as a quote**
   (`automation_lane.py`: "Mở hồ sơ ... để DW2 đọc báo giá"): the lane does
   not use `follow_up.named_order`. Comes with 5b.
3. `follow_up.accept_confirmation(only_if_same=True)` has no caller (5b).
4. The demo tenant's DW1 rules (1.5.3) and the platform's 1.9.0 keep every
   model step off, so the four steps that passed their bar on Qwen
   (layout_proposal 0.977, rfq_extraction 0.941, reply_intent 0.971,
   request_handoff 0.986) are unused until the Sales head applies a version
   that turns them on.
5. The platform DW2 rules (`internal_domains: [seller.example]`,
   `bravo_po.mock: true`) refuse real work until Proterial's own are in.

## Done on 2026-11-04 (Đạt: "tự khớp nếu bước không quan trọng, bước
quan trọng người xác nhận; khảo sát lại khi làm thật ở nhà máy")

- Item 1 above: DW2's lane runs where deployed, on the stored mailbox.
- Items 2 and 3: DW2 reads quotes and confirmations on its own (5b,
  `purchasing.md`); a confirmation that differs from the order still goes
  to a buyer. Both readings measured on Qwen for the demo tenant.
- Candidate 4: one press per line for a request DW1 read (quotes only; the
  PO side not done), and a new layout's first PO only (`sales.md` Open).
- Still Đạt's: candidate 2 (DW1's four measured steps on in the tenant's
  rules), candidate 5 (re-measure `message_intent`), item 5 (Proterial's
  own DW2 rules). Re-surveyed at the plant before go-live.

## Top candidates to relax (each Đạt's call)

1. DW2's lane on where deployed (item 1): removes a press at steps 1–8;
   ceilings in code and the service account's scopes still hold.
2. Turn on DW1's four measured steps in the tenant's order rules: each only
   pre-fills or proposes; the person still confirms.
3. DW2 reads supplier mail on its own: quotes already tied to an RFQ (step
   6) and confirmations with zero differences accepted (5b). No money moves,
   no mail leaves.
4. One press to confirm every model-read value found verbatim in the source
   (Q1, O3) instead of retyping each; the first-POs-of-a-new-layout count
   from 3 to 1 (`layout_onboarding.uncertain_first_pos`).
5. Re-measure `message_intent` (0.898 against 0.90): it retires keyword
   routing for unread mail, the largest group of routed messages.

Also C, smaller: auto-close an exact duplicate PO; merge Q9 "submit" into
pricing; DW2 step 1 opens a case flagged "missing budget code" instead of
refusing the mail; escalate to the last tier only on budget findings.
Proterial's: a price tolerance above 0 (DW1 O6, DW2 re-approval), whether
the O9 cross-check applies to every order, `pc_mailboxes` (sales.md).
