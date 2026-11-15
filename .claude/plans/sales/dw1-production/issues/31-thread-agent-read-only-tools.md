# 31 — The thread agent with read-only tools

Status: done (2026-11-15); the step stays off until a measurement on the plant's model passes (ticket 30)
Blocked by: 26, 30
Category: enhancement

## Why

dw_sales ADR 0012 decisions 1, 2, 4.

## Shape

- Tool specs under `configs/tools/`, side effect none, a toolset under
  `configs/toolsets/` that `configs/workers/sales.yaml` pins; ADR 0005
  decision 5 as amended.
- Tools: thread messages, case snapshot, case by number, conversion
  lookup, lead time and calendar, PC status; customer and workspace bound
  from the run.
- Output: ticket 26's schema; ceilings on calls, spend, time; fallback to
  the one-call reading.

## Acceptance

1. No tool takes a customer, tenant or workspace argument (a test walks
   the specs).
2. A turn over its ceiling falls back and says so.

## Done

- **The platform's turn** (`dw_agent_runtime`): `model/agent_turn.py`
  (`AgentTurnPort`, `TurnCeiling`, `TurnCeilingReachedError`),
  `adapters/agent_turn.py` (`BoundedAgentTurn` over `build_agent`, the turn's
  inputs to `WorkerSystemPrompt` through a context variable, the last
  assistant message validated into the schema; `AgentTurnKit` building a
  worker's turn from its toolset and its profile's chat route),
  `adapters/turn_ceiling.py` (`TurnCeilingMiddleware`: calls and input tokens
  counted from the turn's own messages, checked before the call; time by
  `asyncio.wait_for`), `AgentSpec.ceiling`, `build_agent(checkpointer=False)`
  (measured: a turn inside DW1's node otherwise checkpoints into the host
  run's thread as its subgraph), `OnPremChatModelFactory` and
  `model_stack.onprem_chat_models` (the plant's server only, behind the
  outbound guard), `testing/memory_turns.py` and `MemoryToolExecutions`.
  `configs/models/onprem.yaml` 1.2.0 gains its `chat` route.
- **Six read-only tools** (`dw_sales.application.thread_tools`, specs in
  `configs/tools/sales.*@1.0.0.yaml`, toolset `sales-dw1@1.0.0` pinned by
  `configs/workers/sales.yaml`): thread messages, case snapshot, case by
  number, conversion lookup, lead time, PC status. Side effect `none`,
  approval `never`, scope `sales.inbox.process`. What they read is the
  turn's `ThreadBinding`, set by code (`bound_to`): the one customer of the
  thread's linked cases, those cases as views (no price, amount or person),
  the earlier messages the log puts on them. Unbound, or bound to another
  tenant or workspace than the run, a tool refuses; another customer's
  number or code finds nothing, held in the tool even when the store
  behind it answers for any customer.
- **The thread agent** (`application/thread_agent.py`, prompt
  `sales.thread_agent@1.0.0`, the intents' definitions `reply_intent@2.0.0`'s
  word for word): `ModelThreadIntents`, quotes located by
  `verified_intents` in the message only; `CEILING` 4 calls, 16,000 input
  tokens, 90 s. `OrderIntake._read_thread` asks it first where
  `ModelStep.THREAD_AGENT` is on and measured, then the one-call reading,
  then a person; a fallback is stamped (`ReplyReading.fallback`), shown on
  the case's thread ("DW1 tra cứu thêm không xong (…)") and is a row of its
  own in the activity (`domain/activity.py`). Built in the worker only
  (`assembly.thread_agent`, `WorkflowRuntime.agent_turns`).
- **Gate**: `ModelAssist.thread_agent` (default off), its placement on step
  O1 of the process page, `BARS[THREAD_AGENT]` (0.85 on
  `bar_set.intent_accuracy`; holds only with no false `accepts` and no
  foreign record found), migration `5461a43e48bf` admitting the step in
  both step CHECKs.
- Tests: `dw_agent_runtime/tests/unit/test_agent_turn.py`,
  `test_onprem_provider.py`; `dw_sales/tests/unit/test_thread_agent.py`
  (acceptance 1: the spec walk, and a demonstration that the walk fails on
  a tool taking a customer; acceptance 2: a turn over its ceiling falls
  back and says so; cross-customer, cross-tenant/workspace, the step off
  and unmeasured, an instruction in a tool's result, A0 at the executor);
  `test_dw1_runtime.py` holds every pin to `none`/`never`; web
  `case-replies.test.tsx`.
- Decisions recorded in dw_sales ADR 0012, "Applied to tickets 30 and 31".

Remains: tickets 32 to 34 (drafting, triage card, skills) use the same turn;
the thread agent reads with tools only once a tenant's version turns it on
and a measurement on the plant's model passes (ticket 30).
