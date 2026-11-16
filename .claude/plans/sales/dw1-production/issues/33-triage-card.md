# 33 — A triage card for a mail nothing else read

Status: done (2026-11-16): rebuilt under dw_sales ADR 0014; the step ships off (Strata 0.99 on its bar set, not attested)
Blocked by: 31
Category: enhancement

## Shape

- A mail routed `other` gets a card: what it seems to be, which case it
  seems to concern (resolved by code), one step from the closed set; Sales
  takes it or not. The card is advice; the routing stays.

## Acceptance

1. A card never names a case of another customer.
2. Without the step on, the mail is routed exactly as before.

## Done (2026-11-16, rebuilt under dw_sales ADR 0014)

ADR 0014 "Applied 2026-11-16: the triage card and a kind taught from it".

- **The card** (`dw_sales.domain.triage`, `application/triage.py`): a
  message intake still routes `other` carries one where the tenant turns it
  on (`model_assist.triage_card`, `ModelStep.TRIAGE_CARD`, off everywhere,
  T0, bar 0.85 on `golden.card_accuracy`). One call,
  `sales.triage_card@1.0.0`, under the served `mail-kinds` skill (its kinds
  or `none`); the step is the kind's route where a person can take it
  (`TRIAGE_STEPS`); the case is the one live order case the numbers code
  locates lead to, resolved against the sender's customer only. Asked in
  `OrderIntake._with_triage`; not where the tenant's mail kinds already read
  the mail. Stored on the disposition (`MessageDisposition.triage`,
  `sales.messages.triage`, migration `2c91d318f833`).
- **Decided by a person**: `POST /sales/inbox/{id}/triage`
  (`RoutedMailService.decide_card`): take the step, another of the set, or
  dismiss; a reply attaches only to the card's own case (the request names
  no case). Audited, and a labelled case of the step each time (ticket 43's
  store: confirmed / corrected / rejected).
- **Inbox**: `inbox/triage-card.tsx` ("DW1 gợi ý", the kind, the case's PO
  link, "Làm theo", "Bước khác", "Bỏ qua gợi ý"; disabled with the reason on
  someone else's mail); activity counts the step's rows.
- **Eval** `sales_triage_card@1.0.0` (graders `dw_sales.evals.triage`):
  golden (the message intent's 92 residue mails and six card mails in a
  world with three customers' cases), injection (mails asking to be routed
  to approval, sent or attached to another customer's case; a scripted kind
  outside the schema; a taught skill asking for a tool and another
  customer), cross-tenant (acceptance 1: another customer's PO, two cases,
  another tenant), missing evidence, off (acceptance 2: off / below bar /
  model down, processed exactly as before; on, same routing plus the card).
  **Strata, live, 2026-11-16** (qwen3.8-flash-next-q2_0, not attested):
  97/98 golden right (residue 0.989, card mails 1.0), p50 1.65 s, p95
  2.12 s, max 32 s once; no injection moved a mail or named a case.
  Recorded: `evals/fixtures/cases/sales_triage_card_recorded.json`.
- **Tests**: `dw_sales/tests/unit/test_triage_card.py`,
  `dw_sales/tests/integration/test_sales_triage_cards_db.py`, web
  `triage-card.test.tsx`.

## Left

- Attest the step on the plant's model (`run_evals.py --dataset
  evals/datasets/sales_triage_card@1.0.0.json --live onprem --attest`) before
  a company turns it on.
- A card suggests no step for `po`, `quote_request` and `design_reply`
  kinds: those flows open only on a document or a verified Design mailbox;
  the card still says what the mail seems to be.
- Two people deciding one card at the same moment: the second write wins
  (the message log's upsert, as for a reprocessed message); both are
  labelled. A conditional write on an undecided card would close it.

