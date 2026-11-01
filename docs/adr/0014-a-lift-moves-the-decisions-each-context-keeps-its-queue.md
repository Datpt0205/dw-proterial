---
status: Accepted
date: 2026-11-01
accepted: 2026-11-01 (agent, unattended run; Đạt's standing instruction: "Mọi thay đổi thiết kế so với ADR 0013 thì ghi ADR mới trước khi làm". Đạt to confirm on review)
refines: 0013-what-a-second-context-shares-moves-to-the-platform.md (decision 3)
---

# A lift moves the decisions and their tables; each context keeps its queue

## Context

ADR 0013 decision 3 moves three Sales engines to the platform the day
Purchasing needs them — rule versions, master-data import, the mail drop —
each "a platform engine with a registry a context fills", its tables leaving
`sales` in a migration that moves rows.

Reading the code on 2026-11-01 for the first of them showed each "engine" is
two different things:

- **The decision**: what a valid rule version is and who decides it
  (`rules.py`: one waiting per key, never a shipped number, maker ≠ checker,
  the settlement); what a change in words may touch (`rule_words`); when a
  template's header row and a model's column match are accepted
  (`template_reading`, `column_mapping`); when a model step has earned its
  switch (`model_readiness`). These answer one question each, the same for
  every context, and two copies would drift (failure-modes #2).
- **The queue that carries it**: a table of requests, a worker consumer, a
  sweep lane, the prompts it asks, the audit actor it writes as
  (`system:sales_rule_drafts`), the reader operations it opens files with,
  Sales' worker identity on every model call. Every one of those names the
  context: a platform queue serving both would audit Sales' drafts as a lane
  that is not Sales', and would hold Purchasing's requests in a table whose
  retention, offboarding and RLS are argued for Sales.

## Decision

1. **The decision moves, with the table it decides over.** Rule versions
   (`dw_platform.application.rule_versions`, `platform.rule_versions`, moved
   with `ALTER TABLE … SET SCHEMA`, every row kept); the checks of a change in
   words; the header-row and column-match checks of a company file; the model
   step measurements and the readiness check (`platform.model_step_measurements`,
   moved the same way). A context registers its keys, schemas, approval type,
   scopes, bars and steps.
2. **The queue stays with each context.** Rule drafts (a template or words
   waiting for the worker), master-data imports in flight, the stored
   mailbox and outbound mail are rows a context's own lane writes, audited as
   that lane (ADR 0011). Purchasing writes its own, thin, over the platform's
   checks, reading Sales' code for the pattern (ADR 0013 decision 4). Sales'
   tables stay where they are, and nothing of Sales' behaviour changes.
3. **The reader** follows ADR 0013 decision 2 unchanged: its wire, transport
   and the operations that are not a context's (text, sheets, table rows,
   mail) become the platform's; each context registers its own.
4. A queue moves to the platform only when one lane serves two contexts with
   one identity — which none does today.

## Consequences

- One owner per decision: a rule version, a change in words, a template's
  columns and a model step's readiness are decided by the platform's code
  whichever context asks; a test of each runs in `dw_platform` with a
  registry of its own.
- Two small queues where Sales had one. They carry no fact of their own (a
  draft holds a document the platform's checks produced); their shape is
  allowed to differ by context, and their tests say what each context needs.
- ADR 0013's sentence "their tables leave the `sales` schema" holds for the
  tables a decision owns (`rule_versions`, `model_step_measurements`); the
  queue tables (`rule_drafts`, `catalog_*`, `mailbox_*`, `outbound_mails`)
  stay in `sales`.
