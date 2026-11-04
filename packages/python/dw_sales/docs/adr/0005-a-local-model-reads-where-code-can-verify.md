---
status: Accepted
date: 2026-10-13
accepted: 2026-10-14 (Đạt, with the addenda below)
supersedes: spec decision 13's "no model turn reads document content" and the spec's "no model call" non-goal
---

# A local model reads where code can verify what it read

Proposed by the agent while Đạt was away (he pre-authorised the work on
2026-10-12/13: "turn the tasks a model can take off people over to the local
Qwen3.5-9B and run them"). Accepted by Đạt on 2026-10-14, with the
addenda below.

## Context

Until now DW1 called no model. Spec decision 13 said no model turn reads
document content in this slice, the spec listed "any model call on real
Proterial documents" as out of scope, and `test_dw1_runtime.py` asserted
that DW1's graph takes no model. That was the right default while nothing
needed one: every value was read by deterministic code, and anything unusual
went to a person.

It now costs people work that recurs per line. An item description outside
DW1's own vocabulary (`domain/descriptions.py`) leaves the line
`code_unmapped`, and Sales looks the PRV code up by hand, for every line of
every PO whose customer code is not in the convert list
(`.claude/plans/sales/dw1-portal-demo/ai-automation.md` lists six such
steps; ticket 28 is the first). A model reads "2芯 AWG24 黒" or "4C AWG22 TC
BRD GRY" without a vocabulary table; code cannot, and a keyword table to
make it would be the synonym list Đạt's rule §6 forbids.

The risk is the usual one with a model in a document flow: it is confident
and sometimes wrong, the document is untrusted input that can carry
instructions, and a value it produces can look like a value a person
checked.

## Decision

A DW1 step may call a model only under all of the following, each held by
code and a test:

1. **Typed output, nothing else.** The model turns language into a reading
   validated into a frozen Pydantic schema that refuses undeclared keys. Its
   values come only from closed `Literal` sets built by code; everything else
   it gives is span text copied from the document. It never gives a number, a
   date, an identifier (customer, PRV code, quote, case, recipient), a price,
   a threshold, a route or a choice among candidates.
2. **Code verifies before anything is mapped.** Code locates every span in
   the NFKC-normalised document, exactly once; re-parses every number from its
   span with a deterministic parser that requires the unit (the model's value
   for a number does not exist to disagree with); computes coverage itself
   (every non-space, non-punctuation character inside a span, or the reading
   is refused); and refuses a label span holding a digit. Then the existing
   deterministic rules run unchanged (`descriptions.candidates`).
3. **Flagged, and a person confirms.** A value the model chose is stamped as
   the model's (`SpanRead.read_by = "model"`) on the case's evidence and shown
   beside the text it came from. A line a model read is at best a `candidate`
   Sales confirms, never `exact` (`OrderLine` refuses it). No approval, no
   finding disposition and no checker role is taken over.
4. **Degrade to a person.** Model down, timed out, an answer outside the
   schema, a line it was not sent, or any check refusing: the line is what it
   is today (`code_unmapped`), stamped `unavailable` or `not_understood` with
   the reason, and the screen says DW1 could not read it. A budget or quota
   refusal is not that: it stops the run and is reported as a stop.
5. **No tools in a document turn** (ADR 0007). DW1's worker declares no
   toolset; the port a step calls (`InterpretationPort`) offers none.
6. **One door, attributed to the run.** The step's application declares the
   port; the composition root satisfies it with the platform's model gateway.
   The graph holds no model: it hands the run's `RunContext` down, so the call
   renders the tenant's prompt, spends against the run's budget and is
   recorded against its tenant, worker and release.
7. **Versioned and contained.** Each step's prompt is
   `configs/prompts/sales/<id>@<semver>.yaml`, pinned in the release manifest;
   every interpolated value is contained by `PromptRegistry` (ADR 0010), and
   the prompt carries no master data (no item codes, spec numbers or convert
   list: another tenant's or this one's).
8. **On the deployment's own model, switch per tenant, off by default.** The
   profile is DW1's worker's `default_model_profile`, `onprem`: an
   OpenAI-compatible server the deployment runs itself (provider `onprem`, its
   own endpoint, localhost admitted only outside a deployed profile), thinking
   off on every route, no external fallback. Each step has a switch in the
   tenant's rules (`sales_order_rules.model_assist.<step>`); the platform ships
   it off, a tenant turns it on in its own version, and the case stamps the
   version. A process without such a server composes no model and calls none.
9. **Measured before it is trusted.** Each step ships evals with injection,
   missing-evidence and cross-tenant cases, a smoke that replays the recorded
   answers of the real model in CI, and a live lane outside CI
   (`run_evals.py --live onprem`) reporting accuracy, the share routed to a
   person and latency.

What stays human is listed in `ai-automation.md` ("What stays human"): any
price, every approval and checker role, finding dispositions, hidden
content, identifiers, numbers and dates as values, revision status,
thresholds, tenancy and roles, outbound effects and customer-facing prose,
delivery dates, export control.

## Consequences

- Spec decision 13 keeps its parsing rules and loses its last sentence: "No
  model turn reads document content" becomes "a model reads only under ADR
  0005". The non-goal becomes: no model on real Proterial documents until
  Proterial agrees and a step's live eval meets its bar; on the fictional
  mock data, under this ADR.
- ADR 0004's "No model turn, no tool" keeps "no tool"; a model turn is now
  allowed under this ADR.
- `test_dw1_runtime.py` asserts the real invariant instead of "no model": no
  toolset, no model in the graph, the run handed down, typed output, model
  values flagged.
- A categorical label is the one judgement left to a model, and no check can
  tell `BLK` read as red from `BLK` read as black. That is accepted because it
  can only narrow to a candidate a person confirms beside the highlighted
  text; auto-accepting a single fit would need every attribute from a
  deterministic parse, and is a future rules key, not this ADR.
- Strict checks cost recall: a reading with one word the model could not
  place is refused, so the model's share of the work is what the live eval
  measures, not what it could be with looser checks. Loosening a check is a
  new version of this decision.
- The switch lives in rules a tenant versions. Until ticket 19 stores and
  approves tenant versions, the demo tenant's own version ships in the mock
  sample set, as its master data does, and carries its own version number so
  the case stamp says which applied.

## Applied to tickets 29 and 31 (2026-10-13, by the agent, Đạt away)

Two more steps follow this decision unchanged; what they add is recorded here
rather than in a new ADR, because no rule above moved.

- **Field confusion is flagged, not refused.** A request for quotation (ticket 29) is span text code locates (whole tokens only, inside the item's line)
  and parses, but which field the words fill is the model's reading: a reel
  length or the send date can pass every check. So every value a model read
  is `model_read` and raises `value_uncertain`, which Sales confirms value by
  value before the YCBG; nothing a model read is used unconfirmed.
  **Addendum, 2026-11-04 (Đạt: less for a person to do):** a line whose
  values read right is confirmed with one press, "Xác nhận cả dòng như đã
  đọc" (`QuoteCase.confirm_as_read`), instead of retyping each. It holds
  what each value's own press holds: this person opened every place the
  line's values were read, at this version (`require_value_served` per
  value), and each value is still recorded on its own with what was read
  and what was kept. One finding per press, never the case's: the person
  still looks at each line beside its source. A value read wrong is still
  typed by itself.
- **A kind is not a route.** A message's intent (ticket 31) is a closed-set
  kind; code maps it to the route through one table, a readable document
  decides first, and a number the model names is used only when code finds it
  in the newest part and it resolves to one record of the sender's own
  customer. The Design-mailbox gate and the order flow's own refusals stand
  behind the kind.
- **The newest part only.** What a model is shown of a mail is its subject and
  newest part, history cut by the message's own structure, so quoted or
  forwarded text never reaches it and a value found only there is not found.
- **Bounded input.** Each call is cut or split under the route's declared
  `max_input_tokens`; a request needing more calls than the step allows goes
  to a person unread rather than read in part.
- **One switch block.** All three steps are switched in
  `sales_order_rules.model_assist`, the one tenant-versioned place that says
  which model steps a tenant has on (ticket 29 had named `sales_quote_rules`,
  which has no tenant layer).

## Applied to tickets 32, 33 and 30 (2026-10-13, by the agent, Đạt away)

Three more steps follow the decision unchanged; what they add is recorded here.

- **The case is code's, from the thread.** A reply is linked to its case by
  its `In-Reply-To`/`References` headers naming a message already on one case
  of the sender's own customer (ticket 32), with no model; a reply naming
  another customer's message, two cases or none is classified as any other
  message. The model reads only what the reply says, as a closed-set kind
  standing on sentences code locates once; the step comes from one table by
  the case's kind and status, is shown as a suggestion, and is the case's
  ordinary step a person takes. Keeping a PO as it is resumes the review and
  disposes no finding.
- **Spans in, template out.** A hand-off to PC or QA (ticket 33) carries no
  sentence a model wrote: code writes it from a versioned copy template, with
  the values it located, parsed and resolved (a PO only among the sender's own
  orders and cases) and the customer's sentences in quotation marks, dropping
  any that names an address, a web address or a phone number. The kind is the
  routing reason. Nothing is sent and nothing changes in the ERP.
- **Labels, never values.** A PO layout's pre-fill (ticket 30) names labels
  only, from the form's header pairs and table titles code splits out of the
  form; every label must be one cell of the form, the reader reads the form
  end to end with it, and each column must be plausible (a swapped quantity
  and unit price passes the totals and fails here). A person maps or corrects
  the form, a second person approves it, and later POs are read with no
  model. The first POs of a new layout keep every value `value_uncertain`
  (`layout_onboarding.uncertain_first_pos`). The approval is a checker's
  decision, so it is a platform approval as ADR 0004 says: the proposal opens
  a run-less `sales.layout` approval in its own transaction, stamped with
  `sales.layout.approve` and naming the proposer as its maker (`sales.` is
  strict); the layout's own guard checks it before it is recorded, and the
  worker carries out the `sales.layout.decided` event (CLAUDE.md, "An
  approval with no run announces its decision"). The domain and a CHECK
  refuse the maker again. No Sales route decides it.

## Addendum 2026-10-23: the bar is enforced, not reported (approved by Đạt)

Decision 9 said a step is measured before it is trusted, and the config said a
tenant turns a step on "once that step's live eval meets its bar". Nothing
enforced that (failure-modes #1): the bars were constants in the eval modules
and the live results gitignored files on whoever ran the lane, so the running
process could read neither, and a tenant's version could turn on a step no
live eval had passed. Đạt approved the design below on 2026-10-23.

- **One owner for the bars.** `dw_sales.application.model_readiness.BARS`
  maps each `ModelStep` (the six `model_assist` switches: a test holds the two
  together) to its bar, the path of its metric in its golden grader's details,
  the prompt the step pins, and the dataset and grader that measure it. The
  eval modules read their bar from it (`bar_verdict`); `PROPOSED_BAR` is gone.
- **A store of live measurements.** `sales.model_step_measurements`
  (`2d97d03c937a`): tenant, step, model (the profile route's model), prompt
  `id@version`, metric, value, the bar at the time, passed, dataset
  `id@version`, measured_at, recorded_by. Narrowed by tenant only, like the
  rules it backs; RLS ENABLEd and FORCEd; append-only for `dw_app` (SELECT,
  INSERT; UPDATE and DELETE revoked); a CHECK that a pass meets its bar; not
  partitioned (a row per attested step, not per message). Written only by
  `run_evals.py --live <profile> --attest --tenant <uuid> --workspace <uuid>`:
  the lane `sales_model_attest` (ADR 0011: `recorded_by` and the audit actor
  read `system:sales_model_attest`), as `dw_app` under the tenant's RLS, the
  audit event in the same transaction; a role that bypasses RLS is refused,
  and a run that read nothing records nothing. A row passes only where the
  golden verdict passed AND every case of the run passed. The workspace is
  asked for because every tenant row and every audit event names one.
- **Ready** means: the latest measurement for the step, on the model the
  tenant's profile routes it to now and the prompt version it pins now, passed
  at today's bar on today's metric. A newer model, a new prompt version, a
  raised bar or a later failing run each take readiness away until measured
  again. Anything unreadable is not ready.
- **Enforced where the effect happens.** Every place that would call a model
  (`OrderIntake`: message intent, reply intent, hand-off, layout pre-fill,
  description reading; the quotation flow's request reading) asks
  `ModelStepGatePort.allows`: on AND ready, else the step does exactly what it
  does when it is off, and the log says which step and why. A version of the
  order rules that **turns a step on** (on in it, off in the version in force)
  is refused when it is proposed and when it is decided (409,
  `model_bar_unmet`, naming the step, its bar, the model and prompt, and the
  latest measurement or "chưa đo"); a settlement that finds a step no longer
  ready records the approved version as not applied, with why, as it does for
  a number the platform shipped since, so the key is never held. Turning a
  step off is never refused, and neither is keeping one on (that turns nothing
  on; the gate still keeps it with a person until it is measured).
- **The demo tenant.** `make demo-reset` installs `sales_order_rules@1.5.4`:
  the sample set's 1.5.2 with all six steps off, every other rule the same
  (held so by `test_order_rules.py`). The mock data path needs no model (none
  is composed without `DW_ONPREM_MODEL_BASE_URL`), and a measurement is what
  a live run says, so the demo seed records none and turns nothing on; the
  tenant's own rules (the NOC/ESF hold among them) stay in force. A developer
  with a local model attests the steps and proposes a version that turns them
  on, through the gate. 1.5.2 (all six on) is kept for what runs the steps:
  the API's integration suite, which no live run reaches, records stand-ins
  through the lane's own write path (`seed_test_measurements`) and seeds it;
  unit tests and evals seed an in-memory store that holds the SQL store's
  contract. Nothing goes around the gate.
- **Shown.** `GET /sales/rules/process` serves, per step, its model steps
  (switch, bar, metric, model, prompt, latest measurement, in effect, and the
  live share of the last 7 days from `sales.step_outcomes`), absent for a
  caller who may not read the order rules; the process page's lock on
  `model_assist` now says the bar is enforced.

Known limits: a tenant's own wording of a prompt under the same version is
not told apart (the measurement names `id@version`); the RFQ step's
measurement names its own prompt, not the description prompt it also calls;
`sales.bravo_template_mapping` (a one-call draft, not a `model_assist`
switch) is outside this gate.
