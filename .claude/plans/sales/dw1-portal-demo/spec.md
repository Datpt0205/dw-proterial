# DW1 portal demo — Đơn hàng & Báo giá on mock data

Status: ready-for-agent (amended 2026-10-03)
Owner: Đạt
Started: 2026-10-02

## Why

Proterial Vietnam's Sales department was proposed two Digital Workers. DW1
(Đơn hàng & Báo giá) is in scope now; DW2 (Giao hàng & CDO) is not. Proterial
has not sent any data yet (the requirements doc v1.2 is still to be sent), so
this slice proves the whole DW1 flow end to end on **mock data behind real
ports**. The mocks are later replaced by Bravo, SharePoint/OneDrive or
Microsoft 365 adapters without changing the flow.

Amended 2026-10-03 after a conformance review against the two procedures and
the people who run them. The first version got the mechanics right (reading,
mapping, checks) but not the process steps or the roles. The review quotes
the customer's survey, so it stays outside git. The tickets cite its gap ids
(G1–G39) so that an amendment can be traced back to it.

## Scope

In:

- A portal that follows the two procedures step by step (see "Process map"
  below): WIV-03-012 steps 1–3 and 6–10, and WIV-03-023 steps 1–10. The
  master-list row (step 11) and the yearly screening (step 12) are built on
  mock data.
- Mock inbox as the entry point: sample emails with PO, RFQ and Design-reply
  attachments. Processing starts from a button, not a mailbox.
- **Order flow (WIV-03-012):**
    1. Classify the message and give it a disposition.
    2. Read the PO (Excel, including one sheet per page; text PDF) with
       anchors.
    3. Map each customer code to a PRV code: an exact convert-list hit, or a
       candidate Sales confirms.
    4. Run the checks and stamp each check's basis on the case.
    5. PIC self-check: a disposition on every finding (steps 7–8).
    6. Produce the Bravo upload file.
    7. The PIC records the Bravo sales-order number, stating that the Bravo
       entry was compared with the PO (WIV step 7 on the Bravo entry stays
       with Sales, requirements doc §2.1).
    8. A different Sales member cross-checks against the Bravo entry
       (step 9).
    9. Draft the confirmation. It names both people and gives the confirmed
       delivery date for each line (step 10).

    A finding sent back to the customer produces a correction draft (step 8).
    The customer's revised PO supersedes the previous revision inside the
    same case, and the flow runs again.

- **Quotation flow (WIV-03-023):**
    1. Read the RFQ, with its anchors and the quote due date.
    2. Draft the YCBG. The PIC records the Bravo YCBG number.
    3. Draft the request to Design.
    4. Take Design's reply: an inbox message matched by YCBG number.
    5. If needed, discuss the spec with the customer.
    6. Gather the price evidence and raise the quotation findings.
    7. Sales decides the price (`priced_by`).
    8. Generate the quotation document (xlsx + PDF) and stamp its hash.
    9. Approval by `sales_head` or a deputy who is not the pricer, or the
       quote is returned to the pricer.
    10. Draft the send email.
    11. Sales confirms the master-list row.

    Sales can decline with a reason at any step before the quote is sent.

- Every value shown in review carries its source anchor: one `SourceAnchor`,
  either `sheet!cell` or a page plus boxes on the rendered page
  (`.claude/rules/ui-quality.md`, ADR 0009).
- A stop control: any PIC pauses DW1; only the head resumes it.

Out (this slice):

- Real email, Zalo, customer portals, Bravo API or database access. Bravo
  order history and the open-YCBG list are a mock export.
- Any model call on real Proterial documents. Parsing is deterministic; a
  model step, if added, runs only on the fictional mock data.
- Scanned or image PDFs, `.xls`/`.doc`, archives, and password-protected or
  macro-enabled files. They are routed to Sales with the reason and nothing
  is extracted (ticket 12 reads them).
- Auto-confirmation (A3). DW1 only keeps a shadow count of orders that would
  have qualified.
- DW2. That includes every exchange with PC about dates beyond the suggested
  date (WIV-03-012 steps 4–5) and the backlog report (step 11).
- Export-control evaluation. DW1 warns, and a holder of
  `sales.compliance.ack` acknowledges.
- Support access, tenant overrides of rules and templates, sandboxed
  parsing, retention: ticket 12.

## Process map

