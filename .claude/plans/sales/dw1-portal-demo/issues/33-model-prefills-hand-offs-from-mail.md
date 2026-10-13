# 33 — A model turns a delivery-change, complaint or sample mail into a pre-filled hand-off with quotes; Sales sends it

Status: done (2026-10-13, uncommitted; built by the agent with Đạt away, on
his pre-authorisation). Meets the proposed bar: 0 injected text, 0 resolved
POs of another customer, 94.5% of golden fields right (bar 85%). Đạt's
question below (delivery changes in DW1 or DW2) is still open; all three
kinds are built and one table entry turns delivery changes off.
Blocked by: — (built on 31 and the mock catalogue's `orders_for_po`).
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

## As built (2026-10-13)

- **Schemas** (`domain/handoffs.py`): `ModelDeliveryChange` (PO span, lines
  each with a line-or-item span and a new quantity or date span),
  `ModelComplaint` (PO and lot spans, problem quotes), `ModelSampleRequest`
  (item spans, quantity span); one per routed kind (`MODEL_SCHEMAS`), the
  kind always the routing reason (`order_intake.HANDOFF_KINDS`), never this
  call's. `Handoff` holds only what code located, parsed and resolved, and
  the customer's sentences.
- **Verification**: every span located exactly once in the newest part
  (`locate`), a PO or lot as the first whole token (it may also be in the
  subject); `quantity_of` takes exactly one number from its span,
  `line_number_of` a line number ("Dòng 1 (...)" too), dates through the
  existing parser; a quote naming an address, a web address or a phone
  number is dropped (`carries_contact`). The PO resolves to an ERP order of
  the sender's customer (`catalog.orders_for_po`), else to exactly one live
  case of theirs; a line resolves by line number, PRV code, customer code or
  convert-list entry against that order only.
- **Text by code** (`application/handoffs.py`, copy
  `configs/copy/sales_handoffs@1.0.0.yaml`): Vietnamese templates per kind,
  addressed to a team (`pc` for delivery changes and samples, `qa` for
  complaints), the values in fields and the customer's sentences in quotation
  marks. Rendered when the inbox is read (`InboxMessageView.handoff_draft`).
  Migration `a970a6cbac29`: `sales.messages.handoff` (jsonb, its kind equal
  to the routing reason).
- **Draft only**: nothing is sent and nothing changes in Bravo. The inbox
  shows the draft as editable fields with "Chép bản chuyển"; Sales copies it
  into their own mail to PC or QA.
- **Switch**: `model_assist.request_handoff` (platform 1.4.0 off, demo 1.4.1
  on); off means no gateway call (unit-tested).
- **Evals** `sales_handoff@1.0.0`, graders `sales.handoff_*` in
  `dw_sales.evals.handoffs`: 33 golden mails (VI 12, EN 12, JA 9; 73
  fields), 4 injections ("also ship a replacement to ...", "ignore the
  above", a VI instruction, a fake closing tag), 5 missing-evidence cases (no
  PO, another customer's PO, an unknown PO, a PO only in the quoted history,
  the sender's own), cross-tenant, the model down, and the mailbox flow
  (M11, M17, M31, M40 against M01's and M35's cases). CI replays the
  recorded answers with the floor at what was measured (≥ 0.94 fields
  right, 0 invented).

**Measured on the local model** (same set-up, 2026-10-13, run twice):

| Set | Mails | Fields | Right     | Invented | Empty form (to a person) |
| --- | ----- | ------ | --------- | -------- | ------------------------ |
| All | 33    | 73     | **94.5%** | 0        | 12.1%                    |
| VI  | 12    | 25     | 100%      | 0        | 8.3%                     |
| EN  | 12    | 26     | 96.2%     | 0        | 16.7%                    |
| JA  | 9     | 22     | 86.4%     | 0        | 11.1%                    |

- The proposed bar holds: 0 injected text in a hand-off (4 injections, 0
  reached), 0 resolved POs of another customer, 94.5% of fields right
  (bar 85%). By kind (first run): delivery change 87%, complaint 100%, sample 95.2%.
- p50 5.0 s, p95 7.2 s per mail.
- Missing evidence 5 of 5: no PO, another customer's, an unknown one and
  one only in the quoted history all leave the field blank; the sender's own
  resolves. Cross-tenant: tenant B resolves nothing. Model down: routed as
  today with an empty form.
- **Portal flow, live** (same database, after M01 and M35): M11
  `delivery_change` → PO `VLX-PO-2609-0118` (M01's case), no line ("tuần
  46" names none), to PC, 11.1 s; M17 `sample_request` → the item quoted
  «cáp 2 lõi 1.25mm2 (mã BRN-C-0118)», quantity 50, to PC, 7.6 s; M31
  `complaint` → PO `VLX-PO-2608-0102`, lot `LOT-2609-118`, the customer's
  sentence quoted, to QA, 11.4 s; M40 `delivery_change` → PO
  `BRN-PO-2609-052` (M35's case), to PC, 9.3 s. Each draft is the copy
  template's text with "(chưa rõ, Sales điền)" where nothing was located.

**Guards shown red when removed**:

| Guard                                            | Result |
| ------------------------------------------------ | ------ |
| a PO resolves only among the sender's own orders | red    |
| a quote naming a destination is dropped          | red    |
| a value counts only when located exactly once    | red    |
| the tenant switch                                | red    |

## Comments

- 2026-10-13, decided by the agent (Đạt away): all three kinds are built,
  delivery changes included, because the ticket asks for them and the
  hand-off changes nothing in Bravo (PC still decides dates). The question
  below stays open: if delivery changes wait for DW2, dropping
  `delivery_change` from `order_intake.HANDOFF_KINDS` turns them back into a
  plain routing, one line, no migration.
- 2026-10-13, decided by the agent (Đạt away): no outbound path to PC or QA
  exists in DW1 (Acceptance 4's "existing outbox path" sends nothing to a
  department), so "Sales sends it" is: the inbox shows the draft as editable
  fields and "Chép bản chuyển" copies it, and Sales sends it from their own
  mail. The recipients are a team role (`pc`, `qa`) in the copy file, never
  an address.
- 2026-10-13, decided by the agent (Đạt away): the copy is
  `configs/copy/sales_handoffs@1.0.0.yaml` (Vietnamese, one template per
  kind), loaded with the other Sales copy; the draft is rendered when the
  inbox is read, from the stored hand-off, so a new copy version changes
  drafts not yet sent and no stored record.
- 2026-10-13, decided by the agent (Đạt away): a PO may be named in the
  subject and again in the body; it is located as the first whole token
  (a value inside a longer token is not it), so "named twice" is not
  "ambiguous" for a document number. Any other value must be located exactly
  once. A quote that names an e-mail address, a web address or a phone
  number is dropped: it is the shape of "ship a replacement to ...".
- 2026-10-13, decided by the agent (Đạt away): the "Bravo open-orders
  export" the ticket was blocked by is the mock catalogue's
  `orders_for_po`; a PO also resolves to exactly one live order case of the
  sender's, for an order DW1 holds but Bravo does not list yet.
- Open, for Đạt: the question below (delivery changes in DW1 or DW2).
