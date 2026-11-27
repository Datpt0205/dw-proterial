# 33 — DW2's side of a Bravo write: proposal, approval by the buyer's own Bravo user, outcome

Status: ready-for-agent
Blocked by: 04, 05, 31
Category: Bravo gateway / DW2

## What

§6's DW2 commands, slice 3, and step 3 of the doc's "DW2 cắm vào gateway":
"port trong `dw_purchasing.application`, adapter HTTP (dùng client chung sau
khi nâng); loại phê duyệt `bravo_write.<chứng từ>` do chính người có user
Bravo duyệt, kèm vé ký". Checked 2026-11-27: not built; DW2 writes Bravo
only by an import file (`dw_purchasing/adapters/bravo_file.py`).

## Design

- **Port and adapter:** `BravoWritesPort` in `dw_purchasing.application`; its
  adapter in `dw_purchasing.adapters` over the shared client (ticket 04).
  import-linter keeps `dw_bravo` out of DW2's application and domain.
- **Proposal:** `purchasing.bravo_writes` (case, kind, command, content hash,
  target read from, status; migration; RLS forced, workspace shape),
  mirroring `sales.bravo_line_writes` including the target stamp (Sales
  ticket 85).
- **Approval:** type `bravo_write.purchase_request` (and
  `bravo_write.purchase_order` with ticket 32), decided by the person whose
  employee code (ticket 05) maps to exactly one active Bravo user; the stamp
  is ticket 04's `BravoDecisionStamp`; the strict prefix and the decision
  guard registered at the composition root.
- **Outcome:** the worker's write lane carries the approved write out and
  records written / refused / in doubt, telling the buyer; an in-doubt write
  is never told as fixed (`a012e366`).
- **Web:** a "Ghi vào Bravo" panel on the PR page with the target tag, the
  proposal, its approval link, the outcome in words. The import file stays
  until a tenant switches a kind on.

## Acceptance

- Unit: a decider with no code, two Bravo users, or another target refused
  (fail closed); the proposer cannot decide their own (SoD).
- PostgreSQL: another tenant's proposal unreadable; the table's grants.
- Mutation: the stamp's one-user check, the target comparison: red.

## Owed

- none for the code; live writes wait on 31/32's UAT proofs.
