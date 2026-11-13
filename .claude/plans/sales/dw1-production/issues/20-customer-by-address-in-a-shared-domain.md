# 20 — The customer from the sender's address when group companies share a domain

Status: needs-info
Blocked by: Proterial: each customer's contact addresses (or the rule)
Category: enhancement

## Why

Proterial and nine group companies use one mail domain, and some of them
are customers. A sender's domain cannot tell internal from customer, nor
one group customer from another.

## Shape

- A customer's contacts (addresses) in master data decide first; the
  domain decides only where no address matches and the domain is not
  shared.
- A shared domain with no matching address: "chưa xác định khách", for a
  person, never a guess.
- The group-companies domain list (Box B37) marks which domains are shared.

## Acceptance

1. Two customers on the shared domain are told apart by address.
2. An unknown address on the shared domain is routed to a person.
