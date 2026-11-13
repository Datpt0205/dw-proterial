# 26 — Thread intents: one closed set, several per message

Status: ready-for-agent
Blocked by: 24
Category: enhancement

## Why

dw_sales ADR 0010 decision 1: replaces ticket 32's `ReplyKind` and its two
waits with one set for every message in a thread, the customer's or Sales'.

## Shape

- `ThreadIntent`: `sends_po`, `requests_change`, `cancels`, `accepts`,
  `rejects`, `asks`, `adds_info`, `sends_rfq`, `unclear`; each with up to
  three quotes code locates in the newest part.
- One table from (case kind, status, intent) to a proposed step; anything
  else proposes nothing.
- A new major version of the reply prompt; the eval dataset grows with
  multi-intent, injection and cross-customer cases.

## Acceptance

1. "We accept line 1, please push line 3 to 25/11" reads `accepts` and
   `requests_change`, each with its own quote.
2. An intent without a located quote is `unclear`.
3. Sales' outgoing `asks` marks the case as waiting on the customer.
