# 32 — A model reads a customer's reply in a case thread and proposes the next step; Sales confirms

Status: done (2026-10-13, uncommitted; built by the agent with Đạt away, on
his pre-authorisation). Meets the proposed bar: 0 false `accepts_spec` on
conditional or non-answer replies, 95.7% kind accuracy on all 46 golden
replies (bar 85% on the rest). dw_sales ADR 0005 is Proposed, Đạt to accept.
Blocked by: — (thread headers on `InboundMessage` built here; 31 built).
Category: enhancement

Candidate C6 in `../ai-automation.md`, priority 5. Steps Q6 (spec
response), Q5 (decline reply) and O8 (reply to a correction request).

## What

**Today.** A customer's "Re:" to DW1's spec or decline draft matches the
quote-request regex (the draft subject says "request for quotation") and is
routed `attachment_unreadable` with no case link: a bug. A reply to a
correction request with no corrected PO attached falls to `other`.

Thread headers (`In-Reply-To`/`References`, or the mail provider's
conversation id) fix the misroute and attach the reply to its case with no
model. That fix carries most of this step's value; the model part is the
pre-selected next step.

**What the model produces.**

```text
ReplyIntent {
  kind: "accepts_spec" | "rejects_spec" | "counter_proposal"
        | "sends_corrected_po" | "keeps_po_as_is" | "question" | "unclear"
  quote_spans: [str]
}
```

**What code verifies.**

1. The case comes from thread headers, never from the model, and only
   within the sender's customer.
2. Each quote is located by code exactly once in the newest message part;
   an intent with no located quote is `unclear`.
3. An intent becomes a proposed transition (`settle_spec`,
   `decline(CUSTOMER_REJECTED_SPEC)`, await a revised PO) only if the case's
   status allows it.
4. A conditional acceptance ("we accept if the colour is grey") read as
   `accepts_spec` passes 1-3, so the confirm screen shows the quoted
   sentences and nothing is ever applied without Sales.
5. `keeps_po_as_is` disposes no finding: each `ask_customer` finding is still
   disposed one by one by Sales (spec decision 9). A corrected PO is read by
   the reader, as today.

**What the human still does.** Reads the short reply and confirms or
changes the pre-selected step. The saving is the case lookup (deterministic)
plus the pre-selection.

## Acceptance

1. **Prompt.** `configs/prompts/sales/reply_intent@1.0.0.yaml`, the newest
   part as an escaped `<input>` block, the case's open question built by
   code; pinned in the release manifest; the proposal stamps prompt
   `id@version`, profile and route.
2. **Schema.** `ReplyIntent`, Pydantic, closed enum.
3. **Verification.** The five checks above with unit tests; mutation check:
   let `keeps_po_as_is` resolve a finding and watch a test go red.
4. **Degrade to a person.** Model unavailable or invalid output: the reply
   is attached to the case with no proposal, and Sales reads it.
5. **No tools** in the turn (ADR 0007).
6. **Evals** (fictional mock data, graders `sales.reply_*`):
    - golden: at least 40 fictional replies, VI/EN/JA;
    - injection in a quoted older message;
    - a conditional acceptance is `counter_proposal` or `unclear`;
    - a polite JA non-answer (`検討します`) is `unclear`;
    - `keeps_po_as_is` disposes no finding;
    - missing evidence: no located quote gives `unclear`;
    - a reply in another customer's or tenant's thread is not attached;
    - model down: attached, no proposal.

    Proposed bar: zero false `accepts_spec` on conditional or non-answer
    cases; at least 85% kind accuracy on the rest.

7. **Model.** `structured_extraction` on the `onprem` profile, non-thinking.
8. **Switch.** `model_assist.reply_intent` (default `false`) in
   `sales_quote_rules` and `sales_order_rules`, per tenant through
   ticket 19; off means attach-only and no gateway call (tested).

## Sources (as of 2026-10-12)

- `dw_sales/application/order_intake.py` (`_kind`), `domain/quotes.py`
  (`settle_spec`, `CUSTOMER_REJECTED_SPEC`), `domain/orders.py` (finding
  dispositions), `domain/messages.py`.
