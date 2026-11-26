# 72 — Gateway: create an SO, a new line filled as the screen fills it

Status: ready-for-agent
Blocked by: 70
Category: enhancement (tickets 51, 59, 63)

## Why

A typed SO create is traced twice (11-20, and `02-trace-3.csv` 11-25
16:53:33). What blocked it was how a new line's `QuantityBox` is set. It is in
the layouts: the grid layout 8213 binds the item lookup (`vB20Item_Lookup`)
into the line when `ItemCode` is chosen (`bindingMembers`: `QuantityBox`,
`Length`, `CoilBox`, `BasePriceCode`, `Specification`, `DesignNumber`,
`CartonSize`…), and the data layout 8212 sets `QuantityBox = 1` when
`CartonSize='-'` (`Eval_Detail_QuantityBox_SetValue`). The runner reads 8212
only.

## What

- `dw_bravo` reads the grid layout's `bindingMembers` for the line's lookup
  columns and applies them to a new line from the item read through the
  gateway; then 8212's rules run as today.
- `so.create`: header INSERT and line INSERTs with the traced column sets,
  `SCOPE_IDENTITY` read-back, then the process step (ticket 74).
- Kind leaves `pending`; switch off until UAT proof.

## Acceptance

- Replay of 16:53:33 renders the client's INSERTs.
- A unit test: an item whose `CartonSize` is `-` gets `QuantityBox` 1; another
  gets the item's own value; removing the binding read turns it red.
