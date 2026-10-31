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
  with where it came from (`form` or `mail`, and the mail's id), who received
  it and the tenant rules it was received under (`rules_ref`, stamped once).
  `PurchaseCase`.
- **Case status**: `received` (Đã nhận) — the request is on file;
  `awaiting_approval` (Chờ duyệt) — checked and sent to its approver;
  `approved` (Đã duyệt) / `rejected` (Từ chối) — the approver decided;
  `rfq_drafted` (Đang hỏi giá) — RFQs drafted, offers being recorded;
  `supplier_selected` (Đã chọn nhà cung cấp) — a person chose one per line.
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
  domains. The platform's version ships in `configs/policies`; a tenant's own
  replaces it whole and is read from the platform's policy overrides.

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

## Roles and scopes

- `purchasing_buyer` (Nhân viên mua hàng): `purchasing.request.read`,
  `purchasing.request.intake`.
- `purchasing_viewer` (Xem yêu cầu mua hàng): `purchasing.request.read`.
- `purchasing_head` (Trưởng phòng Mua hàng): `purchasing.request.read`,
  `purchasing.approve.tier1`, `purchasing.approve.tier2`.
- Permission set `purchasing_director_approver`: `purchasing.approve.tier3`.
- The buyer also holds `purchasing.request.submit` and
  `purchasing.rfq.prepare`. Deciding any approval
  also needs the platform's `approvals.decide`.
