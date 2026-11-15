# 32 — Replies drafted by the agent, figures checked by code

Status: done (2026-11-15); the step stays off until a measurement on the plant's model passes (local proxy 0.833 against the 0.85 bar)
Blocked by: 31
Category: enhancement

## Shape

- A draft answer for `asks` and for each step of 29 that writes to the
  customer, from the tenant's mail copy; `figure_check` over every number,
  date and code; recipients chosen by code; sent by a person.

## Acceptance

1. A figure in the draft that no fact supports drops the draft.
2. No amount in a reply that is not about a price.

## Done

2026-11-15, decisions in dw_sales ADR 0012, "Applied to ticket 32".

- **Service** (`application/reply_drafts.py`, `ReplyDrafts`,
  `GET /orders/{id}/reply-draft?kind=…[&message_id=…]`, scope
  `sales.order.prepare`): four kinds, an answer to a customer's reply on the
  order read `asks` (the only draft of it), 6-DW4, 6-DW3 and the
  confirmation (offered exactly while the template draft is,
  `ORDER_GATES`). One call, no tools. Facts by code (`reply_facts`: the
  template's values, never a price, amount or currency); the tenant's own
  letter of the kind as the example (`sales_emails@1.4.0` adds
  `question_answer`); the customer's located `asks` sentences as the
  question. `check_reply`: every figure among the facts (the question is not
  a fact), no amount, no address or link; a dropped draft says why and which
  figures. Recipients: the customer's contacts. Nothing sent or stored.
  Mock copy refused where deployed.
- **Gate**: `ModelStep.REPLY_DRAFT`, `ModelAssist.reply_draft` (off; on in
  the sample tenant's 1.5.2 for tests, off in 1.5.4), placed on O10,
  `BARS[REPLY_DRAFT]` 0.85 on `all.complete`; migration `3aca293b2c92`.
- **Platform**: `figure_check.names_amount` reads "đồng" as money only after
  a number ("đồng ý", "lõi đồng" were dropped as amounts).
- **Prompt** `sales.reply_draft@1.0.0`; **eval** `sales_reply_draft@1.0.0`
  (golden 12 drafts: four kinds in vi/en/ja; injection asking for another
  address, a price and another customer's PO; missing evidence; cross
  customer; cross tenant; no amount; degrade), graders
  `dw_sales/evals/reply_drafts.py`, recorded answers
  `evals/fixtures/cases/sales_reply_draft_recorded.json` replayed in CI.
- **Measured, NOT attested** (local Ollama `qwen3.5-9b-dw`, structured route,
  thinking off, idle machine): 10/12 golden kept and complete (0.833; vi 4/4,
  en 4/4, ja 2/4: thousands separators, and once line 1's quantity given for
  line 2, both dropped by the check); p50 7.3 s, p95 13.9 s a draft; the
  injected and the unanswerable questions were answered without the
  injected address, price or PO and without inventing a lot number.
- **Web**: "Bản AI soạn" beside each template draft it words (files panel)
  and under a customer's reply read as asking (thread card), asked on click;
  the draft with "DW1 đã kiểm: N con số…", or why it was dropped with the
  figures on click, or that the step is off / no model, and the fallback
  (template draft, or Sales answers). `agent-reply.tsx`.
- Tests: `test_reply_drafts.py` (acceptance 1 and 2 both ways, recipients,
  offered states, another order's reply, the gate off/unmeasured, template
  path with the step off, no model, mock copy, scope, tenant, prompt room),
  `test_figure_check.py`, web `agent-reply.test.tsx`,
  `case-replies.test.tsx`.

Remains: the attested run on the plant's model (01); the answer to a
question on a quote case (spec discussion) is orders-only here; a figure
the facts hold but given to the wrong line passes the check (figure_check
checks figures, not attribution): the person reads before sending.
