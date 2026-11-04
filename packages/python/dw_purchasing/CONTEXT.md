# Purchasing (DW2 Mua hàng) — glossary

The language of the Purchasing context, as the code uses it. DW2 takes a
department's purchase request to a draft purchase order: it receives the
request, checks it, asks suppliers, compares their answers and drafts the PO
Bravo imports. People decide; DW2 reads, drafts and checks (ADR 0013,
dw_sales ADR 0005 as DW2 applies it).

## Terms

- **Purchase request (PR, yêu cầu mua hàng)**: what a department asks
  Purchasing to buy, with its own number (`pr_no`), the department, the
  requester, an optional budget code and its lines (description, quantity,
  unit, need-by date, an estimated unit price when the form asks).
  `dw_purchasing.domain.requests.PurchaseRequest`.
- **Purchase case (hồ sơ mua hàng)**: one PR from the moment DW2 received it,
  with where it came from (`form`, `mail` and the mail's id, or `requester`),
  who received it, who asked when DW2 knows them by their sign-in
  (`requested_by`), and the tenant rules it was received under (`rules_ref`,
  stamped once). `PurchaseCase`.
- **Requester (người yêu cầu)**: a member of a department who writes their
  own request in DW2 ("Tôi cần mua…"). The model reads their words into a
  draft (spans only, code keeps whole lines or none); they press "Gửi". The
  number is code's (`DW2-<yymmdd>-<8 hex>`), the name and department the
  directory's. A requester sees only the requests they wrote (narrowed in
  the query) and is a maker of its approval, so never its decider.
- **Case status**: `received` (Đã nhận) — the request is on file;
  `awaiting_approval` (Chờ duyệt) — checked and sent to its approver;
  `approved` (Đã duyệt) / `rejected` (Từ chối) — the approver decided;
  `rfq_drafted` (Đang hỏi giá) — RFQs drafted, offers being recorded;
  `awaiting_reapproval` (Chờ duyệt lại) — the suppliers chosen come to more
  than the approver's tier decides, and the choice waits on the tier its
  total names;
  `supplier_selected` (Đã chọn nhà cung cấp) — a person chose one per line;
  `po_drafted` (Đã soạn PO) — one draft order per chosen supplier;
  `delivered` (Đã nhận đủ hàng) — every line of every order received in
  full, moved there by the receipt that completes them.
- **Cross-check (đối chiếu)**: each line's reference price (a supplier
  quotation still valid, else the last price paid, else the requester's
  estimate), the request's amount (unknown when a line has no price), and
  findings: `item_unknown`, `no_reference_price`, `currency_mismatch`,
  `estimate_above_reference`, `need_by_short`, `budget_missing`,
  `budget_unknown`, `over_budget`. Stamped on the case when it is sent.
- **Approval tier (bậc duyệt)**: the band of amounts one approver decides,
  and the scope (`purchasing.approve.tier1..3`) that approver holds; the
  bands, who each is and which findings send a request to the last tier are
  the tenant's rule. Stamped on the case and on the platform approval
  (`purchasing.request`, strict) when it is sent.
