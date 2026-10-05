/**
 * The Vietnamese words for every Sales code the API sends, keyed by code.
 *
 * The owner of these words is the context's glossary,
 * `packages/python/dw_sales/CONTEXT.md`; the API sends codes and nothing
 * else (views.py: "Labels are the screen's"). This file is the screen's copy
 * of those tables, and `__tests__/labels.test.ts` reads CONTEXT.md and fails
 * on any row that differs, is missing, or is added on one side only, so the
 * two cannot drift quietly (failure-modes.md #2).
 *
 * The words below the glossary tables (`ACTION`, `STEP_COVERAGE`, `SEVERITY`,
 * …) have no row in CONTEXT.md: they are the screen's own copy, kept here so
 * each concept is named once.
 */

// ------------------------------------------------- CONTEXT.md, table by table

/** "Value states". */
export const VALUE_STATE = {
  dw: "Máy đọc",
  uncertain: "Chưa chắc chắn",
  confirmed: "Đã kiểm",
  hand_entered: "Sales nhập tay",
  superseded: "Đã có bản thay thế",
} as const;

/** "Mapping status (customer code → PRV code)". */
export const MAPPING_STATUS = {
  exact: "Khớp convert list",
  candidate: "Một mã ứng viên",
  ambiguous: "Nhiều mã ứng viên",
  unmapped: "Chưa có mã",
  candidate_confirmed: "Sales đã xác nhận mã",
} as const;

/** "Order case states". */
export const ORDER_STATE = {
  received: "Đã nhận",
  checked: "Đã kiểm tra",
  in_review: "Chờ PIC tự kiểm",
  correction_requested: "Chờ khách sửa PO",
  prepared: "PIC đã tự kiểm",
  uploaded_to_bravo: "Đã nhập Bravo",
  cross_checked: "Đã kiểm chéo",
  confirmed: "Đã xác nhận",
  change_review: "Xem thay đổi PO",
  closed: "Đã đóng",
} as const;

/** "Close reasons", from the paragraph under the order states. */
export const CLOSE_REASON = {
  duplicate: "PO trùng",
  not_an_order: "Không phải đơn hàng",
  superseded: "Đã có bản thay thế",
  cannot_supply: "Không cung cấp được",
} as const;

/** "Quote case states". */
export const QUOTE_STATE = {
  received: "Đã nhận",
  ycbg_drafted: "Đã soạn YCBG",
  ycbg_recorded: "Đã lập YCBG trên Bravo",
  sent_to_design: "Chờ Design",
  design_replied: "Design đã phản hồi",
  spec_discussion: "Thảo luận spec với khách",
  priced: "Đã định giá",
  pending_approval: "Chờ duyệt",
  returned: "Bị trả lại định giá",
  approved: "Đã duyệt",
  sent: "Đã gửi khách",
  master_list_recorded: "Đã ghi master list",
  declined: "Từ chối báo giá",
} as const;

/** "Decline reasons", from the paragraph under the quote states. */
export const DECLINE_REASON = {
  not_our_product: "Không phải sản phẩm của công ty",
  design_cannot: "Design không làm được",
  customer_rejected_spec: "Khách không đồng ý spec",
  commercial: "Lý do thương mại",
} as const;

/** "Message dispositions". */
export const MESSAGE_DISPOSITION = {
  case_created: "Đã tạo hồ sơ",
  attached_to_case: "Đã gắn vào hồ sơ",
  routed_to_sales: "Chuyển Sales xử lý",
  not_yet_processed: "Chưa xử lý",
} as const;

/** "Routing reasons", from the paragraph under the message dispositions. */
export const ROUTING_REASON = {
  delivery_change: "Đổi lịch giao — PC, DW2",
  complaint: "Khiếu nại — QA",
  design_reply_unmatched: "Phản hồi Design không khớp YCBG",
  sample_request: "Yêu cầu hàng mẫu",
  customer_unknown: "Chưa xác định được khách hàng",
  attachment_unreadable: "Không đọc được file",
  other: "Khác",
} as const;

