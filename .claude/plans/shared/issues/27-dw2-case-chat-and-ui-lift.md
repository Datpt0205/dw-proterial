# 27 — DW2: a conversation per purchase request; the chat widget and case-chat layout in @dw/ui

Status: ready-for-agent
Blocked by: none
Category: chat / DW2

## What

§1: "Đưa vỏ widget và bố cục chat hồ sơ lên `@dw/ui`" (Đạt reviews) and
"DW2: chat gắn hồ sơ PR" (the actions are ticket 28). Checked 2026-11-27:
DW2 has one assistant page (`apps/web/app/purchasing/assistant/page.tsx`,
sessions and turns in `purchasing.assistant_sessions/assistant_turns`) with
no case conversation and no widget; DW1's widget and case-chat layout are
Sales files (`apps/web/app/sales/_components/assistant-widget.tsx`,
`case-chat.tsx`).

## Design

- **Lifted when the second user arrives** (`code-quality.md`): the widget's
  shell (drawer, tabs "Phiên"/"Tin nhắn", unread dot, one chat per screen)
  and the case page's chat column move to `@dw/ui` as domain-neutral
  components taking the context's API calls and words as props; DW1 switches
  to them in the same change with no visible difference.
- **DW2's conversation per PR:** `purchasing.assistant_sessions` gains
  `case_id` (nullable for the general one; migration; one session per person
  per case, RLS by user as DW1's `bfe2d1aeadcd`); the PR page
  (`apps/web/app/purchasing/requests/[caseId]`) shows the chat; DW2's
  question kinds answer about this PR (bound to it by code, never by a name
  the model read).
- DW2's widget on Purchasing pages for its case readers.

## Acceptance

- DW1's widget and case-chat tests pass against the lifted components.
- DW2: a question on a PR answers about that PR; a PR the caller cannot read
  is 404; another person's conversation never listed; another tenant's 404
  (PostgreSQL).
- `antd-only.test.ts` still green (the lift adds no library).

## Owed

- Đạt: review the `@dw/ui` components' props before DW2 builds on them.
