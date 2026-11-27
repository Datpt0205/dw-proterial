# 04 — The gateway's client and the approval stamp, out of dw_sales

Status: ready-for-agent
Blocked by: none
Category: Bravo gateway / platform lift

## What

§6: "Nâng client gateway và vé duyệt (`bravo_gateway_client.py`,
`BravoWriteStamp`) ra khỏi `dw_sales`". Checked 2026-11-27: still in Sales
(`packages/python/dw_sales/src/dw_sales/adapters/bravo_gateway_client.py`,
251 lines; `BravoWriteStamp` at
`dw_sales/application/bravo_line_writes.py:737`). DW2 cannot write Bravo
without importing a context (forbidden) or copying both (two answers).

## Design

- **The HTTP mechanics move to `dw_bravo`** (the package DW1 and DW2 already
  share): `dw_bravo.adapters.gateway_client` holds the transport, the
  `Bravo-Target` header check, the error mapping (`BravoUnreachableError`,
  refusals), the reads and the write call. Sales keeps its ports in
  `dw_sales.application` and a thin adapter over the shared client (CLAUDE.md:
  a context reaches `dw_bravo` through a port it declares, from its adapters
  only; import-linter already says so).
- **The stamp's generic part moves too:** "the decider's employee code →
  exactly one active Bravo user → sign a token for this content and target"
  becomes `dw_bravo.approval_stamp.BravoDecisionStamp`, taking its ports
  (`ApprovalSignerPort`, employee codes, Bravo users, clock) by constructor.
  What is Sales' own (which proposal, its hash, its stage version) stays in
  Sales as a small `ApprovalDecisionStamp` that calls it, registered at the
  composition root as now.
- `scripts/verify_architecture.py` (`IMPORT_TO_DIST`), the Dockerfile COPY
  lists and `apps/*/pyproject.toml` updated where a dist changes.
- No behaviour change: same tokens, same refusals, same words.

## Acceptance

- Every existing Sales gateway, client and token test passes unchanged in
  outcome (moved where its subject moved).
- import-linter: `dw_bravo` imports no context; `dw_purchasing.adapters` may
  import the client (contract kept explicit).
- Mutation, still red after the move: the stamp signing without the target,
  "exactly one active Bravo user" relaxed to "at least one", the client
  accepting an answer with no `Bravo-Target` header.

## Owed

- none.
