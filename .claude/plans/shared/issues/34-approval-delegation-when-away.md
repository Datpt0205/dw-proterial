# 34 — Delegate approvals while away

Status: needs-info (Đạt, with Proterial's policy: what a delegation is)
Blocked by: Đạt's decision
Category: approvals / authorization

## What

§2: "Ủy quyền khi vắng: A giao quyền duyệt cho B trong khoảng ngày, có
audit" (L). Checked 2026-11-27: not built (nothing in
`dw_agent_runtime/approval_flow.py` or `dw_platform`).

## Why it waits

It changes who may decide, which is authorization, so it is not taken by
recommendation alone. Two shapes, materially different:

- **A. A time-bounded grant by an admin.** A member admin gives B the
  permission set A holds, from–to, audited; scopes resolve by date in the
  same function that builds the access context (`effective_scopes`), so the
  decision rule, separation of duties and the stamped `required_scope` all
  stay one answer. B decides as B.
- **B. A person delegates their own approvals.** A names B; B decides "thay
  mặt A", the decision recording both. Needs a second decider path in
  `ApproveAndResumeService` (two answers to "who may decide").

Recommended: **A**, built in the platform (`memberships` gain
`valid_from`/`valid_until` per role grant, migration, the admin page's
member form, a lane-free expiry since resolution is by date), with two
fixed exclusions: a `bravo_write.*` approval is decided only by the person
whose own Bravo user writes it, and a strict SoD rule still refuses B when B
made the request.

## Acceptance (once decided)

- A grant outside its dates gives nothing (time-travel test on the clock);
  the separation-of-duties trigger still refuses a grant that would join a
  price scope with member admin; another tenant's grant never applies.

## Owed

- Đạt: A or B; who may grant (admin only, or the person for their own role);
  whether a head may delegate approvals of Bravo writes at all (recommended:
  no).
