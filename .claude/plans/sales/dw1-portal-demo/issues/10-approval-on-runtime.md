# 10 — Move the Sales decision onto the runtime

Status: needs-triage
Blocked by: 09

## What

Replace the context-recorded decision (spec decision 5, dw_sales ADR 0001)
with a versioned graph. It pauses on `interrupt` into the platform approvals
inbox and resumes, so approval, autonomy and audit come from the runtime.

## Acceptance (G19)

1. Each approval type declares its decide-scope (`sales.quote` →
   `sales.quote.approve`; `sales.order.cross_check` →
   `sales.order.cross_check`), checked in `ApproveAndResumeService.decide`.
   `GET /approvals` lists only approvals the caller may decide or requested.
2. The interrupt payload names the case's maker (`priced_by` /
   `prepared_by`), and the strict check excludes that person. Wire
   `strict_approval_prefixes |= {"sales."}` at the composition root, with
   `requested_by` set to the maker, not to whoever pressed "DW xử lý".
3. Approval payloads, run results and audit details carry the case id,
   version and hash only, never an amount.
4. `RunAllowancePort` is checked when processing starts, including
   mailbox-triggered runs.
5. `configs/workers/sales.yaml` and the graph are pinned in the release
   manifest.
6. A model turn that reads email or attachment content gets a toolset with
   no outbound tool (ADR 0007).
7. The context-side decide endpoints are deleted in the same change, with a
   test that they are gone.

Negative tests:

- the purchasing manager decides a `sales.quote` → 403;
- the maker decides → 409;
- `dev|dieu.hoang`, holding `approver_boost`, cannot approve a quote she
  priced.
