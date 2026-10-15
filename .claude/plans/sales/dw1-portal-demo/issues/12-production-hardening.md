# 12 — Production hardening (before any real Proterial data)

Status: needs-info (triaged 2026-10-12: what needs nothing from Proterial
became tickets 17 and 19–27; what is left here waits on Proterial's answers
to the requirements doc v1.2)
Blocked by: 09
Category: enhancement

What the demo deliberately leaves out, and which must land before DW1 reads
a real document or serves a real tenant.

## Split out on 2026-10-12 (needs nothing from Proterial)

| Ticket | Item                                                       |
| ------ | ---------------------------------------------------------- |
| 17     | Case reassignment (G22)                                    |
| 19     | Tenant overrides of rules and templates (G15, decision 14) |
| 20     | Legacy Vietnamese encodings detected (G37)                 |
| 21     | Several delivery schedules on one PO line (G36)            |
| 22     | Support access without prices (G20)                        |
| 23     | No price, name or mail text in spans, logs, errors (G32)   |
| 24     | The overview aggregates in SQL                             |
| 25     | Malware scan and parsing in the worker (G17, part 1)       |
| 26     | Public-repo guard over `git ls-files` (G34)                |
| 27     | Legacy Office conversion and image-PDF OCR (G17, part 2)   |

DW1's own service principal (spec, actor table) goes with ticket 16, its
first caller (done there: role `sales_dw1`).

## Waiting on Proterial (requirements doc v1.2, sent by Đạt, confirmed 2026-10-12)

- **Approval matrix (G6).** When Proterial sends who approves which price
  or discount (requirements doc §4 item 5), it becomes a ladder in
  `sales_pricing`. Each step names a scope that a role or permission set in
  the sales migration grants, and a schema check refuses a step naming any
  other scope. The quote stamps its step at submit. Until then any holder of
  `sales.quote.approve` other than the pricer approves.
- **Real Bravo history (G18).** A Bravo adapter for `orders_for_po`,
  `orders_since` and `open_ycbg`, through an anti-corruption layer, and the
  real upload template.
- **Real mailbox (G39).** A Microsoft 365 adapter behind `InboxPort`; it
  fills SPF/DKIM/DMARC from the mail system's headers, which the mock stubs.
- **Retention (G29).** Name a retention rule for sales cases, artifacts and
  served-source records once Proterial answers (requirements doc §3.1).
- **Export control (G35).** An NOEC request draft when the NOC is missing,
  and the denial-list result read from Proterial's real list.
- **Placement (G32, last part).** The data-plane placement follows the
  deployment answer.
- **Reference data.** Convert list, item master, quotation master list and
  LME rule, email wording per language, the A3 conditions.

Each becomes its own ticket when its answer arrives.

## Comments

- 2026-10-12 (triage): the G34 line "whether to alias the customer and
  procedure codes is owed by Đạt" was stale: Đạt decided on 2026-10-05 to
  keep the repo public and not alias them (`sales.md` Open). Ticket 26 builds
  the guard on that decision.
- 2026-10-12 (triage): Đạt chose a real ClamAV service now over a mock
  scanner first (ticket 25).