/** "Finding dispositions". */
export const FINDING_DISPOSITION = {
  open: "Chưa quyết định",
  accepted: "Chấp nhận (có lý do)",
  corrected_by_sales: "Sales sửa giá trị",
  ask_customer: "Yêu cầu khách sửa",
} as const;

/** "Finding codes": the order checks and the quotation findings. */
export const FINDING_CODE = {
  code_unmapped: "Mã chưa có trong convert list",
  code_ambiguous: "Nhiều mã ứng viên",
  price_mismatch: "Đơn giá lệch báo giá",
  currency_mismatch: "Khác tiền tệ với báo giá",
  uom_mismatch: "Khác đơn vị tính",
  quotation_missing: "Không có báo giá còn hiệu lực",
  lme_band_mismatch: "Sai mức LME",
  moq_violation: "Dưới MOQ",
  pack_multiple: "Không chẵn quy cách đóng gói",
  line_total_mismatch: "Tổng dòng không khớp hoặc thiếu dòng",
  value_uncertain: "Giá trị đọc chưa chắc chắn",
  customer_unknown: "Chưa xác định được khách hàng",
  duplicate_po: "PO gửi trùng",
  requested_date_short_lt: "Ngày yêu cầu ngắn hơn lead time",
  missing_noc_esf: "Thiếu NOC/ESF",
  revised_po: "PO sửa đổi",
  revision_without_base: "PO sửa đổi chưa thấy bản gốc",
  customer_temporary: "Khách hàng mã tạm thời",
  sender_unverified: "Chưa xác thực người gửi",
  rfq_incomplete: "Yêu cầu báo giá thiếu thông tin",
  price_below_policy_floor: "Giá dưới mức sàn",
  price_floor_unknown: "Không tính được giá sàn",
  price_basis_mismatch: "Căn cứ giá đồng không đúng",
  above_target_price: "Cao hơn giá khách mong muốn",
} as const;

/** "Roles and permission sets": the Vietnamese name of each key. */
export const SALES_ROLE = {
  sales_pic: "Sales phụ trách (PIC)",
  sales_head: "Trưởng bộ phận Sales",
  sales_viewer: "Lãnh đạo (xem tổng hợp)",
  sales_price_evidence: "Xem giá đã báo cho khách khác",
  sales_quote_approver: "Người duyệt báo giá thay",
  sales_export_control: "PIC kiểm soát xuất khẩu",
} as const;

/** The glossary tables the test compares, by the heading they sit under. */
export const GLOSSARY_TABLES = {
  "Value states": VALUE_STATE,
  "Mapping status (customer code → PRV code)": MAPPING_STATUS,
  "Order case states": ORDER_STATE,
  "Quote case states": QUOTE_STATE,
  "Message dispositions": MESSAGE_DISPOSITION,
  "Finding dispositions": FINDING_DISPOSITION,
  "Finding codes": FINDING_CODE,
  "Roles and permission sets": SALES_ROLE,
} as const;

/** The reason lists written as prose in CONTEXT.md, by the line's lead word. */
export const GLOSSARY_LISTS = {
  "Close reasons": CLOSE_REASON,
  "Decline reasons": DECLINE_REASON,
  "Routing reasons": ROUTING_REASON,
} as const;

// ------------------------------------------------- the screen's own words --

/** The next step a work item names (`WorkItem.action`, `_ORDER_NEXT`). */
export const ACTION = {
  self_check: "Tự kiểm và quyết định từng cờ",
  bravo_entry: "Nhập Bravo và ghi số đơn",
  cross_check: "Kiểm chéo với Bravo",
  confirm: "Gửi xác nhận cho khách",
  apply_change: "Áp dụng thay đổi PO trên Bravo",
  draft_ycbg: "Soạn YCBG",
  record_ycbg: "Ghi số YCBG trên Bravo",
  send_to_design: "Gửi Design",
  price: "Định giá",
  settle_spec: "Chốt spec với khách",
  submit: "Trình duyệt báo giá",
  approve: "Duyệt báo giá",
  reprice: "Định giá lại",
  send: "Gửi báo giá cho khách",
  record_master_list: "Xác nhận master list",
} as const;

