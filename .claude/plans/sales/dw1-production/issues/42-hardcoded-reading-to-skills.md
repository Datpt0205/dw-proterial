# 42 — Hard-coded reading moved to skills, one family at a time

Status: in progress (families 1, 3 and 5 done 2026-11-16; family 6's follow-up wording done 2026-11-16; families 2, 4 and the rest of 6 left, each after its skill passes its bar on Strata)
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

## Done: family 3, customer document formats (2026-11-16)

Under dw_sales ADR 0014 ("Applied 2026-11-16: the document forms").

- **The skill**: `configs/skills/dw1/document-forms/SKILL.md` (1.0.0): per
  form a block (`- kind:` / `customer:` / `route:` / `means:`) read by
  `domain/document_forms.py` (`document_forms_of`, `FORM_ROUTES` =
  `quote_request` only, `customer` a code or `any`) on family 5's one block
  reader (`domain/skill_blocks.py`). The platform's two forms are for any
  customer: the standard English form, naming every label `rfq_excel` reads
  (a test holds them together), and a customer's own request sheet in
  general words. A company's version is a `platform.rule_versions` row
  (`sales_skill_document_forms`, migration `42b7626a1bb7` from
  `99ae8f7eb765`, which also admits the step in the four step CHECKs, each
  rebuilt from the values it holds); proposing one with an unknown route, a
  customer that is no code or a form named twice is refused
  (`skill_words_unreadable`); one that no longer reads when served is not
  used. Never offered to the thread pick (`skills.STEP_SKILLS`).
- **The step**: `application/document_forms.py` (`DocumentFormReader`,
  prompt `sales.document_forms@1.0.0`, schema built per call from the forms
  of the sender domain's customer and of any customer, plus `none`); the
  answer is ticket 29's spans, verified by `verify_rfq` and built into the
  request by `RfqModelReader.request_of` (made public for it, with
  `calls_for`), every value flagged `model_read`. Stamped
  `RequestReading.skill` / `form`; activity and labelled cases count it
  under `ModelStep.SKILL_DOCUMENT_FORMS` (`domain.activity.request_step`),
  bar 0.85 on `all.right_field`, T0, switch `model_assist.skill_document_forms`
  off everywhere (the test rules 1.5.2 too, with the reason).
- **Where it is asked**: the quotation flow (`QuotationService._model_read`)
  after the fixed reader, before ticket 29's reading; intake
  (`OrderIntake._a_form`) where no reader recognised a file, the sender's
  domain names a customer and nobody uploaded it: a file it reads into a
  request makes the mail a quotation request beside the `RFQ No.` marker,
  which stays code's first door. Off, below its bar, the model down, `none`
  or nothing verified: exactly as before. Two readings of one file (intake
  recognises, the quotation flow reads) are two calls; accepted for now.
- **Replay**: `DocumentFormReplay` (the worker's `sales_skill_replay` lane
  dispatches a document-forms proposal to it) on ticket 29's request
  spreadsheets and the forms fixture (`FixtureDocumentFormExamples`), right
  when every stated value reads as stated; the order and the invoice are
  security cases.
- **Eval** `sales_document_forms@1.0.0` (graders `dw_sales.evals.document_forms`):
  golden, a new customer's form by a skill version only (acceptance 2:
  the fixed reader misses all three, the version proposed and waiting,
  intake takes the mail with the step on and not off), injection in a
  cell, cross-tenant and cross-customer, missing evidence (a span not in
  the file, no currency, a hidden row, an order and an invoice), off /
  below bar / down / `none` read as before (acceptance 1). **Strata, live,
  2026-11-16** (qwen3.8-flash-next-q2_0, not attested): 0.893 right (bar
  0.85), 0.005 wrong; ticket 29's 18 files by the platform's skill 0.871,
  the three new forms by the company's version 33/33 (by the platform's
  skill alone 0.939); p50 7.15 s, p95 17.97 s. Recorded:
  `sales_document_forms_recorded.json` (27 answers).
- **Kept both paths** (acceptance 3 met on this run, not acted on): the
  fixed reader and its marker read first, ticket 29's reading after a form
  reads nothing; removing either waits for an attested measurement.
- **Not moved, on purpose**: `domain/change_requests.py`'s mail-body change
  table (also named in item 3). Read again, it reads no header's words: a
  row is the order's by its PO number, its line by a code of the case, the
  asked date's column by the values alone, and a quantity never from a
  table; a change in words already goes to the change-request model step.
  Nothing there is a customer's language. Its "which line" question is item
  6's (one question, two parsers), and belongs with that.
