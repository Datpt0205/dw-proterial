---
status: Accepted
date: 2026-11-15
accepted: 2026-11-16 (Đạt: "tôi duyệt", measured on Giang's home-lab Strata first)
supersedes: dw_sales ADR 0012 decision 3, and "code chooses the step" wherever ADRs 0005 and 0010 imply it
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

- Accepted 2026-11-16 with one condition: measure on Strata (Giang's home
  lab, reached with its API key from `.env`, never committed) before the
  agent replaces a step.
- The skill store's shape (one row per skill version per tenant, the
  replay's example set) and who may write a skill (PIC and head, as ADR 0012
  says, or the admin only).

## Applied to ticket 40 (2026-11-16, by the agent, Đạt away)

Decisions 1, 2, 4 and 5 for the first skill, reading a thread message's
intents. Decision 3 holds as written; what the decisions did not settle was
settled so, and is recorded here because no rule above moved.

- **Files.** `configs/skills/dw1/AGENT.md` (DW1's conduct) and
  `configs/skills/dw1/thread-intents/SKILL.md` (deepagents' format: name,
  description, `metadata.version`, then the instructions; the intents'
  definitions are `reply_intent@2.0.0`'s word for word, a test holds it).
  The release manifest pins each by name, version and checksum
  (`skills`). The turn's own prompt, `sales.dw1_agent@1.0.0`, carries only
  the work and its inputs, contained by the registry. `AGENT.md` is the
  platform's only for now: a tenant edits skills, not the conduct.
- **The store is the rules' own.** A tenant's version of a skill is a row of
  `platform.rule_versions` under `sales_skill_<name>` (migration
  `80584b911796` admits the key): one row per tenant, skill and version,
  with its words, status, proposer and decider, under the table's RLS
  (tenant, ENABLEd and FORCEd), grants and checks, which the platform's
  tests already assert. Scope: the tenant's, as a rule's and a prompt's;
  a skill reads every workspace's mail alike. A second table of the same
  shape would have been a second engine to keep honest.
- **Proposed and decided like a learned rule.** Whoever holds
  `sales.rules.propose` proposes (`POST /sales/skills/{name}/versions`);
  the head (`sales.rules.approve`) decides on a `sales.skills` approval,
  never the proposer, and never applied directly, the head's own proposal
  included (the platform's `RuleVersionEngine`, `RuleDecisionGuard`,
  `RuleVersionSettlement`; the worker carries out `sales.skills.decided`).
  Only a skill the platform ships may be versioned: a tenant's wholly new
  skill is not served yet.
- **Served from the run, loaded by a tool.** Code resolves the run's
  tenant's skills (`SkillBook.skill_set`, through `TenantOverlay`: the
  tenant's approved version, else the platform's, never sideways) and
  serves them around the turn (`dw_agent_runtime.model.skills.serving`).
  deepagents' `SkillsMiddleware` builds the catalogue from a backend that
  answers from that set only; its own words name `read_file`, a builtin the
  platform never installs, so the catalogue's words are the platform's and
  a skill is loaded with `sales.read_skill@1.0.0` through `ToolExecutor`,
  answered from the served set, refused for a run of another tenant or
  workspace. `sales-dw1@1.1.0` pins it; it is offered only to a turn served
  skills, so the thread agent is offered exactly its six. A reading stamps
  the skill versions it loaded (`ReplyReading.skills`), shown on the reply.
- **A step of its own.** `ModelStep.SKILL_INTENTS`, switch
  `model_assist.skill_intents` (off in every platform version), bar 0.85 on
  the bar set's intent accuracy, held with no false `accepts` and no tool
  answering for another customer, as the thread agent's. Asked first; with
  no reading of its own the thread agent reads where that is on, then the
  one call, then a person; off, nothing of it runs (a test compares the
  reading with one made with no agent wired). Its ceiling: five calls,
  24,000 input tokens, 120 seconds (one call more than the thread agent's,
  to load the skill). The bar measures the platform's skill; a tenant's
  version is read by its head before it applies.
- **Not built yet:** the replay of a proposed version on the tenant's
  example mails, with and without it (it needs the model, so the worker),
  and the rules-area page that lists skills, shows a version and its
  replay, and sends it for approval. Ticket 40's follow-up.
- **Measured on Strata, 2026-11-16 (Qwen3.8-Flash-Next Q2_0, Giang's home
  lab, not attested)**: 0.183 on the bar's set (the one call 0.796, the
  thread agent 0.85), 0.175 on all 80. The model loaded the skill in every
  turn and then looked something up in every turn, 276 look-ups in 80 turns
  (the thread agent: 57 in 72), repeating `sales.case_snapshot` and
  `sales.thread_messages` until 63 turns reached the five-call ceiling and
  fell back. No false `accepts`, no tool answered for another customer, and
  every withheld message was looked up with the right tool. One wording
  change aimed at that (look up at most once, never twice; "never call the
  same tool twice" in `AGENT.md`) made it worse (0.083, 74 turns at the
  ceiling) and was not kept. On this model the step stays off and the
  one-call reading reads, as decision 4 says; the open question is below.

