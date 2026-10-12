# 32 — A model reads a customer's reply in a case thread and proposes the next step; Sales confirms

Status: needs-triage
Blocked by: the shared model prerequisites (`../ai-automation.md`); thread
headers on `InboundMessage` (deterministic, step 2 in `../ai-automation.md`); 31.
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

## Comments
