# 03 — Quotation core (deterministic)

Status: ready-for-agent
Blocked by: 01

## What

- Extract a quote request (customer, item description, qty, target price,
  date) from the mock message.
- Design request draft; simulated Design reply (BP code, spec number).
- Price evidence: quote history, prices to other customers (internal only),
  current LME, policy band; a reference price only if the mock policy defines
  a rule. Sales enters the decided price.
- Quote case state machine: received → sent_to_design → design_replied →
  priced → pending_approval → approved → sent | declined.

## Acceptance

- Unit tests for evidence and state transitions; a customer-facing draft never
  contains another customer's price.