- **Not done**: a quantity whose unit is only in its column's header stays
  deferred (`verify_rfq` takes a unit from the item's line only); taking it
  from the same column's header cell is a change to ticket 29's checks,
  left for a decision.

## Done: family 5, hand-off and reply kinds (2026-11-16)

Under dw_sales ADR 0014 ("Applied 2026-11-16: the hand-off and reply kinds").

- **The skills**: `configs/skills/dw1/handoffs/SKILL.md` (1.0.0, ticket 33's
  three kinds, each `asks:` one of the three typed field sets and `to:` the
  team the copy writes it to) and `configs/skills/dw1/reply-drafts/SKILL.md`
  (1.0.0, ticket 32's four drafts, each `drafts:` itself), read by
  `domain/handoff_kinds.py` and `domain/reply_kinds.py` on family 3's one
  block reader (`domain/skill_blocks.py`). A version naming a recipient, a
  send, a price, an amount, a tool, a team, field or draft code does not
  hold, or a hand-off kind named after a route that takes none, is refused
  when proposed (`skill_words_unreadable`) and unused when served. Both are
  `STEP_SKILLS`, never offered to the thread pick. `ReplyKind` moved to the
  domain; `HandoffTeam` too.
- **The hand-off step**: `application/handoff_kinds.py` (`HandoffKindReader`,
  prompt `sales.handoff_kinds@1.0.0`), asked in `OrderIntake._with_handoff`
  first where `model_assist.skill_handoffs` is on and measured
  (`ModelStep.SKILL_HANDOFFS`, T1, bar 0.85 `all.right`): the kind the
  reading stamped (only where its route is the reason the mail was routed
  for), else the reason's platform kind. Every value goes through
  `HandoffReader` as before; the stamp carries the skill version, kind,
  label and team, rendered to the skill's team; the inbox card shows the
  label. No kind of the skill, no usable answer, off or below bar: ticket
  33's one call exactly as before. A disposition holds a hand-off only of
  its reason or its reading's kind.
- **The reply step**: `ReplyDrafts.draft` takes a kind name; where
  `model_assist.skill_reply_drafts` is on and measured
  (`ModelStep.SKILL_REPLY_DRAFTS`, T0, bar 0.85 `all.complete`) and the
  served version names it, it is worded under `sales.reply_kinds@1.0.0` as
  the draft the skill maps it to (gate, facts, `check_reply`, recipients the
  draft's); the view says `drafted_as`, `kind_label`, `skill` and the other
  kinds of the same draft (`others`), which the order page offers by label.
  Otherwise ticket 32 exactly; a company's kind is not found.
- **Storage**: migration `7c00901ada90` (from family 3's `42b7626a1bb7`)
  admits `sales_skill_handoffs`, `sales_skill_reply_drafts` and the two
  steps in the key and four step CHECKs, rebuilt from the catalog.
- **Replay**: `HandoffKindReplay` (ticket 33's golden mails and the new
  kind's, by what code locates, no order resolved) and `ReplyKindReplay`
  (ticket 32's twelve drafts' facts,
  `evals/fixtures/cases/sales_reply_kinds_examples.json`, by `check_reply`
  and the PO stated), dispatched by `SkillReplayer` (`StepSkillReplay`); a
  step skill whose replay is not wired waits unreplayed.
- **Evals** `sales_handoff_kinds@1.0.0` and `sales_reply_kinds@1.0.0`:
  golden re-scored through the skill, a company's new kind by a version only
  (a certificate request to QA through intake; a short confirmation),
  refused versions, injection, cross-tenant, missing evidence, off / below
  bar / down / unreadable exactly as before. **Strata, live, 2026-11-16**
  (qwen3.8-flash-next-q2_0, not attested): hand-offs 0.863 right, 0 wrong
  (bar 0.85; the one call replays 0.849; a first run 0.849 with two
  transport failures), the new kind 2/2; reply drafts 10/12 complete (0.833,
  **below** the 0.85 bar, both Japanese figure refusals). Recorded:
  `sales_handoff_kinds_recorded.json` (40), `sales_reply_kinds_recorded.json`
  (14).
- **Kept both paths**: the reply kinds are below their bar; the hand-off
  kinds passed on this run, but a company uses the step only once its own
  measurement is attested. The tests' rules (mock 1.5.2) keep both steps
  off, as they do the mail kinds.
- Not done here: a new hand-off kind is written with its field set's
  platform words (the `sales_handoffs` copy is keyed by the three kinds;
  keying it by kind is a copy schema change, left for a decision); no
  Design recipient (none in master data).

## Done: family 6, one answer to "which line" (2026-11-16)

- **One function**, `domain/named_lines.py` `named_line(lines, words)`, over
  the order's lines by number and the codes each is known by
  (`LineNames`; a case's line by `names_of`: the customer's code as entered
  and the PRV code its checks ran against; an ERP sales order's line by its
  PRV code). It replaces `domain/handoffs.py` `line_number_of` (removed, with
  its word list `dòng|line|ln|no|#|行`) and `change_requests.named_line`
  (moved). Callers: the hand-off (`HandoffReader._order_line`; the
  customer's conversion list still turns words naming nothing into a PRV
  code, read by the same function), the customer's change request
  (`model_changes`) and PC's internal change (`read_internal`).
- **The rule**: a code of the order written whole in the words names its
  line; else the one number the words state, a number of its own (not part
  of a code such as `KMH-21-0077`, nor of `1.5` or `1,200`; `No.2` is 2);
  where both are there they must agree (a code of one line beside another
  line's number names neither, refused; among lines sharing a code, the
  number tells them apart). No word list decides which words announce a
  line number: the model chose the words.
- **Where the answers differed**, and what each caller now gets: the
  hand-off took the number first and a code only as the whole words
  (`cáp VX-C2F05`, `品番CVG-0005` named no line; now they do where the code
  is one the order's line is known by); a quantity's
  words given as a line's (`12 cuộn`) named no line there and line 12 in the
  change request (now line 12 everywhere: the model said those words name
  the line, and the line must exist); a code of one line beside another
  line's number was the number's line in the hand-off and the code's in the
  change request (now refused); digits of a code (`2行目（KMH-21-0077）`
  with the code not the order's) were three numbers in the change request
  (now the 2).
- **Measured on recorded answers**: `sales_handoff` 7/7 (right 0.849, as
  before), `sales_handoff_kinds` 6/6 (0.863, as before),
  `sales_change_request` 6/6, `sales_internal_change` 5/5.
  Tests: `test_named_lines.py`, `test_handoffs.py`, the change request and
  internal change suites.
- **Left on purpose**: `change_requests._row_line`, which reads a mail
  TABLE's row, answers a different question: no model chose its cells as
  the line's words, so it takes a line only from a cell that IS a code of
  the order (a line number among the cells only tells apart lines sharing
  it). Reading a lone number in a row as the line, as words are read, would
  take a quantity or an id for a line.

## Done: family 6, the follow-ups' words (2026-11-16)

- **The copy**: `configs/copy/sales_reminders@1.0.0.yaml`, read by
  `application/reminder_copy.py` (`ReminderCopy`): a title and body per
  reminder and per way it reads (16 templates, the two new waits of tickets
  06 and 09 among them), the next-step sentences, the morning brief's title,
  three count lines and its words for whom a case waits on, and every push
  word. The platform's words are today's, unchanged: 87 renderings of every
  reminder variant, push, brief and the brief writer's facts compared equal
  to the code's before the move (one-off check against `HEAD`); the existing
  lane, push and feed tests assert them too. That includes the lowercase
  "po" in the PIC's "your turn" reminder, as the code wrote it; a tenant's
  copy may say "PO".
- **The tenant's**: `RuleKey.REMINDERS` (`sales_reminders`), a copy key like
  the hand-off copy: proposed and approved on /sales/rules, in words
  through `rule_words.COPY_KEYS`, resolved per tenant by the rule book
  (`TenantRuleBook.reminder_copy`), read once per tick by the lane
  (`FollowupRulesPort`). A version written before a template existed reads
  it as the platform's (`read_over`). Not price-bearing (counts and
  placeholders only). Migration `57bbf61ae6b8` admits the key in
  `ck_rule_versions_key` and `ck_rule_drafts_rule_key`.
- **Guards stay code**: which template a case gets, every value in it, who
  is told and when. A template may name only its own reminder's
  placeholders, `{name}` and nothing else (the hand-off copy's one check,
  `handoffs._plain_placeholders`); a push's words take none (the lane adds
  the number where the policy allows), so a lock screen still never shows a
  customer, a price or their text.
- **Web**: `rule-labels.ts` labels every field and placeholder; the key is
  under "Nâng cao" (`ADVANCED_RULES`).
- Tests: `test_followup_waits.py` (a tenant's words said, a template it
  lacks is the platform's, another tenant's never reached, a foreign or
  attribute placeholder refused, every follow-up has words).
- **Not moved, on purpose**: the brief writer's own fact labels ("đơn hàng",
  "báo giá", "bộ phận Sales"/"bạn": the model's input, not a sentence a
  person reads), `OPENING_PREFIX` (the feed parses it), and, as asked, the
  assistant's fixed sentences and `QuestionKind`.
