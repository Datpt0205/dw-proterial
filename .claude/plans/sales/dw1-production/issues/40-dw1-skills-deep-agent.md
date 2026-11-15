# 40 — DW1 as one deep agent: AGENT.md, tenant-edited SKILL.md, the first skill measured on Strata

Status: ready-for-agent (after the Strata measurement of 2026-11-16)
Blocked by: none (33 and 34 are rebuilt on top of this)
Category: enhancement

## Why

dw_sales ADR 0014, accepted by Đạt 2026-11-16 ("tôi duyệt"), on the
condition that it is measured on Strata (Giang's home lab) before the agent
replaces a step.

## Shape

- `configs/skills/dw1/AGENT.md` and one `SKILL.md` per kind of work, platform
  defaults with no customer data; a tenant's own or edited skill in its data,
  resolved through `TenantOverlay`; served to deepagents' `SkillsMiddleware`
  through `agent_factory` (the catalogue survives `system_prompt.py`).
- The skill store: one row per skill version per tenant (RLS, FORCE, grants,
  migration), the rule-version flow: written in the UI, replayed on the
  tenant's example mails with and without it, the head approves, never the
  proposer; the case stamps the skill versions a reading used.
- First skill: reading a thread message's intents (ticket 26's schema and
  checks unchanged). Its eval is `sales_reply@2.0.0` plus cases where the
  facts are withheld so only a tool call gets them right, and a grade for
  calling the right tool when needed.
- The agent replaces the one-call step only where it passes that step's bar
  on Strata; the step stays as the fallback.

## Acceptance

1. A tenant's edited skill changes the reading of its replayed example and
   nothing another tenant reads (negative test).
2. A skill asking for a tool, a scope, a recipient or another customer
   changes nothing a tool can reach.
3. The proposer cannot approve their own skill.
4. With the agent off or below its bar, every mail is read exactly as before.
