# Sales context (`dw_sales`) — glossary

DW1, Đơn hàng & Báo giá: a Sales department's order intake (WIV-03-012) and
quotation (WIV-03-023). The UI shows the Vietnamese labels below; code, the
API and the plan use the English terms. The spec is
`.claude/plans/sales/dw1-portal-demo/spec.md`. The decisions are in
`docs/adr/`, next to this file.

## Terms

- **Order case** (Hồ sơ đơn hàng): one customer PO number, from its first
  revision to confirmation. A later revision of the same PO joins the same
  case and supersedes the previous revision; it never opens a new case.
- **Quote case** (Hồ sơ báo giá): one request for quotation, through to a
  sent quotation or a decline.
- **Maker / checker** (Người làm / người kiểm): on an order, the makers are
  the preparer and whoever recorded the Bravo entry, in this round or an
  earlier one (a return, a revision, a change applied in Bravo), and whoever
  typed a value still on the case; the checker is the cross-checker. On a
  quote, the pricer and the approver. A checker is never a maker of the same
  case. Every one of them is named by their principal id.
- **Served source** (Đã mở nguồn): a page or sheet of a case's original that
  a person was shown, for one case version. Prepare and cross-check need the
  person's own record for the current version ("chưa mở nguồn" otherwise).
- **YCBG** (Phiếu yêu cầu báo giá): the quote-request form Sales enters in
  Bravo and sends to Design. Design's reply is matched by the YCBG number
  only.
- **Check basis** (Căn cứ kiểm tra): what a check compared against, stamped
  on the case when the check ran. It is never re-read from master data.
- **Coverage statement** (Phạm vi đã kiểm): what was read and checked on one
  order ("Đã đọc N/N dòng …").
- **Source anchor** (Neo nguồn): where a value was read: `sheet!cell`, or a
  page plus boxes on the rendered page, or a quote. It always carries the
  attachment's sha256.
- **Case version** (Phiên bản hồ sơ): bumped by every change. Every decision
  names the version it was made on.
- **Checker's decision** (Quyết định của người kiểm): approving or returning
  a quotation (WIV-03-023 step 9), cross-checking or returning an order
  (WIV-03-012 step 9). Made on the platform approval DW1's run pauses on
  (`sales.quote`, `sales.order.cross_check`), never on a Sales route; a
  maker's own steps are not checker's decisions (dw_sales ADR 0004).
- **DW1 run** (Lượt chạy DW1): one thing DW1 is asked to do ("DW xử lý", a
  quotation submitted, a Bravo entry recorded), on the agent runtime,
  counted against the tenant's plan.

## Roles and permission sets

| Key                    | Kind           | Vietnamese name               |
| ---------------------- | -------------- | ----------------------------- |
| `sales_pic`            | role           | Sales phụ trách (PIC)         |
| `sales_head`           | role           | Trưởng bộ phận Sales          |
| `sales_viewer`         | role           | Lãnh đạo (xem tổng hợp)       |
| `sales_price_evidence` | permission set | Xem giá đã báo cho khách khác |
| `sales_quote_approver` | permission set | Người duyệt báo giá thay      |
| `sales_export_control` | permission set | PIC kiểm soát xuất khẩu       |

DW1 itself is the **Digital Worker** (tài khoản dịch vụ DW1). Its events
carry `actor_kind = worker`.

## Value states

How sure a value on a case is (ui-quality.md §7). Every one of them is drawn.

| State          | Label              | Meaning                                                                        |
| -------------- | ------------------ | ------------------------------------------------------------------------------ |
| `dw`           | Máy đọc            | Read by DW1 from the source anchor; not yet seen by a person                   |
| `uncertain`    | Chưa chắc chắn     | DW1 could not read it unambiguously (`value_uncertain`); blocks like a failure |
| `confirmed`    | Đã kiểm            | A person checked it against the source                                         |
| `hand_entered` | Sales nhập tay     | Typed by a person, who is named; the cross-checker must be someone else        |
| `superseded`   | Đã có bản thay thế | From a revision a later revision replaced                                      |

## Mapping status (customer code → PRV code)

| Status                | Label                |
| --------------------- | -------------------- |
| `exact`               | Khớp convert list    |
| `candidate`           | Một mã ứng viên      |
| `ambiguous`           | Nhiều mã ứng viên    |
| `unmapped`            | Chưa có mã           |
| `candidate_confirmed` | Sales đã xác nhận mã |

## Price evidence factors

Order history for the item (Lịch sử đặt hàng của khách), freight (Cước vận
chuyển) and management guidance (Ghi chú chỉ đạo), beside quotation history,
other customers' prices, LME and the copper component.

## Order case states

The transitions are owned by `OrderCase` and `QuoteCase` in
`dw_sales.domain`; this file is the one list of names and labels.

