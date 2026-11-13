---
status: Accepted
date: 2026-11-13
accepted: 2026-11-13 (Đạt: "Hồ sơ tìm nguồn làm trục", "Bỏ duyệt theo bậc, tắt ngân sách")
source:
    - ../../../../../.claude/plans/purchasing/dw2-rebuild/spec.md
    - ../../../../../docs/adr/0026-bravo-is-read-through-its-vendor-api-and-written-by-a-person.md
---

# A sourcing case is DW2's axis; a PR is approved on Bravo, not in DW2

## Context

DW2 was built before Proterial's purchasing flows were known: a case began
from a purchase request (PR) with a number, was approved in DW2 by amount
tier, and only then asked suppliers for prices. On 2026-11-13 the BA's two
real flows arrived (raw materials, new and mass; tools, machines and
services, with or without a quotation). In them:

- for a new material, and for tools with no quotation yet, Purchasing finds
  suppliers and gathers quotations **before** any PR exists;
- the requester raises the PR **on Bravo**, with its attachments, and the PR
  is approved **on Bravo**; the PO is approved on paper;
- no step checks a budget;
- tools need at least two quotations from two suppliers unless the supplier
  is exclusive, compared on 13 criteria, and nobody but a person chooses.

Two places approving one PR are two answers to who may approve it, and they
drift (`.claude/rules/failure-modes.md` #2).

## Decision

1. **The case is a sourcing case.** It opens from a requester's mail or a
   Purchasing request, carries DW2's own number, and has a kind that is the
   flows' first gate: raw material new, raw material mass, tools with a
   quotation, tools without one. RFQs may go out before any PR; a supplier's
   reply links by the DW number written in the RFQ's subject.
2. **Bravo's PR attaches to the case** when it exists: the requester writes
   the DW number on the PR (the only link that needs no guess); until Bravo's
   API reads PRs, a person attaches the PR export.
3. **DW2 approves no PR.** The tiered approval (`purchasing.request`), the
   re-approval past a tier, the `submission` switch and the tier-3 permission
   set are retired. In their place Purchasing's PIC confirms DW2's check
   result before submitting on Bravo; DW2 reads the approval state from Bravo.
   The platform's approval stays for one thing: a person approving exactly
   what DW2 will write to Bravo (ADR 0026, 11-13 amendment).
4. **No budget check by default.** The tenant's rules drop the budget fields
   from what a request requires and from what escalates; the code goes when
   Proterial confirms it is not needed.
5. **DW2 never pre-selects a quotation**, the cheapest included. The
   comparison shows every criterion; the PIC chooses and says why.

## Consequences

- The case's states allow RFQ, quotation checks and comparison before a PR.
- What was built for reading mail, files in the sandbox, drafting RFQs,
  reading quotations and confirmations, the Bravo import file, the brief and
  Q&A is kept; the PR-number requirement, the tiers and the budget are not.
- Paper PO approval is known when the PIC uploads the signed scan, until
  Bravo's API reads the PO's approval state (R32).
- The rebuild's tickets are in `.claude/plans/purchasing/dw2-rebuild/spec.md`.