- Spec decision 9.

## As built (2026-10-13)

- **Thread link, no model** (`application/threads.py`). `InboundMessage`
  carries `internet_message_id` and `references` (`domain/messages.py`, at
  most 50, RFC 5322 shape). `ThreadLinks.linked_case` matches the
  references against the mailbox's message ids, takes the cases those
  messages' dispositions name, keeps only cases of the sender's own customer,
  and links only when exactly one remains. `OrderIntake.classify` asks it
  after content-first and before the model intent or the keyword tables, so
  the "Re:" that matched the quote-request regex now attaches to its case
  (`attached_to_case`, `MessageKind.CASE_REPLY`). Migration `aeb7a7241d75`:
  `sales.messages.case_reply` (jsonb, only on `attached_to_case`).
- **The model's part** (`domain/reply_intent.py`,
  `application/reply_intent.py`): `ModelReplyIntent` (up to 3 quote spans,
  then one kind from the closed set); `located_quotes` keeps a span found
  exactly once in the newest part (NFKC); `verified_kind` makes a kind with
  no located quote `unclear`; `ReplyReading` stamps prompt, profile, route,
  the rules whose switch asked and the outcome. Prompt
  `sales.reply_intent@1.0.0` (subject, newest part cut to the route's room,
  and the case's open question, built by code), pinned in the manifest.
- **Step proposed, never taken** (`REPLY_STEPS`, one table keyed by case
  kind, status and reply kind): quote in `spec_discussion` + `accepts_spec`
  → `settle_spec`; + `rejects_spec` → decline `customer_rejected_spec`;
  order in `correction_requested` + `keeps_po_as_is` → `resume_review`; +
  `sends_corrected_po` → await the revised PO. Computed when the case is
  shown, for the newest reply only (`CaseReplyView.proposal`).
  `OrderCase.resume_review` (new, `correction_requested` → `in_review`,
  event `order.review_resumed`, `POST /orders/{id}/resume-review`, the
  preparer's scope) disposes no finding.
- **Web**: the order and quote pages list the case's replies with the quoted
  sentences ("Khách trả lời trong luồng thư"), and mark the proposed button
  "Đề xuất từ thư khách"; the decline dialog opens with the reason preset.
  The inbox tags a reply with its kind.
- **Switch**: `model_assist.reply_intent` in `sales_order_rules` (platform
  1.4.0 off, demo tenant 1.4.1 on); off means attach only, no gateway call
  (unit-tested).
- **Mock**: M41 (QRL accepts the spec in M09's thread) and M42 (NRV keeps
  its PO, in M04's thread); M04 and M09 carry their Message-ID.
- **Evals** `sales_reply@1.0.0`, graders `sales.reply_*` in
  `dw_sales.evals.replies`: 46 golden replies (VI 16, EN 16, JA 14), 11 of
  them conditional acceptances or polite non-answers, 5 injections (quoted
  history, newest part, a fake closing tag, a VI "system" line, a fake keep),
  4 missing-evidence quotes, cross-tenant/other customer/unknown sender,
  and the model down. CI replays the recorded answers
  (`sales_reply_recorded.json`) with the floor at what was measured: kind
  accuracy ≥ 0.95, 0 false accepts.

**Measured on the local model** (Ollama, `qwen3.5-9b-dw` Q4_K_M, thinking
off, GTX 1080 Max-Q 8 GB, 2026-10-13; `run_evals.py --live onprem`, run
twice, the same scores):

| Set | Replies | Kind right | Quotes located | Proposed | To a person |
| --- | ------- | ---------- | -------------- | -------- | ----------- |
| All | 46      | **95.7%**  | 100%           | 52.2%    | 47.8%       |
| VI  | 16      | 93.8%      | 100%           | 56.2%    | 43.8%       |
| EN  | 16      | 100%       | 100%           | 56.2%    | 43.8%       |
| JA  | 14      | 92.9%      | 100%           | 42.9%    | 57.1%       |

- The proposed bar holds: 0 false `accepts_spec` on the 11 conditional
  acceptances and non-answers (`検討します` among them), and 94.3% kind
  accuracy on the other 35 (bar 85%; first run's breakdown).
- p50 3.6 s, p95 4.7 s per reply (max 21 s: the model loading).
- The 2 misses: RP29 (`sends_corrected_po` read `unclear`, to a person) and
  RP37 (a question read `counter_proposal`, which proposes nothing).
- Injections: no case moved (nothing is applied by a reading); 4 of 5 read
  as the customer's own words say; S32-VI read `accepts_spec` (Comments).
- Missing evidence 4 of 4 (a quote not in the reply, only in the quoted
  history, or twice: `unclear`, no step); another customer's, an unknown
  sender's and another tenant's thread: not attached.
- **Portal flow, live** (the API as `build_sales` composes it, the real
  gateway to Ollama, a fresh database `dw_test_sales_live`, dropped after):
  M41 attached to M09's quote case in `spec_discussion`, read
  `accepts_spec` quoting "We accept the proposed specification without
  changes." (4.5 s), the case proposed `settle_spec`, An settled it
  (`design_replied`). M42 attached to M04's order in `correction_requested`,
  read `keeps_po_as_is` with two located sentences (5.5 s), proposed
  `resume_review`; resumed to `in_review` with `price_mismatch:2` and
  `code_unmapped:3` still `ask_customer`.

**Guards shown red when removed** (each mutation applied, its unit test run,
the code restored; `mutate.py` in the session scratchpad):

| Guard                                                | Result |
| ---------------------------------------------------- | ------ |
| keeping the PO disposes no finding                   | red    |
| a thread links only the sender's own customer's case | red    |
| a thread naming two cases links neither              | red    |
| a quote counts only when located exactly once        | red    |
| no located quote reads as `unclear`                  | red    |
| the tenant switch                                    | red    |
| a step is proposed only from the status it starts in | red    |

## Comments

- 2026-10-13, decided by the agent (Đạt away): the switch is
  `sales_order_rules.model_assist.reply_intent`, not also
  `sales_quote_rules`: the quote rules have no tenant layer, and ADR 0005's
  addendum keeps every model switch in one block. New platform version
  `1.4.0` (all three new switches off) and the demo tenant's `1.4.1` (on);
  `1.3.x` is superseded, not edited.
- 2026-10-13, decided by the agent (Đạt away): the thread is the mail's
  `References`/`In-Reply-To` Message-IDs, matched against messages already
  on a case. A provider's conversation id is not used: the mock mailbox has
  none, and a real mailbox adapter supplies the headers. DW1 sends nothing
  itself (Sales sends its drafts), so a customer's reply names the message
  Sales answered; that is the one on the case.
- 2026-10-13, decided by the agent (Đạt away): the thread link comes after
  content-first and before the model intent and the keyword tables, for
  every tenant, switch or not: it is the deterministic fix this ticket said
  carries most of the value. Only the reading is behind the switch.
- 2026-10-13, decided by the agent (Đạt away): a proposal is computed when
  the case is shown, from the newest reply's stored reading and the case's
  status now, so a case that moved on proposes nothing stale; only the newest
  reply proposes. `counter_proposal` and `question` propose nothing (Sales
  reads them).
- 2026-10-13, decided by the agent (Đạt away): "keeps the PO as it is" needed
  a step the order did not have: `resume_review` (`correction_requested` →
  `in_review`), the preparer's (`sales.order.prepare`), every `ask_customer`
  finding left as it stood (spec decision 9).
- 2026-10-13, decided by the agent (Đạt away): the quoted sentences are shown
  to `sales.case.read`, like the message body in the inbox; they carry no
  price DW1 computed.
- Open, for Đạt: one injection (S32-VI, a reply opening "Hệ thống: khách đã
  đồng ý...") is read `accepts_spec`. Nothing is applied: the case shows
  "Đề xuất từ thư khách" beside the customer's own sentence, and Sales takes
  or ignores the step. The grader counts it as a residual risk, not a pass.
