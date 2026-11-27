# 32 — Gateway: a PO from a PR, and a PR's approval (DW2), pending until UAT

Status: ready-for-agent (on Đạt's machine: the trace file is not in git); the PO date change is needs-info
Blocked by: 31
Category: Bravo gateway / DW2

## What

§6's DW2 commands, slice 2: "tạo PO từ PR, duyệt PR
(`usp_B30AccDoc_ApprovalVouchers`) … thiếu sửa ngày PO". Checked
2026-11-27: not built; the 11-26 trace holds a PO created from a PR
(`B30BizDocDetailPO`) and PR approvals through `ApprovalVouchersPR`
(`usp_B30AccDoc_ApprovalVouchers` with the documents as XML; `DocStatus`
10→13; the refusal "Người dùng không có quyền duyệt chứng từ số …"), per
Sales ticket 52's note. No PO date change was traced.

## Design

- **PO from PR:** a create on the PO screen (`layout_9319_BizDocPO__Xml`,
  local) whose lines are taken from the PR as the client takes them (the
  trace decides which columns and how they link back to the PR's lines);
  `WriteKind`, screen, tables, statements and replay as ticket 31.
- **PR approval:** a call of `usp_B30AccDoc_ApprovalVouchers` exactly as the
  trace shows it (parameters, the XML's shape), under the approver's own
  Bravo user from the signed token; Bravo's own refusal is returned as
  `refused` with its words, never retried. The write login's EXECUTE grant
  goes in script 08 (Proterial IT runs it).
- Both `pending` until a UAT proof; switch keys under
  `purchasing_bravo_writes`.

## Acceptance

- Replay of the traced PO create matches on SQL Server 2017, or the
  difference is named and the kind stays pending.
- PR approval: on the throwaway server, a stub of the procedure records the
  call; the parameters equal the trace's; a refusal message maps to
  `refused`.
- A pending kind refused before the ledger.

## Owed

- A traced PO date change (UAT session, Đạt) before that kind exists.
- Proterial IT: EXECUTE on the approval procedure for the write login.
