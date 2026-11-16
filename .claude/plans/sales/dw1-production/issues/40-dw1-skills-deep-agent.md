# 40 — DW1 as one deep agent: AGENT.md, tenant-edited SKILL.md, the first skill measured on Strata

Status: done (2026-11-16): the scored skill pick, the replay and the skills page built; the step stays off (0.800 on Strata's bar set: level with the one call's 0.796, under the 0.85 bar). What is left below is follow-up, not this ticket.
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

## Done (2026-11-16, the follow-up)

Under dw_sales ADR 0015 decision 5 (the skill is picked by one scored call).

- **The scored pick**: `application/skill_pick.py` (`SkillPicker`, prompt
  `sales.skill_pick@1.0.0`): ONE structured call whose schema is an enum of
  the skills served to the run's tenant plus `none`, scored by the name's
  token probabilities; code reads a name the set does not serve, `none`, a
  pick with no confidence or below `model_assist.skill_pick_confidence`
  (tenant config, default 0.9, 0.5..1) as no pick, and the message is then
  read exactly as with the step off (`ThreadAgent.read` returns None,
  `OrderIntake._read_thread` moves on). The picked skill's words go into the
  one reading turn, `sales.dw1_agent@1.1.0` (DW1's conduct, `AGENT.md`
  1.1.0, and the skill, both contained like every input: no shipped prompt
  takes a raw variable); no catalogue and no loading tool, the look-up tools stay
  under `SKILL_CEILING`. The pick's call is timed in the activity record.
- **Measured on Strata, live, once** (2026-11-16, Qwen3.8-Flash-Next Q2_0,
  not attested; `evals/reports/live-onprem/sales_skill_intents@1.0.0.json`):
  bar set **0.800** (the one call 0.796, the thread agent 0.85, the free
  choice 0.183), 0.75 on all 80; the skill alone where picked 0.797. Picks:
  thread-intents for all 80, confidence p50 0.98, min 0.70, one below the
  floor. **One false accept** (RP16). 3.09 model calls per message (one
  pick, 2.1 turn calls), 90 look-ups in 80 turns, 3 at the ceiling (63
  before); per message p50 4.4 s, p95 6.1 s (pick p50 1.04 s). Withheld:
  6/8 looked up with the right tool. No tool answered for another customer.
  The looping is gone; the bar is not met. The step stays off. (A first run
  the same day, with the conduct as a raw variable, read 0.683 with two
  false accepts; the prompt was changed to contain it and measured again.)
- **The eval** records the pick (which skill, how sure, per message), scores
  the step as deployed (the skill's reading where picked, the one call's
  where not) and the skill alone; `bounded` adds the four unsure picks
  (none, below the floor, no confidence, a name not served), each read as
  off. Recorded picks `sales_skill_pick_recorded.json` (answers and
  confidences; `run_evals.py --record` writes `confidences`), turns
  re-recorded, the 1.0.0 transcripts dropped.
- **The replay**: `application/skill_replay.py` (`SkillReplayer`), the
  worker's `sales_skill_replay` lane every five minutes over the workspaces
  with Sales cases (`consumers/sales_skill_replay.py`): each proposed skill
  version of the scope's tenant with no replay is read on example mails with
  the proposal and with the skills in force, by DW1's agent with skills as it
  runs, each reading its own run (the lane's actor, `sales.inbox.process`
  only, freed from the spend ledger after), and stored with its audit row:
  `sales.skill_replays` (migration `e1b1e0cadb66`, from 43's `137ec1972538`;
  tenant-only RLS like `rule_versions`, ENABLE+FORCE, SELECT/INSERT only,
  CHECKs, unique per version, cascades with it). Examples: the 60 golden
  replies of `sales_reply@2.0.0` and the thread agent's 4 injections
  (`adapters/skill_examples.py`, the fixtures the worker image ships); the
  security cases (injections, conditional and non-answer replies) fail on a
  read `accepts`. **The head may approve only a replayed version**
  (`SkillDecisions`: `skill_not_replayed`); rejecting needs none.
- **The skills page** `/sales/rules/skills` (linked from Quy tắc): each
  skill (platform or the company's, its words on click), the company's
  versions with status, the replay ("Đúng X/N với bản đề xuất · Y/N với bản
  đang dùng", incomplete and failed security cases said plainly), "Đề xuất
  sửa" (`POST /sales/skills/{name}/versions`, the idempotency key per press),
  "Mở phê duyệt". `SalesApi.skills()` / `.proposeSkill()`.

## Left (follow-up)

- **Why the reading is 0.80, not 0.85**: the skill's turn reads as the one
  call does (0.797 vs 0.796) and gave one false accept (RP16); the look-ups
  no longer loop. Compare per message (`missed` in the report) before
  another wording.
- The replay reads the platform's example mails only: nobody labels a reply
  reading yet (ticket 43 lists reply intents among the steps no person
  confirms). The stored `source` names it, so the tenant's own cases are a
  second source, not a change of meaning.
- `sales.read_skill@1.0.0` is still registered and pinned by
  `sales-dw1@1.1.0` but offered to no turn (the free choice is gone): drop
  it with the next toolset version.
- A tenant's wholly new skill (a name the platform does not ship), and a
  tenant's own `AGENT.md`.
- The release manifest needs regenerating (`make release-manifest`) once
  tickets 40 and 43 are both in: new prompts, `AGENT.md` 1.1.0.
- **2026-11-16, the plant's RTX PRO 4000 (Strata Q2_0, one slot), measured,
  not attested: `skill_intents` 0.717 on the bar set (lab 0.800), 0.675 all,
  vi 0.654, en 0.743, ja 0.579; false accepts RP16, RP17.** The pick is not
  the cause: `thread-intents` picked for 80 of 80, confidence p50 0.985, one
  below the 0.9 floor. The reading is: 26 misses, nearly all an intent added
  that `thread-intents/SKILL.md` rules 2-4 forbid (accepts -> accepts+asks
  RP03/04; rejects -> cancels+rejects RP11/13; requests_change ->
  asks+requests_change RP14/19, -> accepts+requests_change RP16/17), so 53.7 %
  went to a person; 8 turns gave no answer (180 agent calls for 80 mails, up
  to 5 in a turn). The skill was unchanged (no diff). `thread_agent`, the same
  task on its own shorter prompt, reached 0.85. Ways forward for the code
  session, cheapest first: (1) a guard in code that "accepts" never stands
  with "requests_change" (rule 2; removes both false accepts); (2) two intents
  quoting the same sentence merge into the main one (quotes are 100 %); (3)
  measure thinking on for this step alone; (4) corrections as examples
  (ticket 43); (5) give the case snapshot up front so fewer turns hit the
  ceiling. The step stays off; every reply goes to a person meanwhile.
