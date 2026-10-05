# 03 — Quotation core (deterministic) — amendment

Status: done (2026-10-05, amendment)
Blocked by: 01 (including its 2026-10-03 follow-up), 02 item 1 (`anchors.py`)

## What exists (working tree, not yet reviewed or committed)

The existing code:

- `QuotationService` extracts the RFQ (`RfqDocument`, values `Sourced` with a
  `CellAnchor`) and drafts the Design request.
- `SimulatedDesign` invents Design's reply.
- `PriceEvidence` holds own history, other customers' prices (internal), LME
  and copper, and a reference price per `sales_quote_rules@1.0.0`.
- `PricingDecision` records `decided_by`, and `CustomerQuoteDocument` has no
  field for internal data.
- `QuoteCase` runs `received → sent_to_design → design_replied → priced →
pending_approval → approved → sent | declined`, and `approve` refuses the
  pricer (`separate_from_pricer`).

What stays: the types that keep another customer's price out of
customer-facing data, the pricer ≠ approver rule, and "a reference price is
not a decided price". Everything below is a delta.

## Amendments

1. **Anchors (G12).** Use `dw_sales.domain.anchors.SourceAnchor`; delete
   `CellAnchor`. `QuoteRequest._read_from_this_message` becomes "every
   anchor names an attachment of this message".

2. **State machine (G5, G6, G7).** The state names and labels are in
   `packages/python/dw_sales/CONTEXT.md`; this item owns the transitions.
    - Main path: `received → ycbg_drafted → ycbg_recorded → sent_to_design →
design_replied → priced → pending_approval → approved → sent →
master_list_recorded`. `ycbg_recorded` needs the Bravo YCBG number,
      typed by Sales.
    - `design_replied ⇄ spec_discussion`, and `spec_discussion →
sent_to_design` when Design must answer again.
    - `pending_approval → returned(reason, by)`, then `returned → priced`
      with a new decision; the returned decision is kept in history. This
      replaces today's `return_for_repricing`, which goes to
      `design_replied` and drops the price.
    - `declined(reason)` is reachable from every state before `sent`, with
      `reason ∈ not_our_product | design_cannot | customer_rejected_spec |
commercial` plus free text. Today's `Decline.reason` is free text only.
    - Overdue is derived (`now > quote_due` before `sent`), shown as its own
      group (08), and never stored as a status.
    - `case_version` is bumped by every change. A change to price, MOQ or LT
      after submit returns the quote to `priced`.

3. **Design reply as a message (G5).** A Design reply arrives through
   `InboxPort` and is matched by YCBG number only. A match gives the message
   disposition `attached_to_case`; no match routes it
   `design_reply_unmatched`. `SimulatedDesign` moves to `adapters/mock`. Its
   wiring is refused when `settings.is_deployed` (05). The application layer
   no longer names it.

4. **Request completeness (G24).** A missing quantity or required date
   raises `rfq_incomplete` on the line instead of `RfqUnreadableError` for
   the whole file. Its only disposition is `corrected_by_sales`: Sales asks
   the customer in their own mail and types the answer, recorded as
   hand-entered. `quote_due` keeps its anchor and drives the due-date sort
   (08).

5. **Evidence: every factor Sales weighs (G24).** Add:
    - the customer's order history for the item, from `orders_since`;
    - freight, from the `sales_pricing` freight table;
    - management guidance: free text Sales enters, which the approver sees.
      It is internal; no customer-facing type has a field for it.

    The UI labels for these come from `CONTEXT.md`, written in our own
    words.

    The copper component reads `sales_pricing`'s adder per band.

6. **Quotation findings (G24).** Code computes `rfq_incomplete`,
   `price_below_policy_floor`, `price_basis_mismatch` and `above_target_price`
   from `sales_pricing@1.0.0` and the decision, with the dispositions in the
   spec table. A test decides prices that raise `price_below_policy_floor`,
   `price_basis_mismatch` and `above_target_price` (M10 has a target
   price). There is no approval matrix in this slice: which price or
   discount needs whom is owed by Proterial (requirements doc §4 item 5),
   and ticket 12 adds it.

7. **Quotation document and approval (G6).**
    - At submit, build the document data: customer, item, PRV code, BP code
      and spec no. from the Design reply, MOQ, LT, copper basis (fixed, or
      LME band and month), unit price, currency and validity.
    - Stamp `document_sha256` (the canonical JSON of
      `CustomerQuoteDocument`) and `priced_by` (from `decided_by`).
    - `approve` needs, from the service, a caller holding
      `sales.quote.approve`. The approver is not `priced_by`. The document hash must equal
      the stamp, or the approval is refused. The approval records the hash.
      The rendered files (xlsx/PDF) are ticket 06.

8. **Master list and screening (G7).**
    - After `sent`, `master_list_row()` returns the row. When Sales confirms
      it, `QuotationLedgerPort.record` runs and the case moves to
      `master_list_recorded`. The mock ledger adds the quotation to what
      `quotations_valid_on` returns. A production adapter refuses until
      Proterial grants write access.
    - `QuotationService.screening(scope, as_of)` lists codes quoted to a
      customer with no order in the 12 months before `as_of`
      (`orders_since`).

9. **Ports.** Declare `QuotationLedgerPort` in `application/quote_ports.py`.
   It is the narrowest port that fits, with one consumer.

## Acceptance

- Unit tests per transition, including:
    - `declined` from every state before `sent`;
    - `returned → priced` keeps the history;
    - a price change after submit returns the quote to `priced`.
- Design-reply matching: by YCBG number only. A reply quoting an unknown
  YCBG is routed, never attached.
- Approval is refused for the pricer, for a caller lacking
  `sales.quote.approve`, and after the document changed.
- The document's numbers equal the decided terms. No customer-facing type or
  draft contains another customer's price, a reference price, evidence, or
  the management instruction (property test over M10).
- Quote → order loop: after M10's master-list row is recorded, a later PO
  line for that item finds the quotation through `quotations_valid_on`.
- `screening` returns exactly the codes the mock Bravo history implies.
