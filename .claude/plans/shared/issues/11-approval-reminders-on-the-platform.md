# 11 — Reminders and escalation for every approval, and who was told when

Status: ready-for-agent
Blocked by: none
Category: approvals / platform

## What

§2: "SLA và nhắc/escalate cho phê duyệt ở nền tảng (hiện chỉ DW1 có, trong
`followups.py`)" and "Hiện 'đã báo ai, lúc nào' khi escalate".

Checked 2026-11-27: not built on the platform. `ApproveAndResumeService`
(`dw_agent_runtime/approval_flow.py:144`) decides, waits and withdraws; no
lane reminds anyone of a pending `platform.approval_requests` row. DW1
reminds and escalates its own cases, including those waiting on a checker
(`dw_sales/application/followups.py`, `checker_scope`), and records only how
many were told (`followups.py:420`, `"recipients": len(recipients)`), so no
screen can say who.

## Design

- **Platform lane `approval_followups`** (worker, every 15 min, working hours
  in the tenant's zone): for each pending approval, after
  `remind_after_hours` a notice to the holders of its stamped
  `required_scope` (the requester left out: they cannot decide it); after
  `escalate_after_hours` a notice to those holders' managers
  (`dw_platform.application.hierarchy`), or the member admins where nobody has
  a manager. Audited as the lane (`system:approval_followups`).
- **Numbers are tenant rules:** `configs/policies/approval_followups@1.0.0.yaml`
  (per approval-type prefix, default for the rest), through the rule versions
  and `TenantOverlay`.
- **No double reminder:** a context that follows its own approvals registers
  their prefixes at the composition root (`followed_elsewhere |= {"sales."}`,
  the same pattern as `strict_approval_prefixes`), and the lane skips them.
- **Who was told, when:** `platform.approval_notices` (approval, recipient,
  stage `remind|escalate`, at; migration, RLS forced with the workspace
  shape, append-only: UPDATE and DELETE revoked) written in the lane's
  transaction; `/approvals/[id]` shows "Đã nhắc: Khoa, Dung lúc 09:00 …;
  đã báo lên: Bình lúc …" (names from the directory, times in giờ Việt Nam).
- **DW1's escalation shows its recipients too:** the follow-up's mark
  records the recipient ids beside the count (Sales migration), and the case
  page's history says who was told and when.

## Acceptance

- Unit: remind once, escalate once; a decided or withdrawn approval is never
  reminded; nights and weekends not counted; the requester never reminded;
  a prefix followed elsewhere skipped.
- PostgreSQL: `approval_notices` RLS (another tenant reads nothing),
  append-only grants asserted.
- Web: the approval page lists who was told; empty says "Chưa nhắc ai".
- Mutation: requester exclusion, the followed-elsewhere skip, the decided
  check: each red.

## Owed

- Đạt: the default hours for Proterial (the tenant can change them).
