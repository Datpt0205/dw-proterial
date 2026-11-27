# 31 — Gateway: create and edit a purchase request (DW2), pending until UAT

Status: ready-for-agent (on Đạt's machine: the trace file is not in git)
Blocked by: 04
Category: Bravo gateway / DW2

## What

§6: "**Lệnh của DW2** (W11–W18): tạo/sửa PR, tạo PO từ PR, duyệt PR
(`usp_B30AccDoc_ApprovalVouchers`); bản ghi UAT 26/11 đã có các thao tác
này, thiếu sửa ngày PO" (L, sliced into 31, 32, 33), and the "thêm màn DW2"
part of the watch row. This slice: a PR created by New and a PR edited.

Checked 2026-11-27: not built. `dw_bravo.contract.WRITE_KINDS` holds only the
SO kinds (`contract.py:282-316`). Sales ticket 52 (2026-11-26) records what
the 11-26 rows hold: "PRs created by New (header + 1–3 `B30BizDocDetail`
lines), a PR edited, a PO created from a PR (`B30BizDocDetailPO`), PRs
approved through `ApprovalVouchersPR` … Not traced: a PO's date change". The
trace is `02-trace-3.csv`, local only (outside the repository); the PR and
PO layouts are under `docs/proterial/bravo/layouts/` (gitignored, local):
`layout_1555_BizDocPR__Xml`, `layout_9319_BizDocPO__Xml`.

## Design

- Follow the path DW1 took (doc §6, "DW2 cắm vào gateway"), every column
  from the trace, none assumed:
  1. `dw_bravo.contract`: the PR create and edit commands (typed, versioned),
     `WriteKind`s on the PR screen's `B00Command` key as the trace names it,
     the tables written, `pending` with the reason until a UAT proof.
  2. `statements.SCREENS` gains the PR screen; `SWITCH_KEYS` maps the PR
     prefix to a new DW2 rule `purchasing_bravo_writes@1.0.0` (every kind
     off; switching on needs a `uat_proof`; target `uat|production` as
     Sales ticket 85; decided by a second person).
  3. The statements built by the runner from the layout (New: default values
     then `RowAdded` rules, as ticket 72 did for an SO), replayed against the
     traced rows on the throwaway SQL Server.
  4. The change watch (ticket 02) fingerprints the PR screen and its tables,
     and pauses these kinds on a change.
- The process step after a write (`CreateProcess`, Sales ticket 74) and the
  command right (ticket 75) apply as for the SO, if the trace shows the
  client calling them for a PR; otherwise recorded as a question.

## Acceptance

- Replay of each traced PR create and edit matches column for column on SQL
  Server 2017, or the difference is named and the kind stays pending.
- A write of a pending kind refused before the ledger (test).
- Switch key: a PR kind on in `purchasing_bravo_writes` without `uat_proof`
  refused (domain validator).

## Owed

- A UAT proof per kind (the UAT session, Đạt with Proterial) before a switch
  turns on.
