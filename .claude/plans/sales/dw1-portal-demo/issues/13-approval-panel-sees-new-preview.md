# 13 — The quote approval panel sees a preview rendered on the same page

Status: ready-for-agent
Blocked by: —
Category: bug

## What

On a quote case in `pending_approval`, the approver renders the quotation
preview from the artifacts panel, and the approval panel keeps saying there
is no preview ("Chưa có bản xem trước…") until the page is reloaded. The
Approve/Return buttons are not affected: they never depended on the preview.

Cause (verified 2026-10-12): the approval panel reads the artifact list
through its own `useResource` copy (`useLatestPdf(…, "quotation_preview")`),
and `useResource` keeps data in each component's own state, not a shared
cache. After a render only the artifacts panel reloads its copy; nothing tells
the approval panel's copy, and the case version (its `refreshKey`) does not
change on a render.

## Acceptance

1. After a successful render of `quotation_preview` in the artifacts panel,
   the approval panel shows "Xem bản xem trước" for the new file without a
   page reload.
2. One owner of "the artifacts changed": either the page holds the artifact
   list once and hands it to both panels, or the artifacts panel takes an
   `onRendered` callback the page wires to the approval panel's reload. Not a
   timer, not a second fetch on an interval.
3. A failed render changes nothing in the approval panel.
4. Vitest: render a preview in the artifacts panel and assert the approval
   panel shows the preview link; removing the wiring turns it red (say so in
   Comments).
5. The Playwright walk (`e2e/sales-demo.spec.ts`, test 7) drops its
   `page.reload()` workaround and the comment explaining it.

## Out of scope

- Whether submitting a quote renders the preview itself (Đạt's decision,
  `sales.md` Open).
- The order page: it has no approval panel and reads no artifact list for the
  cross-check dialog, so it does not have this bug.

## Sources (as of 2026-10-12)

- `apps/web/app/sales/quotes/[caseId]/approval.tsx` (`ApprovalPanel`,
  `useLatestPdf`), `_components/artifacts-panel.tsx` (`render`, `reload`),
  `_lib/use-resource.ts`, `quotes/[caseId]/page.tsx`.
- `apps/web/e2e/sales-demo.spec.ts` test 7.

## Comments
