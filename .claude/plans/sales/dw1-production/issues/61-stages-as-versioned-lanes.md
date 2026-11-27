# 61 — DW1's stages as versioned lanes: pinned per case, rolled out per PIC

Status: in-progress — step 2's first slice built (2026-11-23): the write-Bravo stage pinned per case (stamp, dispatch, start-up refusal). Left: per-PIC rollouts and shadow (`sales.stage_rollouts`), the manifest's `stages/<stage>@<semver>`, the other four stages after UAT
Blocked by: none
Category: architecture (inside the modular monolith; no new services)

## Why

Another FPT team (ATLAS) runs many small workers so that a change ships beside
the running version instead of stopping it. Đạt, 11-20: learn the idea, do not
split into services; one host and six PICs do not need them.

Today DW1 is one context (`dw_sales`, about 110 application modules) in the API
and worker processes.

- Its stages exist as modules, and a case moves by its state machine.
- A deploy changes the code under every case at once.
- Only prompts, skills and artifacts are pinned per case (`release_manifest_ref`).

## Shape

- **Stages become worker lanes**, each with its own version and on/off switch:
  read documents, check (rules, mostly Bravo's), wait for people (PC, Design,
  customer, PIC; read from Bravo and mail), write Bravo (the shared Bravo gate,
  DW1 and DW2), communicate.
- **Pinning.** A case records the version of each stage it started with and
  finishes on it. New cases take the new version. The release manifest grows
  from prompts and skills to stage rule sets.
- **Rollout.** A new stage version goes to one PIC first. It also runs in shadow
  beside the old one and is compared before it is promoted.
- **Per person.** Each PIC sees "my DW": their queue, memory and per-case chats.
  Underneath it is the same logic, with cases routed by the customer's Sales
  PIC (`B20Customer.EmployeeCode_Salesman`).

## Acceptance

1. A case started on stage version N finishes on N after N+1 is deployed (test).
2. A version can be switched on for one PIC only.

## Step 1 (2026-11-21): where the 108 application modules go, and how a case pins its versions

No code moved. `dw_sales/application` holds 108 modules (plus `__init__`).
Each is placed in the stage whose work it does; a module that serves every
stage is "shared" and is not versioned per stage.

