# 06 — Admin page for identity links

Status: ready-for-agent
Blocked by: 05
Category: identity

## What

§7 Định danh: "trang admin". Checked 2026-11-27: the admin act exists as API
only (Sales ticket 64: "the admin page" pending). A person left in the link
queue cannot approve a Bravo write (`no_employee_code`,
`dw_sales/application/bravo_line_writes.py:765`).

## Design

- `/admin/identity`: the queue (who waits and why: no code, two candidates,
  a code held by another live account) and the links in force; "Liên kết"
  opens a form taking the employee code; "Gỡ liên kết" asks a confirmation
  naming the person and the code (ui-quality §10). Disabled with its reason
  without `platform.identity.link`.
- API from ticket 05 (queue, links, link, unlink), an idempotency key on each
  mutation.
- No Bravo user id on the page: only whether exactly one active user answers
  for the code (what the approval stamp asks).

## Acceptance

- Web: every region state; the form's validation; a conflict (code already
  linked) shown with both values, what was typed kept.
- API: refused without the scope; another tenant's queue never listed.

## Owed

- none.
