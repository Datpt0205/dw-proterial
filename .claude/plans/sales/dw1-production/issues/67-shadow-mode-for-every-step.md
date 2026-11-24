# 67 — Shadow mode shared by every model step

Status: in-progress (2026-11-24): slice 1 done (the engine and `description_attributes`), one switch on by default with an hourly cap; next, reply reading

## Why

Đạt, 2026-11-24: "làm theo đề xuất, bắt đầu cơ chế shadow dùng chung đi".
The 11-24 review found 18 of 19 model steps off, every one waiting on an
attested run on the plant, and labelled cases (ADR 0015 decision 5) written
for five steps only, and only while the step is on. A step that is off never
runs, so it never proposes, so no person's decision ever labels it: it can
never earn its threshold on real work, and the plant's real mail measures
nothing. ADR 0015 decision 4 says a step "runs in shadow mode (decides and
logs, applies nothing)" until it has its labelled cases; the code had shadow
only for a step that is on and stopped by its audit.

## What

A third state between off and on, the same for every step:

- **The tenant turns a step to shadow** (`model_assist.shadow`, a list of
  steps, on the process page beside the step). A step in shadow that is not
  on and passing runs where a model is configured for it; its result is
  stored (`sales.shadow_readings`) and applied nowhere, shown nowhere.
- **A person's decision labels it.** Where the person makes the decision the
  step would have proposed, the step's own service takes the stored reading
  for that item and writes a labelled case (gate `shadow`) in the decision's
  transaction. The labels count in the head's view, set the step's threshold
  like any other (`ThresholdLane`), and are the accuracy on real work before
  the step is ever turned on.
- **One shared store and engine**, each step adding two lines: where it
  would read (keep), and where the person decides (take and label).
- **Bounded**: a reading is deleted when it is labelled, and the
  `sales_shadow_retention` lane drops readings no person decided within
  `SHADOW_KEPT_FOR`.

Slice 1: the engine and `description_attributes` (a line's PRV code from its
description; the person's decision is the code Sales confirms). Next slices:
reply reading (`reply_intent` and `skill_intents` beside each other, labelled
by the step Sales takes), `message_intent`, `po_body_extraction`.

## Acceptance

1. A step off and listed in shadow reads, stores, and changes nothing on the
   case; not listed, nothing is read.
2. A step on and passing runs as before; in shadow only while not passing.
3. Sales confirming a line's code writes one labelled case from the stored
   reading (confirmed or corrected), and the reading is gone.
4. A tenant's shadow list names only steps with a shadow consumer; any other
   is refused when the rules are read.
5. Another tenant's or workspace's reading is never taken (RLS, tested).
6. Readings no one decided are dropped after the term, in their own scope.

## Done

Slice 1, 2026-11-24 (dw_sales ADR 0015 addendum 2026-11-24):

- **Config**: `ModelAssist.shadow` (tuple of `ShadowStep`, schema offering
  only `SHADOW_STEPS`, refused otherwise), placed on step O2 beside the
  switch; web label "Bước chạy thử ngầm (shadow)".
- **Engine**: `domain/shadow.py` (`ShadowReading`, `item_key` = the gate's
  key, `shadow_label` gated ``shadow``, `description_shadows`);
  `application/shadow.py` (`ShadowReadings.shadows/keep`, `ShadowRetention`);
  `ModelReadiness.configured`; uow member `shadow_readings`
  (`SqlShadowReadings`: keep ON CONFLICT DO NOTHING, take = DELETE ...
  RETURNING, prune); memory twin in the eval world.
- **Migration** `a201f3d7ad6f`: `sales.shadow_readings`, tenant AND
  workspace policy (the shape with `app.workspace_scope`), ENABLE/FORCE,
  SELECT/INSERT/DELETE for `dw_app`, UPDATE revoked, step CHECK held to
  `ModelStep` by a test, lengths by `char_length`.
- **First step**: `OrderIntake._read` reads in shadow when the step is not on
  and passing; `OrderCommands.confirm_mapping` labels the line's reading.
- **Worker**: `sales_shadow_retention`, hourly, per workspace, audited as
  the lane with the count.
- **Tests**: unit `test_shadow_readings.py` (10), integration
  `test_sales_shadow_readings.py` (7) + privileges + RLS coverage, green.
  Mutation check: 7 guards removed one at a time, each turned a test red.
- **Security walk**: tenant (RLS on tenant AND workspace, unscoped reads
  nothing, another scope never takes; tests); authorization (the label is
  written only inside the existing `confirm_mapping`, which checks
  `sales.order.prepare`); autonomy (nothing applied or shown; asserted equal
  to the step off); untrusted content (the same reader and its checks as
  on); audit (labels in the decision's transaction; retention audited as
  the lane); lifecycle (deleted on label, dropped after 60 days, fail closed
  with no model). Deployment: no route, no compose change.

Same day, Đạt: "bật full 1 lần": the list became one switch,
`model_assist.shadow` (on unless a version turns it off), with
`model_assist.shadow_calls_per_hour` (120 per tenant, `ShadowBudget`, per
process): past it a step reads as off until the hour turns. Mutation 3/3.

Measured before choosing the cap (all 45 sample mails, every step ON, live
on Giang's Strata, not attested): 0 errors, 23 calls all usable, 0.5 calls
per mail (max 3, 32 mails none), calls 1-3 s (one 31.7 s, the first
hand-off: a cold start); intake-time steps only (drafts, SalesOrder, chat,
internal change are asked by a person). The reply agent's chat turns are
not counted by the run's wrapper.

Left: reply reading, `message_intent`, `po_body_extraction` as shadow
consumers; a line on the process page showing each step's shadow labels.
