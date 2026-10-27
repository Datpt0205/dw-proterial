# Sales (Proterial Vietnam) — DW1 Đơn hàng & Báo giá

This repo became the Proterial product repo on 2026-10-02: `origin` is
`github.com/Datpt0205/dw-proterial` (public; Đạt keeps it public for now).
The platform seed stays in `Datpt0205/codebase`. DW01 (procurement) keeps
running in `C:\Users\phung\dw` and gets no new features; it moves here when a
Purchasing DW for Proterial is signed (estimated 30–51 person-days).

## State

- 2026-10-27, **a routed message marked handled** (Đạt chose the done state; `application/routed_mail.py`, migration `d90793645086`): a person marks a message routed to Sales handled once dealt with outside DW1, with an optional note, and may reopen it. Who may is whoever Việc cần làm shows it to (`message_owners`, now the one answer both read: its PIC, any PIC for the pool's) and the head (`sales.case.assign`). It leaves Việc cần làm and the overview's waiting count and stays in the inbox (tabs "Chuyển Sales" and "Sales đã xử lý"), saying who and when; processing it again clears the mark. One CHECK (`ck_messages_handled`) holds the shape; `ix_messages_routed_work` leaves handled messages out. Audit `sales.message.handled`/`reopened`, the note kept off the audit row. Checked: unit 5, integration 4 (route, upsert, CHECK, another tenant 404), web 4; mutations of the owner guard, the in-memory filter and the SQL filter each went red.
- 2026-10-27, **ticket 43 run on the Docker stack** (stored mailbox, a scratch drop folder, override outside git): 5 fictional `.eml` files stored by `sales_mail_drop`, queued by `sales_inbox`, processed: the PO with its xlsx opened a case, the Design reply was recognised (verified sender) and routed `design_reply_unmatched`, the internal and body-only RFQ mails `other` (the stack's model is the mock). A PIC proposed `ignored_sender_domains: [seller.example]` from step O1, the head approved it (`sales_order_rules@1.7.1`), and the next internal mail (a subdomain) was `left_out` while a customer's was stored. Fixed on the way: the inbox no longer says "giả lập", and a stored mail's 68-character id shows as `eml-` + 8 digits (`_lib/messages.ts`). **Found by the edge-case sets:** (1) fixed 2026-10-27: the plain-text cut now knows Vietnamese Outlook's "Đã gửi:" (`domain/mail_parts.py`); (2) fixed 2026-10-27: a hand-off quantity in another unit than metres ("3 km", "4 cuộn", "2巻") is not copied, Sales fills it (`domain/handoffs.quantity_of`); (3a) fixed 2026-10-27: a delivery column that reads no date on any line refuses the layout (`requested_date_empty`); (4a) fixed 2026-10-27: an RFQ date in Reiwa (令和8年11月15日, R8.11.15, 令和元年) is read; **open:** (3b) the layout check accepts a thousands separator on a PDF with no grouped number (not fixed: checking it means telling a number from a date or a code in the form's cells, and a wrong guess refuses a good layout); (4b) the reply and RFQ cutters miss "loi"/"x2c" (lab notes; the cases were not kept, so not fixed on a guess). The edge-case sets live outside git (lab) until Đạt decides whether they join the datasets.

- 2026-10-27, **real mail without Microsoft 365 access** (ticket 43, `issues/43-mail-drop-folder.md`): Proterial refuses DW1 any M365 access and its admins are in Japan. Each PIC's Power Automate flow exports every Inbox mail as `.eml` to their OneDrive; a plant PC syncs the PICs' shared folders and shares them over SMB; the worker's `sales_mail_drop` lane parses each file in the reader sandbox (`mail.read`) and stores it (`sales.mailbox_messages`/`_attachments`/`_files`, migration `e544ff20fad6`, append-only, partitioned, RLS). `DW_SALES_MAILBOX=mock|stored` in both processes; `sales_order_rules@1.7.0` adds `ignored_sender_domains` (empty takes all; Design always taken), placed on step O1. Guides for the PICs and for the plant PC/host are Word files outside git. Checked: unit (mail read 12, lane 18), integration 16 on Docker, mutation check 10/10 red. **Owed:** retention of stored mail (must follow the cases'); the plant PC steps (OneDrive shortcuts moved into one folder, SMB over a OneDrive folder) are written from knowledge, not yet measured; a real Exchange export read by `mail.read` (Đạt's test file, not yet in hand).

- 2026-10-26, **user guide for Proterial** (Đạt): `docs/user-guide/Huong-dan-su-dung_Proterial_DW1.docx`, 22 pages, every role (Sales PIC, Sales head, leadership, IT), built from `docs/user-guide/huong-dan-su-dung-dw1.md` with the fdx-word-doc skill (TOC page numbers from Word over COM: no LibreOffice on this machine). Screenshots are the demo tenant's fictional data, taken as each persona through the dev-auth stack; every button label in the text was checked against the code. No screenshot of Thêm người (dev auth has no Keycloak) or of an empty Duyệt page. Rebuild after a UI change: edit the `.md` and rerun the build; the recipe is in this commit's message.

- 2026-10-26, layout from Đạt's look at the running portal:
    - **Home → "Việc cần làm".** Someone with `sales.case.read` landing on `/` is sent to `/sales`, the bar's first page; reverses 2026-10-20 (the board at `/`), because no menu item led back to it. The board stays under Hồ sơ → Pipeline hồ sơ.
    - **Board, one lane at a time** (`?lane=quote`, orders by default, the switch counts each lane); columns as tall as the window, each scrolling its own cards; a long tag wraps inside its card (`StatusTag`, `@dw/ui`).
    - **Lists scroll inside themselves** on `md` and up (`lib/use-fill-height.ts`, `scroll.y` from the window's remaining height): Việc cần làm, Hộp thư, Đơn hàng, Báo giá, Mẫu PO, Dữ liệu chủ, the rule versions, Duyệt, Nhật ký, Tri thức. Not yet: the case pages' line tables, Kiểm chéo & duyệt (two tables stacked), Hoạt động DW1.
    - **Rules for a PIC is by design** (`57a241ea182b`): `sales.rules.propose` on `sales_pic` and `sales_head`, `sales.rules.approve` on the head only, and the proposer never decides their own version. Whether a PIC should propose at all is Đạt's call (one migration).
    - Checked: vitest 613, tsc, lint; e2e `enduser-nav` and `platform-pages` updated for the new home and board, not yet re-run.

- 2026-10-24, web half of defects C, D, E and audit gaps 1–5, the browser-look list of 2026-10-24, and the master-data mismatch. Committed 2026-10-24 with the server half below. **Defects A–E closed**: the full run passed.
    - **Full run 2026-10-24:** integration dw_sales 192 (3 skipped, clamd), dw_platform 328, apps/api 165 (1 h 42 min); e2e platform-pages 3, enduser-nav 13, enduser-data 6, enduser-forms 12, enduser-race 7 (C, D, E now pass, no test.fail), sales-demo 13 + 2 skipped. Found and fixed: the process canvas dropped each card's measured size, so React Flow's fit never ran and "Xem cả quy trình" did nothing while the quote lane's last row sat outside the frame (`LaneViewport` fits from the lane's own layout; enduser-nav test 10 now checks every card and label is inside its frame); a rules-process vitest that read an antd field error synchronously.
    - **Open, found by the run (not caused by it):** sales-demo test 2 times out at 480 s on this machine (38/45 mails): each reader child spends ~4.1 s of ~4.5 s importing `dw_sales.adapters.reader_client` → `catalog_imports` → `dw_agent_runtime.approval_flow` → LangGraph — the reader child must not import the agent runtime (failure-mode #6 shape for time, and the mailbox throughput); 118 leftover `dw_knowledge_test_*`/`dw_memory_test_*` Qdrant collections that some test never deletes (failure-mode #6) make Qdrant take ~4 min to start; the "N giá trị chưa ai mở nguồn" panel also shows to the preparer before Bravo (long on a phone) — limit it to after Bravo? (Đạt); "DW1 chưa làm gì ở hồ sơ này" contradicts the history's "DW1 đọc và kiểm tra PO" when no model step ran; case history shows the raw "(accepted)" code; at 390 two card titles are cut by their extras; back edges remain dense.
    - **C.** The DW1 bar says "hết thư" only when done = total; otherwise "DW1 đang chờ: còn N thư chưa xử lý" (`sales-frame.tsx` `headline()`).
    - **D.** The bar's mailbox resource is published by `SalesFrameProvider` (`progress`); the inbox's "DW xử lý" / "DW xử lý tất cả" reload it after the press, so the bar moves to "sắp đọc / đang đọc" at once and starts polling. Chosen over sharing one resource with the inbox page: the bar's read waits for the overview and the inbox's does not, and five tests render case pages with `sales.case.read` but no mailbox.
    - **E.** A `stale_case_version` refusal on "Ghi giá" reads the quote again and shows, per line, the price now saved (who, when) beside what is being typed, which stays in the form, with "Dùng giá của tôi" (records again on the saved version) and "Giữ giá hiện có" (takes the saved price into the form). Any other refusal is drawn as before (`quotes/[caseId]/pricing.tsx`).
    - **Gaps:** `not_opened` is "Chưa mở nguồn" (warn tone, its own icon; `VALUE_LOOK` is now keyed by every glossary state, so a new one fails the typecheck) and is the weakest state after "uncertain" on a line row. RFQ "Xác nhận" is disabled per `source_not_served` with "Mở nguồn trước khi xác nhận…" beside it, and the quote is read again when a source drawer closes while any value waits on one (the server stays the owner). The quote has "Phạm vi đã đọc: …" from `coverage` (no N/N; warning while a model-read value is unconfirmed, `statements.ts` `quoteCoverageStatement`). The order shows the cross-checker "N giá trị chưa ai mở nguồn (trước khi nhập Bravo)" by line, each opening its source, only when `unopened_values` is non-empty (`orders/[caseId]/unopened-values.tsx`). On both case pages "Hành trình hồ sơ", "DW1 đã làm gì" and the replies moved below the flags, lines, files and changes (gap 3).
    - **Not done, on purpose:** `not_opened` regions are not added to `expectedRegions`: the server's `required_regions` owns which pages prepare and cross-check need, and a stricter copy in the browser would disable buttons the server allows.
    - **Process map:** new `_lib/process-geometry.ts` places a lane from `layoutLane`'s ranks, naming no status: columns wrap into bands of at most 5 (order and quote: two bands each, about 1.5k px wide, zoom ≈0.9 at 1440); a move between neighbours runs through the gap with its words in the gap's middle; every other move runs on a lane of a channel, forward under its band, back (dashed) over it; each card leaves and is entered on its own trunk at the gap's sides, and lane words slide away from other moves' trunks. `process-flow.tsx` draws those polylines and label boxes, fits the lane on load and when measured heights change it (min fit zoom 0.6), and sizes the canvas to the fitted height. A test computes the boxes for the served order and quote lanes (least and taller card heights): no label over a card or another label, no segment through a card, everything inside the canvas. Rendered to an image once to look at (scratch): clean, but the order lane is about 1,230 px tall at zoom 1, so at 1440 the page scrolls vertically past the canvas.
    - **Browser-look list:** (a) "DW1 đã làm gì" says a step's calls and time once per (message, step), on its first entry, "… cho cả thư (N mục của bước này)" when it covers several; grouped in the web, since the server's copy on every row is its documented contract. (b) The drawer splits "Điểm đạt đo trên bộ thử" from "Thực tế 7 ngày: DW1 tự xử lý X% số mục (a/b)" with "Đếm trên việc thật, không cùng thước với điểm đạt". (c) The drawer is a bottom sheet below `md`. (d) The feedback button joins the top bar's actions below `md` (web-ui.md); from `md` up it floats bottom-left as spec 003 US5 says, with room kept under the page. (e) `ProcessFlow` is loaded with `next/dynamic` (`ssr: false`), so a phone never downloads React Flow.
    - **Master data:** a reader reply that fails validation on an import now settles the snapshot `failed` with "không đọc được tệp: trình đọc tệp trả lời không khớp phiên bản…", audited by the lane as before, instead of raising for the outbox to retry (`catalog_imports.py` `_unread`, as `rule_drafts._unopened`).
    - **e2e updated, not run:** `enduser-race.spec.ts` C, D, E lose `test.fail` and assert the correct behaviour (C: the "đang chờ: còn N" headline; D: the bar without a reload; E: 0,689 beside "bạn đang nhập: 0,74", the typed value kept, both buttons); test 4 no longer reloads. `sales-demo.spec.ts` 10's headline regex takes "đang chờ: còn".
    - **Checked:** see web-ui.md 2026-10-24 for the web checks and mutations. Python: ruff, ruff format, mypy (682 files) clean; dw_sales unit + worker catalog consumer passed (about 1,940); the new import test, mutated twice (the `except` narrowed; the reason worded without the reader's sentence), each red, restored.
- 2026-10-24, defects A and B and audit UI gaps 1, 2, 4 and 5 (2026-10-21 entries below), server half. Committed 2026-10-24; the web half is the entry above.
    - **A.** A route's unhandled error is caught by `dw_api/middleware/unexpected_error.py`, the innermost middleware, so the 500 (same body: `code`, `message`, `request_id`) passes back through request-id and CORS. The `Exception` handler stays for an error a middleware raises; both render `exception_handlers.internal_error_response`. `test_cors.py`: allowed origin gets `access-control-allow-origin` on a 500, another origin does not.
    - **B.** A reader reply, or its result, that fails this process's wire models raises `ReaderMismatchError` (`DomainError`, 422, `reason_code: reader_version_mismatch`, logged by field location and error type, never a value) instead of a `ValidationError` 500 or a retried 503. A template draft then settles `failed` with "không mở được tệp mẫu: trình đọc tệp trả lời không khớp phiên bản…", audited as before, not retried.
    - **Gap 1.** A prepared value is `confirmed` only where its preparer was served its page or sheet (same file sha256) before `prepared_at`; otherwise the new value state `not_opened` (CONTEXT.md "Value states").
    - **Gap 2.** `QuoteFindingView.source_not_served`: the flagged values still to confirm whose source this caller has not opened at this version. It is the same fact the 409 uses (`source.value_unserved`).
    - **Gap 4.** `QuoteCaseView.coverage` (`QuoteCase.coverage`): lines read, regions ("page N", sheet, `message_text`), values a model read and how many are confirmed, findings. No "N/N": a request's reader counts no printed rows.
    - **Gap 5.** `OrderCaseView.unopened_values` lists `{field, line_no}` values whose page or sheet nobody was served before Bravo was recorded. Only a holder of `sales.order.cross_check` gets the list; everyone else gets null.
    - **Read from** `SourceServedPort.servings` (every serving of one case), no migration (the existing index leads with the case id).
    - **Web owed:** draw `not_opened`, disable "Xác nhận" per `source_not_served` with a reason, a quote coverage statement, show `unopened_values` to the cross-checker, and include `not_opened` in the regions `expectedRegions` asks the preparer to open, if wanted.
    - **Same shape, fixed in the entry above:** a master-data import (`CatalogParsing`) whose table reply mismatches raises the same `DomainError`; it is not caught there, so the outbox retries it until `max_attempts`.

- 2026-10-23, "Quy trình DW1" slices 2+3, web half (React Flow decided by Đạt the same day, CLAUDE.md "Web UI"). Committed 2026-10-24 with slices 2 and 3.
    - **n8n look (2026-10-24, Đạt; uncommitted):** each status is a compact tile (icon for whose turn: robot DW1, person, flag done; name; step codes; one AI line "AI bật · đạt / AI bật · chưa đạt / AI tắt", `AI_STATE_SHORT`) with visible handles where lines attach; whose turn, settings, ways back and exits moved to a popover on hover and keyboard focus (Esc closes; describes the link) and stay whole in the drawer. Lines keep `process-geometry.ts`'s routes, drawn with rounded bends and arrowheads, words in pills, back moves dashed; dotted background, minimap, horizontal controls in a strip under the lane. Tiles 168×≥88 (measured 90–122), gaps 148. Phone list unchanged. Checks in web-ui.md 2026-10-24 "n8n look".
    - **Calm re-cut (2026-10-24, Đạt: "đơn giản, sạch như n8n"; uncommitted):** the canvas draws the **main path** in one row, left to right, never wrapped (pans; opens at zoom 0.85 from its start; "Xem cả quy trình" fits all). Main path = the longest run of forward moves from the first status that never enters a **detour** (a status whose every way on goes back or out); a tie goes to the API's order (`process-graph.ts` `main`, tested and mutation-checked). Every other status sits on a row below: under the mean column of the row's statuses that move on to it (a detour hangs under where it starts), or one column past the last status that reaches it ("Đã đóng", "Từ chối báo giá"). Forward moves only by default: neighbours straight through the gap, a skip arched over the row, a branch down through the corridor. Switch "Hiện đường quay lại" (`?back=1`, replaced not pushed) adds the ways back (dashed arches over the row; from the row below, up through the corridor) and the exits (dashed, down the gap onto one rail per final status, "Đóng hồ sơ" once). Pills carry only the action; a guarded move gets one lock (antd `Button`, accessible name and `Tooltip` "Điều kiện: …"), guards whole in the drawer and the popover. Order lane: 7 on the row (Đã nhận → Đã xác nhận), Chờ khách sửa PO, Xem thay đổi PO and Đã đóng below; quote: 10 on the row, Thảo luận spec với khách, Bị trả lại định giá and Từ chối báo giá below. Checks in web-ui.md "Calm re-cut".
    - **Open from the browser look (2026-10-24):** ~~at 1440 the order map shows half its 10 states and back edges cross card labels~~ (closed by the calm re-cut: one row that pans, the ways back behind a switch, labels and lines tested clear); "DW1 đã làm gì" repeats a step's whole-mail timing on every line entry; "Điểm đạt" beside "Tự động 7 ngày qua" invites a false comparison (wording pinned in `rules-process.test.tsx`); the drawer opens from the right on phones where ui-quality §9 asks for a bottom sheet; the feedback button covers the O6 chip at 320/390; React Flow is not lazy-loaded, so phones download ~56 kB gz they never draw.
    - **`/sales/rules/process`:** on `lg` and up each lane is a React Flow canvas (`_components/process-flow.tsx`, the one file allowed `@xyflow/react` 12.12.0): cards on the rank columns of `process-graph.ts`, forward moves as arrows, moves back as dashed arches (over the first row, else under), every drawn move labelled with its action (`EDGE_ACTION`) and guard tags (`EDGE_GUARD`), aria-labelled with who takes it; exits into a final status stay words on it. Zoom/fit controls in Vietnamese, wheel scrolls the page, cards are real links (Tab, Enter, new tab), `?node=`/Back/focus return as slice 1. Each card says its model steps' state ("AI bật · đạt", "AI bật · chưa đạt — người làm", "AI tắt"). Below `lg` the list as before (ways back written). The drawer adds "AI ở bước này" (switch, bar, latest measurement or "Chưa đo", effective, 7-day share or "chưa có dữ liệu"; absent when the server sends no model steps), "Dữ liệu bước này dùng" (master-data tabs, Mẫu PO) and "Ai làm, ai duyệt" (roles/permission sets as served; `/admin` link for `platform.members.write`).
    - **Case pages:** "DW1 đã làm gì" under "Hành trình hồ sơ" on orders and quotes (`_components/case-activity.tsx`): per entry the step, result (Đã chấp nhận / Chuyển cho người / Model không trả lời), reason, values read with "Xem nguồn" opening the existing source drawer at the anchor, who took it over, model · prompt · time · calls.
    - **`/sales/activity` "Hoạt động DW1":** nav under Quản lý, `anyScope` overview.read or rules.propose (ScopeGate takes any-of); 7/30 days and lane in the URL; per step handled / automatic (+ share) / to a person / no answer / p50·p95 / top reasons; a count links to `/sales/orders|quotes?tab=all&…` with the server's filter once a lane is chosen (over both lanes a count is one number for two lists, so no link); a per-day table under each row. The order and quote lists read those params, pass them to the API and show "Lọc theo hoạt động DW1: …" with Xóa.
    - **Words:** `labels.ts` `EDGE_ACTION`, `EDGE_GUARD`, `MOVE_ACTOR`, `AI_STATE`, `ACTIVITY_*`; reason codes through `activity.ts` `reasonLabel` (exact tables, then `<field>_not_found|repeated|unparsed`, then a hand-off's field); `activity-labels.test.ts` holds every closed set to the OpenAPI snapshot and every reason code it finds in `dw_sales` sources (each pattern must still find codes).
    - **Checked:** see web-ui.md 2026-10-23 (tsc, lint, prettier, full vitest, mutations). **Run 2026-10-24:** e2e including `enduser-nav.spec.ts` 10 and 11a, all green; looked at in the browser (findings under "Open from the browser look").
- 2026-10-23, "Quy trình DW1" slice 3, AI activity ("DW1 đã làm gì"), server half, and the integration of slices 2–3. Committed 2026-10-24.
    - **Built (slice 3):**
        - **Rows:** `sales.step_outcomes` (`4bca401bcb3a`, after `2d97d03c937a`): one row per item a model step handled (a line for descriptions, the message otherwise), written by `InboxProcessing` in the transaction of the disposition and the case (`domain/activity.py` `outcomes_of`, derived from the stamps and the timed calls, `application/model_calls.py`). Ids, codes, counts and times only; CHECKs on step/result/lane and on the row saying what happened; tenant AND workspace RLS (offboarding shape); `dw_app` SELECT+INSERT, UPDATE/DELETE revoked; monthly partitions through `platform.ensure_time_partitions`, DEFAULT policed; FKs `ON DELETE CASCADE`.
        - **Reads:** `GET /sales/{orders|quotes}/{id}/activity` (`sales.case.read`; another workspace's case 404; a price field absent with its anchor without `sales.price.read`) and `GET /sales/activity` (`sales.overview.read` or `sales.rules.propose`; counts, top reasons, p50/p95, a series per local day; at most 31 days), each count carrying the case list filter it stands for.
        - **Retention:** `retention@1.9.0` gives `sales.step_outcomes` 365 days; the worker's `sales_step_outcomes_retention` lane drops whole expired months (`sales.drop_expired_step_outcomes`, SECURITY DEFINER, NULL drops nothing).
    - **Integration fixes (this session):**
        - **Live share on the process page:** each `models[]` entry carries `live_share` {handled, automatic, share|null, window_days 7}, read only after the order-rules gate, so it is absent (and not read) without `sales.price.read`. The ports moved to `application/activity_ports.py` (the activity service imports the process page; the reverse import was a cycle).
        - **No silent skip:** `step_activity` is a required member of `SalesUnitOfWork`; `record_outcomes` and `StepActivityUnitOfWork` are gone; the evals' `MemoryStore` keeps the rows per transaction (refusing a second write of a row) and reads them (`StepActivityReadPort`).
        - **Demo regression (slice 2):** `make demo-reset` installs `sales_order_rules@1.5.3` (`data/policies/no_model/`): 1.5.2 with all six steps off, every other rule the same (`test_order_rules.py` holds them equal), so the NOC/ESF hold and the tenant's price rule are back. 1.5.2 stays for the unit tests, evals and the API integration suite (over stand-in measurements). No measurement is seeded. demo.md, ADR 0005's addendum, the mock README and e2e 2b/11 comments updated.
        - **Drill-down:** `GET /sales/orders` and `/sales/quotes` take `step, handled_by, result, reason_code, lane, from, to` (a count's `ActivityFilter`, held equal by a test), checked after `sales.case.read`; half a filter, the other lane or more than 31 days is 422. Resolved through `sales.step_outcomes` under RLS (`StepRowFilter.matches` is the definition; the SQL is held to it), carried by the new `ix_step_outcomes_tenant_id_workspace_id_step_occurred_at` (added to `4bca401bcb3a`, uncommitted).
        - **Price leak, real:** the quote case view served the printed target price's anchor (its `quote` is the printed words) to a caller without `sales.price.read`, reachable today by FPT support (`sales.case_support`). The anchor is now absent; the amount stays marked hidden. The API suite's price search now knows the requests' target prices, so the support walks would have caught it.
    - **Decision Đạt owes:** the retention term of `sales.step_outcomes` (365 days in `retention@1.9.0`, proposed by the agent, not decided).
    - **Gap:** a message whose intent read had no usable answer inside `unread_retry_hours` stays not yet processed and writes nothing, so its retried calls leave no row: the activity page undercounts `model_unavailable` for `message_intent` until the retry ends in a disposition.
    - **Run 2026-10-24 (Docker on for the run, then off):** integration dw_sales 191 (3 skipped: no clamd), dw_platform 333, apps/api 162, all passed; e2e platform-pages 3, enduser-nav 13, enduser-data 6, enduser-forms 12, enduser-race 7 (C, D, E expected failures), sales-demo 13 (2 skipped, no model server). The first run failed every insert into `sales.step_outcomes`: the migration's `^[!-~]{1,512}$` CHECK exceeds PostgreSQL's 255 repetition cap (second time, failure-modes #4); fixed with `char_length`, with a test at the 512 bound. Fixed with it: three tests that compared the wrong way (stringified `details`, a CHECK named by the first violated constraint, a Decimal served as "0.65"), the stale `platform-pages.spec.ts:110`, enduser-nav test 10 accepting the empty activity state, and the AI section's layout below `sm`.
- 2026-10-23, a model step earns its switch (failure-mode #1 fixed; dw_sales ADR 0005, addendum of 2026-10-23, design approved by Đạt). Committed 2026-10-24.
    - **Built:**
        - **One owner for the bars:** `application/model_readiness.py` `BARS`, per `ModelStep` (domain, the six `model_assist` switches): bar, metric path in the golden grader's details, prompt, dataset, grader. The six eval modules read it (`bar_verdict`); `PROPOSED_BAR` is gone.
        - **Store:** `sales.model_step_measurements` (`2d97d03c937a`, after `e8192ed5cc59`): tenant-wide RLS (ENABLE+FORCE, the `rule_versions` shape), CHECKs on step, formats, 0..1, "a pass meets its bar"; `dw_app` SELECT+INSERT, UPDATE/DELETE revoked; not partitioned (a row per attested step).
        - **Writer:** `run_evals.py --live <profile> --attest --tenant <uuid> --workspace <uuid>`: lane `sales_model_attest` (`system:sales_model_attest`, audit in the same transaction), as dw_app under the tenant's RLS; refuses a BYPASSRLS role; records nothing when the run read nothing; passes only if the golden verdict and every case passed.
        - **Enforced:** `ModelStepGatePort.allows` before every model call (intent, reply, hand-off, layout pre-fill, descriptions, RFQ): on AND latest measurement for the current model (profile route, per tenant) and prompt version passed at today's bar; else the step runs as if off and logs why; unreadable = not ready. A version that turns a step on (on in it, off in force) gets 409 `model_bar_unmet` at propose and at decision; a settlement that finds it no longer ready records it rejected with why. Off, or kept on, is never refused.
        - **Process page:** per step `models` (switch, bar, metric, model, prompt, latest, effective; absent without `sales.price.read`), `uses` (`STEP_USES`), `actors` (`STEP_SCOPES` x the platform role/permission-set catalog via `RoleCatalogPort`); edges carry `action`, `actor`, `guards` (`EDGES`, held to `order_moves`/`quote_moves` by a test). `LockReason.MODEL_BAR_UNCHECKED` became `MODEL_BAR` with new words.
        - **Demo:** no measurement seeded. This first left tenant-alpha on the platform's rules after `make demo-reset` (1.5.2 refused), dropping its own rules; fixed the same day by 1.5.3 (below). The API integration suite seeds stand-ins through the lane's write path (`seed_test_measurements`) and keeps 1.5.2.
    - **Checked (2026-10-23):** ruff, ruff format, mypy (673 files), lint-imports (12 kept), verify_architecture, verify_invariants, contracts --check, release manifest --check, unit dw_sales 1915 + api/worker 619, eval smoke 10/10, web tsc/eslint/prettier and the 4 touched vitest files (33). Ten mutations, each red, each restored.
    - **Run 2026-10-24, passed:** integration `test_sales_model_measurements.py` (write+audit, RLS cross-tenant, no UPDATE/DELETE, CHECK, migration down/up), `test_sales_schema.py`, `test_privileges.py`, `test_rls_coverage.py`, and the API suite (`test_sales_api_rules.py` new 409 and process-page tests; every model-step test now runs on seeded stand-ins). Still not run: `--attest` against a live model.
    - **Open:** a tenant's own prompt wording under the same version is not told apart; the RFQ measurement names only its own prompt.
- 2026-10-22, "Quy trình DW1" (`/sales/rules/process`), slice 1. Đạt asked for a config page that draws DW1's process as nodes and edges, where a click opens that step's numbers, not hardcoded; the structure stays fixed for now.
    - **Decided by Đạt:**
        - drawn with antd and inline SVG, no diagram library;
        - one open proposal per rule key, refused on the server;
        - the page is for `sales.rules.propose` holders only, as `/sales/rules` is.
    - **Built:**
        - **Graph:** `GET /sales/rules/process` serves it from the domain's own transition tables (`order_moves()`, `quote_moves()`), with no second copy on the web.
        - **Step settings:** `application/process_settings.py` maps every `StepId` to the rule paths it reads, plus lane-wide and process-wide groups.
        - **Locked paths:** model_assist, design_mailboxes, working_hours.time_zone and intake are served as locked, each with a `LockReason`.
        - **Never placed:** `NOT_ON_PAGE` and `BASELINE_ONLY` list, with a reason each, what the page never places.
        - **Price:** price-bearing keys are absent for a caller without `sales.price.read`.
        - **Editing:** the drawer reuses the rules editor, limited to the step's fields. It proposes the whole document through the same propose → approve path.
    - **Guard:** migration `e8192ed5cc59` adds `uq_rule_versions_one_proposed` on `(tenant_id, key) WHERE status = 'proposed'`.
        - The 409 names who proposed the waiting version and when.
        - The upgrade stops on a proposal that has no approval.
        - Settlement now rejects a version whose number the platform shipped before it was applied, so the key is not blocked forever.
    - **Checked:**
        - unit 3535, integration 51 (rules, access, schema), contracts, web vitest 514;
        - security, correctness and UI reviews, with their findings fixed;
        - mutations on the settlement fix, the Back guard, the disabled "Gửi duyệt" and focus return, each turning a test red.
        - **Not yet:** a Playwright run and a look on the Docker build.
    - **Open:**
        - A proposal records no base version, so a stale form can still undo an approved one; the editor now reloads after a 409 to reduce this. This is the other half of decision 2.
        - The 409 does not name the other workspace.
        - Settlement still audits as the decider, not the lane (ADR 0011).
        - The order lane is about 1830 px wide and scrolls inside its frame at 1440.
    - **Slice 2:** an edge table with Vietnamese action and guard labels, step titles, and copy and templates on steps.
    - **Slice 3:**
        - move the RFQ required fields and the 12-month screening look-back into rules;
        - fix the intake binding, which reads the platform file at build time (`assembly.py:192-193`), so a tenant's version is likely unread: failure-mode #1;
        - give the time zone one owner (`order_checks.py:64` against `sales_followups`).
- 2026-10-22, DW2 (Mua hàng) readiness, audited with no code changed:
    - `new_context.py --name purchasing` wires 15 seams and passed every scaffold-smoke gate. It was run once in a throwaway clone, since removed.
    - **Left to do by hand:**
        - migrations, roles and permission sets;
        - configs, prompts and the eval dataset;
        - all web seams (nav, approvals host, badges, roles, api-client);
        - the `purchasing.` approval prefix and its `.decided` handler;
        - demo data.
    - **What blocks reuse:** the reader sandbox and malware scan import `dw_sales` (`apps/reader`), as do the rules editor, master-data import, pipeline, my-work and worker pause.
    - **Before DW2 starts,** decide whether to lift these to the platform (ADR 0004 `dw_evidence`) and whether to port DW01 from `C:\Users\phung\dw` or write it anew. The "30–51 công" line above and the 2026-10-21 "reuse only the ideas" talk disagree.
    - **Drift found:**
        - several files still call delivery/CDO "DW2" (`spec.md`, `dw_sales/CONTEXT.md:284`, `process.py:37`, tickets 02/06/21/33/35);
        - `PolicyOverridePort` is read by nothing;
        - CLAUDE.md says `@dw/ui` owns the case workspace, but it lives in `app/sales`;
        - `Makefile:161` says 13 seams, the script says 15.
- 2026-10-22, model comparison on the home lab: nine configurations in the Excel in Downloads.
    - **Candidates:** Gemma 4 12B with thinking off is the small candidate (6/6 bars). Gemma 4 26B-A4B and Qwen3.6-35B-A3B are the 24 GB candidates.
    - **Ruled out:** Nemotron 3.5 30B-A3B (4/6) and MiMo 9B (5/6, 6 invented RFQ values).
    - **Decision:** the switch from Qwen3.5-9B is still decided on Proterial's server with real data. Before it, check Gemma 4 12B's licence and its thinking switch on Ollama.
- 2026-10-21, end-user browser tests and `make web-screens` (Đạt: "test kiểu end user thôi"):
    - **Five new specs** under `apps/web/e2e/`, black box through the UI, each resetting the demo itself and run serially (shared database):
        - `enduser-forms` 12: input validation, double submit, cancel, close, decline, return, reassign;
        - `enduser-data` 6: master-data import, rules editor diff, "Tạo từ tệp mẫu", layouts, approvals, tenant IT;
        - `enduser-nav` 11: pipeline filters in the URL, Back, case history, viewer forbidden, 320 px, reload, keyboard, offline;
        - `enduser-race` 4 scenarios + 3 known-defect tests: pricing conflict, NOC/ESF hold, pause/resume, the DW1 bar;
        - `case-screens`: case pages per persona at wide-1440 and phone-320 (`DW_SCREENS_SETUP=1`, then `DW_SCREENS=1`).
    - **The first run was blind to its own stack** (failure-modes #0): the reader container was built 2026-10-20, before `text_unseen`, so every Excel source answered 500. Rebuilt; the three markers that blamed it are gone. Rebuild the reader with the API after a change to `dw_sales` the reader imports.
    - **Open defects, each a `test.fail` test that reports when fixed:**
        - C. Right after a reset the DW1 bar says "đã xử lý hết thư" at 0/45 (`sales-frame.tsx` `headline()`).
        - D. After "DW xử lý tất cả" the bar does not refresh until reload (`useWorkerProgress` polls only once its own fetch saw work: one fact, two resources).
        - E. A pricing conflict shows "hồ sơ đã thay đổi" but not the price the other person saved (ui-quality §4 "conflict").
    - **Open defects with no e2e test** (no black-box way to provoke them on a healthy stack):
        - A. A 500 leaves without CORS headers (`exception_handlers.py` runs in `ServerErrorMiddleware`, outside `CORSMiddleware`), so the UI shows "Mất kết nối mạng".
        - B. A reader reply that fails validation becomes a retried `ReaderUnavailableError` (500; a template draft keeps "Đang đọc tệp") instead of a worded refusal.
    - **Not a defect:** a resent identical PO (M08) opens its own case with `duplicate_po`, closed as duplicate (`order_checks.check_history`, issue 02). The board could say "PO trùng" on the card.
    - **Possible defect, unconfirmed:** on a quote at "Đã nhận", opening "Đã lập YCBG" while "Soạn YCBG" is still running closes the dialog when the latter finishes (`quotes/[caseId]/actions.tsx` `finish()` → `setDialog(null)`).
    - **Baseline:**
        - `sales-demo` passes stage 1. Stage 2 times out: 45 mails at about 13 reads a minute take about 9.5 minutes against an 8-minute budget (environment, not app).
        - `platform-pages.spec.ts:110` is stale: "Quản trị nền tảng" moved into the account dropdown's header (92b155a).
    - **Visual review of the 304 screenshots**, not yet fixed:
        - the floating chat button covers the first column on most pages, desktop and phone;
        - pipeline cards are 160–230 px tall, with 23 in one column and nine empty columns. The "Việc của bạn: …" tag overflows the card; on a phone the first screenful is two empty columns;
        - the inbox table is wider than 1440 and its rows are 70–95 px tall;
        - at 320 px the DW1 bar wraps to six lines, Segmented tabs are cut, and identifiers are clipped;
        - 28 admin/platform shots are an HTTP 429 page (seven navigations in 5 s), and that page says "không kết nối được" in English detail instead of "đang bận".

- 2026-10-21, decisions and owed work from Đạt's review (no code):
    - **HIGH PRIORITY, owed; decide once DW1 runs on Proterial's server.** Raise 9B's accuracy with code around the model, never with keyword tables or prompt examples fitted to the eval. The audit found every refused description line was a word left out (16), a span not in the text (5) or one span used twice (2); `single_candidate_wrong` is 0, so a higher score means less manual work, not fewer wrong codes. In order:
        1. A targeted second call on exactly the words the checks named, then the same checks; a still-unexplained word still goes to a person.
        2. 1–3 lines per call instead of 10.
        3. Load the Bravo convert list, so a listed line needs no model.
        4. Catalog retrieval (bge-m3), only to suggest codes for a person to pick.

        Measure each as a new prompt version on the same datasets, plus fresh unseen lines.

    - **Not ReAct.** No model-driven tool loop for reading customer documents: ADR 0007 forbids tools on document-content turns (injection), the 9B is slow per call, and the code checks are what keep wrong codes at 0. A read-only ReAct/deepagents agent stays a fit for staff Q&A over system data (questions come from staff, not from customer files).
    - **UI gaps from the same audit, not yet fixed:**
        1. Prepare relabels every unflagged value "Đã kiểm" (`views.py` ~497-502), though nobody opened them, and the cross-checker then trusts them.
        2. "Xác nhận" on RFQ values can be pressed before the source is opened, and the server then answers 409.
        3. Flags sit below the history.
        4. The quote page has no coverage statement.
        5. Show the cross-checker which values nobody opened.
    - **Channels.** Portal first. Teams preferred over Zalo, through a Teams bot whose inbound goes Azure Bot → an Azure Function queue that the plant server polls outbound. No domain, certificate or inbound port is needed. Proterial's IT owes an Entra app registration, approval of the Teams app, an Azure subscription and outbound 443.
    - **Out of scope for now.** NOEC and ESF drafting (WIV-03-032 steps 4–6) wait for a survey; the contract wording should say so. CDO is not built (a later DW).
    - **Model.** Stay on Qwen3.5-9B. Candidates, measured on our eval sets before any switch: Qwen3.8-27B or Gemma 4 31B (24–48 GB), Gemma 4 12B (8 GB).
    - **Flaky test.** `rule-drafts.test.tsx` "uploads a template, polls…" failed once under the full parallel vitest run on a loaded machine and passed alone 11/11.

- 2026-10-21, "Tạo từ tệp mẫu", phase 1 (Bravo upload template only; the email, document and hand-off copy are phase 2):
    - **Flow.** In the rules editor, for `sales_bravo_upload`, "Tạo từ tệp mẫu" uploads the company's Excel template.
        - `POST /sales/rules/{key}/drafts` answers 202; `GET /sales/rules/drafts/{id}` reads the draft. Both need `sales.rules.propose`.
        - A key outside `rules.DRAFTABLE` is refused with 422, so are a non-.xlsx/.xls file and one over 2 MB. Another tenant or workspace gets 404.
        - The editor polls every 3 s, then opens the draft as start option `draft:<id>`. Values the machine filled carry the "Máy đọc" chip and "Đọc từ Sheet!C3" until edited. An Alert lists the template columns no field takes and why a mapping was refused.
        - The diff and "Gửi duyệt" are unchanged: `POST /rules/{key}/versions` is still the only write path for a version, and the head approves as before.
    - **Worker** (`sales.rule_draft.requested` → `RuleDrafting`, lane audit `system:sales_rule_drafts`): scans the file, opens it through the reader (`ClientSourceView`), takes the first visible sheet with a row of at least 4 visible text cells, and drops hidden rows, columns and same-colour text first.
        - The model is asked under `sales.bravo_template_mapping@1.0.0` through the one-call door: the new `WorkflowRuntime.one_call` carries the runner's own plan rule, and is passed only where an on-prem model is configured.
        - The call runs as the asker, resolved again now. Someone who lost `sales.rules.propose` gets `failed`.
        - Code accepts a mapping only when every header is exactly one visible cell, no column serves two fields, PO/line/item/quantity are named, columns keep the template's order and the result passes `BravoUploadLayout`.
        - Statuses: `ready`; `refused` (fields named); `unavailable` (model down, not configured, or plan day spent); `failed` (with the reason). The file's bytes are deleted once read.
        - refused and unavailable still open: the version in force with only the template's sheet name, columns not guessed, the template's headers offered as AutoComplete choices.
    - **Storage.** `42868d8c21c5`: `sales.rule_drafts` and `sales.rule_draft_files`, RLS ENABLE+FORCE in the workspace shape, CHECKs on status, key, document and error. `dw_app` holds no UPDATE on the files.
        - A request prunes the workspace's drafts older than 30 days, and so does the worker's sweep (review fixes).
        - Found by the CHECK on the first run: JSONB `None` is written as JSON `null` unless the column says `none_as_null`.
    - **Checked.**
        - Unit: `test_rule_drafts.py` 35, the worker consumer 2, the one-call door 1, routes 3.
        - Integration: `test_sales_rule_drafts.py` 5, plus schema, privileges and RLS coverage.
        - Eval `sales_rule_drafts@1.0.0`: 5/5 with full security coverage. The smoke scripts the right mapping (no live reading recorded yet). Whole smoke passes.
        - Web: `rule-drafts.test.tsx` 8, tsc, lint, prettier.
        - Mutations, each turning a test red: verbatim header match loosened; hidden-cell filter removed (2 unit tests and the injection eval); RLS removed from the migration (2 isolation tests); the asker's scope re-check removed; the service gate removed; the door given its own plan service; the "Máy đọc" chip kept after an edit.
    - **Review fixes (same day).**
        - Unseen text: the reader sets `SheetCell.text_unseen` (`excel.text_unseen`): font the colour of its fill, white on a cell with no solid fill (ARGB, theme 0 / lt1, indexed 1 or 9), or 2pt and smaller. The template's header row drops it, and so does `text_parts` (what a model reads of an attachment). White on a dark fill stays visible. New eval case `sales-rule-draft-sec-unseen-text` (grader `sales.rule_draft_unseen_text`).
        - Headers are compared NFC without surrounding spaces, and the document holds the cell's own text so. A header over 64 characters is refused as `header_too_long` with its cell; the 64 now has one owner, `artifact_content.UPLOAD_HEADER_MAX`.
        - Web: the poll stops on an error answer (shown in the editor's error) and gives up after 3 minutes with "DW1 chưa đọc xong tệp mẫu, hãy thử tải lại sau."; the upload button is offered again; an earlier draft stays a start option while a second template is read.
        - Lifecycle: the worker lane `sales_rule_drafts` (every 10 minutes) visits each workspace `sales.rule_draft_scopes_due` names (SECURITY DEFINER, migration `e8a1c3e8ed78`, EXECUTE to `dw_app` only) and, in that workspace's RLS, fails a draft still queued after 1 hour (`STALE_AFTER`, file dropped, lane audit) and drops drafts older than 30 days.
        - `test_live_lane.py` now lists `sales_rule_drafts@1.0.0` among the model steps (it was red since phase 1).
    - **Open.**
        - No live measurement on Qwen3.5-9B yet (`--live onprem` on the dataset).
        - A layout cannot hold a blank template column, so unmapped columns are only listed.
        - A version proposed from a draft does not record that it was machine-drafted (the approver sees the diff only).
        - Drafts are not listed: closing the drawer loses the link to one.
        - `KEPT_FOR` (30 days) and `STALE_AFTER` (1 hour) are code constants in `rule_drafts.py`, not terms of `retention@*.yaml`; the drop of an old draft is not audited (its request and outcome are).
        - A PO value white on no fill or 2pt is still read without a `RegionFlag` (`excel.flags` checks only `font_matches_fill`), and the source viewer's grid does not mark `text_unseen` cells.
        - `sales_rule_drafts@1.0.0` gained a case in place (unreleased, local commits only), so the manifest pins new checksums under the same version.
- 2026-10-21, contract acceptance row 3 made provable ("100% test cases
  that do not meet export-control conditions are held awaiting approval,
  never automatically confirmed"). The hold already existed: `OrderCase.confirm`
  refuses while `missing_noc_esf` is open, and only a holder of
  `sales.compliance.ack` accepts it, with a reason (mode `warn`, kept; Đạt).
  What changed: `missing_noc_esf` is `error` (blocking) in platform rules
  `sales_order_rules@1.6.0` and the demo tenant's `1.5.2` (replaces `1.5.1`,
  `make demo-reset` installs it), so the order reads "chặn" in the list and
  on the case; the order page shows "Đơn đang bị giữ: chờ PIC kiểm soát xuất
  khẩu xác nhận NOC/ESF." while the finding is open; the rules form says
  `warn` is "Giữ xác nhận cho tới khi PIC kiểm soát xuất khẩu chấp nhận".
  Evidence: `test_export_control_hold.py` walks every README scenario whose
  findings include `missing_noc_esf` (read from the table, today M03, M28,
  M35, M45) to the step before confirm through the real services: refused
  until accepted, then confirmed; the API test walks M03 to a 409 on
  `/confirm` with version and status unchanged, then 200 after acceptance; a
  revision re-opens the hold (`test_orders.py`). Mutations: confirm refusal
  deleted, `_compliance_finding` returning None, tenant severity `warning`,
  and the page's condition each turned a test red. Cases checked before keep
  their stamped `warning` severity; the hold applies to them all the same.
  Options left open, not decided: a second person for the export-control
  acceptance (Proterial's survey says the same Sales PIC does export control,
  so no separation now); moving the hold before the Bravo entry (Đạt: no);
  the denial list stays a screening date on the customer, not a screening
  DW1 runs. Review follow-up: the page and the confirm button read one
  helper, `exportControlHold` in `order-actions.ts` (`awaiting_ack` or
  `blocked_by_rule`, the case's stamped `block_confirmation`, which the page
  now names in the rule's words); the notice uses antd's own warning icon,
  not the padlock that means masked prices. Mutations: the helper ignoring
  `block_confirmation`, holding closed cases, and the page drawing one wording
  for both each turned `export-control-hold.test.tsx` red.

- 2026-10-21:
    - **IT proposes rules, the head approves** (decided by Đạt; dw_sales ADR 0003 addendum):
        - Permission set `sales_rules_editor` = `{sales.rules.propose}` (migration `59cf23d3a859`); the seed gives it to `dev|tam.ngo` (org_admin). `org_admin` itself still holds no `sales.*` scope.
        - Price keys fail closed: `PRICE_BEARING` = `sales_pricing`, `sales_quote_rules`, `sales_order_rules` (in `rules.py`, beside `OVERRIDABLE`) also asks for `sales.price.read`. Without it, `GET /rules` leaves those keys out entirely (in force, layers, platform, versions), and their schema, platform documents and proposals answer 403. The web draws only the keys it is given.
        - `sales_order_rules` is price-bearing since the review of 2026-10-21: it holds price policy (`price.relative_tolerance`, the LME rule, which ADR 0003 names confidential). So IT cannot read or propose the order rules; it proposes KPI, copy, the Bravo upload template, hand-offs and follow-ups. Failed closed; relaxing it is Đạt's call and one entry in `PRICE_BEARING`.
        - Non-waivable SoD rule `sod_sales_rules_approve_vs_member_admin` (`platform.members.write` vs `sales.rules.approve`). The insert trigger from `d82a60870baf` checks existing memberships.
        - Tests: `test_rules.py` (unit; also IT holding `approvals.decide` after self-granting `sales_quote_approver`: refused on its own version, and on another proposer's, whose stamped approval it is not even served, so not found), `test_sales_api_rules.py` (Tâm proposes `sales_bravo_upload`, his decision 403, Giang approves; 403 and nothing listed on the three price keys), `test_sales_api_access.py` (Tâm reaches exactly the four rules routes of `sales_bravo_upload`), `test_sales_api_prices.py` (the G2 walk also reads `/rules` and each listed key's schema and platform documents; it also seeds a tenant `sales_pricing@9.0.1` proposal whose `floor_margin` is the known price 0.6890; An's `/rules` shows it (control), so with `PRICE_BEARING` emptied Tâm's walk goes red, d16c6fa), `test_sales_roles.py`, `test_sales_personas.py`, `nav.test.ts`, `rules.test.tsx`.
        - Mutations: with the price check removed, the unit and API tests went red; with the SoD insert removed, `test_it_cannot_also_approve_rules` went red; with `sales_order_rules` taken out of `PRICE_BEARING`, the unit IT test and the API price-key test went red. Downgrade and upgrade round-trip clean.
        - **Owed by Đạt (noted, not fixed):** `admin_console.py` refuses only `platform.*` scopes on a permission-set grant, so tenant IT can already give itself `sales_quote_approver` (no price scope, so no SoD rule stops it). Whether IT may grant `sales_*` sets at all is Đạt's call. **Decided 2026-10-25 (Đạt):** yes, every business role and set, price included, never an administrative one; the members screen now offers the catalog's roles (`platform-runtime/member-sign-in-accounts/spec.md`).
    - **DW1 bar.** It names what DW1 does: reading "<subject>", N waiting, all done and waiting for new mail, or paused. Never a bare "đang chạy" (`worker-bar.test.tsx`).
    - **Contract.** Đạt asked how the contract's acceptance bars and hardware should read against the measured Qwen3.5-9B figures. The advice was given in the session and kept out of the repo, which is public:
        - define the test set and that routing to a person is not an error;
        - split digital and scanned POs;
        - every new PRV code confirmed by Sales (descriptions measure 71%);
        - Q&A only over agreed question types (not measured; Teams needs internet);
        - one shared server: L4 24 GB or a 32 GB card, 64 GB RAM, RAID1 NVMe, internal backup disks plus a daily off-machine copy.

- 2026-10-20, "does the AI follow the template?" (Đạt), answered from the code and checked:
    - **No rule document reaches a prompt.** All nine keys are applied by code: email, document and hand-off copy by `string.Template` / `str.format`, the Bravo file by the upload layout plus openpyxl, and thresholds read as numbers. The model only reads incoming mail (spans); code verifies the spans and fills the tenant's template.
    - **Config → output tests.** The existing ones cover emails and hand-offs. New: `test_a_bravo_upload_follows_the_tenants_own_template` checks sheet, columns, order and headers, and that a template missing PO/line/item/quantity is refused at validation.
    - **Live eval on the host's qwen3.5-9b-dw: `sales_handoff` PASS.**
        - 33 mails, 73 fields: 94.5% right, 0 invented.
        - By language: vi 100%, en 96.2%, ja 86.4%.
        - 12.1% go to a person.
        - Injection cases: nothing followed.
        - Latency: p50 22 s, max 154 s on the first load.
    - **Docker stack with the model.** `api` and `worker` point at the host's Ollama through an override kept outside the repo (scratchpad `compose.host-model.yml`); `make demo-reset`, then the inbox lane processed the mailbox with the model.
    - **UI (Đạt: banner too big, text still large, less scrolling).**
        - The DW1 bar is one line: state, who paused and why, the mail being read, done/total, queued, failed. It is polled every 5 s while busy; the explanation sits in an info icon.
        - Body text is 13px, small text pinned at 12px.
        - Page header: tighter, 16px title, 12px subtitle and breadcrumb.

- 2026-10-20, the rules editor made plainer (Đạt: "Biểu mẫu và JSON nâng
  cao nhìn phức tạp ... người cấu hình sẽ mệt"; the configurator is
  **Proterial's IT**):
    - **Step 1, done.**
        - `schema_version`, `policy_id` and `copy_id` are kept in the document but not drawn (`SYSTEM_FIELDS`).
        - The version's own fields (number, mock, note) come last under "Phiên bản" (`VERSION_FIELDS`).
        - The note starts empty for a new proposal and is labelled "Ghi chú thay đổi".
        - Template values carry Vietnamese names and a copy button (`PLACEHOLDER`).
        - The JSON tab stays for IT.
        - Tests: `rule-form.test.tsx` +2; a mutation drawing the system fields again turns one red.
    - **Step 2, decided, not built: "Tạo từ tệp mẫu".**
        - The rule keys covered: the Bravo upload template (from the Excel template's header row), and the email, document and hand-off copy (from a sample the company sends).
        - The file is read in `reader` and queued for the worker. The model proposes a version into the same form, every machine-read value is flagged, and the diff and approval stay as they are.
        - The price, KPI and follow-up rules get suggestions only.
        - It needs an eval with a prompt-injection case in the uploaded file.
    - **OCR.**
        - Templates are born-digital, so `reader` already extracts them without a model.
        - Scans use the Tesseract (vie) already in `reader`.
        - EasyOCR and docling were not added: PyTorch would grow the image by GBs and compete for the GPU with Ollama. Measure Tesseract on Proterial's real scans first; Japanese would need `tesseract-ocr-jpn`.
    - **Owed by Đạt.** IT configures, but `sales.rules.propose` sits on the Sales roles only (`tam.ngo`, tenant IT, holds no `sales.*` scope). Decide whether to grant IT a permission set with `rules.propose`, keeping approval with the Sales head.

- 2026-10-20, the pipeline (Đạt: "UI mà thành từng tab ... k thành 1 cái
  pipeline", then "làm thẳng luôn pipeline", each role its own view):
    - **Board.** `GET /sales/pipeline` (`application/pipeline.py`, `sales.case.read`, no support context):
        - one column per status in the enum's order, each with whose turn it is (`STATUS_BUCKETS`) and its WIV steps;
        - one card per case with its reference, assignee, when it entered its status (the follow-ups' `_entered`), due date and flags;
        - `my_action` is the caller's next step, read from `my_work`, so a role differs by reading, not by a second rule;
        - done cases show for 7 days, then are only counted.
    - **History.** `GET /sales/{orders,quotes}/{id}/history`: the case's events, oldest first (`OverviewReadPort.history`, SQL and in-memory). Another tenant's case answers 404.
    - **Web.**
        - `/sales/pipeline` and the home page (`/`) for anyone with `sales.case.read`: two lanes, "Tất cả / Việc của tôi", search;
        - the order and quote pages gain "Hành trình hồ sơ": the statuses the case passed through, and every event with who did it;
        - nav: "Pipeline hồ sơ" under "Hồ sơ".
    - **Denser theme** (`@dw/ui`): controls 28px, `sizeStep` 3, a 48px bar, 20px page titles, tighter page padding; text stays 14/12px.
    - **Checked.**
        - Integration: `test_sales_api_pipeline.py` 5/5, plus overview;
        - mutations: removing the history's existence check turns the cross-tenant test red (200 vs 404), and removing the "mine" filter turns its vitest red;
        - web: vitest 420, tsc.
    - **Open.**
        - Not looked at on a rendered page by anyone yet; `make web-screens` is owed for the pipeline.
        - Viewers (`sales_viewer`) still get the overview, not the board.
        - Production build in Docker (`make docker-up`) was started for Đạt to view at localhost:3300.

- 2026-10-19, local Docker, tests and the on-premises models (Đạt: "chạy
  test full ... chạy docker lên test"):
    - **Without Docker:** lint, mypy, import contracts, invariants, the manifest and the contracts all pass. Unit tests: 3430 pass. Web: 466/466 vitest, plus typecheck, lint and format.
    - **Integration.** One 2-hour run on a loaded machine gave 766 pass, 53 fail and 84 errors. Per file and per package, everything passes except two real defects:
        - `dw_app` held UPDATE on three append-only tables (tickets 41 and 42); fixed by `89bcd0d49ea6`.
        - The two Sales route walks lacked tickets 41's path parameters.
          The rest were load: Qdrant timing out while images built, docgen's toolchain check run right after its fork bomb, and `DW_DOCGEN_URL` defaulting to 8110 where this machine maps 38110.
    - **Live evals on `qwen3.5-9b-dw`.** Six datasets PASS:
        - RFQ 94.9%, with **one invented value**;
        - layout 97.7%;
        - reply 97.8%;
        - hand-off 94.5%;
        - intent 89.8%, **below** the 90% bar the agent proposed;
        - descriptions VI/EN 71.1%.
          The container's Ollama 0.34.4 matched the host's 0.40.4.
    - **The on-premises compose files ran for the first time,** in the `local` profile: rerank, bge-m3 and chat, each through the API's own builders. Findings are in `infra/onprem/README.md`.
    - **Scope.** Which DW1 feature Proterial's process asks for, which the platform requires, and which we added: `sales/dw1-scope.md`.
    - **`PUBLIC_REPO_DENYLIST`** is set: the GitHub secret, plus `DW_PUBLIC_REPO_DENYLIST` on Đạt's machine, from the Sales survey and the proposal decks. The list has no customer names yet, because no real Proterial data has arrived.

- 2026-10-19, ticket 41 built (Đạt's goal of 2026-10-18: master data is
  loaded by business users, not hard-coded): customers, items, convert list,
  quotations and LME are imported per list from Excel/CSV on
  `/sales/master-data`, read by the worker in the reader sandbox, previewed
  as a diff with rejected rows, submitted on a stamped `sales.catalog`
  approval the head decides on `/approvals`; an approved snapshot replaces
  the mock for that list (migration `511ef1b71dee`). Bravo orders and open
  YCBG stay on the mock until the ERP adapter. Owed on Docker: the
  integration tests and the migration round trip (ticket 41).

- 2026-10-15, batch merge (agent; Đạt: "còn task nào và ticket nào còn
  sót lại không làm luôn đi"): every open Sales, platform and CI item that
  needed no decision of Đạt's was taken up in eight batches, each reviewed
  and its findings fixed, and merged on `main` from `0bc1395` (`b2ea975` ..
  `57d3c20`). Two are partial (`web-ui.md`: the support routes'
  Idempotency-Key; offline on ten platform screens). Each ticket records its
  part; choices the agents made read "decided by the agent 2026-10-15 (Đạt:
  làm luôn)".
    - **Sales.** Processing's audit rows name the run (10); a pause whose
      notification fails still answers (05); My work offers `confirm` when
      no cross-check is needed (14); a correction re-checks the PO's
      history, the price lock reads the server, corrected values show as
      entered (15); the mailbox lane's channel, `service|` subjects refused
      at sign-in, DW1's account provisioned with every new tenant, its row
      in the job's transaction (16); KPI keys a closed set (37); a version
      shows its decider's reason, `/sales/rules` proposes (38); the inbox
      links an intent's PO to its case (31); the picker compares with what
      DW1 read (08); orders are due on their short-LT date (24); one file
      of a kind per version, orphans removed (06); a model-read quote value
      waits for its source to be served (29); rich-text fonts read, legacy
      RFQ values refused (20); the live lane fails when nothing was read
      (28); eval-only M92, `sales@1.3.0` (13 cases); refusals in
      Vietnamese by rule code; the walk visits a reply, the layouts page, a
      hand-off draft and a rule decision (step 11).
    - **Platform, web and CI.** In `platform-runtime.md`, `web-ui.md`,
      `ops-hardening.md` and `channels.md`. Migrations `1a8fd934194f`,
      `2dd12f5b9c88`, `358bfa9b231f`, `546a6a81e58c`, `2e0354b50d10`,
      `d82a60870baf`, `0d8f03566652`, `271bdb87af91`; re-chained at merge
      (`2dd12f5b9c88` on `1a8fd934194f`, `2e0354b50d10` on
      `546a6a81e58c`), one head `271bdb87af91`.
    - **Verified (no Docker).** Contracts, API types and the release
      manifest regenerated; ruff, mypy (637 files), lint-imports 12/12,
      verify_invariants, manifest `--check`, web typecheck, lint, format,
      416 vitest, eval smoke 9/9; the full unit suite green.
    - **Owed to CI/Docker.** Every integration test the batches wrote, the
      eight migrations' round trips and mutation runs (listed per ticket),
      the walk with its new steps, promtool, the pinned images with trivy,
      the worker image rebuild, the Đ-after-D collation on Postgres 16.15, a
      real Keycloak expiry, `make web-screens`. The walk is blocking since
      2026-10-15 (ticket 18: six consecutive green `sales-walk` jobs).
    - **CI on `9bbce15` (pushed before Đạt's "no pushes").** Green but for
      three: the artifacts' new unique keys did not lead with tenant and
      workspace; a lane test read DW1's account through sign-in, which ticket
      16 now refuses; the walk passed 13/13 and then setup-uv's cache prune
      waited on the still-running worker. Fixed locally in `fac68c8`, not
      pushed: they run again at the next push or on local Docker.
    - **Owed to Đạt.** The ClamAV bump's
      Actions setting (ticket 25); the `PUBLIC_REPO_DENYLIST` secret (ticket
      26); the Open items below dated 2026-10-15.

- 2026-10-15 (Đạt: "làm luôn mục 1–3, 5, 6"): `legacy_text_anchor` no
  longer hands a price's anchor to a viewer who may not see amounts (tickets
  20/22, `953086f`); the API integration price scan looks for VND prices
  and every printed grouping (ticket 34); offboarding exports and purges
  each row of a partitioned table once (platform, owed upstream); the plan
  statuses and `demo.md` brought up to date; and a race found on the way:
  the demo seed and the worker both carried out the seed's `sales.rules`
  decision, and the loser failed `make demo-reset` in CI run 38545009082
  (`9704778`: a settlement that loses the race finds the decision applied).

- 2026-10-14, Đạt's decisions (afternoon): dw_sales ADRs 0004 (with both
  amendments) and 0005 (with its addenda) **Accepted**; the bars of tickets
  29–33 kept as proposed; every released rules version kept readable
  (ticket 37); rule versions decided on the platform's approvals (ticket
  38); ticket 28 with thinking on measured: unusable on this card. Built by
  the agent:
    - **37.** The rule book holds every platform version the checkout ships
      (`TenantRuleBook.released`); a version written before a field of its
      schema existed reads it as the platform's current version has it
      (`read_over`), tenant versions included (the next required field
      would otherwise have stopped DW1 for every tenant with its own
      version). A stamp asks the tenant first. A file any release manifest
      pinned is never edited or deleted (test over `contracts/release`); the
      two deleted 1.0.0 files are restored byte for byte.
    - **38.** Proposing a version opens a run-less `sales.rules` approval
      (migration `218118b8f0e5`); `RuleDecisions` guards it, the worker
      carries out `sales.rules.decided` (`RuleSettlement`), `/approvals`
      decides it in place; the Sales decision route is gone, and the
      "no Sales route decides" test, which could not see a `/decision`
      suffix, now does. Integration tests rewritten, owed while Docker is
      down.

- 2026-10-14, CI on 1621cbc: every job green (integration incl. the
  processing queue, the reader image with LibreOffice and Tesseract, tickets
  35/36; container build and trivy; the DW1 browser walk in 13m38s) except
  the public-repo guard, which fails by design until Đạt creates the
  PUBLIC_REPO_DENYLIST secret (the repo has no secrets at all). The first
  CI run of tests written while Docker was down found a regex repetition
  over 255 in a CHECK, an unquoted .env.example value, OCR labels losing
  their diacritics (now matched without accents on OCR pages) and five
  stale tests. Still local-only after a reboot (WSL hung since 2026-10-13):
  measure_reader timings for ticket 27 and the support-access 03 walk.

- 2026-10-14, tickets 25 and 27 built, pending measurement (agent; Đạt
  decided "DW xử lý" asynchronous, the agent took the ticket's recommended
  reader container while he was away; "As built", Comments and "Post-reboot
  checks" in each ticket):
    - **25.** "DW xử lý" and "DW xử lý tất cả" answer 202 with a job per
      message (`sales.processing_jobs`, migration `0a78ca5e96d3`, parented
      on 36's `26a5276840ba`); the worker's `sales_processing` lane runs
      each as whoever asked, re-resolved and cut to `sales.inbox.process`,
      through `Dw1Runs.process` (quota, pause, key unchanged); the reaper
      settles a dead worker's job; the mailbox lane queues through the same
      door. Every file is read in the `reader` container (`apps/reader`,
      no network, one throwaway process per request under docgen's runner,
      reached over a Unix socket); the API imports no reader. The inbox
      shows each job's state and polls while any runs.
    - **27.** In that container: `.xls`→`.xlsx` and `.doc`→PDF by
      LibreOffice (fresh profile, macros disabled), anchors carrying both
      hashes and the PO its converter; a scanned page OCRed by Tesseract
      (`vie+eng`), every value flagged `ocr` (`value_uncertain`). A tool
      failure routes the message with the reason. No `.xls` is committed
      (the public-repo guard cannot read one); the scan fixture and its OCR
      truth are generated.
    - **Verified (no Docker).** ruff, mypy (627 files), lint-imports 12/12
      (the new "API imports no reader" contract included), verify_architecture,
      verify_invariants, release manifest and contracts current; unit 3,108
      passed, 3 skipped; eval smoke all PASS (`sales_legacy@1.0.0` 6/6); web
      typecheck, lint, 350 vitest, prettier. 36 mutations, all red (the
      reader's body cap first survived and got two tests).
    - **Owed after the reboot**: `scripts/measure_reader.py`, the image's
      size and socket, the full stack's "DW xử lý" (ticket 25 "Post-reboot
      checks" 1, 3 and 7) and ticket 27's macro fixture (ticket 27's checks
      after them). The image build, trivy (`dw-reader` included), the
      image suite, migration `0a78ca5e96d3`, the integration suites and the
      full profile's compose smoke ran green on CI (run 38545008947 on
      `99cb905`), and the walk with a worker on the Web E2E workflow (run
      38548179383 on `a89ca01`).

- 2026-10-14, tickets 35 and 36 triaged and done (agent, Đạt away, on his
  ask of 2026-10-14; committed in `8adbe08`; Triage, "As built", "Owed" in
  each ticket):
    - **35.** A split line is confirmed per schedule (decided by the agent:
      one date per schedule, the recommended default): `OrderLine` holds a
      date per delivery, the route takes `schedule_dates`, the draft
      (`sales_emails@1.2.0`) and the portal checklist list each schedule,
      the drawer asks per schedule. Migration `b2afb906fbf2` (`date[]`
      replaces the one-date column, backfilled).
    - **36.** Quote rules, pricing, e-mail and document copy, the Bravo
      upload template and the hand-off copy resolve per tenant through the
      rule book, ticket 19's routes unchanged (ADR 0004 option noted); a
      quote case's later steps read its stamped rules, files of one case
      version the copy the first stamped. Hand-off placeholders and e-mail
      subjects are validated before a tenant can propose them. Migration
      `26a5276840ba` (eight keys; the document check no longer passes a
      NULL comparison).
    - **Verified (no Docker).** ruff, mypy (619 files), lint-imports 12/12,
      verify_architecture, verify_invariants, release manifest and
      contracts current; unit 3,074 passed, 3 skipped (one collection error
      in ticket 25's worker test, in progress in parallel); eval smoke all
      PASS; web typecheck, lint, 346 vitest. 19 mutations, all red.
    - **Owed after the reboot.** The two migration round trips and their
      scratch-database mutations listed under "Owed" in tickets 35 and 36;
      their integration runs are green on CI (run 38545008947 on `99cb905`).

- 2026-10-13, CI on 399920d: 6 of 7 jobs green (unit, evals, frontend with
  vitest, integration, container build, scaffold-smoke). The public-repo
  guard fails by design until Đạt creates the PUBLIC_REPO_DENYLIST secret.
  The DW1 browser walk on CI passed on e97042b and failed on 399920d at step
  2: it pinned "DW xử lý tất cả (42)" while 44 were left after M44/M45;
  the click is now count-agnostic. Local integration and the support-access
  03 walk wait on a reboot (WSL hung at 22:01, needs admin).

- 2026-10-13, ticket 25 needs-info, 27 needs-info (agent, Đạt away; "As
  built" and Comments in each ticket):
    - **25, built.** Every attachment is scanned by ClamAV before anything
      reads it (`ScannedInbox` in `build_dw1`), then held to its name: an
      infected one routes its message `malware_detected` unread and audited
      (ids and signature), a scanner that cannot answer leaves it not yet
      processed (503 "chưa quét được, thử lại"), a renamed program or an
      encrypted Office file is refused unread; every reader call has a wall
      clock. Compose `clamav` (`clamav/clamav:1.5.4` by digest, own internal
      network `dw-scan`, read-only, no capabilities, 947 MiB resident, trivy
      0 HIGH/CRITICAL); EICAR caught by the real clamd; CI starts it.
      Migration `13c687788955`. `DW_SALES_MALWARE_SCAN=skip` for a host-run
      local API only (refused where a deployed process reads a mailbox).
    - **25, owed.** Acceptance 5, parsing in a sandbox: which one (docgen, or
      a reader container of its own) and whether "DW xử lý" may become
      asynchronous. The integration suites it touches were running when
      Docker's WSL VM died, and are owed.
    - **27.** Not started: it runs in 25's sandbox, and the measurements need
      Docker. `WslService` is stuck in StopPending; restarting it needs an
      administrator. Ollama was not touched.
- 2026-10-13, tickets 23 (review), 24 and 19 done (agent, Đạt away;
  committed in `399920d`; Comments and "As built" in each ticket):
    - **23.** The review found the end-to-end test asserting that no model
      was called, since 28-33 made DW1 call one; a new test runs M36's
      description reading on the real gateway and finds no prompt, answer or
      12-character window of a description in any span or log. And every
      span exported the text and stack trace of any exception crossing it,
      the SDK recording it a second time on its own: a span now records the
      type and a `DWError`'s message only (`dw_observability.otel`).
    - **24.** The overview's figures are SQL aggregates and the work list is
      a keyset page (`GET /my-work?limit&cursor`), behind `OverviewReadPort`;
      the old Python computation is the in-memory store's and the test's
      reference, held equal over the walked demo. Partial indexes on open
      work (migration `6d0252a87a6c`); measured on 50,000 cases: 51 rows
      read, 0.5 ms generic plan. The kernel cursor gained an optional leading
      `group` (the due date).
    - **19.** A tenant's own `sales_order_rules` and `sales_kpi` versions are
      proposed (PIC or head), approved (head, never the proposer) and
      resolved through `TenantOverlay`; a recheck reads the version its case
      stamped. `sales.rule_versions` (migration `57a241ea182b`, narrowed by
      tenant only), `/api/v1/sales/rules`. The demo tenant's `1.5.1` is
      proposed by An and approved by Giang through the service at
      `make demo-reset`; the API no longer reads the sample set's policies.
      The quote rules, pricing, copy and upload template: ticket 36.
    - **Owed.** Docker Desktop (WSL) stopped answering at 22:00 mid-run: the
      full Sales integration suite was not re-run after 19's last changes
      (ticket 19, "Owed"). Run since on CI, green on `99cb905` (run
      38545008947).
- 2026-10-13, ticket 34 done (agent, Đạt away; "As built" and Comments in
  the ticket): a PO line printed with no requested date (blank, or a dash)
  reads with none and raises `requested_date_missing` (ask the customer, or
  accept with the date to follow), in both readers and through an approved
  layout; an `.xlsx` and its PDF print in one mail are one PO read from the
  workbook, the print kept as a source and each value it shows differently
  `value_uncertain` (`print_differs`). Rules `sales_order_rules@1.5.0`, the
  demo tenant's `1.5.1` (replaces `1.4.1`), readers `@1.5.0`, migration
  `a459e2244a9c`, mock M44 and M45 (the mailbox is 45 messages). Found on the
  way: a PDF anchor's quote showed prices to a viewer without amounts (support
  and leadership); the order view now leaves a price's anchor out.
- 2026-10-13, ticket 21 done (agent, Đạt away; built in `dd5ef1d`, verified,
  finished and reviewed; "As built" and Comments in the ticket): a PO line
  keeps every delivery schedule from the reader to the upload file (a row per
  schedule, `sales_bravo_upload@1.1.0`), the cross-check sheet and the order
  page. Review added a PostgreSQL round trip (M34) and found a cubic
  backtracking pattern on customer text in the schedule list (75 s on one
  4,000-character entry) and a quadratic one in the PDF total; both are linear
  now, each with a test that goes red with the pattern back. Ticket 35
  (needs-triage): confirmation is one date per line, so a split line is
  confirmed as one delivery.
- 2026-10-13, tickets 32, 33 and 30 built (uncommitted; Đạt away, on his
  pre-authorisation; "As built" and Comments in each ticket):
    - **What.** A customer's reply is attached to its case by its thread
      headers (no model) and a local model reads what it says; the case
      suggests the step, Sales takes it (32). A delivery change, complaint
      or sample request becomes a hand-off draft code writes from the
      customer's located words, for Sales to send to PC or QA (33). A new
      customer's PO form is mapped once on an onboarding screen, a model may
      pre-fill the labels, the head approves it on a platform approval, and
      later POs are read with no model, the first 3 flagged value by value
      (30).
    - **Where it is on.** `sales_order_rules@1.4.0` ships `reply_intent`,
      `request_handoff` and `layout_proposal` off; the demo tenant's `1.4.1`
      has all six model steps on.
    - **Measured** (Qwen3.5-9B, thinking off): replies 95.7% kind accuracy,
      0 false accepts, p50 3.6 s; hand-offs 94.5% of fields, 0 invented,
      p50 5.0 s; layouts 98.2% of fields, 11 of 12 pre-fills kept, 0 kept
      wrong, p50 9.4 s. Every proposed bar holds.
    - **Live portal flow.** M41 → `settle_spec` proposed and taken; M42 →
      `resume_review`, both findings still asked; M11/M17/M31/M40 drafts to
      PC/QA; M43 pre-filled, approved by Giang on the platform approval,
      read with every value flagged; the 43-message mailbox, 0 unprocessed.
    - **Shipped with it.** Migrations `aeb7a7241d75` (`messages.case_reply`),
      `a970a6cbac29` (`messages.handoff`), `63242ec52c4b`
      (`sales.po_layouts`, `messages.layout_prefill`, `sales.layout.approve`
      for `sales_head`); mock M41-M43 (43 messages); prompts
      `reply_intent`, `request_handoff`, `po_layout_proposal` `@1.0.0`;
      copy `sales_handoffs@1.0.0`; evals `sales_reply`, `sales_handoff`,
      `sales_layout` `@1.0.0`; a worker handler for `sales.layout.decided`;
      dw_sales ADR 0004 amendment (a checker's decision with no run).
    - **Next.** Ticket 34 (blank requested date, an .xlsx and its PDF
      print), then 21/23, 24, 25, 27, 19.
- 2026-10-13, tickets 29 and 31 built (uncommitted; Đạt away, on his
  pre-authorisation; "As built" and Comments in each ticket):
    - **What.** A local model reads a request for quotation no reader reads
      (mail body, a PDF's text, the customer's own sheet; ticket 29) and the
      intent of a message no reader accepted (ticket 31). A readable
      document now decides its message's kind first, for every tenant.
    - **Where it is on.** `sales_order_rules@1.3.0` ships `rfq_extraction`
      and `message_intent` off; the demo tenant's `1.3.1` has all three
      model steps on.
    - **Rules.** dw_sales ADR 0005 unchanged; its addendum records how both
      steps apply it (field confusion flagged, a kind is not a route, the
      newest part only, bounded input, one switch block).
    - **Measured.** RFQ: 94.6% VI/EN values in the right field (bar 85%),
      JA 96.0%, p50 15 s per request. Intent: 90.9% kind accuracy (bar 90%)
      against 27.3% for the keyword tables, p50 2.7 s.
    - **Live portal flow.** 40 messages in 149.7 s; M37-M39 quote cases with
      every value flagged; M40 `delivery_change` naming M35's PO; a value
      confirmed through the API.
    - **Shipped with it.** Migration `dab4fd83b8cb` (messages stamp the
      reading; `reply_to_case`), mock M37-M40 (the mailbox is 40 messages),
      evals `sales_rfq@1.0.0` and `sales_intent@1.0.0`, prompts
      `rfq_extraction@1.0.0` and `message_intent@1.0.0`.
    - **Next.** Ticket 30, then 32 and 33.
- 2026-10-13, ticket 28 built (uncommitted; Đạt away, on his
  pre-authorisation; "As built" in the ticket):
    - **What.** DW1 reads an item description its own vocabulary does not
      through the local Qwen3.5-9B (provider `onprem`, Ollama, thinking off)
      for a tenant whose `sales_order_rules.model_assist` turns it on.
    - **Where it is on.** The platform's 1.2.0 ships it off; the demo
      tenant's own 1.2.1 has it on.
    - **Rules.** dw_sales ADR 0005 (Proposed) replaces spec decision 13's "no
      model": typed output that code verifies (spans found once, numbers
      parsed from their span, coverage), labels flagged, never exact, and
      degrading to a person.
    - **Measured.** VI/EN gold code among the candidates 71.1% (bar 70%,
      Đạt 2026-10-15), JA 50.0%; 0 wrong single candidates, 0 injection
      effects; about 77 s per 10-line call.
    - **Against an API model (2026-10-14).** The same set on `luna`
      (gpt-5.6-luna; a throwaway copy of the profile adding
      `max_input_tokens: 6000`, which `luna` does not declare for DW1's
      route): VI/EN 97.8%, JA 100%, 1 of 67 lines to a person, 0 wrong
      single candidates, 0 injection effects, p50 11.6 s per call (9 calls).
      The gap is the model, not the code: verification is the same.
    - **Thinking on (2026-10-14).** Qwen 9B with thinking on (a throwaway
      Ollama model at num_ctx 32768, 2,000 output tokens per line, 600 s
      timeout) on the GTX 1080: 189 minutes for the set, p50 808 s per
      10-line call, 5 of 9 calls failed (44 of 67 lines unavailable); of the
      23 lines answered, 1 read and 22 refused by code (9 lines left out of
      the answer, 11 text not covered). VI/EN 0%, 0 wrong candidates, 0
      injection effects. Thinking is not usable on this card; the context
      that thinking needs spilled part of the model off the GPU, so a 16 GB
      card would be faster, not measured. The live lane reported [PASS]
      with every call unavailable: it grades the guards, not the bar.
      Fixed 2026-10-15 (`b279cc2`, `6d837e0`): a live run fails when the
      model read nothing; a case's bar is reported, not enforced.
    - **Live portal flow.** The whole mailbox in 57.5 s; M36 lines 1 and 3
      suggested correctly and confirmable.
    - **Shipped with it.** Migration `a9977d62e09b`, mock `M36` (the mailbox
      is 36 messages), eval `sales_descriptions@1.0.0`, and the live lane
      `run_evals.py --live onprem`.
    - **Next.** Ticket 29.
- Context `dw_sales` scaffolded with `scripts/new_context.py` (14 seams).
- Feature in progress: `sales/dw1-portal-demo/` — DW1 end to end on mock data
  behind real ports. Spec: `sales/dw1-portal-demo/spec.md`. Tickets 01–27 in
  `sales/dw1-portal-demo/issues/`.
- 2026-10-12, ticket 12 triaged: what needs nothing from Proterial became
  17 and 19–27 (rule overrides, legacy encodings, delivery schedules,
  support without prices, telemetry, SQL overview, ClamAV and worker
  parsing, public-repo guard, legacy Office and OCR), all ready-for-agent;
  12 keeps what waits on the requirements doc (needs-info). Đạt sent the
  requirements doc to Proterial (confirmed 2026-10-12). Order agreed with Đạt:
  13 → 14 → 17, then 19–27.
- 2026-10-12, ticket 23 built (uncommitted; "As built" in the ticket): no
  price, customer name or mail text reaches a span, a log line or an error.
  Sales spans go through one helper (`dw_sales.application.telemetry`) whose
  allowlist checks each key and its value's shape; DW1 emits
  `sales.message.processed` per message. The API's 422 for a request body no
  longer echoes `input` (platform-wide). Tested end to end: three fixture
  POs (one walked to `confirmed`), real OTel exporter, root logs, five
  refusals, 43 document values searched for. Left for the platform: a span
  records `str(exc)` of any exception that crosses it.
- 2026-10-12, ticket 22 built (uncommitted; "As built" in the ticket): FPT
  support reads the overview and the order and quote lists and details
  under a customer's grant, every amount hidden; every other Sales route
  refuses a support context. Set `sales.case_support` =
  `{sales.overview.read, sales.case.read}` for the workspace; `sales_head`
  alone holds `support.grant` (migration `7c8ba908575f`). Found on the way:
  the platform's route-table test saw no included router (FastAPI 0.141),
  fixed. Open for Đạt: whether platform operators count as FPT identities
  (`dev|chi.le` holds `platform_admin` in the demo tenant). Adversarially
  reviewed 2026-10-12: support is the first caller with `sales.case.read`
  and no `sales.price.read`, so the leak search now walks every case the
  inbox opens (it caught a mutation the two-case walk missed); a revocation
  is tested end to end; the route walker is FastAPI's `iter_route_contexts`,
  which also sees a dependency added at `include_router`.
- 2026-10-12, ticket 20 built (uncommitted; "As built" in the ticket): a PO
  value typed in a TCVN3/VNI font (`.VnTime`, `VNI-Times`) is detected by the
  readers. It raises a blocking PO-level `legacy_encoding` whose only decision
  is `ask_customer` (the Unicode re-send arrives as a revision), and no
  attribute is matched on that text. Migration `0d7fd21052a4`,
  `sales_order_rules@1.1.0`, `sales_emails@1.1.0`, readers `@1.2.0`, fixture
  `M33` (the mailbox is 33 messages), eval `sales@1.1.0` 11/11. Reviewed the
  same day. Two guards had no test that could fail, and each now has one:
  the PDF page fallback, and a typed `value_uncertain` value over legacy
  text, which must not clear the finding. The review also found a problem
  that predates this ticket and belongs to ticket 22. A PDF anchor's `quote`
  is the printed text, so for a price field it shows the price to a viewer
  whose amounts are hidden.
- 2026-10-12, ticket 15 built (uncommitted; "As built" in the ticket): a
  `value_uncertain` is corrected per field with a typed value
  (`POST /orders/{id}/findings/{key}/corrections`), kept beside the value as
  read (migration `33f444c15062`), and the upload file, the cross-check sheet
  (`sales_documents@1.1.0`) and the drafts print the entered value; the
  corrected line's checks (header: PO-level checks) run again and a finding
  whose values did not change keeps its decision. Reviewed the same day: a
  revised order's change list now carries the corrected value, and the
  findings card offers the sheet note only when the case would take it.
- 2026-10-12, tickets 13, 14 and 17 built (uncommitted; each ticket's "As
  built" has the detail and its mutation checks):
    - 13: the quote page reads the artifact list once (`useCaseArtifacts`)
      and hands it to the files panel and the approval panel, so a rendered
      preview shows without a reload; the walk's `page.reload()` is gone
      (the walk itself was not run then; it has passed on CI since `e97042b`);
    - 14: a cross-check decision the run cannot apply is recorded on the
      order (`unapplied_decision`, migration `58184771c541`) and in the
      audit (run, approval, reason code), and "Gửi kiểm chéo lại"
      (`POST /orders/{id}/resend-cross-check`; the Bravo recorder, or the
      head with the new `sales.order.resend_cross_check`) raises a new
      approval; `bravo-entry` on an order already in Bravo no longer
      withdraws its pending cross-check. The platform's resume payload now
      names the approval (`approval_id`), and its in-memory run store has
      `active_since`: both are platform code changed in this repo, owed
      upstream;
    - 17: the head reassigns a case (`PUT /orders|quotes/{id}/assignee`,
      `sales.case.assign`, migration `934101cde272`), eligibility from
      `ScopeHoldersPort.holding`, audit with old and new ids, the new
      assignee notified.
      Found while running the integration suites: `ck_approval_requests_sales_stamped`
      (`a64b918fc1f2`) lets a `sales.` approval with a NULL `required_scope`
      through, because `false OR NULL` is NULL and a NULL CHECK passes; its two
      tests fail (`test_sales_constraints.py`, `[sales.quote-None]`,
      `[sales.order.cross_check-None]`). **Closed 2026-10-12 by migration
      `d9e73228e7d7`**: the constraint, same name, now reads
      `coalesce(required_scope, '') LIKE 'sales.%'`; validated on ADD, so an
      unstamped Sales row already in the table stops the upgrade (measured on
      a scratch database: "violated by some row"); downgrade restores
      `a64b918fc1f2`'s definition. Both tests red before, green after.
- 2026-10-12, the gaps left in the demo flow became tickets 13–18, each
  checked against the code that day (the Open items below point at them):
    - 13 the quote approval panel sees a new preview without a reload
      (ready-for-agent);
    - 14 an order whose cross-check decision failed to apply can be
      cross-checked again (ready-for-agent; wider than the race noted under
      ticket 10: any version bump between decide and apply strands it);
    - 15 `value_uncertain` corrected per field, and the upload file prints the
      correction (done 2026-10-12, uncommitted, reviewed; re-run the corrected line's checks, plus the total check);
    - 16 a worker lane processes new mail (done 2026-10-12, uncommitted:
      the worker's `sales_inbox` lane acts as DW1's service account per
      tenant, role `sales_dw1` = `sales.inbox.process` only, migration
      `af154486381e`, resolved by `SqlMembershipLookup.find_service_access`
      and cut to that one scope; one run per message, oldest first; the
      message log's (workspace, message_id) key refuses a second disposition
      on a case; pause state only; 60 s tick; the lane audits as
      `system:sales_inbox`. DW1 is built for both processes by
      `dw_sales.adapters.assembly.build_dw1`. The lane is on by default;
      `DW_WORKER_SALES_INBOX_LANE=false` for the walk-through by button,
      which demo.md now says. Reviewed 2026-10-12: the lane re-reads each
      message and the pause just before its run, so it never re-processes
      one a person routed mid-tick nor spends a run a pause would refuse;
      the worker image is scanned by CI's trivy since);
    - 17 the head reassigns a case (G22, moved out of 12; ready-for-agent);
    - 18 CI runs vitest and the DW1 walk (ready-for-agent 2026-10-12: vitest on
      every push; the walk on `main` and nightly, blocking after three green
      runs in a row). Built and adversarially reviewed 2026-10-12, committed
      in `395dbf3`; the walk first passed on a runner on `e97042b`, and is
      blocking since 2026-10-15.
- Tickets 01 and 07 committed 2026-10-03; 01 follow-up (fixtures M13–M32,
  mock Bravo history, open YCBG list, snapshot as_of, one SourceAnchor) and
  02/03 reworked to the amended spec, adversarially reviewed and committed
  2026-10-05 (dw_sales 683 unit tests; import contracts 9 kept).
- 2026-10-03, conformance review done. The review itself stays outside git
  because it quotes Proterial's survey. The plan gets the mechanics right
  (reading, mapping, checks) but not the process:
    - WIV-03-012 steps 9–10 are missing: no cross-check by a second Sales
      member, no joint confirmation. One PIC can approve and confirm alone.
    - The revised-PO loop dead-ends: a correction request plus Rev.1 never
      yields an upload file.
    - The confirmation carries no delivery date, and the short-LT rule counts
      from the PO date, not the date the PO was received.
    - Quotation steps 2, 5, 6, 8, 9, 11 and 12 have no state or artifact.
    - Roles are three generic scopes, so the walk-through only works as
      platform_admin.
    - ADR 0008, 0009 and 0010 decisions are not followed, nor recorded as
      exceptions.
- 2026-10-03, spec and tickets amended per the review: the process map, the
  actor/role/scope table, maker/checker, price visibility, per-finding and
  per-message dispositions, check basis, the ADR 0009 source gate and the
  interim behaviour per open decision are in the spec. 02/03 are amendment
  tickets, 01 has a fixture follow-up, 11 seeds the personas, and 12 holds
  the production-only gaps. Context glossary and ADRs 0001–0003 are under
  `packages/python/dw_sales/`.
- 2026-10-03, a second pass checked the amendments against the survey and
  the requirements doc. It corrected three process facts: the short-LT
  rule uses the standard lead time; the PIC still compares the Bravo entry
  with the PO when recording the order number; NOC/ESF blocks confirmation,
  not preparation. The cross-checker must also differ from the Bravo
  recorder. The quotation approval matrix waits for Proterial (ticket 12).
- 2026-10-05, ticket 05 built (`3557de8`): 42 routes under
  `/api/v1/sales`, each on the verified access context, scope before the
  idempotency key, amounts left out by one mapper per resource, ids-only
  mutation answers. The items owed into 05 landed: the case carries every
  earlier maker and refuses the cross-check itself (409 "tách nhiệm"), quote
  cases stamp rules version and catalog `as_of` (the parser is the
  request's), one actor id type (principal uuid, migration `075dca5a6168`),
  audit rows in the same transaction, the Design mailbox in
  `sales_quote_rules@1.1.0`, and `price_floor_unknown` (fail closed, Đạt did
  not object). `sales_kpi@1.0.0` shipped. Details in the ticket's "As built".
- 2026-10-05, ticket 06 built (`2f737ca`): every artifact in the table
  rendered from the case by `POST /orders|quotes/{id}/artifacts`, listed by
  `GET .../artifacts`, stored under `{tenant}/{workspace}/sales/{case}/{id}`
  with template `id@version`, case version and sha256, downloaded only in its
  state and at the case's current version (409 `stale_artifact` after an
  edit). Copy `sales_emails@1.0.0`, `sales_documents@1.0.0` and policy
  `sales_bravo_upload@1.0.0` (MOCK) are pinned by the manifest. reportlab
  stays a runtime dependency (G38). The confirmation draft opens at
  `confirmed`, not `cross_checked`; details in the ticket's "As built".
- 2026-10-06, ticket 09 built (`2284d3c`): eval dataset `sales@1.0.0`
  (10 cases, full security coverage) graded by seven `sales.*` graders that
  live in `dw_sales.evals` and run the real Sales services in one process
  over an in-memory store; `scripts/run_evals.py` is the composition root
  that injects them, so `dw_evals` imports no context. Pinned in the release
  manifest. Demo runbook `sales/dw1-portal-demo/demo.md` (Vietnamese),
  `make demo-reset` (start state), `make test-web-sales` (Playwright walk).
  Security reviews (feature and deployment) recorded in ticket 09.
- **What "done" means for the demo:** the personas walk the spec's Done-when
  on the local stack from `make demo-reset`, the walk is automated
  (`make test-web-sales`), and `make eval-smoke` scores extraction and
  findings on the mock set. It is a demo on fictional data, and nothing
  production-only exists. What remains is ticket 12 (production hardening:
  sandboxed parsing, support access, tenant overrides, rules approval, DW1's
  service principal, Proterial's real inputs).
- 2026-10-06, ticket 10 committed (`8d098b3`): DW1 runs on the agent runtime
  (dw_sales ADR 0004, Proposed, supersedes ADR 0001; spec decision 5
  amended). "DW xử lý", submit and the Bravo entry are each a DW1 run
  (`configs/workers/sales.yaml`, graph 1.0.0, pinned), counted by the
  runner's `RunAllowancePort` check. Submit and the Bravo entry pause on a
  platform approval (`sales.quote`, `sales.order.cross_check`) stamped with
  its decide scope (`sales.quote.approve`, `sales.order.cross_check`, never
  `approvals.decide`) and naming every maker; `sales.` is strict and has a
  Sales decision guard; the run applies the decision. The context decide
  routes are gone; the pages decide on `decision.approval_id` with a
  required comment. Platform gained: stamped decide scope, makers, decision
  guard, inbox audience filter, withdraw by subject, an in-memory runtime
  the eval world uses. Walk: 11/11 passed on the third run (`make demo-reset`, `make test-web-sales`); the two before timed out at different steps under machine load (a draft render at stage 1; M29's reprocess at stage 8, whose run row shows 107 s against 0.2 s measured idle). Details and open items in the ticket's
  "As built".
- 2026-10-07, platform `96f95ad` merged (`chore/platform-merge-2`): Sales
  approvals moved onto the platform's approval model (dw_sales ADR 0004
  amendment). The stamp is the `required_scope` column (migration
  `ac31ff0f2087` copies a payload `decide_scope` into it and renames the
  key; `DecisionAsked` still reads `decide_scope` from runs paused before);
  deciding asks `approvals.decide` AND the stamp, so `sales_pic`,
  `sales_head` and `sales_quote_approver` gained `approvals.decide`; seeing
  is the platform's `ApprovalAudience` (the product's own filter and its
  `test_approval_audience.py` are gone). The purchasing manager now gets
  404, not 403, on a Sales request. Kept: makers, `CaseDecisions.check`
  (async guard, longest-prefix keyed), withdrawal (reads the approval as
  the run's requester). Platform ADR 0004 is `docs/adr/0011` here.
- 2026-10-08, platform `ab33703` merged: the antd-only web (see
  `web-ui.md`), decision audit (one `approval.decided` row per decision, the
  platform's; Sales writes none of its own), append-only decisions, 401 for
  a missing bearer (`test_sales_routes.py` follows), `ScopeHoldersPort.holding`
  takes the tenant id as the platform's does, Sales role labels in the one
  role-label table, `/approvals` links a Sales approval to its case. DW1
  renders no prompt (spec decision 13), so the platform's prompt containment
  versions no Sales prompt and `sales@1.0.0` is unchanged.
  **Owed from that merge (Docker became unavailable mid-pass):** the
  integration suites ran once before it stopped (729 passed, 6 failed: the
  five new `ck_approval_requests_sales_stamped` cases on a test bug, and
  `test_sales_api_access.py` still expecting 403 for a missing bearer); both
  are fixed and NOT re-run. Playwright (sales spec, platform specs) and
  `make check-rerank` were NOT run. `make db-migrate` did run on the dev DB
  (head `a64b918fc1f2`) before the stop. Since then the integration suites
  and the sales spec run green on CI (integration on `99cb905`; the walk
  green on 13 of 16 finished runs from `e97042b` to 2026-10-14); the
  platform specs and `make check-rerank` are still not run.
- Next: 12 (needs-info since its triage on 2026-10-12).
  Owed by the API to the pages: delivered 2026-10-15 (refusals only where a
  rule code exists). The PO-read attributes for the candidate picker
  (`136893d`, `734dccd`; stamped at mapping, decided by the agent: the stamp
  rule, four attributes only),
  order due dates in my-work (`27e36bb`), server time (`7ed84b6`: the API
  exposes `Date`, `lib/server-clock.ts` keeps the offset, `useNow` counts by
  it), Vietnamese refusals (`4fa6799`, `04708ec`, `e9cd4bc`: decided by the
  agent, the web words only codes whose server sentence is still English,
  one table per context in `lib/error-message.ts` `REFUSAL_TABLES`;
  separation-of-duties refusals and `stale_case_version` are worded by the
  server (owed on Docker: `test_sales_store.py`,
  `test_sales_constraints.py`)). Still English: refusals with no code (e.g.
  "the approval is not one DW1 raised", "the layout is already decided", order/quote status
  moves, the pricer refusal in `domain/quotes.py`); each needs a
  `details.rule` and a table entry, or a Vietnamese server sentence. The
  picker's khớp/lệch mirrors `StatedAttributes.fits` (a test holds it);
  the lasting fix is the server sending each candidate's fit. (Role names
  and permission-set scopes landed in `/auth/bootstrap` on 2026-10-05; the
  web stopgap roster is gone.)
- Offboarding export reads a partitioned parent and its partitions, so audit
  and event rows come out twice (pre-existing; platform; fixed 2026-10-15,
  `953086f`).
- Open from the 02/03 pass: routing reasons (complaint, sample request,
  delivery change) are keyword tables, against operator guideline §6,
  accepted by the spec for the demo; ticket 03 added the ledger to the mock
  catalog; the sales policy files stayed at 1.0.0 (never released).

- 2026-10-05, UI compared with the E-HSDT v3 prototype (screenshots in the
  session scratchpad): the Sales pages are antd v6 but keep the platform's
  navy theme and system font, the header shows the platform menus in
  English, and lists are plain tables. The prototype uses Be Vietnam Pro
  (JetBrains Mono for codes), a bright primary, a Sales-only header with
  counts, a "Cần xử lý" panel, Segmented tabs with counts, search/sort and
  two-line rows. Primary decided `#0071e3` by Đạt 2026-10-05.
- 2026-10-05, restyle built (`92b155a`): theme from the prototype
  (`web-ui.md` has the mapping and the nearest-passing values); Sales-only
  bar for a PIC/head/viewer with counts (my-work, unprocessed mail) and the
  Vietnamese role name; the four lists on the prototype's list pattern
  (breadcrumb, summary line, "Cần xử lý", Segmented tabs with counts,
  diacritics-insensitive search, `Intl.Collator('vi')` sort, two-line rows,
  `StatusTag`s, red "còn X giờ" inside a day, assignee avatar; tab/q/sort in
  the URL); order and quote detail with the 4-fact summary strip, the
  procedure card and findings as severity-barred rows. API: bootstrap
  returns `role_names` and the effective scopes (roles + permission sets,
  via `effective_scopes`); OpenAPI and TS types regenerated.
  Left different from the prototype: lists on white tables; no command
  palette; the bar overflowed "…" from 992 to beyond 1600 px with nine
  pages (2026-10-15). It now folds them into the "Hồ sơ" and "Quản lý"
  submenus (ticket 39, `f84643e`); the visual check at 992-1600 px is still
  owed. Customer names come
  from the mock master data (a code it lacks shows the code).
- Dev: realm redirect URIs allow port 3300 only; `.env` sets
  `DW_WEB_PORT=3300`, but `scripts/dev.sh` defaults to 3000, so a run
  without the env var cannot sign in. Fixed 2026-10-15 (`9c08926`):
  `dev.sh` reads the port from `DW_PUBLIC_WEB_URL`, and `.env.example`
  uses port 3300. Still open: the local keycloak service gets no
  `DW_PUBLIC_WEB_URL` (the realm falls back to 3300), and the Docker web
  publishes `DW_WEB_HOST_PORT=3000`, so a Docker stack in dev auth at :3000
  is refused by CORS and by Keycloak; follow-up: default
  `DW_WEB_HOST_PORT` to 3300 and change CI's smoke curl (`ci.yml`,
  `http://localhost:3000`) in the same change. A real `make dev` sign-in
  is owed (Docker).

## Inputs owed by Proterial

The requirements doc `DW1_Don-hang-Bao-gia_Nhung-gi-can-co_30-09-2026_v1.2.docx`
(kept outside git) lists them: convert list, item master, quotation master
list and LME rule, Bravo upload template, sample POs with their Bravo orders,
mailbox access, AI/data approval, WIV-03-012/023 texts. Sent by Đạt
(confirmed 2026-10-12); answers awaited.

## Slice log

| Ticket | Commit    | What                                                                                                      |
| ------ | --------- | --------------------------------------------------------------------------------------------------------- |
| 07     | `78af2bd` | antd v6 shell: registry on the `antd` layer, theme owns tokens, top navbar, dates/money                   |
| 01     | `b5f990b` | Mock catalog and inbox behind `SalesCatalogPort`/`InboxPort`; 12 fictional emails M01–M12                 |
| 02, 03 | `ad467dd` | Amended to WIV steps: maker/checker, dispositions, revised PO, quote steps 1–12; fixtures M13–M32         |
| review | `077d54b` | Security review of the core: Design mailbox, decided_by, scope-bound mocks, confirm_mapping               |
| 04     | `5ed607b` | `sales` schema, RLS by tenant+workspace, maker/checker across revisions, roles, offboarding               |
| 11     | `87ab107` | Demo personas: `dw_sales.testing.seed_personas`, `khoa.lam`/`tam.ngo` in the platform seed, roster fixed  |
| 05     | `3557de8` | API routes and scopes, overview/my-work, source gate, pause/resume, actor uuids, `sales_kpi@1.0.0`        |
| 06     | `2f737ca` | Artifacts: upload file, cross-check, drafts, quotation xlsx+PDF; copy pinned; download gates              |
| 08     | `88fb7b6` | Sales pages on the E-HSDT v3 visual language; walked in a browser as every persona, refusals shown        |
| 09     | `2284d3c` | Evals `sales@1.0.0` + graders injected; security reviews; demo runbook, `demo-reset`, Playwright walk     |
| 10     | `8d098b3` | DW1 on the runtime: checker decisions are platform approvals, decide scope stamped, makers refused        |
| 12     | `e60592c` | Triaged into 13-27; what waits on the requirements doc stays (needs-info)                                 |
| 13     | `a995031` | The quote approval panel sees a newly rendered preview                                                    |
| 14     | `4027c0d` | An order whose cross-check failed to apply is cross-checked again                                         |
| 17     | `4db04fc` | The head reassigns a case                                                                                 |
| 15, 16 | `8ac3d33` | Per-field value corrections; the DW1 mailbox lane                                                         |
| 18     | `395dbf3` | Web vitest on every push, the DW1 browser walk on main and nightly                                        |
| 20, 22 | `dd5ef1d` | Legacy Vietnamese encodings refused; FPT support reads cases without prices                               |
| 26     | `dd5ef1d` | Public-repo guard over `git ls-files`, deny-list outside git                                              |
| 21, 23 | `399920d` | Built in `dd5ef1d`; 21 finished and 23 reviewed 2026-10-13                                                |
| 28     | `61a5ae5` | A local model reads free-text item descriptions; code verifies (ADR 0005)                                 |
| 29, 31 | `1009491` | A local model reads RFQs in any shape and classifies unread mail                                          |
| 30-33  | `e97042b` | Model steps for case replies, hand-offs and new PO layouts                                                |
| 34     | `399920d` | Blank requested dates, an `.xlsx` and its PDF print as one PO                                             |
| 24, 19 | `399920d` | Overview figures and a paged work list in SQL; a tenant's own rules proposed and approved (2026-10-13)    |
| 25, 27 | `8adbe08` | "DW xử lý" queued, every file read in the `reader` container; legacy Office and OCR (scanning `399920d`)  |
| 35, 36 | `8adbe08` | A split line confirmed per schedule; a tenant's own quote rules, pricing, copy and upload template        |
| 37, 38 | `8894874` | Released rules versions stay readable; rule versions decided on platform approvals                        |
| batch  | `57d3c20` | Eight batches merged 2026-10-15 (`b2ea975`..`57d3c20`): open items of 05-38 closed (State)                |
| 41     | `035d5a7` | Master data imported from a file, previewed, approved on `sales.catalog`; mock until approved (`ed78006`) |
| 40     | `6659d14` | Rules edited in a form drawn from each key's schema; diff before sending and on the approval (look owed)  |
| 42     | `4235dde` | Follow-ups and the 07:30 brief, every timing in `sales_followups`; integration owed on Docker             |
| 43     | State     | Real mail from a drop folder of `.eml` files, stored in PostgreSQL; ignored sender domains in the rules   |

## Open

- From tickets 32, 33 and 30 (2026-10-13, agent, Đạt away):
    - ADR 0005's addendum and ADR 0004's amendment (a PO layout decided
      on a run-less `sales.layout` approval the worker carries out):
      accepted by Đạt 2026-10-14.
    - `layout_onboarding.uncertain_first_pos` = 3 is an interim default,
      Proterial's call.
    - Delivery changes in DW1 or DW2 (ticket 33's question): built in DW1;
      one table entry (`HANDOFF_KINDS`) turns them off.
    - A reply opening "Hệ thống: khách đã đồng ý..." was read
      `accepts_spec` (S32-VI): nothing is applied by a reading, and the case
      shows the sentence beside the suggestion.
    - A hand-off is copied and sent by Sales from their own mail: DW1 has no
      path to PC or QA.
    - Ticket 34 holds two of ticket 30's reader fixes.
    - The browser walk (`make test-web-sales`) passes, 11 of 12 (2b skipped:
      no model server), with its counts at 43 messages (42 to process) and
      two assertions that had drifted before this work brought up to date: a
      stamped request an outsider may not see answers 404 (ADR 0004
      amendment 2026-10-07), and the forbidden state reads "Bạn không có
      quyền xem mục này" (`3d1f9a5`). It needs Valkey up: with it stopped,
      every authenticated request waited about 4 s on the cache and the
      order page never loaded within the walk's 60 s. The walk does not yet
      visit the layouts page or a reply or hand-off (unit, API and web tests
      do). Done 2026-10-15, owed one green run (`b478685`, `70df3ff`): it
      visits a case reply (M42 on M04), the layouts page (M43), a hand-off
      draft (2d, skipped without a model server) and a `sales.rules`
      decision on `/approvals` (step 11, proposed on `/sales/rules`); it
      runs only in CI or on a local stack. If a platform release ships
      `sales_order_rules` 1.5.99, step 11's version must change.

- From tickets 29 and 31 (2026-10-13, agent, Đạt away):
    - ADR 0005 with its addendum and the two bars (85% and 90%): accepted
      by Đạt 2026-10-14. `model_assist.unread_retry_hours` (24 h) stays an
      interim value.
    - Confirming a model-read value is not gated on the server on the person
      having opened its source, as an order's prepare is (`require_served`):
      the mail text has no served record yet. Resolved 2026-10-15
      (`5c0e28d`, migration `546a6a81e58c`; ticket 29 Comments): gated per
      value; the mail text has its own route and served record.
    - A request stating no currency goes to a person (`currency_missing`);
      a quantity whose unit is only in a column header is asked for. Both
      by design, both cost recall (ticket 29's misses).
    - Thread headers on `InboundMessage`: built with ticket 32.
    - The browser walk's sign-in step had looked for "Sign in" since the
      antd sweep (`3d1f9a5`); fixed here to "Đăng nhập". The nightly walk
      cannot have passed in between.
    - The intent's resolved references are stamped and shown; ticket 33
      resolves its own PO from the mail, so they are still read by no route.
      2026-10-15 (`0d8806b`): the inbox reads `order_case_id` (a link to
      the case). No route reads them to decide: 32 keeps thread headers, 33
      resolves its own PO; switching either to the intent's numbers is
      Đạt's call.

- From the batch merge (2026-10-15, agent, Đạt: làm luôn):
    - ~~The review page listed every `uploaded_to_bravo` order while My
      work offered `confirm`; `confirm()` let None skip the check
      `awaiting()` waited on (ticket 14).~~ Closed 2026-10-17 (`b65956a`):
      `OrderCase.awaits_cross_check` is the one answer; confirm,
      `awaiting()` and `OrderSummaryView` read it.
    - ~~`supported_channels: [web]` was read by nothing (ticket 16).~~
      Closed 2026-10-17 (`b65956a`): the runner refuses a run from an
      undeclared channel; sales.yaml declares `[web, sales_inbox]`.
    - Offboarding never deletes `platform.users`, so a purged tenant leaves
      DW1's per-tenant user row (ticket 16). Closed 2026-10-18 (`981f3a1`;
      decided by Đạt: the purge deletes that tenant's service subjects,
      never a person's row). `purge_rows` deletes the users inside
      `service_subject_bounds(tenant)` (by subject, so a resumed purge still
      finds them) and lists their ids on the purge audit row. Owed on
      Docker/CI: `test_purge_deletes_the_tenants_service_accounts_and_nobody_elses`,
      `test_a_resumed_purge_still_finds_the_service_accounts`.
    - ~~The candidate picker compared the unit and quantity as read
      (ticket 15).~~ Closed 2026-10-17 (`2b23a1b`): `_lib/entered.ts`.
    - A legacy-font run in an inline string, and legacy text reaching the
      model through a non-form `.xlsx` RFQ, are not detected; refusal
      versus a quote-side finding is Đạt's to revisit (ticket 20).
    - The final eval bars are Đạt's; until then a live run fails only when
      the model read nothing (ticket 28).

- **Sales roles decide unstamped approvals** (CLOSED 2026-10-18, `89e33d6`:
  Đạt chose "the platform stamps its own types". `memory.review` is stamped
  with the new platform scope `memory.review`, held by `approver`, `manager`,
  `director` and `approver_boost` and by no Sales role; migration
  `445f93c2ea2a` grants it, stamps existing rows and adds
  `ck_approval_requests_memory_review_stamped`; `docs/adr/0011` amendment
  2026-10-18. A Sales decider now gets 404 on a memory review.
  `platform-runtime.md` has the details. Kept below for the history; from
  `ac31ff0f2087`). Every Sales approval type is stamped, and since the
  platform merge of 2026-10-08 the database says so
  (`ck_approval_requests_sales_stamped`, migration `a64b918fc1f2`, NULL
  refused since `d9e73228e7d7`: a `sales.` approval carries a `sales.`
  scope or is not written). That does
  not close the widening: the platform decides on `approvals.decide` AND the
  stamp (`docs/adr/0011`), so `sales_pic`, `sales_head` and
  `sales_quote_approver` keep `approvals.decide` and with it every
  UNSTAMPED request in their workspace (`memory.review` today). Closing it
  needs a platform decision, not a product patch: either a stamp stands in
  for `approvals.decide` (then the three drop it), or the platform stamps
  its own types (`memory.review`).
- From ticket 09 (2026-10-06): the approval panel needed a page reload after
  the approver rendered the preview (closed by ticket 13); whether submit should render the preview
  itself (Đạt); the release manifest pins an eval dataset file but not the
  fixtures and truth files it names (platform; pinned since 2026-10-15,
  `5452299`, except data a grader opens by its own code: ticket 09 Open);
  the mock README's
  Design-reply dispositions assume Sales recorded the YCBG first (the eval
  states those steps); CI does not run `make test-web-sales` (ticket 18); the walk passed
  11/11 once, then a re-run timed out on Hà's overview ("Loading…", 60 s)
  under heavy machine load: unexplained, and not seen again: stage 9 passed
  on every green CI walk since `e97042b` (13 runs to 2026-10-14), and no CI
  failure was on that stage.

- From ticket 06 (2026-10-05): a `value_uncertain` correction is one value
  for a whole region, so the upload file carries the values as read
  (closed by ticket 15, 2026-10-12); an object written before its record commits can be orphaned
  (purged by offboarding; removed when its record does not commit since
  2026-10-15, `76c3792`, ticket 06); rendering was not stopped by the pause:
  closed 2026-10-18 (`f4705f9`, decided by Đạt: pausing DW1 also stops
  rendering drafts and files; drawing one is refused with `worker_paused`,
  reading what exists is not); the web client types need `pnpm run generate:api-types` (current:
  CI's "Generated API client is current" check was green on `99cb905`).

- From ticket 05 (2026-10-05):
    - The overview loaded every case of the workspace: SQL aggregates and a
      paged work list since ticket 24 (2026-10-13).
    - The A3 shadow count uses interim conditions (no finding, every line
      exact, an original) until Proterial defines A3.
    - Ticket 08 must render a served PDF page with pdf.js scripting off and
      a sheet grid's cell text as text; a download's file name needs
      `Content-Disposition` in the CORS `expose_headers` if the browser is
      to read it. Closed by ticket 08 (`88fb7b6`): pdf.js runs with no
      scripting, XFA or annotations (`pdf-page.tsx`), cell text renders as
      text, and a download is saved under the name the file list gives, so
      the header need not be exposed.
    - A pause commits before its notification: a delivery failure answers
      500 while DW1 is paused (a retry answers 409 "đã tạm dừng"). Closed
      2026-10-15 (`55ade02`): the failure is logged and the pause answers
      as one. A failed notification is not retried; if retries are wanted,
      it moves to an outbox event.
    - The committed OpenAPI snapshot was stale on `main` before 05 (the
      contract test failed); 05 regenerated it, platform drift included.
- Ticket 11 (2026-10-05): the full demo seed is
  `uv run python -m dw_sales.testing.seed_personas` (platform seed, then the
  Sales keys). The new personas sign in through Keycloak via
  `scripts/keycloak_dev_users.py`, which links by email; the realm file was
  not changed. The platform seed resets roles, so a full re-run rewrites the
  Sales keys (same end state); the Sales seed alone writes nothing on a
  re-run. (The `approver_boost` item owed to ticket 10 is closed: a Sales
  approval requires its stamped `sales.quote.approve`, so Diệu's
  `approvals.decide` decides none; tested in the API suite, the unit suite,
  the eval and the walk.)
- From ticket 10 (2026-10-06): the generic Approvals page sends no case
  version, so deciding a Sales approval there would be refused. Closed by the
  platform's `approval-inbox-link` (merged 2026-10-08): `salesApprovalHost`
  in `apps/web/app/sales/_meta/approvals.ts` makes `/approvals` show "Mở hồ
  sơ để quyết định", linking to the case page, instead of the decide
  buttons. An order whose decision passed the guard and then failed in its
  run had no step that raises its cross-check again: closed by ticket 14. Processing's
  audit rows do not name the run (decision rows do): closed 2026-10-15
  (`79be08d`). No mailbox consumer
  exists, and one must start a DW1 run to be counted: ticket 16 (built
  2026-10-12; each message is its own counted run).
- Public repo: the repo name and these plan files name Proterial and its
  procedure codes (WIV-03-0xx). Đạt decided on 2026-10-05 to keep the repo
  public and not alias them. Mock data, people and figures stay fictional,
  and Proterial's documents stay outside git. Guarded since 2026-10-12
  (ticket 26, `scripts/check_public_repo.py`; done and reviewed, uncommitted):
  owed by a person, the `PUBLIC_REPO_DENYLIST` repository secret (the CI step
  fails until it exists) and, on each machine that commits, a deny-list file
  named by `DW_PUBLIC_REPO_DENYLIST`. Without one the hooks only say they
  skipped, and CI finds a term only after the push has published it.
- Defaults adopted until Proterial answers, taken from the requirements
  doc's own interim answers (Đạt may overrule); the spec's "Interim
  behaviour" table names the policy key or role each answer changes:
    - the cross-check is kept;
    - the signed hard copy stays the quotation approval of record, and portal
      approval is shown as the proposal;
    - only the quotation PIC and the head see other customers' prices;
    - NOC/ESF warns, and the export-control PIC must acknowledge it;
    - quotation steps 11–12 are built on mock data.
- Quotation-time target: under 1 day (Đạt, 2026-10-05).
- UI reference (2026-10-05): Đạt's E-HSDT v3 prototype in `docs/design/`
  (untracked, another product's handoff) is the visual language for ticket
  08; the screen mapping is in ticket 08. `docs/design/` is in `.gitignore` (Đạt, 2026-10-05)
