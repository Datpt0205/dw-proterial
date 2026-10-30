---
status: Accepted
date: 2026-10-30
accepted: 2026-10-30 (Đạt: "ok" to lifting the shared pieces before DW2, recorded as an ADR)
---

# What a second context shares moves to the platform, small pieces first

## Context

Purchasing (DW2: purchase request → purchase order, supplier RFQ and
comparison, supplier confirmation, a brief and status Q&A) is the second
business context, and its contract gives it four weeks from kickoff. Sales
(DW1) built several capabilities a Purchasing worker needs, and they live in
`dw_sales`. The architecture forbids one context importing another
("Sales is independent", consumer-declared Protocols only), so Purchasing
cannot reuse them where they are. Copying them would be failure-modes #2 in
code: two answers to one question that drift.

A survey of the code on 2026-10-30 (recorded in `.claude/plans/sales.md`)
sorted each capability by how Sales-bound it is:

| Capability | Where | Bound to Sales by |
| --- | --- | --- |
| Malware scan port, verdict, ClamAV adapter | `application/malware.py`, `adapters/clamd.py` | an inbox helper only |
| Figure check, amount check | `application/figure_check.py` | the names `DW1`, `DW2` |
| One-call model door (`caller_run`, `InterpretationPort`, `GatewayInterpretation`) | `application/runs.py`, `model_reading.py`, `adapters/model_interpretation.py` | the files they share with Sales types |
| Reader sandbox wire and transport | `apps/reader`, `adapters/reader_wire.py`, `reader_client.py` | `ReaderOp` (all `po.*`, `quote.*`) and Sales result types |
| Stored message, attachment content | `domain/messages.py`, `domain/mail_parts.py` | nothing material |
| Outbox folder (send from the presser's mailbox) | `adapters/outbox_folder.py` | nothing |
| Mail drop lane and stored mailbox | `mail_drop.py`, `mailbox_*` tables | the ignored-sender rule from `OrderRules` |
| Tenant rule versions | `rules.py`, `rule_versions` | the `RuleKey` registry |
| Master-data import from Excel | `catalog_imports.py`, `catalog_*` tables | the `SPECS` / `CatalogList` registry |
| Follow-ups, brief, assistant, pipeline, pause | many | Sales statuses and views throughout |

## Decision

1. **Small, already-generic pieces move first, with no table move:** the
   malware port and ClamAV adapter, the figure and amount checks, the one-call
   model door, the stored message and attachment types, and the outbox folder
   adapter. Each moves to the platform package that owns its kind
   (`dw_platform` for scanning and mail, `dw_agent_runtime` for the model
   door), keeps its tests, and Sales imports it from there. Behaviour does not
   change; the move is one commit per piece, each with the suite green.
2. **The reader moves after its registry is split.** The sandbox, wire and
   transport become the platform's; each context registers its own operations
   and result types. Until then Purchasing reads files through the shared
   text, table and mail operations only.
3. **The engines move when a second registrant needs them:** rule versions,
   master-data import and the mail drop each become a platform engine with a
   registry a context fills (rule keys and schemas, list specs, a sender
   predicate), and their tables leave the `sales` schema in a migration that
   moves rows, never drops them. This is done for each engine the day
   Purchasing needs it, not ahead of it (code-quality: no abstraction before
   its second caller).
4. **Sales-shaped capabilities stay in Sales.** Follow-ups, the brief, the
   assistant, the pipeline and the worker pause read Sales statuses and views
   throughout; Purchasing writes its own over the lifted pieces. A pattern is
   shared by reading Sales' code, not by importing it.
5. **Purchasing is scaffolded with `make new-context NAME=purchasing`** and
   built on mock data until Proterial's purchasing samples arrive; every value
   their process decides (approval limits, who approves, the request form,
   Bravo's fields) is a tenant rule from the start.

## Consequences

- A product built on this platform gains the scanning, model door and mail
  types without Sales; `dw_sales` shrinks by those files.
- The reader and the three engines carry the cost of a registry only when
  Purchasing reaches them, and each move is its own decision in the plan.
- Until the engines move, Purchasing has no rule editor or master-data import
  of its own; its first slices take their settings from versioned policy
  files, as Sales did before ticket 19.
