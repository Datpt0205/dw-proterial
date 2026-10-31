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
- **Case status**: `received` (Đã nhận) — the request is on file. Later slices
  add the states after it.
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

## Roles and scopes

- `purchasing_buyer` (Nhân viên mua hàng): `purchasing.request.read`,
  `purchasing.request.intake`.
- `purchasing_viewer` (Xem yêu cầu mua hàng): `purchasing.request.read`.
