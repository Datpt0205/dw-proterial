# 35 — The DW1 process map redrawn; the configuration made simple

Status: done (2026-11-16)
Blocked by: none (redrawn again as 24–29 land)
Category: enhancement

## Why

Đạt, 11-13: redraw DW1's flow on the portal (React Flow, the one place
`@xyflow/react` is allowed) to the BA's merged flows and dw_sales ADRs
0009–0012, and keep the configuration simple: few settings, each one a
non-technical head understands, never so many they confuse.

## Shape

- The map shows the BA's step codes (0-KH … 6.3; 1 … 2.1.6), the thread
  before the PO, the change loop and the confirmation wait. The moves come
  from code (`order_moves()` and the quote moves); the map never lists them
  a second time.
- The settings a tenant changes are a short list with defaults and one
  sentence each; everything else stays the platform's.

## Acceptance

1. A move added in code appears on the map without editing the map.
2. The settings a head sees fit one screen per DW, each with one sentence.

## Done

2026-11-16. Presentation and grouping only: no rule semantics, migration or
authorization changed.

- **The BA's step codes** (`domain/process.py` `BA_STEPS`, beside
  `WIV_STEPS`): the one owner of code → words, per procedure, keyed by the
  place DW1 is at while the step runs (a status, or `<flow>.<step>`). Served
  on each node (`ProcessNodeView.ba_steps`) and each flow step through
  `GET /sales/rules/process`; the web names none. Codes are the BA's; the
  words are ours. A BA step DW1 does not do yet (5.1, 6.1B, 6-HUY, 2.2.x, the
  JP & HQ and mass/pcs branches) has no place and is left out; `confirmed`
  (the customer's agreement, ADR 0011) and `ycbg_drafted`/`returned` have no
  BA step. The `.drawio` files are gone and the spec does not list the
  codes: they were read from the local flow review outside git (codes only,
  no customer data).
- **The flows beside the statuses** (`process_settings.SUBFLOWS`, served as
  `ProcessLaneView.subflows`): the thread before the PO (24), the wait on PC
  before Bravo (07), a change asked by mail (27) and the update loop (29).
  Every status set and move is read from the domain:
  `orders.changeable_statuses()`, `CONFIRMATION_LEFT`,
  `update_loop_statuses()` and the new `update_loop_moves()` (`_LOOP_NEXT`),
  which `_loop_with` now enforces, so the map's table is the domain's own and
  not a second copy. The confirmation wait (28) is the status
  `confirmation_sent`, already a node.
- **Web** (`rules/process/page.tsx`, `_components/process-subflows.tsx`,
  `process-map.tsx`, `process-flow.tsx`): a tile carries its BA codes
  ("BA 5-KC"); its details and the phone card carry codes with words and the
  flows that run while a case is there; under the map, "Luồng bên cạnh các
  trạng thái" opens each flow on click (steps in order, codes, statuses,
  next). Flow and step words in `labels.ts` (`SUBFLOW`, `SUBFLOW_STEP`); a
  step the API adds shows as its code.
- **Simple configuration**: `process_settings.HEAD_SETTINGS` (10, the cap
  `HEAD_SETTINGS_MAX`), each a placement plus one plain sentence, served as
  `head_settings` (a key the caller may not read left out). `audience()`
  fails closed: anything not listed, a field added later included, is the
  admin's. The page shows "Thiết lập chính" first (`head-settings.tsx`: the
  sentence, what applies now, the platform's default), edited in the same
  drawer as a status (`?node=head`, one proposal per key, approved as
  before); "Nâng cao" holds the whole-process and per-lane settings, and
  every step's settings stay on its status.

**Inventory** (every setting a tenant changes for DW1 today):

| Where                                                                     | Fields                                                                                                                                                                                                                                    | Shown                                   |
| ------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------- |
| `sales_order_rules`                                                       | `price.relative_tolerance`, `cross_check_required`                                                                                                                                                                                        | head                                    |
| `sales_order_rules`                                                       | `lme_band`, `short_lead_time.*`, `export_control_mode`, `export_control.denial_list_max_age_days`, `fiscal_year_start_month`, `layout_onboarding`, `shared_mail_domains`, `implied_acceptance` (per customer), 24 `findings.*` severities | Nâng cao (on their step)                |
| `sales_order_rules`                                                       | `model_assist.*` (locked: bar), `intake.*` (locked: bound at build)                                                                                                                                                                       | Nâng cao, read-only                     |
| `sales_quote_rules`                                                       | `validity_days`                                                                                                                                                                                                                           | head                                    |
| `sales_quote_rules`                                                       | `reference_price.*`, `copper_basis`; `design_mailboxes` (locked: trust)                                                                                                                                                                   | Nâng cao                                |
| `sales_pricing`                                                           | `copper_adders`, `floor_margin`, `freight` (price readers only)                                                                                                                                                                           | Nâng cao                                |
| `sales_followups`                                                         | `waiting_pc`, `waiting_customer`, `order_unconfirmed` remind and escalate hours, `quote_waiting_design` hours, `quote_deadline` hours, `morning_brief.at`                                                                                 | head                                    |
| `sales_followups`                                                         | each follow-up's `enabled` and `notify`, `morning_brief` (`enabled`, `model_opening`, `due_within_days`, `notify`), `working_hours` (zone locked), `implied_acceptance.enabled`, `your_turn`                                              | Nâng cao                                |
| `sales_kpi`                                                               | targets, `manual_baseline_minutes.*`                                                                                                                                                                                                      | Nâng cao                                |
| `sales_emails`, `sales_documents`, `sales_handoffs`, `sales_bravo_upload` | copy, templates, the paste sheet's columns                                                                                                                                                                                                | `/sales/rules` (Nâng cao there already) |
| `sales_salesorder_rules`                                                  | per customer, learned by example (38)                                                                                                                                                                                                     | master data, never edited               |
| outside the rules                                                         | PO layouts (`/sales/layouts`), master data, roles and permission sets (`/admin`)                                                                                                                                                          | their own pages                         |

**Why these ten**: each is a number or a switch a Sales head decides from
what their team does (how much price drift is acceptable, whether a second
person checks, how long to wait on PC, the customer and Design before a
reminder, when to escalate, how long a quote stays valid, when the morning
brief arrives), each readable as one sentence without the rule's schema, and
none locked. Everything per finding, per customer, per step's minutes,
compliance and the model switches stays under "Nâng cao".

**Questions** (kept under "Nâng cao" until answered): is
`export_control_mode` the head's decision or the export-control PIC's?
Should each customer's days of silence (`implied_acceptance`) live in master
data beside the customer rather than in the order rules? What do
`short_lead_time.from`/`lead_time`, `layout_onboarding.uncertain_first_pos`
and `fiscal_year_start_month` mean to Proterial, and does anyone there want
to change them? The BA's words for 0-KH, 6-PC and the gate "Khách quyết
định?" (no code) are ours; the BA to confirm.

Tests: `test_process_settings.py` (every BA place drawn and served, codes
unique; the flows read from the domain; the loop refuses a step off its
table; the head's list fits, one sentence each, placed and unlocked;
`audience` fails closed; served without an unreadable key), web
`rules-process.test.tsx` "ticket 35" (codes as served and one the server
adds; tile codes; flows on click; a flow step and move the server adds drawn
without a change; the head's list counted, each with its sentence, value and
default; edited in the drawer).
