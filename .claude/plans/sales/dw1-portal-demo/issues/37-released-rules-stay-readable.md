# 37 — Every released rules version stays readable after a deploy

Status: done (2026-10-14; Đạt chose "keep every released version" on 2026-10-14; built and mutation-checked by the agent)
Blocked by: —
Category: enhancement

## What

A case stamps the rules it was checked under (`sales_order_rules@x.y.z`, a
quotation's `sales_quote_rules@x.y.z`, a file's copy version), and a later
step reads the stamp, so its result does not move under the people working
it. The platform layer held only the version each file currently pins, so a
deploy that moved `sales_order_rules` from 1.4.0 to 1.5.0 left every case
checked under 1.4.0 answering 409 `rules_version_gone` on its next recheck.

Measured before the change: the files 1.1.0–1.4.0 were still in the checkout,
but none loaded under today's `OrderRules` (each later version added a
required field: `model_assist`, `layout_onboarding`, a severity per new
finding code), and the 1.0.0 files of the order and quote rules had been
deleted after a release manifest pinned them. The same schema change would
also have made a tenant's own approved version unreadable: `current()`
validated the stored document under today's schema, so the first required
field added after a tenant approved its version would stop DW1 for that
tenant.

## Acceptance

1. Every platform version of each overridable key in the checkout is held by
   the rule book (`TenantRuleBook.released`), and a stamp naming one reads it.
2. A version written before a field of its schema existed reads that field as
   the platform's current version has it (`read_over`): the schema's fields at
   any depth and a mapping over a closed key set (a severity per finding
   code); a mapping of data is never topped up; an unknown field is refused.
   The same reading applies to a tenant's stored versions.
3. A file any release manifest pinned is never edited or deleted (test over
   `contracts/release`); the two deleted 1.0.0 files are restored byte for
   byte from git, checksums matching the pins.
4. A tenant may not take any number the platform ever released, and where the
   platform ships a number a tenant already holds, a stamp of it on that
   tenant's cases still means the tenant's (asked first).

## As built

- `application/rules.py`: `read_over`, `TenantRuleBook.released`, `ships`,
  `at` asks the tenant first; propose and decide refuse any released number.
- `adapters/policy_files.py`: `load_released`, `SalesPolicies.released` and
  `.current()`; `rule_book` hands both.
- `configs/policies/sales_order_rules@1.0.0.yaml`,
  `sales_quote_rules@1.0.0.yaml` restored (`dd5ef1d^`, `3557de8^`).
- `tests/unit/test_released_rules.py`: 8 tests. Mutations, each red: the
  stamp asked platform-first; `released` empty; no fill; closed keys not
  filled; data mappings topped up; `ships` only the current number; a released
  file deleted; a released file edited.

## Left open

- A step's code still changes with a deploy: an old version keeps its values,
  not the code that applied them. A check added later runs on an old case at
  the platform's severity.
- A mapping keyed by plain strings that a validator holds to a closed set
  (`SalesKpi.manual_baseline_minutes` per step code) is not filled; a KPI step
  added later would make an older KPI version unreadable. Typing those keys
  as a closed set brings them under the rule.
