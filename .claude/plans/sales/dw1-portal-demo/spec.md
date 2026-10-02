# DW1 portal demo — Đơn hàng & Báo giá on mock data

Status: ready-for-agent
Owner: Đạt
Started: 2026-10-02

## Why

Proterial Vietnam's Sales department was proposed two Digital Workers. DW1
(Đơn hàng & Báo giá) is in scope now; DW2 (Giao hàng & CDO) is not. Proterial
has not sent any data yet (the requirements doc v1.2 is still to be sent), so
this slice proves the whole DW1 flow end to end on **mock data behind real
ports**. The mocks are later replaced by Bravo, SharePoint/OneDrive or
Microsoft 365 adapters without changing the flow.

## Scope

In:

- A portal that follows Proterial's sales process (WIV-03-012 order entry
  steps 1–3 and 6–10; WIV-03-023 quotation steps 1–12).
- Mock inbox as the entry point: sample emails with PO and quote-request
  attachments. Processing starts from a button, not a mailbox.
- Order flow: classify → read PO (Excel incl. one-sheet-per-page; text PDF)
  → map customer code to PRV code → checks → Sales review → Bravo upload file
  + confirmation or correction email draft.
- Quotation flow: quote request → Design request draft → Design reply
  (simulated) → price evidence → price decided by Sales → quotation file →
  head-of-Sales approval → email draft.
- Every value shown in review carries its source anchor (sheet!cell or
  page/line), per `.claude/rules/ui-quality.md`.

Out (this slice):

- Real email, Zalo, customer portals, Bravo API or database access.
- Any model call on real Proterial documents. Parsing is deterministic; a
  model step, if added, runs only on the fictional mock data.
- Auto-confirmation (A3), DW2, export-control evaluation (DW1 only warns).

## Decisions

1. **Mock data is fictional.** No real company, person or Proterial figure
   is committed. The repo is public (Đạt chose to keep it public on
   2026-10-02); Proterial's own documents stay outside git.
2. **Master data is read through ports, not stored in sales tables.**
   `SalesCatalogPort` (customers, items, convert list, quotations, LME, NOC
   status) and `InboxPort` (messages, attachments) are implemented by mock
   adapters over fixture files shipped in `dw_sales/adapters/mock/`. Bravo or
   SharePoint adapters replace them later. One owner per fact: the context
   never copies master data into its own tables.
3. **Case state lives in PostgreSQL** (`sales` schema, RLS FORCEd, tenant and
   workspace on every row). Generated files are artifacts stored by the
   context under tenant/workspace keys.
4. **Code decides.** Code does the mapping, price/LME/MOQ checks, dates and
   the numbers in every file and email. Templates render the emails.
5. **Approval in this slice is a case decision recorded by the context with
   an audit event, not yet a runtime interrupt.** This deviates from
   CLAUDE.md "Approval pauses and resumes a durable, checkpointed run". It is
   recorded here, and ticket 10 moves the decision onto the runtime
   (graph + interrupt + approvals inbox) once the demo stands. Nothing in this
   slice writes outside the platform, so no external side effect runs
   unapproved.
6. **Web UI uses antd v6** as CLAUDE.md requires. The shell slice (ticket 07)
   is platform work and lands first.

## Findings the checks raise

| Code                     | Rule                                                                 |
| ------------------------ | -------------------------------------------------------------------- |
| `code_unmapped`          | Customer code not in the convert list and no attribute match         |
| `code_ambiguous`         | No exact convert entry; more than one item matches the attributes     |
| `price_mismatch`         | PO unit price ≠ valid quotation price (tolerance from policy)        |
| `quotation_missing`      | No valid quotation for customer + item on the PO date                |
| `lme_band_mismatch`      | Quotation's LME band ≠ band of the month's LME                       |
| `moq_violation`          | Quantity < MOQ                                                       |
| `pack_multiple`          | Quantity not a multiple of the packing unit                          |
| `requested_date_short_lt`| Requested date earlier than PO date + standard lead time             |
| `missing_noc_esf`        | Customer has no NOC or no ESF for the current fiscal year (warning)  |
| `duplicate_po`           | Same customer PO number already has a case                           |
| `revised_po`             | Same PO number with a higher revision; diff instead of a new upload  |

## Done when

- `make lint typecheck test-unit test-architecture` pass; RLS and
  cross-tenant tests pass in `test-integration`.
- With the stack running, a user signs in, opens the portal, processes every
  mock email, reviews and approves an order and a quotation, and downloads
  the Bravo upload file and email drafts. Each finding in the table above is
  triggered by at least one mock email.
- An eval dataset `sales@1.0.0` with prompt_injection, cross_tenant_attack
  and missing_evidence cases passes.
- `reviewing-feature-security` has been run and its negative tests exist.

## Tickets

See `issues/`. Order: 01 → 02/03 → 04 → 05 → 06; 07 in parallel; 08 after
05–07; 09 last; 10 after the demo.
