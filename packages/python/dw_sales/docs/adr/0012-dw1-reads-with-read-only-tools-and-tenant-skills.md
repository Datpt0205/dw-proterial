---
status: Accepted
date: 2026-11-13
accepted: 2026-11-13 (Đạt, on the grilling's recommendations Q9, Q11: "có chỗ nào để làm kiểu agentic … thay vì cứ code thuần")
amends: ADR 0005 decision 5 (no tools in a document turn)
---

# DW1 reads a thread with read-only tools and tenant skills; code still decides

## Context

Every DW1 model step so far is one call with a fixed input. A mail that does
not fit the input it was given (a table in the body, a portal notice, a
reply about two POs, a customer's own way of writing dates) falls to a
person as `other`, and the next one like it does too. The platform already
assembles agents (`agent_factory`: `create_agent`, every tool through
`ToolExecutor`, `SkillsMiddleware`); platform ADR 0007 (SEC02) forbids a
turn with document content any **outbound** tool, not read tools. DW1
declared no toolset at all, stricter than that. Tool calling on the plant's
model (Qwen3.8 on Strata, ADR 0025) is not measured.

## Decision

1. **Read-only tools, scoped by code.** DW1 gets a toolset of read tools:
   the thread's earlier messages, a snapshot of the thread's cases, a case
   by number, the conversion list, lead time and calendar, PC status. The
   tenant, workspace and customer a tool reads are bound from the run, never
   an argument the model passes: a mail saying "look up customer X's PO"
   reaches nothing outside the thread's customer. No tool writes, sends or
   approves.
2. **Where it is used:** reading a thread message into ADR 0010's intents
   and change lines; drafting a reply (code checks every figure, chooses the
   recipients, a person sends); a triage card for a mail nothing else read
   (what it seems to be, which case, a step from the closed set). Its output
   is the same typed schema code verifies today (ADR 0005 decisions 1–4).
3. **Skills are words, never power.** A skill is a versioned instruction a
   tenant adds through the tenant-version flow: a PIC or the head writes it
   in words from the triage card ("next time a mail like this…"), for one
   customer or all; the head approves, never the proposer, after a dry run
   showing the triggering mail read with and without it. A skill adds no
   tool, scope, recipient or number. Platform skills in `configs/` hold no
   customer data (the repository is public); a customer's own skill lives
   in the tenant's data. The case stamps the skill versions a reading used.
4. **Bounded and degrading.** A turn has a ceiling on tool calls, spend and
   time; no usable answer falls back to the one-call reading and then to a
   person, never to a guess.
5. **Measured first.** An eval of tool calling on the plant's model, with
   injection and cross-customer cases, is the gate (`model_steps`, ADR 0005
   addendum of 10-23); until it passes, every step stays one call.

Thread linking, the customer, case moves, recipients, sending, Bravo
writes, approvals and quota stay code's.

## Applied to tickets 30 and 31 (2026-11-15, by the agent, Đạt away)

Decisions 1, 4 and 5 for the first use decision 2 names, reading a thread
message into ADR 0010's intents. Drafting replies, the triage card and skills
are tickets 32 to 34. What this adds is recorded here, because no rule above
moved.

- **One bounded turn, on the platform's agent.** `AgentTurnPort`
  (`dw_agent_runtime.model.agent_turn`) asks a model what
  `InterpretationPort` asks, "these inputs into this schema, for this run",
  with the tools the worker's toolset pins. `AgentTurnKit` builds it with
  `build_agent` (every platform middleware, every call through
  `ToolExecutor`) and a `TurnCeiling` the agent factory now carries
  (`TurnCeilingMiddleware`, counted from the turn's own messages). The
  agent is compiled with no checkpointer at all (`checkpointer=False`):
  measured, a graph invoked inside DW1's node otherwise runs as its
  subgraph and writes the customer's words into the run's checkpoints.
- **The turn's ceiling is code's, not a tenant's.** Four model calls (the
  answer is one), 16,000 input tokens, 90 seconds
  (`thread_agent.CEILING`): bounds on a loop, sized to the plant's model,
  that no Sales person would set; the run's own ceiling
  (`configs/models/onprem.yaml`) still stops the run. Over the turn's,
  the one-call reading reads the message (`reply_intent`), else a person,
  and the reading says why (`ReplyReading.fallback`: `calls`, `spend`,
  `time`, `unavailable`), on the case's thread and in the activity rows.
- **Bound by code, around the turn.** The tools read a `ThreadBinding`
  code sets for one turn: the scope, the one customer the thread's linked
  cases are of (a thread of two customers' cases is not read by the agent),
  those cases as views, and the thread's earlier messages the log puts on
  them. No input names a customer, tenant or workspace; a tool with no
  binding, or one whose binding is another tenant's or workspace's than the
  run, refuses. Another customer's number or code finds nothing, held in
  the tool whatever the store behind it answers. No price, amount or
  person is shown.
- **Six tools, read-only**: `sales.thread_messages`,
  `sales.case_snapshot`, `sales.case_by_number`,
  `sales.conversion_lookup`, `sales.lead_time`, `sales.pc_status`; side
  effect `none`, approval `never`, scope `sales.inbox.process`, pinned by
  `sales-dw1@1.0.0`, which `configs/workers/sales.yaml` now names. Every
  one-call step still offers none. At a tenant ceiling of A0 a read asks a
  person (the platform's ladder), so the turn reads nothing and falls back.
- **The same answer, checked the same way.** The schema is
  `ModelThreadIntents`, the intents' definitions are `reply_intent@2.0.0`'s
  word for word (`thread_agent@1.0.0`), and `verified_intents` locates
  every quote in the message's newest part: a sentence a tool returned is
  never a quote a reading stands on, which is what holds an instruction
  planted in an earlier message.
- **Gated like every step.** `ModelStep.THREAD_AGENT`, the switch
  `model_assist.thread_agent` (off in every platform version and where a
  version does not say), and its bar (`model_readiness.BARS`): 0.85 on the
  bar set's intent accuracy, as the one call's, held only with no false
  `accepts` and no tool answering with another customer's record. Proposed
  by the agent. Known limit: a measurement names the profile's structured
  route's model, which the chat route shares today.
- **Only where mail is processed.** The worker builds the turn where it
  reaches the deployment's model server (`onprem_chat_models`); the API
  processes no mail and builds none.
