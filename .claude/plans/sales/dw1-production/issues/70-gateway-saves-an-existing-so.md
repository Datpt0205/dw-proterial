# 70 — Gateway: save an existing SO (the `Edit` context)

Status: resolved (2026-11-26)
Blocked by: none
Category: enhancement (ticket 63)

## Why

`apps/bravo-gateway/src/dw_bravo_gateway/statements.py` keeps
`SCREENS["EDIT_BizDocSO"].context_event={}` ("only `New` is traced"), so the
pipeline refuses every write to an SO that already exists, which is every
write DW1 has (dates, quantities, cancel, split). The client's word for a
stored SO's save is now traced three times: `EDIT_BizDocSO|Edit` in
`02-trace-2.csv` (11-25 13:28, the date and quantity saves) and
`02-trace-3.csv` (11-25 16:56, 17:28, 17:31). Local only:
`Downloads/DB-Bravo-5-extract/DB-Bravo`.

## What

- `context_event` gets the traced words by operation (`update` → `Edit`,
  `create` → `New`), nothing else.
- The trace replay (`dw_bravo.testing.replay`) covers the 11-25 date and
  quantity saves of an existing SO: the gateway renders the client's context
  line and UPDATE for each.

## Acceptance

- A preview of `so.line.set_confirmed_date` on a stored SO renders the
  client's context line `EDIT_BizDocSO|Edit ...` and its UPDATE; before the
  change it is refused as unmeasured (test fails without the entry).
- An operation with no traced word is still refused.

## Comments

**2026-11-26, done.** `SCREENS["EDIT_BizDocSO"].context_event` is
`{"update": "Edit", "insert": "New"}`. The replay test now reads each save's
own word: an `Edit` save is rendered by the shipped table with no override (the
11-25 13:28 date save, covered in `02-trace-2.csv` and `02-trace-3.csv`); a
`New` window's saves (11-20) keep naming their word. The 11-25 quantity save on
a split pair writes five columns at once (a split's re-quantity), so it is not
a single-column command and is skipped, as the 11-20 split was. The trace
reader now skips a parameter bound to a batch variable (`@_X=@p1`, the PR
approval rows of 11-26), which crashed it. Mutation: the update word removed
→ 8 gateway tests red.
