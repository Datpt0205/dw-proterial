# 42 — Hard-coded reading moved to skills, one family at a time

Status: in progress (family 1 done 2026-11-16; families 2-6 left, each after its skill passes its bar on Strata)
Blocked by: 40
Category: enhancement

## Why

Đạt, 2026-11-16: whatever code interprets that a skill and a tool could do
should move ("model cũng khá mạnh"), under dw_sales ADR 0014. Inventory
taken 2026-11-16 (read-only sweep of `dw_sales`): 18 places where code reads
language or a customer's format (A), 21 guards that stay code (B). The
2026-11-13 hardcode audit's closed findings are not repeated.

## A — to move (the model reads or proposes, code verifies)

By how often Proterial would otherwise need a code change:

1. **Mail kinds and their step table**: `domain/message_intent.py`
   `IntentKind`, `domain/dispositions.py` `RoutingReason` (also in the API
   contract and `labels.ts`), `application/order_intake.py` `MessageKind`
   and `INTENT_ROUTES`. A new kind of mail costs Python, contract, web and
   a deploy. Becomes the mail-classifying skill; code keeps the legal moves.
2. **Thread intents and `INTENT_STEPS`** (`domain/reply_intent.py`): the
   tenant's `thread-intents` skill (ticket 40) still cannot add an intent or
   a step proposal. The proposal becomes the skill's; B21 stays.
3. **Customer document formats**: `adapters/rfq_excel.py` reads RFQ forms by
   the mock customers' English labels, and its `"RFQ No."` marker decides a
   mail is a quote request before any model; `domain/change_requests.py`'s
   mail-body change table. Every new customer's form hits them.
4. **Item wording**: `domain/descriptions.py`'s word list and order (the
   default path; the model step is optional) and `domain/catalog.py`'s
   attribute values ("LIGHT BLUE" needs code). The values are better tenant
   reference data than a skill.
5. **Hand-off and reply kinds**: `order_intake.HANDOFF_KINDS`,
   `domain/handoffs.py` `HandoffKind`/`MODEL_SCHEMAS`,
   `reply_drafts.ReplyKind`: one drafting/hand-off skill family.
6. Smaller: file-name revision hints (`domain/revision_hints.py`); two
   different parsers for "which line" (`domain/handoffs.py` and
   `domain/change_requests.py`: one question, two answers, failure-modes #2);
   Bravo item-name grammar (`domain/item_names.py`, stable, errs blank);
   staff reminder and brief wording in `application/followups.py` and the
   assistant's fixed sentences (`configs/copy/` does not cover them); the
   assistant's fixed question catalogue (`QuestionKind`: ADR 0007 chose it,
   so moving it needs a decision).

Model steps that become skills: `message_intent`, `reply_intent` +
`thread_agent` (done in 40), `request_handoff`, `change_request`,
`pc_dates`, `design_text_reply`, `sender_customer`, `thread_summary`,
`rfq_extraction`, `po_body_extraction`, `description_attributes`, the
drafting family (`reply_draft`, `customer_reminder`, `screening_followup`),
`morning_brief`, `finding_explanation`, the assistant. Kept as one-call
proposals the head approves: `po_layout_proposal`, `bravo_template_mapping`,
`catalog_columns`, `salesorder_rules_proposal` (ticket 41 replaces it),
`rule_change_in_words`.

## B — stays code

Thread linking by headers; the classification order (malware, document,
upload, headers, then the model, then a person); a reading opens no door
code would not; Design mail by its verified mailbox; the buyer and the
sender's customer; outgoing mail by a member's sign-in address; unread mail
to a person; every quote, span, figure and unit check; `check_reply`; the
change request's unit/line checks; revisions by the printed revision;
`ModelStep` gates; file passwords; cutting quoted history; the state
machine and the person's confirmation.

## Found: a defect, fix first

`application/pc_dates.py` `reads_as` (about line 113) compares PC's dates
assuming day before month and ignores `dw_platform.domain.notation`, which
audit finding 9 made the one owner: a month-first or 年月日 date is dropped
silently. Fix it through `notation` with a test that fails today (ticket 37
territory, but it is a bug now).

## Acceptance

Per family moved:

1. With the skill off or below its bar, every mail is read exactly as before.
2. A tenant's new kind (of mail, intent, hand-off or draft) needs no code
   change: it is a skill version the head approved, and its step proposal
   is still checked against the legal moves.
