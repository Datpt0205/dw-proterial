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
  number is code's (`DW2-<yymmdd>-<6 hex>`), the name and department the
  directory's. A requester sees only the requests they wrote (narrowed in
  the query) and is a maker of its approval, so never its decider.
- **Case status**: `received` (Đã nhận) — the request is on file;
  `awaiting_approval` (Chờ duyệt) — checked and sent to its approver;
  `approved` (Đã duyệt) / `rejected` (Từ chối) — the approver decided;
  `rfq_drafted` (Đang hỏi giá) — RFQs drafted, offers being recorded;
  `supplier_selected` (Đã chọn nhà cung cấp) — a person chose one per line;
  `po_drafted` (Đã soạn PO) — one draft order per chosen supplier.
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
- **Mail outcome**: what DW2 did with one mail in the purchasing mailbox,
  settled once: `opened` (a case was opened) or `to_person` (a person reads
  it), with a reason code: `sender_not_internal`, `sender_unverified`,
  `no_pr_number`, `no_department`, `span_not_found`, `line_unreadable`,
  `currency_unreadable`, `need_by_unreadable`, `value_malformed`, `no_lines`,
  or a form rule `missing:<field>`, `too_many_lines`, `currency_not_allowed`.
- **Purchasing rules (quy tắc mua hàng)**: one versioned document per tenant
  (`purchasing_rules@<version>`): what a PR form requires, the company's mail
  domains, the approval tiers, whom to ask for quotes, the Bravo layout. The
  platform's version ships in `configs/policies`; a tenant's own replaces it
  whole.
- **Rule version (phiên bản quy tắc)**: a tenant's own version, held by the
  platform's rule-version engine (`platform.rule_versions`, ADR 0013/0014):
  proposed by the configurer or the head, decided on a `purchasing.rules`
  approval by a second person, the head's own applied at once. A field a
  stored version predates reads as the platform's current version has it; a
  stored version today's schema refuses stops intake (409), never falls back.

- **RFQ (yêu cầu báo giá)**: one drafted mail per supplier code picks from
  the master data (supplies the item, quoted it or was paid for it, at most
  the rules' number per line), to the supplier's contacts. The model words
  it from code's facts; kept only when every figure is in the facts and no
  amount is named, else code's template. DW2 sends nothing.
- **Offer (báo giá)**: one supplier's unit price, currency, lead time and
  validity for one line; typed by a buyer, or read from the supplier's
  verified reply (spans, tied to the lines that supplier was asked for).
- **Comparison (bảng so sánh)**: per line, the valid offers in the request's
  currency, cheapest first, each with its total and whether it meets the
  need-by date. Code's, never a model's or a supplier's.
- **Selection (lựa chọn)**: one offer per line, chosen by a person, its total
  held to the most the approver's tier decides (stamped on the case).

- **Draft PO (PO nháp)**: one order per chosen supplier (`<pr_no>-NN`, by
  supplier code), its lines at the chosen offers' prices, the supplier's name
  from the master data. Nothing is recorded in Bravo by DW2.
- **Bravo import file (file nhập Bravo)**: one sheet, the columns, headers,
  order and date format the tenant's rule (`bravo_po`) gives, each column one
  of DW2's fields; stamped on the case with the orders, so the file drawn
  again is the file drawn then. Every string cell is text, never a formula.

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
- The buyer also holds `purchasing.request.submit` and
  `purchasing.rfq.prepare` and `purchasing.po.prepare` (draft the orders,
  download the file). Deciding any approval
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
| 6 | Read a supplier's quote (body, PDF, Excel) | AI tự làm once measured | not yet: replies are linked by hand |
| 7 | Compare (code), propose with reasons (model); a buyer accepts | AI làm, người duyệt | not yet: proposal not built |
| 8 | Draft the orders and the Bravo file; a buyer imports it | AI tự làm | `po_drafting` |
| 9 | The PO number Bravo gave, read back | AI tự làm | function 5, not built |
| 10 | A supplier's confirmation read and compared with the PO | AI tự làm when it matches | function 5, not built |
| 11 | Delivery tracked (code); a reminder worded (model), a buyer sends | AI làm, người duyệt | function 5, not built |
| 12 | Each person's morning brief, questions about a case | AI tự làm | function 6, not built |

A step gets its switch the day code reads it, never before.

- **Automation lane (`purchasing_automation`)**: the worker takes each step
  under DW2's service account at the level in effect; at "AI làm, người
  duyệt" a case DW2 opened from a mail carries a **review** ("Máy đọc, chờ
  người xem") a buyer clears with one press before DW2 sends it on. A known
  supplier's verified mail is never read as a request. Every person is told
  in the app what is theirs to do, once per case and step; a step that
  refuses is told once in its own words. The lane audits as itself.
