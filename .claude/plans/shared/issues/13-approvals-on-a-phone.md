# 13 — Approve on a phone

Status: ready-for-agent
Blocked by: none
Category: approvals / web

## What

§2: "Duyệt trên điện thoại (`/approvals` hiện là bảng cho máy tính)".
Checked 2026-11-27: partly there. The pending approvals are already cards
(`apps/web/app/approvals/page.tsx:167`, buttons in a wrapping `Flex`); the
decided list is a `Table` (`page.tsx:280`); nobody has looked at either at
phone width, and `playwright.config.ts` has no phone project.

## Design

- Add the phone projects `ui-quality.md` §12 asks for (390 px and 320 px) to
  `apps/web/playwright.config.ts` in this change, used by an `e2e` spec that
  opens `/approvals` and an approval page as a decider and approves one.
- Fix what that run shows: the payload (`ToolApprovalPayload`) and each
  host's detail wrapping without sideways scroll; Duyệt/Từ chối `size="large"`
  on touch; the decided list as cards below `md` (the pattern Sales' phone
  tables use); the comment field above the buttons; the disabled reason as
  visible text (already there) kept in view.
- No change to what an approval decides or who may.

## Acceptance

- e2e at 390 and 320 px: no horizontal page scroll, every control reached
  by role and name in Vietnamese, an approval decided.
- Vitest: the decided list renders as cards below `md`.

## Owed

- none.