3. The family's eval passes on Strata before its code path is removed; the
   removed code leaves no second answer behind.

## Done

- 2026-11-15, the defect above, fixed. `pc_dates.reads_as` reads PC's date
  with `rfq_reading.written_date`, now split out of `parse_date` so both
  read a written date the same way, in the order `notation_of` settles for
  the pasted mail. A month-first date (`11/20/2026`) and a 年月日 date
  (`2026年11月20日`, `12月4日`) are read. A date the mail does not settle
  (`03/04/2027` with no day over 12 beside it) is dropped for Sales to type,
  not guessed; so is a date in a mail whose dates go both ways. `written_in`
  treats a wide (Japanese) letter as a word edge, so a date written straight
  into Japanese text counts as whole, but 年月日 still join, so `11月20日`
  is not taken from `2027年11月20日`. The eval fixture now marks what code
  keeps (`kept`): the English `06/11/2026` and the lone `05/12` go to Sales.
  The injection mail's own date became `20/11/2026` so its live check still
  tests the injection.
  Tests: `dw_sales/tests/unit/test_pc_dates.py`.

## Done: family 1, mail kinds (2026-11-16)

Under dw_sales ADR 0014 ("Applied 2026-11-16: the mail kinds").

- **The skill**: `configs/skills/dw1/mail-kinds/SKILL.md` (1.0.0), the kinds
  and rules of `sales.message_intent@1.1.0` word for word, each kind a
  block (`- kind:` / `route:` / `label:` / `means:`) read by
  `domain/mail_kinds.py` (`mail_kinds_of`, `ROUTES` = `INTENT_ROUTES`' rows).
  A company's version is a `platform.rule_versions` row
  (`sales_skill_mail_kinds`, migration `beba87138cda` from `e1b1e0cadb66`,
  which also admits the step in the four step CHECKs); proposing one with
  an unknown route is refused (`skill_words_unreadable`); one that no
  longer reads when served is not used. Never offered to the thread
  message's skill pick (`skills.STEP_SKILLS`).
- **The step**: `application/mail_kinds.py` (`MailKindReader`, prompt
  `sales.mail_kinds@1.0.0`, schema built per call from the served kinds plus
  `none`), asked in `OrderIntake._classified` before the one call where
  `model_assist.skill_mail_kinds` is on and measured (`ModelStep.SKILL_MAIL_KINDS`,
  bar 0.90 on `all.kind_accuracy`, T0); one table routes both readings
  (`_routed_read`). No kind read: the one call, else a person, exactly as
  before. The reading stamps the kind, `routed_as`, `kind_label` and the
  skill version; activity counts it under its own step.
- **API and web**: `IntentReading.kind` is a string (no enum the web must
  know), with `kind_label`, `routed_as`, `skill`; the inbox shows
  `intentKindLabel` (the skill's label, else today's word).
- **Replay**: `MailKindReplay` (the worker's `sales_skill_replay` lane
  dispatches a mail-kinds proposal to it) on the message intent's 92 golden
  mails and 5 injections (`FixtureMailKindExamples`), by route.
- **Eval** `sales_mail_kinds@1.0.0`: golden re-scored through the skill,
  a company's new kind by a skill version only (acceptance 2), injection,
  cross-tenant, missing evidence, off/below bar/down/none read exactly as
  before (acceptance 1). **Strata, live, 2026-11-16**
  (qwen3.8-flash-next-q2_0, not attested): 92/92 (one call the same day
  0.978), p50 1.41 s / p95 1.52 s; the new kind 4/4; no injection opened a
  case. Recorded: `sales_mail_kinds_recorded.json` (101 answers).
- **Kept both paths** (acceptance 3 met on this run, not acted on): a
  company uses the skill step only once its own measurement is attested
  (`run_evals.py --live onprem --attest`), and the one call is what every
  company with `message_intent` on reads with today. Removing it is the
  step after the demo tenant is attested and switched.
- **The tests' rules (mock `sales_order_rules@1.5.2`) keep the mail kinds
  off**, the one exception to "every step on" there: the API's integration
  suite reads residue mail through the one call's recorded answers, and
  turning the step on would send it through `sales.mail_kinds`, which has
  no recordings for those mails. The skill path is tested with its own rules
  (`evals/mail_kinds.py`, `test_mail_kinds.py`).
- Not done here: item 6's "two parsers for which line" (not small: two
  readers with different inputs; left in item 6).
