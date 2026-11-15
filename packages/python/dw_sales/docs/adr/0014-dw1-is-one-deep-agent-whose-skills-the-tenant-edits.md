---
status: Proposed
date: 2026-11-15
proposed-by: Đạt (2026-11-15, in conversation); written by the agent, not yet accepted
supersedes-if-accepted: dw_sales ADR 0012 decision 3, and "code chooses the step" wherever ADRs 0005 and 0010 imply it
---

# DW1 is one deep agent whose skills the tenant edits; code only guards

## Context

Đạt, 2026-11-15: code choosing which step reads a mail "là if else ... cứ
code nhiều hơn"; mail classification, intent, replies, thread tracking and
the other work should be skills (`AGENT.md`, `SKILL.md`, LangChain deep-agent
style) that Proterial configures without a code change, because flows written
as LangGraph nodes feel hard-wired.

What is true of the code today:

- Every DW1 model step is one versioned prompt with a fixed input and a typed
  output, its own eval, a live bar and a per-tenant switch (`model_steps`).
  This is measurable and easy to switch off, but adding a new kind of mail
  needs code: a member in a closed enum (`ThreadIntent`, the routing reasons),
  a row in a dispatch table (`INTENT_STEPS`), and a deploy.
- The platform already builds agents with `deepagents` 0.7.5
  (`agent_factory.build_agent`, every tool through `ToolExecutor`), and the
  system-prompt middleware keeps deepagents' skills catalogue in place
  (`system_prompt.py`). No skill store exists: nothing serves a tenant's
  `SKILL.md` to the agent.
- Prompts already resolve per tenant through `TenantOverlay`, and the
  rule-version flow (propose, dry run or replay, the head approves, never the
  proposer, stamped on the case) exists for rules and for learned SalesOrder
  rules (ADR 0013).
- Measured 2026-11-15 (ticket 30, local Qwen3.5-9B, not attested): the
  thread agent called a tool 2 times in 72 turns. A design whose routing
  depends on the model choosing a skill depends on exactly that behaviour.

## Proposed decision

1. **One DW1 agent, described in words.** An `AGENT.md` (role, conduct, what
   DW1 never does) and one `SKILL.md` per kind of work: classifying a mail,
   reading its intents, tracking a conversation, drafting a reply, asking PC,
   the confirmation, a change request, and so on. The agent reads the
   catalogue and loads the skill a mail needs. A new kind of mail is a new
   skill, not a new enum member or branch.
2. **Skills are tenant artifacts.** The platform ships defaults in
   `configs/skills/` (no customer data: the repository is public); a tenant's
   own or edited skill lives in its data and resolves through
   `TenantOverlay`. Editing one is the rule-version flow: written in the UI,
   replayed on the tenant's example mails with and without the change, approved by the head
   (never the proposer), stamped on every case that used it.
3. **Code guards; it does not route.** Code no longer chooses which skill
   reads a mail. Code still owns, and a skill can change none of:
   - the tenant, workspace and customer every tool is bound to;
   - the typed output each skill must produce, quotes located in the mail,
     every figure checked against a fact (`figure_check`);
   - every effect: a case moved, a recipient chosen, a Bravo file, an
     approval. The agent proposes; a person confirms;
   - conversation tracking by Message-ID / In-Reply-To / References (ADR
     0009). It is one deterministic function, not a branch, and a model's
     guess is worse than it.
   A skill adds no tool, scope, recipient or number (ADR 0012 decision 3
   holds inside this).
4. **Measured first, old steps kept as the fallback.** Each skill keeps its
   step's eval set, with added cases where the facts a skill needs are
   withheld from the prompt, so that only fetching them gets the answer right,
   and a grade for calling the right tool when needed. Until the agent passes a
   step's bar on the plant's model (Qwen3.8 on Strata, ADR 0025), that step
   stays the one-call reading it is today.
5. **Migrated one skill at a time**, intent reading first, each against its
   existing dataset before and after.

## Consequences

- Proterial changes how DW1 reads or writes a kind of mail without FPT on
  site; the cost moves from code review to the replay and the head's
  approval.
- Accuracy now depends on the model choosing well. On the 9B proxy it rarely
  chose to call a tool; if Qwen3.8 is the same, mails fall to a person more
  often than today, and the one-call steps stay.
- Tickets 33 and 34 (triage card, tenant skills) are rebuilt under this ADR
  rather than as ADR 0012 designed them; ticket 32's drafts become the
  drafting skill.

## Open

- Đạt: accept, amend or reject.
- The skill store's shape (one row per skill version per tenant, the
  replay's example set) and who may write a skill (PIC and head, as ADR 0012
  says, or the admin only).
