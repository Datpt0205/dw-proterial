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
- **Value correction** (Giá trị Sales sửa): the value Sales typed for one
  field a `value_uncertain` flagged, with who and when. It is kept beside the
  value as read, which stays the evidence; the order is entered, uploaded and
  confirmed with the corrected value. A line's number and the PO's number and
  revision are only confirmed as read, never changed.
- **Delivery schedule** (Đợt giao): one delivery of a PO line's quantity, a
  quantity on a requested date, with where the PO prints it. A line printing
  one quantity and one date has one; a line the PO splits over several dates
  (rows under the line, or a "date: quantity" list in its date cell) has one
  per date, which must add up to the line's printed quantity
  (`line_total_mismatch` otherwise). The lead time is checked per schedule,
  the MOQ, pack and price per line; the upload file has a row per schedule
  (ticket 21). A split line's dates are asked of the customer, never typed.
  Sales confirms a split line per schedule, one date each, and the
  confirmation lists each schedule's quantity with its date (ticket 35).
- **Tenant version** (Phiên bản riêng): a customer's own version of a Sales
  rule or copy file (order and quote rules, pricing, KPI, e-mail and document
  copy, the Bravo upload template, the hand-off copy), proposed by a PIC or
  the head and approved by the head, never its proposer, on a `sales.rules`
  platform approval. It applies to that
  tenant only; a case keeps reading the version it stamped (tickets 19, 36).
- **Malware scan** (Quét mã độc): every attachment is scanned by ClamAV
  before anything reads it, then held to its name (ticket 25). An infected
  one routes its message to Sales (`malware_detected`) with nothing in it
  read or served; a scanner that cannot answer leaves the message not yet
  processed ("chưa quét được, thử lại"); a file that is not what its name
  says, or an encrypted Office file, is refused unread.
- **Date to follow** (Ngày giao báo sau): a PO line printed with its
  requested date blank. It reads with no date and no schedule, and raises
  `requested_date_missing`: Sales asks the customer for the date, or goes
  ahead with it to follow, DW1 suggesting the first day the lead time allows
  (ticket 34).
- **PDF print** (Bản in PDF): a PDF print of a PO attached beside its
  workbook in the same mail. The two are one PO, read from the workbook; the
  print is kept as a second source, and a value it prints differently is
  flagged `print_differs` on the workbook's value (`value_uncertain`), never a
  second case (ticket 34).
- **Legacy encoding** (Font tiếng Việt cũ): Vietnamese typed in a TCVN3
  (`.VnTime`, `.VnArial`, …) or VNI (`VNI-Times`, …) font, whose letters are
  stored as other characters ("Cña hµng" for "Cửa hàng"). DW1 detects it by
  the font of a cell or a PDF text run, raises `legacy_encoding` and matches
  nothing on that text; the customer is asked to send the PO again in
  Unicode. Converting it is ADR 0010-document-intake-at-real-size-and-format decision 3, later.
- **Source anchor** (Neo nguồn): where a value was read: `sheet!cell`, or a
  page plus boxes on the rendered page, or a quote. It always carries the
  attachment's sha256. A value a model read from a PDF's text layer names its
  page and words without a box; one read from the mail itself points at the
  characters of the mail's newest part, which the quote case keeps (its
  sha256 in place of a file's).
- **Newest part** (Đoạn mới nhất của thư): the subject and what the sender
  wrote now, with quoted history and forwarded mail cut by the message's own
  structure (HTML blockquote and reply containers, `>` lines, a client's
  "On … wrote:" or "-----Original Message-----"). The only part of a body a
  model is shown.
- **Case version** (Phiên bản hồ sơ): bumped by every change. Every decision
  names the version it was made on.
- **Checker's decision** (Quyết định của người kiểm): approving or returning
  a quotation (WIV-03-023 step 9), cross-checking or returning an order
  (WIV-03-012 step 9), approving or rejecting a PO layout (ticket 30) or a
  tenant version (ticket 38). Made on a platform approval, never on a Sales
  route: the one DW1's run pauses on (`sales.quote`,
  `sales.order.cross_check`), or the run-less one a layout's or a tenant
  version's proposal opens (`sales.layout`, `sales.rules`); a maker's own
  steps are not checker's decisions (dw_sales ADR 0004).
- **DW1 run** (Lượt chạy DW1): one thing DW1 is asked to do ("DW xử lý", a
  quotation submitted, a Bravo entry recorded), on the agent runtime,
  counted against the tenant's plan.
- **Model reading** (Mô hình đọc): what a local model read from a customer's
  words, under dw_sales ADR 0005: closed-set labels and the exact text each
  came from. Code locates every text once, parses every number from its text
  and refuses a reading that leaves a word uncovered; a label is the model's
  ("Mô hình đọc, cần kiểm"), a number is DW1's ("DW1 tính từ chữ"). Stamped on
  the line's check basis with the prompt, profile and route, as `read`,
  `not_understood` (with the check that refused it) or `unavailable` (no
  usable answer: "DW1 không đọc được mô tả"). A line read this way is at best
  a candidate Sales confirms, never `exact`. Turned on per tenant by
  `sales_order_rules.model_assist` (ticket 28).
- **Message intent** (Mô hình đọc loại thư): the kind a model reads a message
  no reader accepted as (`po`, `quote_request`, `design_reply`,
  `reply_to_case`, `delivery_change`, `complaint`, `sample_request`,
  `other`), its language and the document numbers it names. Code maps the
  kind to the route and takes a number only when it is in the newest part
  and resolves to exactly one record of the sender's own customer. Stamped on
  the disposition; a readable attachment decides its message's kind first,
  and no model is asked (ticket 31).