| Stage | What it does | Modules | n |
|---|---|---|---|
| 1. Read documents | turn a mail or file into typed values with their anchors | `inbox_lane`, `inbox_service`, `mail_drop`, `scanned_inbox`, `po_uploads`, `processing`, `order_intake`, `po_body_reading`, `rfq_reading`, `model_reading`, `change_reading`, `document_forms`, `layouts`, `column_mapping`, `template_reading`, `customer_notations`, `sender_customers`, `message_intent`, `mail_kinds`, `reply_intent`, `threads`, `thread_agent`, `thread_tools`, `thread_summaries`, `triage`, `skill_pick`, `source` | 27 |
| 2. Check | rules first (Bravo's own via `dw_bravo`, tenant rules, BR-*), the model only where rules cannot decide | `decisions`, `rules`, `rule_words`, `rule_drafts`, `convert_gaps`, `linked_quotes`, `order_quotes`, `quotation`, `catalog_imports`, `master_data_service`, `snapshot_catalog`, `salesorder_rules`, `salesorder_skills`, `salesorder_learning`, `salesorder_pairs`, `salesorder_fill` | 16 |
| 3. Wait for people | PC, Design, the customer, the PIC: asked, reminded, and their answer read (from Bravo or mail) | `pc_requests`, `pc_dates`, `design_requests`, `design_text_reading`, `ycbg_exports`, `confirmations`, `customer_reminders`, `screening_followups`, `followups`, `change_requests`, `update_loop`, `internal_changes`, `handoffs`, `handoff_kinds`, `routed_mail` | 15 |
| 4. Write Bravo | the shared Bravo gate (DW1 and DW2): what is written, under whose user, and read back | `salesorder_case_fill`, `bravo_sales_orders`, `bravo_exports` (+ `dw_bravo`, tickets 51/53/59) | 3 |
| 5. Communicate | words to a customer or a person, and the files sent | `outbound_mail`, `outgoing`, `reply_drafts`, `drafting`, `artifact_content`, `artifacts_service`, `order_artifacts`, `quote_artifacts`, `reminder_copy`, `brief_writing`, `finding_explanations` | 11 |
| Model-step governance (shared) | how any model step is gated, measured and taught (ADR 0015) | `autonomy`, `auto_apply`, `model_readiness`, `labelled_cases`, `examples`, `prompt_optimiser`, `prompt_versions`, `skills`, `skill_replay`, `model_calls`, `activity`, `activity_ports` | 12 |
| Shared shell | access, ports, API services, views, the person's day | `access`, `visibility`, `assignment`, `worker_service`, `support`, `ports`, `case_store`, `order_ports`, `quote_ports`, `overview_ports`, `services`, `orders_service`, `quotes_service`, `overview_service`, `pipeline`, `next_steps`, `today`, `assistant`, `assistant_copy`, `process_settings`, `views`, `telemetry`, `local_time`, `runs` | 24 |

Reading the map:

- Stage 4 is thin today because DW1 still stops at a file the PIC pastes;
  tickets 51/53 and `dw_bravo` fill it, and DW2 shares it, so it is the one
  stage built as a package outside `dw_sales` from the start.
- A few modules straddle two stages and are placed by their effect:
  `pc_dates` and `design_text_reading` read a mail (stage 1's skill) but only
  to close a wait (stage 3); `salesorder_fill` checks before it writes;
  `bravo_exports` reads Bravo for both stage 3 and stage 4.
- The shared rows (36 modules) are not versioned per case. A change there is
  a platform change and ships the old way (one deploy, all cases).

### Pinning design (to confirm before step 2)

1. **What a stage version is.** `stages/<stage>@<semver>` in the release
   manifest: the stage's code handler name plus the artifacts it uses (prompts,
   skills, tools, model profile, rule-set versions). Most new versions change
   artifacts, not code; a code change adds a second handler beside the first.
2. **Stamped on the case.** `order_cases`/`quote_cases` already carry
   `release_manifest_ref`. Step 2 adds `stage_versions jsonb NOT NULL`
   (`{"read": "1.4.0", "check": "2.0.0", ...}`), written once when the case is
   opened, never updated (a trigger refuses an UPDATE that changes it, the
   `updated_at` rule's spirit: a past decision does not move). Every lane reads
   the stamp, never the current config (CLAUDE.md "One owner per fact": a stamp
   beats a fresh lookup).
3. **Dispatch.** A stage's lane keeps a registry `(stage, version) -> handler`
   built at the composition root (`ConsumerRegistry` stays as it is; the lane
   dispatches inside). A case whose pinned version has no handler is refused
   loudly, not run on the newest. A handler may be removed only when no open
   case is pinned to it: a start-up check counts open cases per pinned version
   and refuses to boot otherwise.
4. **Rollout per PIC.** `sales.stage_rollouts` (tenant, stage, version,
   audience: all | listed PICs, state: shadow | active | retired). A new case
   takes, per stage, the newest `active` version whose audience holds the
   case's PIC (Bravo's `B20Customer.EmployeeCode_Salesman`, mapped to the DW
   user), else the tenant default. Who may change a rollout is a permission
   (`sales.rollout.manage`), checked where the row is written.
5. **Shadow.** A version in `shadow` runs beside the pinned one on the same
   input, writes nothing, and its output is stored as a labelled case against
   what the pinned version and the PIC did (ADR 0015's ledger). Promotion
   to `active` cites the run that passed the stage's bar (ticket 57's rule).
6. **Bravo is not pinned.** Bravo's rules are Bravo's: the check stage records
   the layout hash it ran (for ticket 62's trail) but always runs Bravo's
   current layout, because Bravo enforces its current rules on the write.

Tests step 2 owes: a case opened on N finishes on N after N+1 is registered
(acceptance 1); N+1 active for one PIC only opens that PIC's new cases on N+1
and everyone else's on N (acceptance 2); a pinned version with no handler is
refused; removing a handler with open cases pinned refuses to start.

## Comments

## Decided (2026-11-23, Đạt ("làm theo khuyến nghị"))

The pinning design is confirmed. Step 2 moves one stage first, **write
Bravo** (3 modules, the stage with the hardest consequences and the fewest
files), so the pin, the stamp and the dispatch are proven on it before the
other 105 modules move; those wait until UAT has run on the current code.

## Step 2, first slice (2026-11-23): write Bravo pinned per case

- **The stamp**: `CaseOrigin.stage_versions` (`dw_sales.application.stages`),
  written when a case opens from `STAGE_DEFAULTS` (`write_bravo` 1.0.0) and
  read back with the case; migration `7add0d23936a` adds
  `stage_versions jsonb NOT NULL` to `sales.order_cases` and
  `sales.quote_cases` (open cases backfilled 1.0.0, no column default: one
  owner) and a trigger that refuses any UPDATE changing it, from any role.
- **The dispatch**: `StageHandlers` per stage. For write Bravo a version is
  the gateway's command set (`BravoCommandsPort`, `write_bravo_versions`,
  1.0.0 = `dw_bravo.contract` today): a line write is prepared by the set of
  the case's version, the approval names `stage_version`, and the decision's
  stamp checks the hash with that same set. Not served, or not stamped:
  refused, nothing opened.
- **Removing a version**: the API (lifespan) and the worker refuse to start
  while `sales.open_cases_by_stage()` (SECURITY DEFINER, counts only) shows
  an open case on a version with no handler.
- **Tests**: unit (the stamp, a case keeping 1.0.0 while 1.1.0 is served,
  refusals, start-up) and PostgreSQL (read back as stored, no role moves the
  stamp, counts as `dw_app`, start-up refused). Mutations red: the dispatch,
  the stamp, the start-up refusal, the read-back, the trigger (dropped from
  the migration).
- **Left**: `sales.stage_rollouts` (a version active for listed PICs, shadow
  runs compared before promotion, `sales.rollout.manage`), which acceptance
  2 needs; `stages/<stage>@<semver>` in the release manifest; the other
  four stages once UAT has run on the current code.

