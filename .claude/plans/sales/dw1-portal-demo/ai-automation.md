# DW1: where a model takes work off people

Status: proposal, 2026-10-12. Đạt decides. All six candidates are built
(2026-10-13, uncommitted, Đạt away): 28, 29 and 31, then 30, 32 and 33.

Until 2026-10-13 DW1 called no model. Reading, mapping, checks, files and
emails are deterministic code, and anything unusual is routed to a person.
This file lists the steps where a local model should take over part of that
work, in the order to build them, and what stays with people.

**Built (2026-10-13, Đạt away, on his pre-authorisation):** the shared
prerequisites below ("Before any model step") and ticket 28 (O2 only). The
rules are now dw_sales ADR 0005 (Proposed). Measured on the local
Qwen3.5-9B (thinking off, GTX 1080 Max-Q):

- Golden set (67 lines): the gold code is among the candidates for 71.1% of
  VI/EN lines (VI 65.2%, EN 77.3%) and 50.0% of JA, against a proposed bar of
  80%. 28.9% of VI/EN lines go to a person.
- 0 wrong single candidates, 0 numbers from the model, 0 injection effects,
  3 of 3 missing-evidence lines unmapped.
- About 77 s per 10-line call (p95 94 s), about 7.7 s per line.
- Live portal flow: the whole mailbox processed in 57.5 s, M36 lines 1 and 3
  suggested correctly and confirmed through the API.

Detail, the run-by-run table and the decisions taken: ticket 28's "As built"
and Comments.

**Built next (2026-10-13, same footing):** ticket 29 (Q1, a request for
quotation in the mail body, a PDF's text or the customer's own sheet) and
ticket 31 (O1/Q1 routing, the intent of a message no reader accepted), on
the same local model:

- Ticket 29, 34 golden requests: 94.6% of the stated VI/EN values read into
  the right field (bar 85%), JA 96.0%; every value flagged and confirmed by
  Sales one by one; 0 target prices in price evidence, 0 injection effects;
  p50 15 s, p95 24 s per request.
- Ticket 31, 88 golden messages: 90.9% kind accuracy (bar 90%) against
  27.3% for the keyword tables; 97.6% on the 42 phrasings the tables miss;
  every miss lands on a person; p50 2.7 s per message.
- Live portal flow: the 40-message mailbox in 149.7 s, 15 model calls,
  14,317 input tokens in the one run.