- **Model-read request** (Yêu cầu báo giá mô hình đọc): a request for
  quotation in the mail body, a PDF's text or the customer's own sheet, read
  by a model into span text that code locates and parses. Every value it
  read is flagged `model_read` and raises `value_uncertain` on the quote
  case; Sales confirms each one, typing it as it should be, before the YCBG.
  The customer is the sender domain's; a target price the customer states
  is kept as their words only and never reaches price evidence (ticket 29).
- **Reply in a case's thread** (Khách trả lời trong luồng thư): a message
  whose `In-Reply-To`/`References` name a message already on one case of the
  sender's own customer; it is attached to that case (`attached_to_case`)
  with no model. Where the tenant turns it on, a model reads what it says
  (accepts the spec, rejects it, keeps the PO as it is, ...), quoting the
  sentences code then locates, and the case proposes its next step; Sales
  takes the step, or another (ticket 32).
- **Hand-off** (Bản chuyển PC/QA): the mail Sales sends PC or QA about a
  delivery change, a complaint or a sample request, pre-filled by code from
  a versioned template with the values a model copied and code located,
  parsed and resolved, and the customer's own sentences in quotation marks.
  Sales reviews, edits and sends it; DW1 sends nothing (ticket 33).
- **PO layout** (Mẫu PO): which label on a customer's PO form names each
  value, mapped once by a PIC on the onboarding screen and approved by
  Trưởng bộ phận Sales, who did not map it, on the platform approval the
  proposal opens (`sales.layout`). Tenant data: DW1 reads that
  customer's later POs with it, the first few with every value flagged
  `new_layout` for Sales to confirm. A model may pre-fill the mapping, label
  names only (ticket 30).

## Roles and permission sets

| Key                    | Kind           | Vietnamese name               |
| ---------------------- | -------------- | ----------------------------- |
| `sales_pic`            | role           | Sales phụ trách (PIC)         |
| `sales_head`           | role           | Trưởng bộ phận Sales          |
| `sales_viewer`         | role           | Lãnh đạo (xem tổng hợp)       |
| `sales_price_evidence` | permission set | Xem giá đã báo cho khách khác |
| `sales_quote_approver` | permission set | Người duyệt báo giá thay      |
| `sales_export_control` | permission set | PIC kiểm soát xuất khẩu       |
| `sales_dw1`            | role           | DW1 (tài khoản dịch vụ)       |

DW1 itself is the **Digital Worker** (tài khoản dịch vụ DW1). Its events
carry `actor_kind = worker`.

**DW1's service account** (Tài khoản dịch vụ DW1): one per tenant, a platform
user with a membership holding the role `sales_dw1` (`sales.inbox.process`
only), resolved by the platform like any member. It signs in nowhere. The
**mailbox lane** (DW1 tự xử lý thư, the worker's `sales_inbox` lane, ticket 16) acts under it: every new message processed in a DW1 run of its own, as if
"DW xử lý" had been pressed, except while DW1 is paused.

**Support access** (Quyền hỗ trợ, set `sales.case_support`): FPT support
staff reading a tenant's Sales cases under a grant the head issued (platform
ADR 0024, dw_sales ADR 0003 §5, ticket 22): the overview and the order and
quote lists and details, for the workspace, every amount hidden. Never a
price, never a write; no other Sales route admits it.

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

**Decision not applied** (Quyết định chưa được áp dụng): a cross-check
decision the platform recorded and DW1's run could not apply to the order,
because the case changed in between. The order says so until whoever
recorded its Bravo entry, or the head (`sales.order.resend_cross_check`),
raises the cross-check again (**Gửi kiểm chéo lại**, ticket 14).
Not-applied reasons: `stale_case_version` (Hồ sơ đã đổi phiên bản sau khi
quyết định), `decision_stale` (Hồ sơ không còn chờ quyết định này),
`source_not_served` (Người kiểm chưa mở nguồn của phiên bản này).

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
được khách hàng), `attachment_unreadable` (Không đọc được file),
`malware_detected` (Tệp đính kèm có mã độc), `reply_to_case` (Trả lời về hồ
sơ đang xử lý), `other` (Khác).

## Processing jobs

"DW xử lý", "DW xử lý tất cả" and DW1's mailbox lane queue a message; the
worker processes it, reading every file in the reader sandbox (ticket 25). A
message's job is in one state, beside its disposition:

| State     | Label               |
| --------- | ------------------- |
| `queued`  | Đang chờ DW1        |
| `running` | DW1 đang xử lý      |
| `done`    | DW1 đã xử lý        |
| `failed`  | DW1 chưa xử lý được |

Processing failures: `quota` (Hết lượt chạy DW1 trong ngày của gói),
`not_permitted` (Người yêu cầu không còn quyền xử lý hộp thư), `paused` (DW1
tạm dừng trước khi xử lý), `conflict` (Thư đã được xử lý trong lúc chờ),
`not_found` (Hộp thư không còn thư này), `unavailable` (Chưa quét hoặc chưa
đọc được tệp đính kèm), `model_retry` (Mô hình chưa đọc được thư, DW1 thử lại
sau), `abandoned` (Lượt xử lý bị gián đoạn), `error` (Lỗi khi xử lý).

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
| `legacy_encoding`          | Font tiếng Việt cũ (TCVN3/VNI)       |
| `requested_date_missing`   | Dòng chưa có ngày yêu cầu            |
| `rfq_incomplete`           | Yêu cầu báo giá thiếu thông tin      |
| `price_below_policy_floor` | Giá dưới mức sàn                     |
| `price_floor_unknown`      | Không tính được giá sàn              |
| `price_basis_mismatch`     | Căn cứ giá đồng không đúng           |
| `above_target_price`       | Cao hơn giá khách mong muốn          |
