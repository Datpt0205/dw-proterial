# 30 — Eval: tool calling on the plant's model, the gate for 31–34

Status: ready-for-agent (the dataset and the harness; the live run waits on Strata)
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
