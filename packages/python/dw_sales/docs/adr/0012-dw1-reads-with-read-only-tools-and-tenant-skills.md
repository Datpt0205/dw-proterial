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

## Applied to ticket 32 (2026-11-15, by the agent, Đạt away)

Decision 2's second use, drafting a reply. What this adds is recorded here,
because no rule above moved.

- **One call, no tools.** The draft is worded from facts code gathered, and
  code's check reads those facts alone (`figure_check`): a figure a tool
  found would be dropped by that check anyway, so a turn with tools would
  add calls, spend and an injection surface and nothing the draft may say.
  Decision 4's fallback is then simply "no draft". The toolset stays the
  reading's.
- **Four kinds** (`application/reply_drafts.py`, prompt
  `sales.reply_draft@1.0.0`): an answer to a customer's reply on the order
  read `asks` (no template exists: the model's wording is the only draft,
  or Sales answers), 6-DW4 and 6-DW3 (ADR 0010, ticket 29) and the
  confirmation (ADR 0011; 6.3 when the loop sends it again). The last three
  are offered exactly while the template draft of the same kind is
  (`ORDER_GATES`, their one owner), beside it, never in its place: with the
  step off, the template path is unchanged.
- **The example is the tenant's own letter** of that kind, from its mail copy
  (`sales_emails`, through `ArtifactCopyPort`), placeholders kept, its line
  template left out (the confirmation's line names a price). The question's
  letter is new in `sales_emails@1.4.0` (`question_answer`); no draft is drawn
  from it. Where deployed, copy marked mock is refused as for a template.
- **No amount in any draft.** None of the four is "about a price" here: no
  unit price, total, currency or percent is a fact of any kind, the
  confirmation's included (its prices reach the customer in the template's
  draft and the processed Excel, drawn under `sales.price.read`), and the
  check drops a draft naming one. A customer's question about a price is a
  person's. A price-bearing wording would be a new kind with its own scope.
- **The check**: every figure of subject and body among the facts (a figure
  only the customer's question holds is not a fact: echoing their asked date
  as if confirmed is dropped), no amount, no e-mail address or link. A
  dropped draft says why and which figures; the person has the template's
  draft, or nothing. Recipients are the customer's contacts in master data,
  as every customer draft's; the model's answer has no field for one.
- **`names_amount` no longer reads "đồng" alone as money** (platform
  `figure_check`): only after a number ("1.000 đồng", "5 triệu đồng").
  Measured: every Vietnamese 6-DW3 writes "đồng ý" (agree), and a cable
  maker writes "lõi đồng" (copper core); both were dropped as amounts.
- **Gated like every step**: `ModelStep.REPLY_DRAFT`, the switch
  `model_assist.reply_draft` (off in every platform version and where a
  version does not say; placed on O10 of the process page), bar 0.85 on
  `all.complete` (a draft kept and stating the PO and each date it answers
  with), held only while no kept draft names an amount or an address.
  Proposed by the agent. Migration `3aca293b2c92` admits the step in both
  step CHECKs. Nothing is stored and nothing is sent; no activity row.
