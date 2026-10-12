# 13 — The quote approval panel sees a preview rendered on the same page

Status: done (2026-10-12; not committed)
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

## As built (2026-10-12)

- One owner of the file list: `useCaseArtifacts(kind, caseId, caseVersion)`
  in `_components/artifacts-panel.tsx` reads it once per page (after the
  case has loaded, and again when the case version changes). The quote page
  hands it to `ArtifactsPanel` (`list`, which reloads it after a render) and
  to `ApprovalPanel` (`artifacts`); `useLatestPdf` and its second fetch are
  gone, replaced by the pure `latestPdf(artifacts, version, kind)`. The order
  page uses the same hook for its one panel. No timer, no polling.
- A failed render leaves the list untouched: the reload runs only on the
  API's 2xx (`useAction`).
- Vitest `app/sales/_lib/__tests__/quote-preview.test.tsx` renders the whole
  quote page (mocked API): rendering the preview in the files panel makes the
  approval panel offer "Xem bản xem trước (PDF…)" with one read of the case
  and two of the list; a failed render keeps "Chưa có bản xem trước…".
  Red before the change (the approval panel kept its own copy). Mutation
  checks, each turning the first test red: the page passing `artifacts={[]}`
  to the approval panel; the files panel not reloading the shared list after
  a render.
- `e2e/sales-demo.spec.ts` test 7 no longer reloads the page after rendering
  the preview, and the comment explaining the workaround is gone. The walk
  itself was NOT run in this pass (needs the full stack).

## Comments

- 2026-10-12 (agent): removing the wiring turns the vitest red, as above.