## Amended 2026-11-16 by dw_sales ADR 0015 decision 5

The skill a mail needs is chosen by one constrained, scored call (a
JSON-schema enum of the tenant's skills, scored by the token
probabilities), not by the agent's free choice: measured on Strata in
ticket 40, the free choice looped (0.183). Skills stay tenant-edited text;
tools stay for the facts a reading lacks.

## Applied 2026-11-16: the scored pick, the replay (ticket 40's follow-up, by the agent)

- **The pick** is one structured call (`sales.skill_pick@1.0.0`, an enum of
  the served skills plus `none`, scored by token probabilities); code reads
  an unserved name, `none`, no confidence or less than the tenant's
  `model_assist.skill_pick_confidence` (default 0.9) as no pick, and the
  message is read as with the step off. The picked skill's words are in the
  one reading turn (`sales.dw1_agent@1.1.0`, `AGENT.md` 1.1.0); no catalogue,
  no loading tool. Measured on Strata: 0.800 on the bar's set (one call
  0.796, bar 0.85), one false accept, 3 turns at the ceiling instead of 63.
  The step stays off.
- **The replay** (decision 2) runs in the worker on the platform's example
  mails, with and without the proposal, and is stored beside it
  (`sales.skill_replays`); the head may approve a version only once its
  replay is stored, and a failed security case is said plainly on the
  skills page. The tenant's own labelled reply readings would come first,
  but none are labelled yet (ticket 43).

## Applied 2026-11-16: the mail kinds (ticket 42 family 1, by the agent)

Decision 3 read for the classification of a mail no reader accepted: the
KINDS a company tells apart and their words are a skill; what a kind DOES
stays code.

- **The skill** `configs/skills/dw1/mail-kinds/SKILL.md` names each kind in a
  block code reads (`- kind:`, `route:`, `label:`, `means:`;
  `dw_sales.domain.mail_kinds`). The platform's version is
  `sales.message_intent@1.1.0`'s kinds and rules word for word (a test
  holds it). Each kind maps to ONE route of a closed set, the one call's
  kinds (`INTENT_ROUTES`' rows); a kind the platform does not ship carries
  the label Sales sees it by. Code reads and checks the blocks when a
  version is proposed (an unknown route, a kind named twice, an unknown line
  refuse the proposal, `skill_words_unreadable`) and again whenever the
  skill is served (a version that no longer reads is not used).
- **A fixed step, not a pick.** The classification order is code's (malware,
  document, upload, headers, then the model, then a person), so the mail
  kinds are read at the model's place in it and never offered to a thread
  message's skill pick (`skills.STEP_SKILLS`). A pick among one candidate
  would be a call that decides nothing.
- **One call**, `sales.mail_kinds@1.0.0`, the skill's words contained like
  the mail's; its schema is built per call from the kinds the served version
  names plus `none`, and code reads a name the version does not hold as no
  kind. The reading stamps the kind, the route it took, its label and the
  skill version (`IntentReading.skill`, `routed_as`, `kind_label`); the API
  serves the kind as a string and the web shows the label, falling back to
  the platform's word.
- **Its own step**, `ModelStep.SKILL_MAIL_KINDS` (`model_assist.skill_mail_kinds`,
  off everywhere), bar 0.90 on the one call's metric, T0 like the one call.
  Off, below its bar, the model down or `none`: the message is classified
  exactly as before (the one call where that is on, else a person).
