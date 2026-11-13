# 20 — The customer from the sender's address when group companies share a domain

Status: ready-for-agent (the rule; Proterial's real contacts fill it)
Blocked by: none for the rule; Proterial: each customer's contact addresses for real data
Category: enhancement

## Why

Proterial and nine group companies use one mail domain, and some of them
are customers. A sender's domain cannot tell internal from customer, nor
one group customer from another.

## Shape

- A customer's contacts (addresses) in master data decide first (Bravo
  R01 once its API exists); then the sender ledger (an address Sales
  confirmed, `sender_customers.py`), never against Bravo's contacts; the
  domain decides only where no address matches and the domain is not
  shared (dw_sales ADR 0009 decision 5).
- A shared domain with no matching address: "chưa xác định khách", for a
  person, never a guess.
- The group-companies domain list (Box B37) marks which domains are shared.

## Acceptance

1. Two customers on the shared domain are told apart by address.
2. An unknown address on the shared domain is routed to a person.