**Built last (2026-10-13, same footing):** tickets 32 (Q5, Q6, O8: a reply in
a case's thread), 33 (O5, CL1, samples: a hand-off draft) and 30 (O3: a new
customer's PO form), on the same local model:

- Ticket 32, 46 golden replies: 95.7% kind accuracy, 0 false
  `accepts_spec` on 11 conditional or non-answer replies (bar: zero, and
  85% on the rest: 94.3%); every quote located; 52.2% propose a step, 47.8%
  go to Sales with no proposal; p50 3.6 s, p95 4.7 s. The thread link that
  attaches the reply needs no model.
- Ticket 33, 33 golden mails (73 fields): 94.5% of fields right (bar 85%),
  0 invented, 0 injected text in a hand-off, 0 POs of another customer;
  12.1% open an empty form; p50 5.0 s, p95 7.2 s.
- Ticket 30, 12 golden forms (171 fields): 98.2% of fields right (bar 90%),
  11 of 12 pre-fills kept, 0 kept with a wrong label, swaps and the order
  date as delivery date refused; p50 9.4 s, p95 9.9 s, once per form. The
  onboarding screen and the approval (a run-less platform approval, dw_sales
  ADR 0004 amendment) work with no model.
- Live portal flow: M41/M42 proposals taken through the case's own steps,
  four hand-off drafts, M43 pre-filled, approved and read with every value
  flagged; the 43-message mailbox processed, 23 model calls, 21,444 input
  tokens.

## The rule every candidate follows

- The model turns language into a typed, validated reading: span text from
  the document and values from closed `Literal` sets. Nothing else.
- Code locates every span exactly once, re-parses every number and date
  from it, resolves every identifier against real data, checks authority and
  acts. A model value is never an identifier, a route, a permission, a
  price or a threshold.
- Every model-read value a person relies on is flagged, and a person
  confirms it. No approval and no finding disposition is dropped.
- Model down, invalid output or a refused check: the step degrades to what
  happens today (routed to a person, "DW1 did not understand"). Budget or
  quota exhaustion is a stop, reported as one.
- Each step has a versioned prompt pinned in the release manifest, a
  Pydantic schema, no tools in the turn (ADR 0007), evals with injection,
  missing-evidence and cross-tenant cases, and a per-tenant switch that
  defaults to off.

## Candidates, in priority order

| #   | Ticket | Step             | Why                                                                                                                                                |
| --- | ------ | ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | 28     | O2, Q1 lines     | Unknown item descriptions recur per line, not per customer; the model reads attributes, code finds the PRV code, Sales picks from a short list.    |
| 2   | 29     | Q1               | RFQs in a mail body, a PDF or a customer's own Excel are typed by hand today; every model-read value is flagged for Sales to confirm.              |
| 3   | 30     | O3               | Every customer form without a layout is typed by hand; the model pre-fills the mapping once per form, on top of a deterministic onboarding screen. |
| 4   | 31     | O1, Q1 routing   | Replaces the keyword tables §6 rules out, only for mail no reader accepted; content decides for a readable document.                               |
| 5   | 32     | Q5, Q6, O8       | Pre-selects the next step from a reply; thread headers (no model) already carry most of the value.                                                 |
| 6   | 33     | O5, CL1, samples | Pre-fills hand-offs to PC/QA with verbatim quotes instead of retyping; draft only.                                                                 |

Lower, not ticketed yet: free-text Design replies (low volume, the price
floor still comes only from the form), a cited summary of a spec thread (a
read aid, no reply prose), PC date replies (overlaps the Bravo plan), a
vision model on scans (OCR plus ticket 30 gives the same), and a shadow
second reader (raised as real flags, it adds confirmations instead of
removing them; shadow measurement only).

## What stays human, and why

- **Price in any form.** Proposing, ranking or adjusting a price, the copper
  floor, freight, price evidence. A customer-stated target price is stored
  as model-read customer input and never reaches price evidence or a later
  prompt.
- **Every approval and checker role.** A model is never the second person.
- **Finding dispositions.** Accepting with a reason, asking the customer,
  clearing or re-grading a flag, and drafting the reason a person signs: a
  model-written justification turns the decision into a rubber stamp.
- **Hidden content.** Whether a hidden sheet, row or same-colour text is
  part of the order. It is also the injection channel.
- **Identifiers, numbers and dates as values.** Customer, case, PRV code,
  quote, YCBG, sales order, owner, recipients; quantities, amounts and
  dates. Code resolves or parses them from a span it located.
- **Revision status, anchors, thresholds and policy.** Facts of the document
  or versioned tenant data that code evaluates.
- **Tenant, workspace, scopes and roles.** From the verified context only.
- **Any outbound effect and any customer-facing prose.** Replies,
  confirmations and quotations stay code-filled templates a person sends.
- **Delivery dates and schedule changes** (PC and Sales), **export control**
  (denial lists, NOC acknowledgement, approvals).
- **Two things better done without a model:** the buyer on forwarded mail
  (exact match on tax id and approved aliases) and unit-of-measure aliases
  (a once-per-customer confirm from the closed conversion set).

## Order to build

1. **Seed the convert list from Bravo sales history** (customer item code to
   PRV code). No model. It removes most O2 lookups for repeat items, and the
   same pairs are the free gold labels for ticket 28.
2. **Deterministic fixes the model tickets lean on:** content-first ordering
   in `_kind` (done with ticket 31); thread headers on `InboundMessage`
   (done with ticket 32: `internet_message_id` and `references`); the RFQ
   `.xlsx` filename gate (done with ticket 29: the bytes decide); the PO
   reader fixes listed in ticket 30 (an optional revision and a currency
   alias done; a blank date and an .xlsx with its PDF print are ticket 34).
3. **A layout-onboarding screen** with layouts stored as tenant data and an
   approval record (the larger half of ticket 30's value, no model). Done
   with ticket 30: `/sales/layouts/new`, `sales.po_layouts`, the
   `sales.layout` approval.
4. **Before any model step** (one change, shared by tickets 28-33):
    - a `dw_sales` ADR that replaces spec decision 13 and the "no model
      call" non-goal;
    - `test_dw1s_graph_takes_no_model` rewritten to assert the real
      invariant: no toolset, typed output, model-read values flagged;
    - `RunContext` carried from the graph node to an application-declared
      port, so the tenant reaches the gateway from the run;
    - an `onprem` model profile: a local OpenAI-compatible server, no
      external fallback, `outbound_allowed_hosts`, a declared
      `max_input_tokens`, and a non-thinking server default (the
      `openai_compatible` provider cannot switch thinking off per call
      today, and a thinking call costs minutes on CPU);
    - a context-overflow refusal is not retried;
    - `configs/prompts/sales/` and a regenerated manifest;
    - a live eval lane outside CI on the local model, recording accuracy
      and latency per document on GPU and on CPU.

    **Done 2026-10-13** (with ticket 28), with these differences:
    - The `openai_compatible` adapter now switches thinking off per route
      (`reasoning_effort: none`), so no server default is needed.
    - The local server is its own provider (`onprem`), apart from the gateway.
    - `max_input_tokens` is not declared, because nothing reads it; code
      bounds each call instead (10 lines). The context-overflow item stays
      open for that reason. **Closed with ticket 29:** `onprem` declares
      6,000 on its structured route, the composition root reads it, and
      tickets 29 and 31 cut or split every call under it.
    - Latency was measured on GPU only, not on CPU.

5. Tickets **28**, **29** and **31**, then **30**, **32**, **33** (all done
   2026-10-13).

Each ticket ships with its switch off for every tenant. A tenant turns one
on through an approved version of its own rules (ticket 19) once that
step's live eval meets its bar.