- **The replay** of a proposed version reads the message intent's 92 golden
  mails and its injections with the proposal and with the version in force,
  graded by route, an injection failing when read into the order or
  quotation flow (`MailKindReplay`).
- **Measured on Strata** (2026-11-16, qwen3.8-flash-next-q2_0, not
  attested): 92/92 golden mails routed right (the one call, same model and
  day: 0.978), p50 1.41 s, p95 1.52 s per mail (one call 1.32 s / 1.43 s);
  a company's added kind (`invoice_request`, routed `other`) read for 4 of
  its 4 fictional mails with no code change; no injection opened a case.
  Both paths are kept: the skill step is used by a company only once its
  own measurement is attested, and the one call is the reading every
  company with `message_intent` on has today.

## Applied 2026-11-16: the triage card and a kind taught from it (tickets 33 and 34, by the agent)

ADR 0012 decision 2's third use and decision 3, rebuilt here: the card reads
with the tenant's mail kinds, and teaching DW1 a kind is a version of that
skill. No rule above moved.

- **The card** (`domain/triage.py`, `application/triage.py`): a message intake
  still routes `other` carries one where the tenant turns it on
  (`model_assist.triage_card`, `ModelStep.TRIAGE_CARD`, off everywhere, T0,
  bar 0.85 on `golden.card_accuracy`, held only while no card names another
  customer's case). One structured call, `sales.triage_card@1.0.0`, with the
  mail kinds' inputs and schema (the served version's kinds plus `none`);
  code reads a name the version does not hold as no kind, maps the kind onto
  its route by the skill, and suggests a step only where a person can take
  that route on a routed message (`TRIAGE_STEPS`: the routing-reason rows of
  `INTENT_ROUTES` but `other`); `po`, `quote_request`, `design_reply` and
  `other` suggest none, since only a document or a verified mailbox opens
  those flows. The case is the one live order case the numbers code locates
  lead to, resolved by the one resolution intake has (`IntentReader.resolve`,
  the sender's customer only); several or none name none. No card where the
  model gives no usable answer, the skill's words no longer read, or the
  tenant's mail kinds already read the mail (the card would ask the same
  question again). The routing is never changed by the card.
- **Decided by a person** (`RoutedMailService.decide_card`,
  `POST /sales/inbox/{id}/triage`): whoever may mark the message handled
  takes the step, takes another of the set, or dismisses the card. The
  request names a step and "attach", never a case: a reply is attached only
  to the card's own case, checked again against the message's customer where
  it moves. A step routes the message again with that reason (owner and
  customer kept; a sample request with the customer's export-control
  status). Each decision is stamped on the card, audited
  (`sales.message.triage_decided`) and written as a labelled case of the
  step (taken: confirmed; another step: corrected; dismissed: rejected).
- **Teaching a kind** (ticket 34): from a card, a holder of
  `sales.rules.propose` proposes a version of `mail-kinds`
  (`SkillProposal.from_message`); the server finds that mail, with its card,
  in the proposer's own workspace and records it on the version
  (`SkillDocument.trigger`: workspace and message id; only the mail kinds
  are taught from a card). The replay reads it with the version and with the
  one in force beside the golden mails (`SkillReplay.trigger`), in that
  workspace's lane only, and the skills page says both readings. The head
  decides as for every skill version, never the proposer.
- **Storage**: migration `2c91d318f833` (from `456986ea413a`) adds
  `sales.messages.triage` and `sales.skill_replays.trigger` (JSON objects,
  bounded, CHECKed) and admits `triage_card` in the four step CHECKs, read
  from the catalog as `711e8b760139` does.
- **Measured on Strata** (2026-11-16, qwen3.8-flash-next-q2_0, not
  attested): 97/98 golden cards right on step and case (the message intent's
  92 residue mails 0.989, six card mails in a world with three customers'
  cases 1.0), p50 1.65 s, p95 2.12 s; no injection moved a mail or named
  another customer's case. The step stays off until a company's own
  measurement is attested.

## Applied 2026-11-16: the document forms (ticket 42 family 3, by the agent)