/** How far this slice takes a surveyed step (`dw_sales.domain.process.Coverage`). */
export const STEP_COVERAGE = {
  yes: "DW1 làm",
  suggestion: "DW1 gợi ý",
  mock: "Trên dữ liệu giả lập",
  out: "Ngoài phạm vi (DW2)",
} as const;

export const PROCEDURE = {
  "WIV-03-012": "Đơn hàng (WIV-03-012)",
  "WIV-03-023": "Báo giá (WIV-03-023)",
} as const;

/** Flags a reader raises on a value it does not take on trust. */
export const REGION_FLAG = {
  hidden_sheet: "Sheet ẩn",
  hidden_row: "Dòng ẩn",
  hidden_column: "Cột ẩn",
  font_matches_fill: "Chữ trùng màu nền",
  formula_without_cached_value: "Công thức chưa có giá trị",
} as const;

/** The fields a source anchor names, as a person reads them. */
export const FIELD = {
  po_no: "Số PO",
  revision: "Lần sửa",
  po_date: "Ngày PO",
  currency: "Tiền tệ",
  buyer: "Bên mua",
  total: "Tổng",
  line_no: "Dòng",
  customer_item_code: "Mã hàng của khách",
  description: "Mô tả",
  quantity: "Số lượng",
  uom: "Đơn vị tính",
  unit_price: "Đơn giá",
  amount: "Thành tiền",
  requested_date: "Ngày yêu cầu",
  needed_by: "Ngày cần hàng",
  target_price: "Giá mong muốn",
  rfq_no: "Số RFQ",
  rfq_date: "Ngày RFQ",
  quote_due: "Hạn báo giá",
  ycbg_no: "Số YCBG",
  bp_code: "Mã BP",
  spec_no: "Số spec",
  prv_code: "Mã PRV",
  copper_kg_per_km: "Đồng (kg/km)",
} as const;

/** Waits the overview measures apart from DW1's own time. */
export const TIME_BUCKET = {
  dw: "DW1 xử lý",
  sales: "Sales quyết định",
  design: "Chờ Design",
  approver: "Chờ người duyệt",
  customer: "Chờ khách hàng",
} as const;

/** The files DW1 renders (ticket 06's artifact table), by kind. */
export const ARTIFACT_KIND = {
  bravo_upload: "Tệp nhập Bravo (mẫu giả lập)",
  cross_check_sheet: "Phiếu kiểm chéo",
  confirmation_draft: "Thư xác nhận PO (nháp)",
  portal_checklist: "Danh sách xác nhận trên cổng của khách",
  correction_request: "Thư yêu cầu khách sửa PO (nháp)",
  change_summary: "Tóm tắt thay đổi cho Bravo",
  convert_list_proposal: "Đề xuất bổ sung bảng quy đổi mã",
  design_code_request: "Phiếu nhờ Design tạo mã",
  cannot_supply_draft: "Thư báo không cung cấp được (nháp)",
  ycbg_draft: "YCBG (nháp, mẫu giả lập)",
  design_request_draft: "Thư gửi Design (nháp)",
  spec_discussion_draft: "Thư thảo luận spec (nháp)",
  decline_draft: "Thư từ chối báo giá (nháp)",
  quotation_preview: "Tài liệu báo giá (bản xem trước)",
  quotation_final: "Tài liệu báo giá (bản đã duyệt)",
  send_draft: "Thư gửi báo giá (nháp)",
  master_list_update: "Cập nhật master list",
} as const;

/** The language a draft is written in (`Customer.language`). */
export const LANGUAGE = {
  vi: "tiếng Việt",
  en: "tiếng Anh",
  ja: "tiếng Nhật",
} as const;

/** A label for `code` from `table`; an unknown code shows as itself. */
export function label<T extends Record<string, string>>(
  table: T,
  code: string | null | undefined,
): string {
  if (!code) return "";
  return (table as Record<string, string>)[code] ?? code;
}
