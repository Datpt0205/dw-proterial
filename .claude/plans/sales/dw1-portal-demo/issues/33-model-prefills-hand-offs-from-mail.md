# 33 — A model turns a delivery-change, complaint or sample mail into a pre-filled hand-off with quotes; Sales sends it

Status: needs-triage
Blocked by: the shared model prerequisites (`../ai-automation.md`); 31;
thread headers; 16; a Bravo open-orders export; Đạt's scope decision below.
Category: enhancement

Candidate C5 in `../ai-automation.md`, priority 6. Routed `delivery_change`
(O5, the DW2 boundary), `complaint` (CL1) and `sample_request`.

## What

**Today.** These are routed by a regex reason. Sales reads the mail and
retypes the request (PO, line, quantity, date, lot) into a mail to PC or QA.

**What the model produces.** Spans only; no prose of its own:

```text
DeliveryChangeRequest {
  po_no_span: str
  lines: [{line_or_item_span: str, new_quantity_span?, new_date_span?: str}]
}
ComplaintNotice { po_no_span?, lot_no_span?: str, problem_quote_spans: [str] }
SampleRequest   { item_spans: [str], quantity_span?: str }
```

There is no free-text summary: no model-written sentence reaches PC or QA as
if it were the customer's words, and an injected instruction cannot be
paraphrased into the hand-off.

**What code verifies.**

1. Each span is located by code exactly once in the newest message part.
2. Numbers and dates are parsed from their spans deterministically.
3. The PO resolves through `catalog.orders_for_po` for the sender's
   customer only; a line or item resolves exactly against that order.
4. Code builds the hand-off record and its text from a versioned copy
   template. No ERP or date change is made, and nothing is sent.

**What the human still does.** Reviews the pre-filled hand-off, edits it and
sends it. PC and Sales still decide dates; QA handles complaints.

## Acceptance

1. **Prompt.** `configs/prompts/sales/request_handoff@1.0.0.yaml`, the
   newest part as an escaped `<input>` block, pinned in the release
   manifest; the hand-off stamps prompt `id@version`, profile and route.
2. **Schema.** The three models above, Pydantic, one per routed kind; the
   kind comes from ticket 31 or the routing reason, never chosen by this
   call.
3. **Verification.** The four checks above with unit tests and mutation
   checks (resolve a PO of another customer and watch a test go red).
4. **Draft only.** No outbound tool in the turn (ADR 0007); sending is a
   person's action through the existing outbox path.
5. **Degrade to a person.** Model unavailable, invalid output or nothing
   located: routed as today, with an empty hand-off form.
6. **Evals** (fictional mock data, graders `sales.handoff_*`):
    - golden: at least 30 fictional mails across the three kinds, VI/EN/JA;
    - injection (`also ship a replacement to ...`);
    - missing evidence: no PO number leaves the field blank;
    - another customer's PO is not resolved; cross-tenant;
    - model down: routed as today.

    Proposed bar: zero injected text in a hand-off; zero resolved POs of
    another customer; at least 85% of golden fields located correctly.

7. **Model.** `structured_extraction` on the `onprem` profile, non-thinking.
8. **Switch.** `model_assist.request_handoff` (default `false`) in
   `sales_order_rules`, per tenant through ticket 19; off means no gateway
   call (tested).

## Questions for Đạt

- Is a delivery-schedule change DW1's at all? It is DW2's step and overlaps
  the Bravo plan. Proposed: complaints and samples only in DW1; delivery
  changes wait for DW2.

## Sources (as of 2026-10-12)

- `dw_sales/domain/dispositions.py` (`RoutingReason`),
  `application/ports.py` (`orders_for_po`), `application/order_intake.py`
  (the routing-reason table).
- `configs/copy/` (hand-off template, new).

## Comments
