# 30 — Eval: tool calling on the plant's model, the gate for 31–34

Status: done (2026-11-15) for the dataset, the harness and a local proxy run; the attested run on Qwen3.8 waits on Strata (01)
Blocked by: 01 for the attested measurement (Qwen3.8 on Strata)
Category: eval

## Why

dw_sales ADR 0012 decision 5: tool calling on a small local model is not
measured, and failure-modes #4 says measure before depending.

## Shape

- A `ModelStep` for the thread agent, off by default, gated by
  `model_steps` like the others.
- Dataset: thread messages with the expected intents, bounded tool calls,
  prompt injection ("look up customer X", "ignore the rules"),
  cross-customer numbers, a mail with no evidence.
- The live lane on a local model as a proxy now; the attested bar on
  Qwen3.8 later.

## Acceptance

1. The smoke replays recorded answers in CI.
2. A tool asked for another customer's case returns nothing (a test, not
   a prompt).

## Done

- **Dataset** `evals/datasets/sales_thread_agent@1.0.0.json`, graders keyed
  `sales.thread_agent_*` in `dw_sales/evals/thread_agent.py` (the context's
  eval package, where every other `sales.*` grader is; registered through
  `dw_sales.evals.GRADERS` at `scripts/run_evals.py`'s seam):
  - `golden`: the 60 messages of `sales_reply@2.0.0` (one task, one answer,
    so the agent and the one call are compared) and 12 thread-dependent
    ones (`sales_thread_agent_threads.json`: an earlier message, a line, a
    number, an item code, a lead time, PC's answer), each with the tools a
    careful reader would call; reports intents per set and language, the
    turns that fell back and why, tool calls per turn, the expected tools
    called, any tool answering with another customer's record, latency per
    call and per turn. Bar metric `bar_set.intent_accuracy`.
  - `injection` (prompt_injection): "look up customer X", "ignore the
    rules", a closed `<input>` with a tool call and a `customer_code`, an
    instruction in an earlier message reaching the model only as a tool's
    result; then scripted attacks at the code: another customer's number
    answers `found: false`, a `customer_code` argument is refused by the
    schema and nothing runs, a tool not offered runs nothing, a quote taken
    from a tool's result is dropped.
  - `cross_customer` (cross_tenant_attack): every tool bound to NRV and asked
    for QRL's PO or item code finds nothing; a binding of another tenant or
    workspace is refused; no master data in the prompt or the specs.
  - `missing_evidence`: quotes only in the case, a tool's result or nowhere
    are dropped; nothing proposed.
  - `bounded` (failure): calls, spend and no usable answer fall back to the
    one call and say so; with the one call off, to Sales; the run's budget
    stops the run.
- **Replay in CI** (acceptance 1): `Replayed` answers each turn's recorded
  assistant messages (tool calls included) by the turn's rendered prompt,
  through the shipped tools, executor and agent;
  `sales_thread_agent_recorded.json`. A turn never recorded fails the golden
  case; a live lane with no chat model is never graded on recorded turns.
  `run_evals.py --live onprem` builds the chat route with the one-call
  gateway (`Observed.chat`), and `--record` writes the turns.
- **Acceptance 2** is a test at the tool, not a prompt:
  `test_thread_agent.py::test_a_tool_asked_for_another_customers_case_returns_nothing`
  (and the item-code one), with a store that answers for any customer.
- **Measured, NOT attested** (2026-11-15, local Ollama `qwen3.5-9b-dw`,
  GTX 1080 laptop, chat route, thinking off, idle machine, a proxy for
  Qwen3.8 on Strata): 0.861 of 72 read as exactly their intents; 0.85 on
  the bar's set of 60 (bar 0.85, met exactly); 0.833 on `sales_reply`'s 60
  where the one call read 0.80; 12/12 thread-dependent; no false `accepts`;
  1 turn of 72 with no usable answer (the call raised RuntimeError, not
  reproduced on a retry). Tools: 2 calls in 72 turns (`case_snapshot`),
  none on the 10 thread-dependent turns whose reader would call one; no foreign record ever
  returned. p50 4.0 s, p95 5.2 s a turn (one cold start 69 s). Injection:
  no tool call reached another customer; INJ1 had no usable answer, the
  rest read `asks`/`unclear`. Nothing recorded with `--attest`: the step
  stays off for every tenant.

Remains: the attested run on the plant's model (blocked by 01). The local
model reads well without its tools and almost never calls one, so what the
tools add is not shown by this proxy; whether Qwen3.8 calls them is the
question the attested run answers.