| State                  | Label            |
| ---------------------- | ---------------- |
| `received`             | Đã nhận          |
| `checked`              | Đã kiểm tra      |
| `in_review`            | Chờ PIC tự kiểm  |
| `correction_requested` | Chờ khách sửa PO |
| `prepared`             | PIC đã tự kiểm   |
| `uploaded_to_bravo`    | Đã nhập Bravo    |
| `cross_checked`        | Đã kiểm chéo     |
| `confirmed`            | Đã xác nhận      |
| `change_review`        | Xem thay đổi PO  |
| `closed`               | Đã đóng          |

Close reasons: `duplicate` (PO trùng), `not_an_order` (Không phải đơn hàng),
`superseded` (Đã có bản thay thế), `cannot_supply` (Không cung cấp được).

## Quote case states

| State                  | Label                    |
| ---------------------- | ------------------------ |
| `received`             | Đã nhận                  |
| `ycbg_drafted`         | Đã soạn YCBG             |
| `ycbg_recorded`        | Đã lập YCBG trên Bravo   |
| `sent_to_design`       | Chờ Design               |
| `design_replied`       | Design đã phản hồi       |
| `spec_discussion`      | Thảo luận spec với khách |
| `priced`               | Đã định giá              |
| `pending_approval`     | Chờ duyệt                |
| `returned`             | Bị trả lại định giá      |
| `approved`             | Đã duyệt                 |
| `sent`                 | Đã gửi khách             |
| `master_list_recorded` | Đã ghi master list       |
| `declined`             | Từ chối báo giá          |

Decline reasons: `not_our_product` (Không phải sản phẩm của công ty),
`design_cannot` (Design không làm được), `customer_rejected_spec` (Khách
không đồng ý spec), `commercial` (Lý do thương mại). "Quá hạn" (overdue) is
derived from the quote due date and is not a state.

## Message dispositions

| Disposition         | Label              |
| ------------------- | ------------------ |
| `case_created`      | Đã tạo hồ sơ       |
| `attached_to_case`  | Đã gắn vào hồ sơ   |
| `routed_to_sales`   | Chuyển Sales xử lý |
| `not_yet_processed` | Chưa xử lý         |

Routing reasons: `delivery_change` (Đổi lịch giao — PC, DW2), `complaint`
(Khiếu nại — QA), `design_reply_unmatched` (Phản hồi Design không khớp
YCBG), `sample_request` (Yêu cầu hàng mẫu), `customer_unknown` (Chưa xác định
được khách hàng), `attachment_unreadable` (Không đọc được file), `other`
(Khác).

## Finding dispositions

| Disposition          | Label                |
| -------------------- | -------------------- |
| `open`               | Chưa quyết định      |
| `accepted`           | Chấp nhận (có lý do) |
| `corrected_by_sales` | Sales sửa giá trị    |
| `ask_customer`       | Yêu cầu khách sửa    |

## Finding codes

| Code                       | Label                                |
| -------------------------- | ------------------------------------ |
| `code_unmapped`            | Mã chưa có trong convert list        |
| `code_ambiguous`           | Nhiều mã ứng viên                    |
| `price_mismatch`           | Đơn giá lệch báo giá                 |
| `currency_mismatch`        | Khác tiền tệ với báo giá             |
| `uom_mismatch`             | Khác đơn vị tính                     |
| `quotation_missing`        | Không có báo giá còn hiệu lực        |
| `lme_band_mismatch`        | Sai mức LME                          |
| `moq_violation`            | Dưới MOQ                             |
| `pack_multiple`            | Không chẵn quy cách đóng gói         |
| `line_total_mismatch`      | Tổng dòng không khớp hoặc thiếu dòng |
| `value_uncertain`          | Giá trị đọc chưa chắc chắn           |
| `customer_unknown`         | Chưa xác định được khách hàng        |
| `duplicate_po`             | PO gửi trùng                         |
| `requested_date_short_lt`  | Ngày yêu cầu ngắn hơn lead time      |
| `missing_noc_esf`          | Thiếu NOC/ESF                        |
| `revised_po`               | PO sửa đổi                           |
| `revision_without_base`    | PO sửa đổi chưa thấy bản gốc         |
| `customer_temporary`       | Khách hàng mã tạm thời               |
| `sender_unverified`        | Chưa xác thực người gửi              |
| `rfq_incomplete`           | Yêu cầu báo giá thiếu thông tin      |
| `price_below_policy_floor` | Giá dưới mức sàn                     |
| `price_floor_unknown`      | Không tính được giá sàn              |
| `price_basis_mismatch`     | Căn cứ giá đồng không đúng           |
| `above_target_price`       | Cao hơn giá khách mong muốn          |