One row per surveyed step. The code owner of this mapping is
`dw_sales.domain.process` (ticket 02). The overview route (05) and page (08)
read it, and this table describes it.

| WIV step                   | DW1 does                                                                                | Sales / head does                                                                              | State or artifact                                                         | In this slice? |
| -------------------------- | --------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- | -------------- |
| O1 receive PO              | Classify; one disposition per message; detect duplicate and revised POs                 | Handle messages routed to Sales                                                                | message disposition; order `received`                                     | yes            |
| O2 PRV code                | Convert-list lookup; attribute candidates, never a guess                                | Confirm a candidate; ask Design for a new code                                                 | `mapping_status`; convert-list proposal xlsx                              | yes            |
| O3 enter PO                | Read every line with anchors; Bravo upload file once prepared                           | Upload to Bravo; record the sales-order number                                                 | `uploaded_to_bravo`; upload xlsx (MOCK template)                          | yes            |
| O4 delivery date           | Suggested date per line from received date + standard lead time                         | Enter the confirmed date; agree a short LT with PC                                             | per-line suggested / confirmed date                                       | suggestion     |
| O5 schedule change         | —                                                                                       | —                                                                                              | —                                                                         | DW2 / out      |
| O6 check against quotation | Validity, price, LME band, MOQ, pack, currency, UoM                                     | Decide each finding                                                                            | findings with dispositions                                                | yes            |
| O7 self-check              | Coverage statement; anchors on every value                                              | PIC disposes of every finding and prepares; after upload, compares the Bravo entry with the PO | `prepared` (`prepared_by`); `bravo_entry_compared` on `uploaded_to_bravo` | yes            |
| O8 ask customer to correct | Correction draft listing exactly the `ask_customer` lines                               | Send it                                                                                        | `correction_requested`; the revision supersedes                           | yes            |
| O9 cross-check             | Cross-check sheet: PO value, anchor, upload value, disposition, who typed it            | A Sales member other than the preparer checks against Bravo                                    | `cross_checked` (`cross_checked_by`)                                      | yes            |
| O10 confirm PO             | Confirmation draft naming both people, confirmed date per line                          | Send it; the stamped hard copy stays the record until Proterial says                           | `confirmed`; confirmation draft                                           | yes            |
| O11 backlog report         | —                                                                                       | —                                                                                              | —                                                                         | DW2 / out      |
| Q1 receive RFQ             | Classify; extract with anchors and quote due date; assign from the customer's Sales PIC | Take it on                                                                                     | quote `received`; `assigned_to`                                           | yes            |
| Q2 YCBG                    | YCBG draft (MOCK form)                                                                  | Enter it in Bravo; record the YCBG number                                                      | `ycbg_drafted` → `ycbg_recorded`                                          | yes            |
| Q3 send to Design          | Design request draft                                                                    | Send it                                                                                        | `sent_to_design`                                                          | yes            |
| Q4 Design reply            | Match the reply by YCBG number; list YCBGs still waiting                                | Read the result                                                                                | `design_replied`; "YCBG chờ Design" list                                  | yes (mock)     |
| Q5 decline                 | Decline draft with the reason                                                           | Decide and send                                                                                | `declined(reason)`                                                        | yes            |
| Q6 spec discussion         | Spec-discussion reply draft                                                             | Discuss with the customer and Design                                                           | `spec_discussion`                                                         | yes            |
| Q7 price                   | Evidence for every factor; quotation findings                                           | Decide the price                                                                               | `priced` (`priced_by`)                                                    | yes            |
| Q8 quotation document      | Fill the xlsx + PDF from the decided terms (MOCK form)                                  | Check it                                                                                       | `document_sha256`                                                         | yes            |
| Q9 approval                | Approval pack with the document preview                                                 | Head or deputy (not the pricer) approves or returns                                            | `pending_approval` → `approved` / `returned`                              | yes            |
| Q10 send                   | Send draft attaching the document and naming the spec no.                               | Send; mark sent                                                                                | `sent`                                                                    | yes            |
| Q11 master list            | Master-list row                                                                         | Confirm it                                                                                     | `master_list_recorded`; master-list xlsx (MOCK)                           | yes (mock)     |
| Q12 yearly screening       | Codes quoted with no order in 12 months                                                 | Decide what to remove                                                                          | screening report                                                          | yes (mock)     |

