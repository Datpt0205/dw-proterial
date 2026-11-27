# 14 — DW1: decide a rule, prompt, skill or master-data version in its row of "Việc cần làm"

Status: ready-for-agent
Blocked by: none
Category: approvals / DW1 web

## What

§2: "Duyệt phiên bản quy tắc, layout, dữ liệu gốc ngay trong hàng việc DW1
(hiện chỉ link)". Checked 2026-11-27: still a link. "Việc cần làm"
(`apps/web/app/sales/page.tsx:321-346`) counts Sales' own approvals and links
to `/approvals` or the layouts page (`9b8a49e8` names their kinds); the
decision and its changes are drawn only on `/approvals`
(`apps/web/app/sales/_meta/approvals.ts`: `RuleApprovalChanges`,
`PromptApprovalChanges`, `SkillApprovalChanges`; `sales.catalog` decided
there too).

## Design

- Each pending `sales.rules`, `sales.prompts`, `sales.skills` and
  `sales.catalog` approval the person may decide becomes its own row in
  "Việc cần làm": what changed drawn by the same host detail component (one
  owner of how a version is shown), Duyệt / Từ chối with the comment the
  approval requires, calling the platform's decide exactly as `/approvals`
  does (same idempotency key handling).
- `sales.layout` stays a link: it is decided on `/sales/layouts`, which
  sends the layout's version.
- The server refuses as before (scope, separation of duties: the proposer
  cannot decide their own version); the row shows the server's reason, and
  the button is disabled with that reason when the view already knows it.
- One at a time: no bulk decide (ui-quality §7).

## Acceptance

- Vitest: a rules approval row shows the diff and decides through the
  platform API; the proposer's own row is disabled with the reason; a
  layout approval stays a link.
- API test kept: deciding one's own version is refused at the server
  (the hidden button proves nothing).

## Owed

- none.
