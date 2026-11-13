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