**Deviation Proterial must accept.** WIV-03-012 enters the PO in Bravo
first, then checks price (step 6) and compares the PO with the Bravo entry
(step 7). DW1 runs its checks and the PIC's self-check **before** the Bravo
entry, and the cross-check (step 9) stays after it. The PIC's own
comparison of the Bravo entry with the PO is not dropped: the requirements
doc (§2.1, step 7) leaves it with Sales unless Proterial exports entered
orders, so recording the sales-order number carries that statement. This may
need a WIV revision under document control (requirements doc §3.2). Until
Proterial answers, the demo presents the reordering as a proposal.

**Overlap with Proterial's own Bravo plans** (requirements doc §3.3). O6 is
presented as checking quotation validity, LME band, MOQ and pack size before
entry, which a unit-price link in Bravo does not do. The O4 suggestion is
presented as interim until Bravo's own date suggestion arrives. No time saved
on an overlapping step is counted in the "Promises" figures.

## Actors, roles and scopes

| Actor                               | Platform mapping                                                   | Scopes                                                                                                                                                                                                                   | Demo persona                                                     |
| ----------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------- |
| Sales phụ trách (PIC)               | context role `sales_pic`                                           | `sales.overview.read`, `sales.case.read`, `sales.price.read`, `sales.inbox.process`, `sales.order.prepare`, `sales.order.cross_check` (only on cases someone else prepared), `sales.quote.prepare`, `sales.worker.pause` | `dev\|an.nguyen` (PIC đơn hàng), `dev\|dieu.hoang` (PIC báo giá) |
| Người kiểm chéo                     | inside `sales_pic`; per case, not a maker of it (decision 7)       | `sales.order.cross_check`                                                                                                                                                                                                | Diệu cross-checks An's orders                                    |
| PIC báo giá được xem giá khách khác | permission set `sales_price_evidence`                              | `sales.price.other_customers.read`                                                                                                                                                                                       | `dev\|dieu.hoang`                                                |
| Trưởng bộ phận Sales                | context role `sales_head`                                          | everything `sales_pic` holds, plus `sales.price.other_customers.read`, `sales.quote.approve` (never on a quote they priced) and `sales.worker.resume`                                                                    | `dev\|giang.do`                                                  |
| Người duyệt báo giá thay            | permission set `sales_quote_approver` on a `sales_pic`             | `sales.quote.approve`                                                                                                                                                                                                    | `dev\|khoa.lam` (new, fictional)                                 |
| PIC kiểm soát xuất khẩu             | permission set `sales_export_control` on a `sales_pic`             | `sales.compliance.ack`                                                                                                                                                                                                   | `dev\|an.nguyen`                                                 |
| Lãnh đạo (xem tổng hợp)             | context role `sales_viewer`                                        | `sales.overview.read` only: counts and times, no amounts, no case list                                                                                                                                                   | `dev\|ha.vu`                                                     |
| IT (quản trị tenant)                | platform `org_admin`, no `sales.*`                                 | none; a separation-of-duties rule keeps `platform.members.write` and `sales.price.read` off one membership                                                                                                               | `dev\|tam.ngo` (new, fictional)                                  |
| Người ngoài phòng Sales             | `member` / `manager`, no `sales.*`                                 | none: 403 on `/api/v1/sales/*`                                                                                                                                                                                           | `dev\|binh.tran` (mua-hang)                                      |
| Tenant khác                         | `sales_pic` in tenant-beta                                         | 404 on tenant-alpha's ids; empty mocks                                                                                                                                                                                   | `dev\|bao.pham`                                                  |
| DW1 (tài khoản dịch vụ)             | production: a worker principal; demo: `actor_kind='worker'` events | `sales.inbox.process` only. It never prepares, cross-checks, prices or approves; in Bravo, if granted at all, it is draft-only                                                                                           | no sign-in; events labelled "DW1"                                |
| Đội hỗ trợ FPT                      | ADR 0008 grant only (ticket 12)                                    | support list `{sales.overview.read, sales.case.read}`; never a price or write scope                                                                                                                                      | not seeded                                                       |
| Design, PC, Kế toán, QA             | no portal role                                                     | none; Design reaches DW1 by mail                                                                                                                                                                                         | Design is a fictional internal `.example` address                |

- The sales migration (ticket 04) inserts the roles and permission sets, with
  the Vietnamese name in the `name` column. No `sales.*` scope sits on
  `member`, `approver`, `manager`, `director`, `executive` or `org_admin`; a
  migration test asserts this.