- **Stored mailbox (hộp thư đã lưu)**: the purchasing mailbox as DW2 holds
  it, `DW_PURCHASING_MAILBOX=stored` (else the demo's mock). Each person's
  flow exports each mail as an `.eml` file into their own folder of the one
  drop folder every DW shares; the worker's `purchasing_mail_drop` lane reads
  each new file once, in the folders of the members holding
  `purchasing.request.intake` only, in the reader sandbox
  and stores the message and its attachments (`purchasing.mailbox_*`),
  audited as itself. A file it cannot read is told to whoever holds
  `purchasing.request.intake`, once; a folder it cannot list, once a day.
  Everything else reads the store, never the folder.
- **Attachment reading (tệp đính kèm đã đọc)**: what the mail drop lane read
  of each attachment as it stored the mail, kept beside it
  (`domain.attachments`): scanned by ClamAV first (an infected file is
  never read and its bytes not kept), then, a document (an Excel PR form, a
  PDF, a legacy `.xls`/`.doc` converted first), its text taken in the reader
  sandbox, a page with no text layer read by OCR and marked so; an image is
  not read as a form. Nothing after the lane parses the file. DW2 reads a
  mail with the one document beside it; a mail with an infected file, more
  than one document or one too long to show whole goes to a person.
- **Read from (đọc từ)**: on a case read from mail with a document attached,
  the file its lines came from (or the mail's own words) and whether any
  value was read only on a scanned page. A request read from a scan waits
  for a person to compare it with the paper (`Review`) whatever the switch,
  because OCR misreads a digit without saying so.
- **Mail outcome**: what DW2 did with one mail in the purchasing mailbox,
  settled once: `opened` (a case was opened), `supplier` (a known supplier's
  verified mail handled at the one case it is about: its quote or order
  confirmation read there, or its buyer told) or `to_person` (a person reads
  it), with a reason code: `sender_not_internal`, `sender_unverified`,
  `no_pr_number`, `no_department`, `span_not_found`, `line_unreadable`,
  `currency_unreadable`, `need_by_unreadable`, `value_malformed`, `no_lines`,
  or a form rule `missing:<field>`, `too_many_lines`, `currency_not_allowed`.
- **Purchasing rules (quy tắc mua hàng)**: one versioned document per tenant
  (`purchasing_rules@<version>`): what a PR form requires, the company's mail
  domains, the approval tiers, whom to ask for quotes, the Bravo layout, and
  how long rows are kept (`retention`: a case in years, 1–30, default 10; a
  mail outcome in days, 30–3650, default 365; stored mail in days, 30–3650,
  default 365 and never past its outcome, since 1.7.0). The platform's version ships
  in `configs/policies`; a tenant's own replaces it whole.
- **Rule version (phiên bản quy tắc)**: a tenant's own version, held by the
  platform's rule-version engine (`platform.rule_versions`, ADR 0013/0014):
  proposed by the configurer or the head, decided on a `purchasing.rules`
  approval by a second person, the head's own applied at once. A field a
  stored version predates reads as the platform's current version has it; a
  stored version today's schema refuses stops intake (409), never falls back.

- **RFQ (yêu cầu báo giá)**: one drafted mail per supplier code picks from
  the master data (supplies the item, quoted it or was paid for it, at most
  the rules' number per line) or the buyer names for a line, to the
  supplier's contacts. The model words it from code's facts; kept only when
  every figure is in the facts and no amount is named, else the draft waits
  for the buyer to write it (`pending`), never a fixed template. DW2 sends
  nothing.
- **Offer (báo giá)**: one supplier's unit price, currency, lead time and
  validity for one line; typed by a buyer, or read from the supplier's
  verified reply (spans, tied to the lines that supplier was asked for).
- **Comparison (bảng so sánh)**: per line, the valid offers in the request's
  currency, cheapest first, each with its total and whether it meets the
  need-by date. Code's, never a model's or a supplier's.
- **Selection (lựa chọn)**: one offer per line, chosen by a person. Past the
  most the approver's tier decides (stamped on the case), plus the tenant's
  `reapproval_tolerance_percent` (default 0), it is not refused: it goes
  back for approval.
- **Reapproval (duyệt lại)**: a strict, run-less `purchasing.reapproval` at
  the tier the new total names, its makers everyone who made the case and
  the buyer who chose; the reason in words is the model's, kept only when
  every figure is one of code's facts. Approved, the choice is the
  selection; rejected, the case goes back to choosing, the choice kept.

- **Draft PO (PO nháp)**: one order per chosen supplier (`<pr_no>-NN`, by
  supplier code), its lines at the chosen offers' prices, the supplier's name
  from the master data. Nothing is recorded in Bravo by DW2.
- **Bravo import file (file nhập Bravo)**: one sheet, the columns, headers,
  order and date format the tenant's rule (`bravo_po`) gives, each column one
  of DW2's fields; stamped on the case with the orders, so the file drawn
  again is the file drawn then. Every string cell is text, never a formula.
- **Master data (dữ liệu chủ)**: the company's items (vật tư), suppliers
  (nhà cung cấp), quotations on file (báo giá), prices paid (giá đã mua) and
  budgets (ngân sách): one version the tenant holds of
  `purchasing_master_data`, empty as the platform ships it
  (`domain.master_lists`, `docs/adr/0001-master-data-is-a-rule-version.md`).
  Loaded from one workbook, one sheet per list; a sheet left out keeps its
  list. An upload (`purchasing.master_imports`) is `queued` (Đang đọc),
  `parsed` (Đã đọc, chờ gửi duyệt), `failed` (Không đọc được) or `submitted`
  (Đã gửi duyệt); a refused row names its sheet, row and why, never a value.
- **RFQ mail (thư hỏi giá gửi đi)**: one supplier's RFQ a buyer sent from
  their own mailbox ("Gửi từ hộp thư của tôi"), through the one outbox
  folder and flow per person DW1 uses too (`application.rfq_mail`):
  `queued` (Đang chuyển sang hộp thư), `written` (Chờ luồng gửi), `sent`
  (Đã gửi), `failed` (Không gửi được: no outbox folder, or the flow failed)
  or `stalled` (Chưa có xác nhận gửi, 30 minutes without a receipt). One
  active per supplier of a case; a failed or stalled one may be sent again.
- **Order follow-up (theo dõi đơn)**: DW02 function 5, per drafted order by
  its `po_ref` (`domain.tracking`, `application.follow_up`): **Bravo's
  number** (số PO Bravo), typed by the buyer once the file is imported; the
  **supplier's confirmation** (xác nhận của nhà cung cấp), read from a
  verified mail of the order's own supplier that names the order (by Bravo's
  number or the `po_ref`, matched by code), held line by line to the order:
  each **difference** (chỗ khác đơn) is `quantity` (số lượng), `unit_price`
  (đơn giá), `delivery_on` (ngày giao, later than needed), `missing` (thiếu
  dòng) or `not_ordered` (dòng ngoài đơn); it is accepted (Đã chấp nhận) by a
  buyer. A **receipt** (ghi nhận hàng) is what arrived of a line, never more
  than is owed. A line is **late** (trễ hạn) past the date the supplier
  confirmed, else its need-by date, with less arrived than ordered.

## Roles and scopes

- `purchasing_buyer` (Nhân viên mua hàng): `purchasing.request.read`,
  `purchasing.request.intake`.
- `purchasing_viewer` (Xem yêu cầu mua hàng): `purchasing.request.read`.
- `purchasing_head` (Trưởng phòng Mua hàng): `purchasing.request.read`,
  `purchasing.approve.tier1`, `purchasing.approve.tier2`.
- `purchasing_requester` (Người yêu cầu mua hàng): `purchasing.request.create`,
  `purchasing.request.read_own`.
- `purchasing_configurer` (Người cấu hình DW2): `purchasing.request.read`,
  `purchasing.rules.propose`; their version waits for the head.
- The head also holds `purchasing.rules.propose` and
  `purchasing.rules.approve`.
- `purchasing_dw2` (DW2 tài khoản dịch vụ): the automation lane's account in
  each tenant, `purchasing.request.read/intake/submit`, `purchasing.rfq.prepare`,
  `purchasing.po.prepare`; no approve scope, no `approvals.decide`.
- Permission set `purchasing_director_approver`: `purchasing.approve.tier3`.
  Whoever an approval stamps reads that one request while it waits.
- Permission sets a tenant's admin grants on the members page, so who may do
  these is the tenant's setting, not a release: `purchasing_po_downloader`
  (`purchasing.po.download`, the Bravo file), `purchasing_request_reader`
  (every request), `purchasing_rules_approver` (decide a rule change; reads
  the settings page, proposes nothing).
- The buyer also holds `purchasing.request.submit`,
  `purchasing.rfq.prepare`, `purchasing.po.prepare` (draft the orders) and
  `purchasing.po.download` (the file). Deciding any approval
  also needs the platform's `approvals.decide`.

## Automation (Đạt, 2026-11-01)

DW2 is the real product signed with Proterial. Every step a model can do,
it does; an easy step runs on its own, an important one is prepared and a
person decides it with one press. Limits that do not move: the model only
reads and writes, code checks and decides; money, approvals, mail leaving the
company and Bravo always have a person; an unsure step goes to a person with
the reason in words, never a guess.

- **Switch (công tắc)**: one per step, three levels, the tenant's rule
  `purchasing_automation@<version>` (proposed and decided like the rules):
  `ai_auto` **AI tự làm**, `ai_review` **AI làm, người duyệt**, `person`
  **Người làm**. `domain.automation`.
- **Ceiling (trần)**: the furthest a step may be set, in code, never a rule:
  a step that spends money, approves, mails outside or records in Bravo stops
  at `ai_review`.
- **Level in effect**: `ai_auto` takes effect only while every model step the
  step runs on has a live measurement at its bar on the plant's model
  (`platform.model_step_measurements`); until then it runs at `ai_review`,
  and the settings page says "chưa đo trên model của nhà máy". A version
  that raises a step to `ai_auto` before it is measured is refused (409).

The twelve steps, the default proposed, and where each stands:

| # | Step | Default | Switch |
| --- | --- | --- | --- |
| 1 | Sort an incoming mail by its sender; else "Cần người xem" | AI tự làm | `mail_sorting` |
| 2 | Open a request from a mail (later: Excel, scan, a sentence) | AI tự làm once measured | `pr_drafting` |
| 3 | Cross-check (code), each finding explained (model) | code | not yet: explanations not built |
| 4 | Send to the approver its amount names; requester ≠ approver | AI tự làm | `submission` |
| 5 | Pick suppliers (code), word the RFQ (model); a buyer sends | AI làm, người duyệt | `rfq` |
| 6 | Read a supplier's quote (the mail's body) | AI tự làm once measured | `quote_reading` |
| 7 | Compare (code), propose with reasons (model); a buyer accepts | AI làm, người duyệt | not yet: proposal not built |
| 8 | Draft the orders and the Bravo file; a buyer imports it | AI tự làm | `po_drafting` |
| 9 | The PO number Bravo gave, read back | AI tự làm | function 5, not built |
| 10 | A supplier's confirmation read and compared with the PO | AI tự làm when it matches | `confirmation_reading` |
| 11 | Delivery tracked (code); a reminder worded (model), a buyer sends | AI làm, người duyệt | late lines told (code, no switch); the reminder's wording not built |
| 12 | Each person's morning brief, questions about a case | AI tự làm | Q&A built (Hỏi đáp DW2); the brief built (counts, code's; 11-04) |

