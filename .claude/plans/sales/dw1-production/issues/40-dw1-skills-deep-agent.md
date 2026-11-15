# 40 — DW1 as one deep agent: AGENT.md, tenant-edited SKILL.md, the first skill measured on Strata

Status: in progress (2026-11-16): 1, 2, 3, 5, 6 and the approval flow done; the replay and the skills page left (below). The step stays off: 0.183 on Strata.
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

## Done

Built under dw_sales ADR 0014 ("Applied to ticket 40" records each decision).

- **Platform skills**: `configs/skills/dw1/AGENT.md` (DW1's conduct) and
  `configs/skills/dw1/thread-intents/SKILL.md` (deepagents' format, intent
  definitions `reply_intent@2.0.0`'s word for word); pinned by the release
  manifest (`skills`: name, version, checksum). Turn prompt
  `sales.dw1_agent@1.0.0`.
- **Runtime** (`dw_agent_runtime`): `model/skills.py` (`Skill`, `SkillSet`,
  `serving`: the set code resolved, served around one turn, and the refs it
  loaded); `adapters/skills.py` (deepagents `SkillsMiddleware` over a
  backend that answers from the served set only, the catalogue in the
  platform's words, the skill loader tool refused for another tenant's or
  workspace's run); `AgentSpec.skills`, `AgentTurnKit.turn(skills=...)` and
  `register_skill_reader` (the loader offered only to a turn served skills).
- **The store**: a tenant's skill version is a `platform.rule_versions` row
  (`sales_skill_<name>`; migration `80584b911796` admits the key and the
  `skill_intents` step), tenant scope, RLS/grants/checks as the rules'.
  `dw_sales.application.skills`: `SkillBook.skill_set` (TenantOverlay, never
  sideways), `SkillsService` (list, propose; never applied directly),
  `SkillDecisions` (registered for `sales.skills`), `SkillSettlement`
  (worker handler for `sales.skills.decided`). Routes `GET /sales/skills`,
  `POST /sales/skills/{name}/versions` (`sales.rules.propose`).
- **The step**: `ModelStep.SKILL_INTENTS` (`model_assist.skill_intents`, off
  everywhere), bar 0.85 on `bar_set.intent_accuracy`; asked before the
  thread agent, then the one call, then a person. The reading stamps the
  skill versions loaded (`ReplyReading.skills`), shown on the reply in the
  case ("Đọc theo kỹ năng: …"). Tool `sales.read_skill@1.0.0`, toolset
  `sales-dw1@1.1.0`.
- **Eval** `sales_skill_intents@1.0.0`: golden (the 60 of `sales_reply@2.0.0`,
  the thread agent's 12, and 8 WITHHELD messages whose meaning is only in an
  earlier message; the share that looked up the right tool is graded),
  injection (a tenant's approved skill asking for a tool, another customer
  and an acceptance), cross-tenant (acceptance 1), missing evidence,
  bounded and off (acceptance 4). Recorded on Strata 2026-11-16: 0.183 on
  the bar's set (one call 0.796, thread agent 0.85), 276 look-ups in 80
  turns, 63 at the ceiling; withheld look-ups 8/8; no false accepts. One
  wording change against the looping was tried and made it worse (0.083);
  not kept. The step stays off.

## Left (follow-up)

- **The replay** of a proposed skill version on the tenant's example mails,
  with and without it (needs the model: a worker job), shown to the head
  before deciding (ADR 0014 decision 2). Until it exists, the head decides
  on the words alone, through `/approvals`.
- **The skills page** under the rules area (list skills, view the text,
  propose an edit, see the replay, send for approval): antd only, less
  text, detail on click. The API it needs exists.
- A tenant's wholly new skill (a name the platform does not ship), and a
  tenant's own `AGENT.md`.
- Why the agent loops on Strata, before the next measurement: the thread
  agent without skills does not (57 look-ups in 72 turns).
