# 07 — Shadow mode moved into the agent runtime

Status: ready-for-agent
Blocked by: none
Category: agent runtime / platform lift

## What

§7 Shadow mode: "Nâng lên `dw_agent_runtime` trước khi DW2 có bước model".
Checked 2026-11-27: only in `dw_sales/application/shadow.py` (Sales ticket
67: engine, hourly budget, retention lane `sales_shadow_retention`); nothing
in `dw_agent_runtime`. DW2 already has model steps
(`dw_purchasing/domain/mail_reading.py`, `offer_reading.py`) with no shadow.

## Design

- **What moves:** the decision `ShadowReadings.shadows` (switch on, step has a
  consumer, not on-and-passing, a model configured, hourly budget left),
  `ShadowBudget`, `SHADOW_KEPT_FOR` and the retention pass, as
  `dw_agent_runtime.shadow`, with Protocols for what it needs
  (`ShadowGatePort`, `ShadowReadingRepositoryPort`, the tenant's switch).
- **What stays in each context:** the readings' table (a reading is taken in
  the transaction of a person's decision on that context's case, so it lives
  in the context's unit of work), which steps have consumers, and how a
  decision labels a reading. Sales keeps `sales.shadow_readings`.
- **Switch and cap stay tenant rules** (`model_assist.shadow`,
  `shadow_calls_per_hour`); each context passes its own rule reader.
- The retention lane becomes one runtime consumer that each context registers
  with its repository in `apps/worker/src/dw_worker/main.py` (one lane name
  per context, as ADR 0011's audit actor needs).
- DW2 adopting it for its first step is a DW2 ticket after this one.

## Acceptance

- Sales' shadow tests pass with the engine imported from the runtime.
- Runtime unit: the budget is per tenant (tenant A's spent hour never stops
  tenant B); a step on and passing never shadows; no model, no shadow.
- import-linter: `dw_agent_runtime` imports no context.
- Mutation: the per-tenant budget key and the on-and-passing check, each red.

## Owed

- none.
