# 74 — Gateway: run Bravo's process step after a write

Status: needs-info (Đạt decides)
Blocked by: none
Category: enhancement (ADR 0027 amendment)

## Why

Every client save in the three traces ends with
`exec dbo.usp_B30BizDocProcess_CreateProcess @_BizDocId, @_BizProcessGroupUnique=NULL, @_BranchCode, @_DocCode`
on the same session, right after the statements. The gateway sends no such
call and its write login holds no EXECUTE, so after a DW write Bravo's
process view of the document lags what a person's save would show.

## Options

- **A (recommended):** the gateway executes that one procedure after the
  write, in the same transaction, under the PIC's context; the grant script
  (08) adds `GRANT EXECUTE ON dbo.usp_B30BizDocProcess_CreateProcess` to the
  write login only; ADR 0027 amended ("nothing created in Bravo's DB" still
  holds; one Bravo procedure is executed). Needs script 07-style proof on UAT
  that it succeeds under the write login.
- **B:** not called; the write's result page tells the person Bravo's process
  view refreshes on the next save in Bravo.

## Acceptance (A)

- Replay renders the call after the statements with the traced arguments.
- On UAT, the document's process rows equal those after a person's save.
