# 07 — antd v6 shell slice (platform)

Status: done (2026-10-03)
Blocked by: —

## What

Per CLAUDE.md "Web UI" and `.claude/plans/web-ui.md`: antd v6,
`@ant-design/nextjs-registry` in the `antd` layer, layer order before
`@import "tailwindcss"` with a test that fails without it, theme + `vi_VN` in
`@dw/ui`, dayjs `vi` behind `lib/dates.ts`, `lib/money.ts`, top navbar with a
drawer below `lg`, `lang="vi"`.

## Acceptance

- Layer-order test red without the fix, green with it; `next build` passes.
