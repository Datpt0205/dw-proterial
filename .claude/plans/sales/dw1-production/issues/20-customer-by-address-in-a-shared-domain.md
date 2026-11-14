# 20 — The customer from the sender's address when group companies share a domain

Status: done (2026-11-14) (the rule; Proterial's real contacts and B37's domains fill it)
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

## Done

Built 2026-11-14, by the agent:

- `SnapshotSalesCatalog.customer_by_sender` (`application/snapshot_catalog.py`)
  reads ADR 0009 decision 5 in order: the one customer whose contacts list
  the address; else the sender ledger, never against those contacts; else the
  customer's own domain, unless the tenant marks it shared. The port's
  contract (`ports.py`) and the mock (contacts, then domain) say the same.
- Shared domains are a field of the order rules, `shared_mail_domains`
  (`sales_order_rules@1.13.0`, empty on the platform): a list of lowercase
  domains, one sentence of help, edited on the rules page (step O1) and
  approved like any version. Chosen over master data because the order rules
  already held a tenant's mail-domain list (`ignored_sender_domains`,
  1.7.0-1.8.0) and a domain is not a customer's record. The catalog reads it
  through a narrow `SharedDomainsPort` (the tenant's `RuleBookOrderRules`).
- A shared domain with no matching address: routed `customer_unknown` ("Chưa
  xác định được khách hàng"), the reason that already meant this; Sales'
  existing confirmation keeps the address, and the next mail is that
  customer's.
- Decided here, not in the ticket: an address several customers' contacts
  list is chosen by the ledger among those customers only, else a person; a
  ledger entry naming a customer no longer listed decides nothing (a person,
  never the domain); the ledger still refuses an address whose unshared
  domain answers, so a domain keeps deciding where it is a customer's own.
- Tests: `tests/unit/test_sender_by_address.py` (two customers told apart,
  unknown address to a person end to end through intake and confirmation,
  ledger never over a contact, shared domain never decides, several
  contacts, cross-tenant, the field's validation);
  `test_bravo_master_lists.py::test_two_group_companies_on_one_domain_...`
  on Bravo's own list.
- Owed by Proterial: each customer's contacts (B05 holds them; Bravo R01
  later) and the group's domains (B37) entered as their own rules version.