A step gets its switch the day code reads it, never before.

- **Automation lane (`purchasing_automation`)**: the worker takes each step
  under DW2's service account at the level in effect; at "AI làm, người
  duyệt" a case DW2 opened from a mail carries a **review** ("Máy đọc, chờ
  người xem") a buyer clears with one press before DW2 sends it on. A known
  supplier's verified mail is never read as a request: code ties it to the
  one order it names or the one case it answers, and there a quote is read
  into its offers and a confirmation that differs from the order in nothing
  is accepted (one that differs goes to a buyer). Every person is told
  in the app what is theirs to do, once per case and step; a step that
  refuses is told once in its own words. The lane audits as itself.

## Screen words

The labels the DW2 pages show, one line per code set; the web's
`app/purchasing/_lib/labels.ts` is tested against these lines and the case
status and role lines above, so a word changed on one side turns a test red.

Steps: `mail_sorting` (Phân loại thư đến), `pr_drafting` (Mở yêu cầu từ thư),
`submission` (Gửi người duyệt), `rfq` (Soạn thư hỏi giá), `po_drafting` (Soạn
PO và file Bravo), `quote_reading` (Đọc báo giá của nhà cung cấp),
`confirmation_reading` (Đọc thư xác nhận đơn).

Levels: `ai_auto` (AI tự làm), `ai_review` (AI làm, người duyệt), `person`
(Người làm).

