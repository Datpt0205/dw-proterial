# 34 — Skills: a tenant teaches DW1 a kind of mail in words

Status: done (2026-11-16): rebuilt under dw_sales ADR 0014; most of it was built by tickets 40 and 42, the card-to-skill path and the taught mail in the replay are built here
Blocked by: 33
Category: enhancement

## Why

dw_sales ADR 0012 decision 3 (grilling Q11).

## Shape

- A skill is a tenant version (the `sales.rules` flow): words, a scope
  (one customer or all), proposed by a PIC or the head from a triage card,
  approved by the head (never the proposer) after a dry run showing the
  triggering mail read with and without it.
- A skill adds no tool, scope, recipient or number; the reading stamps
  the skill versions used.

## Acceptance

1. The proposer cannot approve their own skill.
2. A skill text asking for a tool or another customer changes nothing a
   tool can reach (negative test).

## Done (2026-11-16, rebuilt under dw_sales ADR 0014)

Already met before this ticket, by tests that exist:

- A skill is a tenant version in the rule-version flow, proposed by
  `sales.rules.propose`, decided on a `sales.skills` approval by
  `sales.rules.approve`, never applied directly (ticket 40).
- **Acceptance 1** (the proposer cannot approve their own skill):
  `test_skills.py::test_the_proposer_cannot_approve_their_own_skill` (the
  rule guard's maker-checker, kept); for a kind taught from a card,
  `test_triage_card.py::test_the_proposer_of_a_taught_kind_cannot_approve_it`.
- **Acceptance 2** (a skill asking for a tool or another customer changes
  nothing): for the thread reading, `sales_skill_intents@1.0.0`'s injection
  case (ticket 40); a version naming a route outside the closed set is
  refused when proposed and unused when served
  (`test_mail_kinds.py::test_a_proposal_naming_an_unknown_route_is_refused_and_a_new_kind_waits`,
  `::test_a_version_naming_an_unknown_route_is_not_used_when_served`); a
  version names no tool, scope or recipient
  (`test_skills.py::test_a_proposal_names_no_tool_scope_or_recipient`).
- A new kind needs only a skill version (ticket 42, `sales_mail_kinds`
  new-kind case); the reading stamps the skill version
  (`IntentReading.skill`, `ReplyReading.skills`); the replay reads golden
  mails with and without the version (`MailKindReplay`).

Built here:

- **From a card**: `SkillProposal.from_message`; the server finds the mail
  and its card in the proposer's own workspace (RLS) and records it on the
  version (`SkillDocument.trigger`); only the mail kinds are taught from a
  card (`skill_trigger_refused`). Inbox: "Dạy DW1 loại thư này" opens the
  mail kinds' words to edit (`_components/propose-skill.tsx`, shared with
  the skills page).
- **The taught mail in the replay**: `SkillReplayer` reads it with the
  version and with the one in force beside the golden mails, in its own
  workspace's lane only (`TriggerReplay`, `sales.skill_replays.trigger`);
  the skills page says both readings.
- **Acceptance 2 for the mail kinds**: a taught skill whose words ask for a
  tool, another customer and a route to approval changes nothing a card
  can reach (`test_triage_card.py::test_a_taught_skill_asking_for_a_tool_or_another_customer_reaches_nothing`,
  and the `sales_triage_card` injection grader).

## Left

- A skill scoped to one customer (Shape: "one customer or all"): skills
  are the tenant's (ADR 0014 as applied to ticket 40); a customer's own
  words exist only for its SalesOrder skill (ticket 41).
- A workspace with routed mail but no Sales case is not enumerated by the
  replay lane (`SqlFollowupScopes`), so a kind taught from a mail there would
  wait unreplayed.