- No walk-through uses `platform_admin`. It passes every check, so it would
  hide the ones that are missing.
- `sales.rules.approve` (for `sales_head`) and `sales.case.assign` are
  declared only together with the routes that read them (ticket 12). Neither
  is declared earlier.
- Persona names are fictional and never the survey's PIC names.

## Decisions

1. **Mock data is fictional.** No real company, person or Proterial figure
   is committed. The repo is public (Đạt chose to keep it public on
   2026-10-02); Proterial's own documents stay outside git.
2. **Master data is read through ports, not stored in sales tables.**
   `SalesCatalogPort` covers customers, items, the convert list, quotations,
   LME, NOC status, the 12-month Bravo order export and the open-YCBG list.
   `InboxPort` covers messages and attachments. Mock adapters implement both
   over fixture files in `dw_sales/adapters/mock/`, and every catalog read
   returns the snapshot's `as_of`. Bravo or SharePoint adapters replace them
   later. One owner per fact: the context never copies master data into its
   tables. The one exception is a case's check basis (decision 11), which is
   evidence and never master data.
3. **Case state lives in PostgreSQL** (`sales` schema, RLS FORCEd, tenant and
   workspace on every row). Generated files are artifacts stored by the
   context under tenant/workspace keys.
4. **Code decides.** Code does the mapping, price/LME/MOQ checks, dates and
   the numbers in every file and email. Templates render the emails.
5. **Approval in this slice is a case decision recorded by the context with
   an audit event, not yet a runtime interrupt.** This deviates from
   CLAUDE.md ("Approval pauses and resumes a durable, checkpointed run").
   `packages/python/dw_sales/docs/adr/0001-case-decision-before-runtime.md`
   records it, with every runtime guarantee it bypasses and the substitute
   used meanwhile. Ticket 10 is the exit. Nothing in this slice writes
   outside the platform; a person uploads or sends each artifact, and the
   download gates (ticket 06) stand in for the runtime's approval.
6. **Web UI uses antd v6** as CLAUDE.md requires. The shell slice (ticket 07)
   is platform work and lands first.
7. **Maker/checker per WIV-03-012 step 9.** The cross-checker holds
   `sales.order.cross_check` and is none of the case's makers: not the
   preparer, not whoever recorded the Bravo entry, and not anyone whose
   hand-entered value is still on the case (ADR 0009 decision 2: a typed
   value needs a second person). The dw_sales handler enforces this per
   case, and a CHECK on `order_cases` backs the first two
   (`cross_checked_by` distinct from `prepared_by` and from
   `bravo_recorded_by`). Platform `sod_rules` cannot
   express it, because every PIC both prepares and checks. The same applies
   to quotations: `approved_by <> priced_by`, by handler and CHECK. The
   policy key `cross_check_required: true` in `sales_order_rules` holds until
   Proterial answers. If they make it false, `uploaded_to_bravo` goes
   straight to `confirmed`.
8. **Price visibility fails closed.** A response carries an amount only when
   the caller holds `sales.price.read`. Another customer's price (quote
   evidence, master-data quotations) also needs
   `sales.price.other_customers.read`, which only the quotation PIC
   (`sales_price_evidence`) and `sales_head` hold. Audit events,
   notifications, logs, traces and error messages never carry an amount, a
   target price, or a validation message that echoes input. They carry ids,
   finding codes, transitions, `case_version` and counts. Prices, quotations
   and the LME rule are classified confidential; customer contacts are
   personal data. See dw_sales ADR 0003.
9. **Every finding gets its own disposition.** The values are `open`,
   `accepted` (reason, by, at), `corrected_by_sales` (value, source note,
   by, at) and `ask_customer` (by, at). `prepared` is refused while any
   finding other than `missing_noc_esf` is `open`, or any line's mapping is
   neither `exact` nor `candidate_confirmed`. `missing_noc_esf` is decided
   by the export-control PIC and blocks only `confirmed`, as the
   requirements doc's interim answer for export control has it (§3.2), so
   the PIC's preparation does not wait on a second person. Nothing accepts
   findings in bulk. Any
   `ask_customer` moves the case to `correction_requested`. Which
   dispositions a code allows is in the findings table.