Model steps: `purchasing_pr_mail_reading` (Đọc yêu cầu từ thư),
`purchasing_supplier_quote_reading` (Đọc báo giá),
`purchasing_order_confirmation_reading` (Đọc thư xác nhận đơn).

Why a level: `set` (theo quy tắc của công ty), `not_measured` (chưa đo trên
model của nhà máy), `unreadable` (số đo không đọc được).

Findings: `item_unknown` (mã hàng chưa có trong danh mục),
`no_reference_price` (chưa có giá tham chiếu), `currency_mismatch` (giá
tham chiếu ở loại tiền khác), `estimate_above_reference` (giá ước tính cao
hơn giá tham chiếu), `need_by_short` (ngày cần hàng sớm hơn thời gian giao),
`budget_missing` (thiếu mã ngân sách), `budget_unknown` (mã ngân sách không
có), `over_budget` (vượt ngân sách còn lại).

Reference bases: `quote` (báo giá còn hạn), `history` (giá đã mua lần
trước), `estimate` (giá ước tính của người yêu cầu).

Sources: `form` (Biểu mẫu), `mail` (Thư), `requester` (Người yêu cầu tự viết).

Mail outcomes: `opened` (Đã mở hồ sơ), `to_person` (Cần người xem),
`supplier` (Thư nhà cung cấp).

Mail reasons: `sender_not_internal` (người gửi không thuộc công ty),
`sender_unverified` (hệ thống thư không xác thực được người gửi),
`no_pr_number` (thư không có số yêu cầu mua hàng), `no_department` (thư
không nói bộ phận yêu cầu), `span_not_found` (DW2 đọc ra một giá trị không
có trong thư), `line_unreadable` (DW2 không đọc trọn được một dòng hàng),
`currency_unreadable` (không rõ đơn vị tiền), `need_by_unreadable` (không
đọc được ngày cần hàng), `value_malformed` (một giá trị trong thư không đúng
dạng), `no_lines` (thư không có dòng hàng nào), `too_many_lines` (thư có
nhiều dòng hàng hơn quy tắc cho phép), `currency_not_allowed` (loại tiền
quy tắc không cho phép), `attachment_infected` (tệp đính kèm có mã độc),
`several_documents` (thư có nhiều tệp tài liệu), `document_too_long` (tệp
đính kèm quá dài để đọc trọn), `attachment_unreadable` (DW2 không đọc được
tệp đính kèm).

Marks: `machine_read` (Máy đọc), `machine_written` (Máy viết), `template`
(Mẫu cố định), `person` (Người nhập).