Decision 3 read for a customer's own request form: which label or column
of a customer's form means which field is words, a skill; what a form opens
and every check of every value stay code.

- **The skill** `configs/skills/dw1/document-forms/SKILL.md` names each form
  in a block written as the mail kinds' are (`- kind:`, `customer:`,
  `route:`, `means:`; `dw_sales.domain.document_forms`, on the one block
  reader `domain.skill_blocks`). `customer` is a customer's code or `any`;
  `route` is one of a closed set holding only `quote_request`, the flow whose
  request code verifies value by value (a PO is read by its approved layout,
  never by words). The platform's version names two forms for any customer:
  the standard English form, in words naming every label the fixed reader
  reads (a test holds the two together), and a customer's own request sheet
  in general words. Code reads and checks the blocks when a version is
  proposed (an unknown route, a customer that is no code, a form named
  twice refuse it, `skill_words_unreadable`) and whenever it is served.
- **One customer's forms only.** A reading is shown the guidance and the
  forms of the sender domain's customer and of any customer, never another
  customer's words, and its answer's schema is built from those names plus
  `none`; code reads a name it did not offer as no form, and two forms named
  for one file as nothing read.
- **The same request, the same checks.** The model gives ticket 29's spans
  (`ModelRfqReading`) and code verifies them as ticket 29 does
  (`verify_rfq`: each span once, whole, in its line's cell; parsed by code;
  notation by the document, else the customer's record), and one builder
  makes the request (`RfqModelReader.request_of`): every value flagged
  `model_read` for Sales. The reading stamps the prompt
  (`sales.document_forms@1.0.0`), the skill version and the form
  (`RequestReading.skill`, `form`), and counts under its own step.
- **Its own step**, `ModelStep.SKILL_DOCUMENT_FORMS`
  (`model_assist.skill_document_forms`, off everywhere), T0 like ticket 29's,
  bar 0.85 on `all.right_field` (ticket 29's number on its own metric).
  Asked in the quotation flow after the fixed reader and before ticket 29's
  reading; at intake where no reader recognised a file, the sender's domain
  names a customer and no person uploaded it: a file it reads into a request
  makes the mail a quotation request, beside the `RFQ No.` marker, which
  stays. Off, below its bar, the model down, `none`, or nothing verified:
  read exactly as before.
- **The replay** reads a proposal and the version in force on ticket 29's
  request spreadsheets and the forms fixture's files (`DocumentFormReplay`),
  a file right when every value it states is read as stated; an order and an
  invoice are security cases that fail when read into a request at all.
  Like the mail kinds' examples, these are the platform's fictional
  customers: a company's own example files are the next source.
- **Measured on Strata** (2026-11-16, qwen3.8-flash-next-q2_0, not
  attested): 0.893 of 196 stated values right (ticket 29's 18 files by the
  platform's skill 0.871; three new customers' forms, Vietnamese, Japanese
  and English, by a company's version 33/33, by the platform's skill alone
  0.939), 0.005 wrong, the rest deferred; p50 7.15 s, p95 17.97 s per call;
  the order and the invoice read as no request; an instruction in a cell
  changed no value. Both paths are kept: the fixed reader reads first, ticket
  29's reading after a form reads nothing, and a company uses the step only
  once its own measurement is attested.
- **Not done**: a quantity whose unit is only in the column's header
  (`Số lượng (m)`) is still deferred, because `verify_rfq` takes a unit only
  from the item's own line; reading it from the header cell of the same
  column would be a change to ticket 29's checks, left for a decision.

## Applied 2026-11-16: the hand-off and reply kinds (ticket 42 family 5, by the agent)

Decision 3 read for the hand-off to PC or QA (ticket 33) and the mail to a
customer the model words (ticket 32): which KINDS a company writes, Sales'
label for each and how each is copied or written are words, two skills; what
a kind does stays code, from closed sets.

- **The skills** `configs/skills/dw1/handoffs/SKILL.md` and
  `configs/skills/dw1/reply-drafts/SKILL.md`, written in the mail kinds'
  blocks (`domain.skill_blocks`). A hand-off kind (`domain.handoff_kinds`) is
  named after the mail kind it is for and names `asks`, one of the three
  typed field sets ticket 33 built (`order_lines`, `lot_and_problem`,
  `sample_items`), and `to`, one of the teams (`pc`, `qa`: a team, never an
  address; Sales picks the people). A reply kind (`domain.reply_kinds`) names
  `drafts`, one of the platform's drafts, which gives it everything that is
  not words: when it is offered (`ORDER_GATES`), its facts (`reply_facts`,
  never an amount), its check (`check_reply`) and its recipients (the
  customer's contacts). Neither skill has a line for a recipient, a send, a
  price, an amount or a tool: any other key refuses the version when it is
  proposed (`skill_words_unreadable`) and makes it unused when served. A
  hand-off kind named after a platform route that takes no hand-off (`po`,
  `other` ...) is refused. The platform's versions are today's three
  hand-offs, to the copy's teams, and today's four drafts, each as itself
  (tests hold both).
- **Fixed steps, not picks**: both are `STEP_SKILLS`. The hand-off kind is the
  kind the message's reading stamped, honoured only where that reading's
  route is the reason the message was routed for (a reading opens no door its
  route does not), else the platform kind of the reason; never the model's
  choice. The reply kind is the one a person asked for, resolved by the
  server against the version it serves.
- **One call each**, `sales.handoff_kinds@1.0.0` and
  `sales.reply_kinds@1.0.0`: ticket 33's and ticket 32's prompts with the
  skill's words contained beside the mail and the facts. The hand-off stamps
  the skill version, its kind, label and team (`Handoff.skill`,
  `skill_kind`, `kind_label`, `to`; `kind` stays the fields); its team is the
  skill's when written. The draft says the kind asked, the draft it was
  worded as, the label and the version (`ReplyDraftView.drafted_as`,
  `kind_label`, `skill`), and the skill's other kinds of the same draft,
  which the page offers by their labels (`others`).
- **Their own steps**, `ModelStep.SKILL_HANDOFFS` (T1 hand-off, bar 0.85 on
  `all.right`) and `ModelStep.SKILL_REPLY_DRAFTS` (T0, bar 0.85 on
  `all.complete`), ticket 33's and 32's bars on their metrics, off
  everywhere (migration `7c00901ada90` admits the keys and steps). Off, below
  its bar, the model down or a version that no longer reads: the hand-off is
  pre-filled by ticket 33's one call exactly as before, the draft worded by
  ticket 32's, and a company's own kind gets no hand-off and is not offered.
- **The replays** read a proposal and the version in force on the
  platform's examples: the hand-offs on ticket 33's golden mails and the new
  kind's mails, located by code with no order resolved
  (`HandoffKindReplay`); the reply drafts on ticket 32's twelve drafts' facts
  (`ReplyKindReplay`, right when every kind of that draft is kept by
  `check_reply` and states the PO).
- **Measured on Strata** (2026-11-16, qwen3.8-flash-next-q2_0, not
  attested). Hand-offs: 0.863 of the 73 fields the 33 golden mails state
  right, none wrong (bar 0.85; ticket 33's one call replays 0.849), p50
  4.31 s, p95 27.96 s on a busy server; a first run the same day scored
  0.849 with two calls failing at the transport. A company's certificate
  request to QA, added by a version only, pre-filled for both its mails
  with the PO, the lot and the sentence, routed to QA; no injected
  instruction or address reached a hand-off. Reply drafts: 10 of 12 kept and
  complete (0.833, below the 0.85 bar; both drops Japanese figure
  refusals, as ticket 32's one call recorded); a company's short
  confirmation worded as the confirmation to the customer's contacts with
  its label; a version whose words asked for another address, a price and
  another customer's PO: every scripted draft obeying them dropped, the
  model's kept draft named none. **Both code paths are kept**: the reply
  kinds are below their bar, and the hand-off kinds are used by a company
  only once its own measurement is attested; the one calls stay what every
  company with ticket 32 or 33 on reads with.
- **Not done**: a company's new hand-off kind is written with the words of
  the platform kind whose fields it asks for (`sales_handoffs` copy); its
  own subject and body would be the copy's to hold, keyed by kind, a change
  to that copy's schema left for a decision. A Design team as a recipient is
  not in the closed set: there is no Design recipient in master data for a
  hand-off, and adding one is code by design.