10. **Every inbound message ends in exactly one disposition:**
    `case_created(order|quote)`, `attached_to_case` (a revision, or a Design
    reply), `routed_to_sales(reason)`, or `not_yet_processed`. The reasons
    are `delivery_change`, `complaint`, `design_reply_unmatched`,
    `sample_request`, `customer_unknown`, `attachment_unreadable` and
    `other`. Each routed message has an owner. "No message missed" becomes a measured
    count: messages `not_yet_processed`, and routed messages with no owner.
11. **A check's basis is stamped on the case and never re-read.** For each
    line the case stores immutably:
    - the convert entry or candidate list;
    - `quote_no`, price, currency, validity and copper basis;
    - the LME month and value;
    - the item's MOQ, pack size and lead time, and where the lead time came
      from.

    For the case it stores the rules `id@version`, the parser version, the
    attachment sha256, the master-data snapshot's `as_of` and the release
    manifest ref. Clean lines get a basis too. The basis is case evidence: it
    is never served as master data and never refreshed from the catalog.

12. **ADR 0009 conformance, exception-first.** The verifier sees the
    original: the rendered PDF page with boxes drawn on it, or the sheet grid,
    never highlighted extracted text. The server records each source it
    serves as `(principal, case, case_version, attachment, page or sheet)`.
    `prepare` and `cross-check` answer 409 "chưa mở nguồn" unless that same
    principal was served, for the current `case_version`, the order's source
    and every page or sheet holding a flagged or hand-entered value. Review is
    per order and exception-first. A clean line needs no action on each of
    its values once the coverage statement shows every check ran ("Đã đọc
    N/N dòng …"). Each flagged line needs its disposition.
13. **Demo exception to ADR 0010 and ADR 0007.** Attachments are parsed in
    the API process, and only the repo-generated fixtures. Readers sniff the
    type from the bytes, refuse encrypted and macro-enabled files, and
    enforce byte/sheet/page/cell caps from `sales_order_rules`. Production
    parses in the worker sandbox after a malware scan (ticket 12). No model
    turn reads document content in this slice, so ADR 0007's toolset rule is
    not triggered yet. Ticket 10 must hold to it when a model step arrives.
14. **Proterial's rules, templates and wording arrive only as tenant
    overrides in storage.** Nothing of theirs is committed. `configs/`
    carries the platform layer with fictional defaults, read through
    `TenantOverlay`; the tenant layer goes through `PolicyOverridePort`. A
    new tenant version of a Sales rule or template takes effect only after a
    holder of `sales.rules.approve` approves it. Whoever proposed that version
    cannot approve it. The route, its check and its audit event are ticket 12.

## Findings the checks raise

"Blocking: yes" is `error` in `sales_order_rules`; the case stamps the
severity it was raised with. A blocking finding can be `accepted` only where
the last column says so, and then only with a reason. A warning's `accepted`
is an acknowledgement.

| Code                      | Blocking | Rule                                                                                                                                                                                                                                                                                                                                                                                                                           | Dispositions allowed                                                                                                                                                              |
| ------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `code_unmapped`           | yes      | Customer code not in the convert list and no attribute match                                                                                                                                                                                                                                                                                                                                                                   | `corrected_by_sales` (a PRV code that exists in the item master, typed by hand, e.g. once Design has created it; a "Cần Design tạo mã" note is drafted meanwhile), `ask_customer` |
| `code_ambiguous`          | yes      | No exact convert entry; more than one item matches the attributes                                                                                                                                                                                                                                                                                                                                                              | `corrected_by_sales` (via a candidate confirmation), `ask_customer`                                                                                                               |
| `price_mismatch`          | yes      | PO unit price ≠ valid quotation price, beyond the policy's tolerance, in the same currency                                                                                                                                                                                                                                                                                                                                     | `accepted`, `ask_customer`                                                                                                                                                        |
| `currency_mismatch`       | yes      | PO currency ≠ the quotation's currency. Never converted silently; the exchange-rate rule is owed by Proterial                                                                                                                                                                                                                                                                                                                  | `accepted`, `ask_customer`                                                                                                                                                        |
| `uom_mismatch`            | yes      | PO unit unknown, or ≠ the quotation's or item's unit. An unknown unit is a finding on that line, not a load failure                                                                                                                                                                                                                                                                                                            | `accepted`, `ask_customer`                                                                                                                                                        |
| `quotation_missing`       | yes      | No valid quotation for customer + item on the PO date                                                                                                                                                                                                                                                                                                                                                                          | `accepted`, `ask_customer`                                                                                                                                                        |
| `lme_band_mismatch`       | yes      | Quotation's LME band ≠ the band of the policy's LME month                                                                                                                                                                                                                                                                                                                                                                      | `accepted`, `ask_customer`                                                                                                                                                        |
| `moq_violation`           | yes      | Quantity < MOQ (the quotation's, else the item's)                                                                                                                                                                                                                                                                                                                                                                              | `accepted`, `ask_customer`                                                                                                                                                        |
| `pack_multiple`           | yes      | Quantity not a multiple of the packing unit                                                                                                                                                                                                                                                                                                                                                                                    | `accepted`, `ask_customer`                                                                                                                                                        |
| `line_total_mismatch`     | yes      | The sum of the extracted line amounts ≠ the printed total, or the line numbers are not contiguous 1..N across sheets/pages                                                                                                                                                                                                                                                                                                     | `corrected_by_sales`, `ask_customer`                                                                                                                                              |
| `value_uncertain`         | yes      | A value not parsed unambiguously, or read from a flagged region (hidden sheet/row/column, font colour = fill, formula without a cached value, unchecked sheet)                                                                                                                                                                                                                                                                 | `corrected_by_sales`, `ask_customer`                                                                                                                                              |
| `customer_unknown`        | yes      | The sender's domain is no customer's (a forward from a Sales or manager address, or an unknown domain). The customer was taken from the buyer the document names, by exact match, and Sales has not confirmed it. With no exact match there is no case: the message is routed `customer_unknown`                                                                                                                               | `corrected_by_sales` (Sales confirms or picks the customer)                                                                                                                       |
| `duplicate_po`            | yes      | Same customer + PO no. + revision with identical lines, in a DW1 case or in the Bravo export                                                                                                                                                                                                                                                                                                                                   | none; the case's only exit is `closed(duplicate)`, linked to the original                                                                                                         |
| `requested_date_short_lt` | no       | Requested date < the date the PO was **received** (Asia/Ho_Chi_Minh) + the **standard** lead time (WIV-03-012 step 4 and the requirements doc's proposal both name the standard lead time; the valid quotation's LT is shown beside it). Which table and day basis apply is owed by Proterial (requirements doc §4 item 9), so both are policy keys. The line cannot reach `confirmed` without a PC-confirmed date (who, when) | `accepted`                                                                                                                                                                        |
| `missing_noc_esf`         | no       | Customer has no NOC, no ESF for the current fiscal year, or a denial-list check that is missing or older than policy allows. While open it blocks `confirmed` only (decision 9); `export_control_mode: block_confirmation` refuses `confirmed` even after the acknowledgement                                                                                                                                                  | `accepted`, only by a holder of `sales.compliance.ack`                                                                                                                            |
| `revised_po`              | no       | Same customer + PO no. with a higher revision, or the same revision with different lines. Attached to the existing case as a new revision; every check re-runs; the line diff to the previous revision is shown                                                                                                                                                                                                                | `accepted` (Sales read the diff)                                                                                                                                                  |
| `revision_without_base`   | no       | A revision whose earlier revision DW1 has never seen, in a case or in the Bravo export: processed out of order, or entered in Bravo before DW1. Handled as a new PO, never diffed against nothing                                                                                                                                                                                                                              | `accepted`                                                                                                                                                                        |
| `customer_temporary`      | no       | The customer holds a temporary code (WIV-03-031)                                                                                                                                                                                                                                                                                                                                                                               | `accepted`                                                                                                                                                                        |
| `sender_unverified`       | no       | The mail system's SPF/DKIM/DMARC result for the sender is not `pass`. It would block any later auto-confirmation                                                                                                                                                                                                                                                                                                               | `accepted`                                                                                                                                                                        |

Quotation findings (ticket 03), computed from `sales_pricing` and the decision:

| Code                       | Blocking | Rule                                                                                                                                                              | Dispositions allowed                                                                |
| -------------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `rfq_incomplete`           | yes      | A requested line lacks its quantity or required date. The case cannot leave `received` except by decline                                                          | `corrected_by_sales` (Sales types the customer's answer; asking is Sales' own mail) |
| `price_below_policy_floor` | yes      | Decided price < copper component + the policy's floor margin                                                                                                      | `accepted` with a reason, only by the approver (decision 7: not the pricer)         |
| `price_basis_mismatch`     | yes      | The decision's copper basis (fixed or banded; the LME month used) is not what the policy prescribes, or not the latest published month when the price was decided | re-decide, or `accepted` with a reason by the approver                              |
| `above_target_price`       | no       | Decided price > the customer's target price                                                                                                                       | acknowledged by the approval itself                                                 |

Price-bearing codes are `price_mismatch`, `currency_mismatch`,
`lme_band_mismatch`, `line_total_mismatch` and all four quotation codes. Their
`expected`/`actual` values reach only holders of `sales.price.read`.

## Promises and what this demo shows

What the proposal promises, what is measured on the mock set, and what is not
claimed. Targets and the manual baseline come from `sales_kpi@1.0.0`, whose
committed values are fictional. Proterial's own figures exist only as tenant
data loaded at runtime. The proposal states two different quotation-time
targets; which one the demo measures is owed by Đạt, and until then it is a
policy key with a fictional default.

| Promise (paraphrased)                      | Measured on the mock set                                                                                                        | Not claimed                                                                             |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| No message is missed                       | Messages without a disposition and routed messages without an owner: both 0                                                     | Coverage of a real mailbox (none is connected; the interim mode is mail Sales forwards) |
| Every PO line is checked                   | Lines printed vs read; checks × lines run; the coverage statement on every order                                                | Formats this slice does not read (scans, `.xls`)                                        |
| POs right the first time                   | Orders prepared with no corrected value, and the shadow count of orders meeting the A3 minimum conditions                       | Any rate: the mock set is far below the sample a rate needs (requirements doc §5)       |
| Faster PO confirmation and quotation       | DW-controlled time from ingest to draft ready, and Sales decision time, kept separate from waits on Design, the approver and PC | End-to-end times that include those waits; overnight processing                         |
| Drafts Sales can use without rewriting     | Drafts sent unedited                                                                                                            | A rate                                                                                  |
| Sales can stop DW1                         | Pause by a PIC, resume only by the head, with the reason and a notification                                                     | —                                                                                       |
| DW1 has its own identity and a log         | `actor_kind` worker vs user on every case event                                                                                 | A production service principal (ticket 10)                                              |
| Prices stay with those allowed to see them | Each persona's refusals (Done when)                                                                                             | Support access controls (ticket 12)                                                     |
| Hours saved                                | An export per surveyed step (O1 … Q12) and month, in the format Proterial already fills in                                      | Any hours figure; overlapping steps (requirements doc §3.3) are not counted             |

DW time is measured from ingest, the moment "DW xử lý" processes a message.
The fixtures' `received_at` stays fixed, because it drives the short-LT rule.

## Interim behaviour until Proterial answers

One row per open decision in the requirements doc §3.2, plus one new
question. An answer changes a policy key or a role assignment, never code.

| Open decision                                                            | Interim behaviour in the demo                                                                                                                                                                                                                                           | Who acts                                 | What changes when they answer                                                                  |
| ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Self-check, cross-check, stamp (O7, O9, O10)                             | Kept. The confirmation draft names both people as the electronic stand-in; the stamped hard copy stays the record                                                                                                                                                       | `sales_pic` (maker), another `sales_pic` | `cross_check_required`; or split `sales.order.cross_check` into a `sales_order_reviewer` set   |
| Quotation approval (Q9)                                                  | The portal approval is demonstrated; the signed hard copy stays the approval of record. Any holder of `sales.quote.approve` who is not the pricer approves                                                                                                              | `sales_head`, or `sales_quote_approver`  | Spec wording; Proterial's approval matrix (requirements doc §4 item 5) becomes data, ticket 12 |
| Where Sales approves                                                     | In the portal, on files and drafts DW1 prepares; a person uploads to Bravo and sends                                                                                                                                                                                    | `sales_pic`                              | Nothing in this slice (approving in Bravo needs a Bravo account; see ticket 12)                |
| Auto-confirm within thresholds                                           | Not applied; shadow count only                                                                                                                                                                                                                                          | —                                        | A future policy key and ticket                                                                 |
| Export control (WIV-03-032)                                              | Warn. The finding is acknowledged before confirmation                                                                                                                                                                                                                   | `sales_export_control`                   | `export_control_mode`; who holds `sales_export_control`                                        |
| Price evidence and price confidentiality                                 | Evidence only, plus an internal reference price where `sales_quote_rules.reference_price` defines one; no figure reaches the document or a draft until Sales decides; other customers' prices are seen only by the quotation PIC and the head                           | `sales_price_evidence`, `sales_head`     | `reference_price` (`null` disables it); who holds `sales_price_evidence`                       |
| Delivery date in the confirmation                                        | Sales enters the confirmed date, as today (the requirements doc's interim). DW1's suggestion is shown beside it, labelled as the proposal; a short LT is agreed with PC outside the portal                                                                              | `sales_pic`                              | `short_lead_time.lead_time` (default `item_standard`), `short_lead_time.day_basis`             |
| Temporary-code customer (WIV-03-031)                                     | Flagged (`customer_temporary`, warning); Sales handles it                                                                                                                                                                                                               | `sales_pic`                              | The severity of `customer_temporary`                                                           |
| Who may stop DW1                                                         | The proposal is demonstrated: any PIC pauses, only the head resumes, and holders of `sales.worker.resume` are notified. Outside the demo the requirements doc's interim holds until Proterial answers: Sales asks the implementation team to stop DW1 and works by hand | `sales_pic`, `sales_head`                | Who holds `sales.worker.pause` / `sales.worker.resume`                                         |
| Acceptance criteria                                                      | Results on the sample set are reported without a pass/fail verdict                                                                                                                                                                                                      | Đạt / FPT team                           | Thresholds in the tenant's `sales_kpi`                                                         |
| (new) Does a re-quote of an item that already has a BP code skip Design? | The Design step is kept                                                                                                                                                                                                                                                 | `sales_pic`                              | A policy key in `sales_quote_rules`                                                            |

## Done when

- `make lint typecheck test-unit test-architecture` pass; RLS and
  cross-tenant tests pass in `test-integration`.
- With the stack running, the personas walk the flow. No step is performed
  as `platform_admin`.
    - **An (PIC đơn hàng)** processes every mock message, and each ends in
      one disposition. On M04 he asks the customer to correct; M07 then
      supersedes it in the same case. He disposes of every finding, confirms
      M05's candidate, prepares the order, downloads the upload file and
      records the Bravo number. He acknowledges M03's `missing_noc_esf`.
      After Diệu's cross-check he confirms with a date per line.
    - **Diệu (PIC báo giá)** cross-checks An's order. She prices M10 from the
      evidence, including other customers' prices, and submits it.
    - **Giang (Trưởng bộ phận)** approves M10 and downloads the approved
      quotation document. He resumes DW1 after An pauses it.
    - **Khoa (duyệt thay)** approves a quote Giang priced.
    - **Refusals shown:**
        - An cross-checks his own order: the control is disabled with the
          reason in words, and the API answers 409.
        - An sees "Đã ẩn" on other customers' prices for M10.
        - An's prepare with an open blocking finding gets 409, naming the
          finding.
        - Diệu approves her own quote: 403, since she lacks
          `sales.quote.approve` whatever `approver_boost` gives her.
        - Giang approves a quote he priced: 409.
        - A PIC without `sales_export_control` acknowledges NOC/ESF: 403.
        - An resumes DW1: 403.
        - Hà (viewer) sees only the overview; every other Sales URL gets 403,
          and no response carries a price string.
        - Bình (purchasing) gets 403 on `/api/v1/sales/*`.
        - Tâm (IT) gets no Sales access and no price.
        - Bảo (tenant-beta) sees an empty inbox and gets 404 on tenant-alpha's
          ids.
        - Each download is refused before its state.
- Each finding in both tables is triggered by at least one mock message or
  fixture; the three quotation codes raised at decision time
  (`price_below_policy_floor`, `price_basis_mismatch`,
  `above_target_price`) by a scripted price decision in ticket 03's tests.
- An eval dataset `sales@1.0.0` with prompt_injection, cross_tenant_attack
  and missing_evidence cases passes, scored by `sales.extraction_accuracy`
  and `sales.findings_recall`.
- `reviewing-feature-security` and `reviewing-deployment-security` have been
  run and their negative tests exist.

## Tickets

See `issues/`. Order: the 01 follow-up (fixtures), then the 02 and 03
amendments, then 04, 11 (personas), 05, 06, then 08 (after 05–07), then 09.
Ticket 10 comes after the demo. 07 is done. 12 (production hardening) is
needs-triage, after 09.

The state names and their labels are listed once, in
`packages/python/dw_sales/CONTEXT.md`; tickets 02 and 03 own the
transitions until the code does. Every other document refers to them.
