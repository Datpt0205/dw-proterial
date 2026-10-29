import type { SalesSchemas } from "@dw/api-client";

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
  not_opened: "Chưa mở nguồn",
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

/**
 * Why a cross-check decision was not applied (`UnappliedDecision.reason_code`,
 * ticket 14). A code not listed is shown as itself.
 */
export const NOT_APPLIED_REASON = {
  stale_case_version: "Hồ sơ đã đổi phiên bản sau khi quyết định",
  decision_stale: "Hồ sơ không còn chờ quyết định này",
  source_not_served: "Người kiểm chưa mở nguồn của phiên bản này",
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
  malware_detected: "Tệp đính kèm có mã độc",
  reply_to_case: "Trả lời về hồ sơ đang xử lý",
  other: "Khác",
} as const;

/** What Sales does with a message routed to them, by its reason: the note
 * DW1 keeps beside it is a technical diagnostic in English, for IT. */
export const ROUTING_ADVICE = {
  delivery_change:
    "Khách xin đổi lịch giao: chuyển cho PC từ hộp thư của bạn (DW1 soạn sẵn bản chuyển bên dưới khi đọc được thư).",
  complaint:
    "Khách khiếu nại: chuyển cho QA từ hộp thư của bạn (DW1 soạn sẵn bản chuyển bên dưới khi đọc được thư).",
  design_reply_unmatched:
    "Thư giống phản hồi của Design nhưng không khớp YCBG nào đang chờ: kiểm tra số YCBG, rồi bấm “DW xử lý lại” khi YCBG đã gửi Design.",
  sample_request:
    "Khách xin hàng mẫu: xem tình trạng kiểm soát xuất khẩu của khách rồi xử lý theo quy trình hàng mẫu.",
  customer_unknown:
    "DW1 không xác định được khách hàng từ địa chỉ gửi và tài liệu: xem khách DW1 đoán bên dưới rồi xác nhận, hoặc chọn khách khác; nếu là khách mới, thêm vào Dữ liệu chủ.",
  attachment_unreadable:
    "DW1 không đọc được tệp đính kèm: mở tệp gốc để xử lý tay, hoặc thiết lập mẫu PO nếu đây là PO của khách.",
  malware_detected:
    "Tệp đính kèm có mã độc nên DW1 không mở: đừng mở tệp, báo IT.",
  reply_to_case:
    "Thư trả lời về một hồ sơ đang xử lý: mở hồ sơ để xem và trả lời khách.",
  other:
    "Thư không phải PO hay yêu cầu báo giá: đọc thư và xử lý nếu cần, rồi đánh dấu đã xử lý.",
} as const;

/** "Processing jobs": where a message's "DW xử lý" stands (ticket 25). */
export const PROCESSING_STATE = {
  queued: "Đang chờ DW1",
  running: "DW1 đang xử lý",
  done: "DW1 đã xử lý",
  failed: "DW1 chưa xử lý được",
} as const;

/** "Processing failures": why a message's job failed. */
export const PROCESSING_ERROR = {
  quota: "Hết lượt chạy DW1 trong ngày của gói",
  not_permitted: "Người yêu cầu không còn quyền xử lý hộp thư",
  paused: "DW1 tạm dừng trước khi xử lý",
  conflict: "Thư đã được xử lý trong lúc chờ",
  not_found: "Hộp thư không còn thư này",
  unavailable: "Chưa quét hoặc chưa đọc được tệp đính kèm",
  model_retry: "Mô hình chưa đọc được thư, DW1 thử lại sau",
  abandoned: "Lượt xử lý bị gián đoạn",
  error: "Lỗi khi xử lý",
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
  legacy_encoding: "Font tiếng Việt cũ (TCVN3/VNI)",
  requested_date_missing: "Dòng chưa có ngày yêu cầu",
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
  sales_rules_editor: "Người đề xuất quy tắc",
  sales_dw1: "DW1 (tài khoản dịch vụ)",
} as const;

/** The glossary tables the test compares, by the heading they sit under. */
export const GLOSSARY_TABLES = {
  "Value states": VALUE_STATE,
  "Mapping status (customer code → PRV code)": MAPPING_STATUS,
  "Order case states": ORDER_STATE,
  "Quote case states": QUOTE_STATE,
  "Message dispositions": MESSAGE_DISPOSITION,
  "Processing jobs": PROCESSING_STATE,
  "Finding dispositions": FINDING_DISPOSITION,
  "Finding codes": FINDING_CODE,
  "Roles and permission sets": SALES_ROLE,
} as const;

/** The reason lists written as prose in CONTEXT.md, by the line's lead word. */
export const GLOSSARY_LISTS = {
  "Close reasons": CLOSE_REASON,
  "Decline reasons": DECLINE_REASON,
  "Routing reasons": ROUTING_REASON,
  "Processing failures": PROCESSING_ERROR,
  "Not-applied reasons": NOT_APPLIED_REASON,
} as const;

// ------------------------------------------------- the screen's own words --

/** The kinds a model reads a message no reader accepted as (ticket 31). */
export const INTENT_KIND = {
  po: "Đặt hàng",
  quote_request: "Yêu cầu báo giá",
  design_reply: "Phản hồi Design",
  reply_to_case: "Trả lời về hồ sơ",
  delivery_change: "Đổi lịch giao",
  complaint: "Khiếu nại",
  sample_request: "Yêu cầu hàng mẫu",
  other: "Khác",
} as const;

/** What a model read a customer's reply in a case's thread as (ticket 32). */
export const REPLY_KIND = {
  accepts_spec: "Đồng ý thông số",
  rejects_spec: "Không đồng ý thông số",
  counter_proposal: "Đề nghị khác / đồng ý có điều kiện",
  sends_corrected_po: "Gửi PO đã sửa",
  keeps_po_as_is: "Giữ nguyên PO",
  question: "Hỏi lại",
  unclear: "Không rõ",
} as const;

/** The existing step a reply proposes; Sales confirms it (ticket 32). */
export const REPLY_STEP = {
  settle_spec: "Ghi khách đã đồng ý spec",
  decline_customer_rejected_spec: "Từ chối báo giá vì khách không đồng ý spec",
  resume_review: "Xem xét lại đơn, quyết lại từng cờ đã gửi khách",
  await_revised_po: "Chờ PO đã sửa: DW1 đọc khi PO đến",
} as const;

/** Who read a value of a model reading of a description (ticket 28). */
export const READ_BY = {
  code: "DW1 tính từ chữ",
  model: "Mô hình đọc, cần kiểm",
} as const;

/** The attributes a description reading names (`description_reading.py`). */
export const READ_ATTRIBUTE = {
  family: "Họ cáp",
  stranding: "Kiểu lõi",
  conductor: "Ruột dẫn",
  shield: "Chống nhiễu",
  colour: "Màu",
  packaging: "Đóng gói",
  cores: "Số lõi",
  gauge: "Tiết diện",
  pack_length_m: "Chiều dài mỗi cuộn (m)",
  spec_no: "Số spec",
} as const;

/** Why DW1 did not take a model's reading (`NotUnderstood`). */
export const READING_REASON = {
  line_missing: "mô hình bỏ qua dòng này",
  no_attribute: "mô tả không nêu thuộc tính nào",
  span_not_found: "chữ mô hình chỉ ra không có trong mô tả",
  span_repeated: "chữ mô hình chỉ ra xuất hiện hơn một lần",
  spans_overlap: "hai thuộc tính được đọc từ cùng một chữ",
  value_unparsed: "DW1 không đọc được giá trị từ chữ đó",
  text_uncovered: "còn chữ không thuộc thuộc tính nào",
  digit_in_label: "nhãn chứa con số",
  value_refused: "giá trị không có mặt hàng nào mang",
} as const;

/** The next step a work item names (`WorkItem.action`, `_ORDER_NEXT`). */
export const ACTION = {
  self_check: "Tự kiểm và quyết định từng cờ",
  bravo_entry: "Nhập Bravo và ghi số đơn",
  cross_check: "Kiểm chéo với Bravo",
  confirm: "Gửi xác nhận cho khách",
  apply_change: "Áp dụng thay đổi PO trên Bravo",
  resend_cross_check: "Gửi kiểm chéo lại",
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

/**
 * What an event on a case's history did (`CaseEvent.action`, the actions
 * `case_store.py` writes). An action not listed shows as its code.
 */
export const CASE_EVENT = {
  "order.checked": "DW1 đọc và kiểm tra PO",
  "order.revised": "Nhận PO sửa đổi",
  "order.review_started": "Bắt đầu tự kiểm",
  "order.review_resumed": "Tự kiểm lại",
  "order.finding_disposed": "Quyết định một cờ",
  "order.value_corrected": "Sửa một giá trị",
  "order.mapping_confirmed": "Xác nhận mã PRV",
  "order.pc_date_recorded": "Ghi ngày PC trả lời",
  "order.correction_requested": "Yêu cầu khách sửa PO",
  "order.prepared": "Tự kiểm xong",
  "order.bravo_recorded": "Ghi số đơn Bravo",
  "order.cross_checked": "Kiểm chéo đạt",
  "order.returned": "Kiểm chéo trả lại",
  "order.cross_check_resent": "Gửi kiểm chéo lại",
  "order.decision_not_applied": "Quyết định không áp dụng được",
  "order.confirmed": "Gửi xác nhận cho khách",
  "order.closed": "Đóng hồ sơ",
  "order.reassigned": "Giao cho người khác",
  "quote.received": "Nhận yêu cầu báo giá",
  "quote.ycbg_drafted": "Soạn YCBG",
  "quote.ycbg_recorded": "Ghi số YCBG trên Bravo",
  "quote.sent_to_design": "Gửi Design",
  "quote.design_replied": "Design phản hồi",
  "quote.spec_start": "Bắt đầu thảo luận spec",
  "quote.spec_settle": "Chốt spec",
  "quote.spec_ask_design_again": "Hỏi lại Design",
  "quote.finding_answered": "Trả lời một cờ",
  "quote.value_confirmed": "Xác nhận một giá trị",
  "quote.priced": "Định giá",
  "quote.submitted": "Trình duyệt",
  "quote.approved": "Duyệt báo giá",
  "quote.returned": "Trả lại định giá",
  "quote.signed_copy_attached": "Tải lên bản báo giá đã ký",
  "quote.sent": "Gửi báo giá cho khách",
  "quote.master_list_recorded": "Ghi master list",
  "quote.declined": "Từ chối báo giá",
  "quote.reassigned": "Giao cho người khác",
} as const;

/** How far this slice takes a surveyed step (`dw_sales.domain.process.Coverage`). */
export const STEP_COVERAGE = {
  yes: "Trong phạm vi DW1",
  suggestion: "DW1 gợi ý",
  mock: "Trên dữ liệu giả lập",
  out: "Ngoài phạm vi (DW2)",
} as const;

export const PROCEDURE = {
  "WIV-03-012": "Đơn hàng (WIV-03-012)",
  "WIV-03-023": "Báo giá (WIV-03-023)",
} as const;

/** How the bytes a PO was read from were made (ticket 27), as the case's facts say. */
export const DERIVATION = {
  converted: "Đọc từ bản chuyển đổi",
  ocr: "Đọc bằng OCR",
} as const;

/** Flags a reader raises on a value it does not take on trust. */
export const REGION_FLAG = {
  hidden_sheet: "Sheet ẩn",
  hidden_row: "Dòng ẩn",
  hidden_column: "Cột ẩn",
  font_matches_fill: "Chữ trùng màu nền",
  formula_without_cached_value: "Công thức chưa có giá trị",
  model_read: "Mô hình đọc, cần xác nhận",
  new_layout: "Mẫu PO mới duyệt, cần xác nhận",
  print_differs: "Bản in PDF ghi khác",
  ocr: "Đọc bằng OCR, cần xác nhận",
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
  schedules: "Lịch giao (ngày: số lượng)",
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

/**
 * What makes a case move, by the action the process page serves on each move
 * (`process_settings.EdgeAction`). Keyed by every action the API names, so
 * one it adds fails the typecheck until it has words; `process-labels.test.ts`
 * also holds the keys to the OpenAPI enum.
 */
export const EDGE_ACTION: Record<SalesSchemas["EdgeAction"], string> = {
  check: "DW1 đọc và kiểm tra",
  close: "Đóng hồ sơ",
  start_review: "Bắt đầu tự kiểm",
  prepare: "Tự kiểm xong",
  request_correction: "Yêu cầu khách sửa PO",
  revise: "Khách gửi PO sửa đổi",
  resume_review: "Tự kiểm lại",
  record_bravo_entry: "Ghi số đơn Bravo",
  edit: "Sửa sau khi tự kiểm",
  cross_check: "Kiểm chéo",
  return: "Trả lại",
  confirm: "Gửi xác nhận cho khách",
  apply_change: "Áp dụng thay đổi PO",
  draft_ycbg: "Soạn YCBG",
  record_ycbg: "Ghi số YCBG trên Bravo",
  send_to_design: "Gửi Design",
  record_design_reply: "Ghi phản hồi của Design",
  discuss_spec: "Thảo luận spec với khách",
  settle_spec: "Chốt spec",
  price: "Định giá",
  submit: "Trình duyệt",
  approve: "Duyệt báo giá",
  send: "Gửi báo giá cho khách",
  record_master_list: "Ghi master list",
  decline: "Từ chối báo giá",
};

/** What the domain refuses a move without (`process_settings.EdgeGuard`). */
export const EDGE_GUARD: Record<SalesSchemas["EdgeGuard"], string> = {
  blocking_findings: "Không còn cờ chặn",
  ask_customer: "Có cờ gửi khách",
  entry_compared: "Đã đối chiếu Bravo với PO",
  approval: "Cần duyệt",
  maker_checker: "Người làm không tự duyệt",
  cross_check_not_required: "Quy tắc không yêu cầu kiểm chéo",
  export_control_hold: "Không bị giữ vì kiểm soát xuất khẩu",
  pc_confirmed_date: "PC đã xác nhận ngày",
  request_findings: "Đã trả lời cờ của yêu cầu",
};

/** Who takes a move: DW1, Sales, or someone outside whose mail DW1 reads. */
export const MOVE_ACTOR: Record<
  SalesSchemas["ProcessEdgeView"]["actor"],
  string
> = {
  dw: "DW1",
  sales: "Sales",
  design: "Design",
  approver: "Người duyệt",
  customer: "Khách hàng",
};

/**
 * A model step as the process page shows it: switched on and its latest
 * measurement passing (the model is used), switched on and not passing (a
 * person does the step), or switched off.
 */
export const AI_STATE = {
  on: "AI bật · đạt",
  failing: "AI bật · chưa đạt — người làm",
  off: "AI tắt",
} as const;

/**
 * The same states in the few words a process-map tile has room for on one
 * line (2026-10-24, Đạt); the tile's details and the drawer say the whole
 * `AI_STATE` words.
 */
export const AI_STATE_SHORT: Record<keyof typeof AI_STATE, string> = {
  on: "AI bật · đạt",
  failing: "AI bật · chưa đạt",
  off: "AI tắt",
};

/** What one entry of "DW1 đã làm gì" was (`ActivityEntry.kind`). */
export const ACTIVITY_KIND: Record<
  SalesSchemas["ActivityEntry"]["kind"],
  string
> = {
  read: "DW1 đọc",
  route: "DW1 phân loại và chuyển thư",
  check: "Kiểm tra của DW1 không nhận câu trả lời",
  to_person: "Đọc được, nhưng không mã hàng nào khớp",
  model_unavailable: "Mô hình không trả lời",
};

/** Kết quả of an entry: DW1 carried it, a person does it, or no answer came. */
export const ACTIVITY_RESULT = {
  accepted: "Đã chấp nhận",
  to_person: "Chuyển cho người",
  unavailable: "Model không trả lời",
} as const;

/**
 * Why DW1 left an item to a person, or refused a value inside one, for the
 * reason codes no other table here names (`domain/activity.py`, the layout
 * checks, the request and hand-off readers). `reasonLabel` in `activity.ts`
 * reads this, `READING_REASON` and `ROUTING_REASON`, and composes the
 * per-field codes (`description_not_found`).
 */
export const ACTIVITY_REASON: Record<string, string> = {
  no_item_fits: "Đọc được, nhưng không mã hàng nào khớp",
  nothing_located: "Không tìm thấy trong thư điều mô hình chỉ ra",
  not_used: "Mô hình đã trả lời, nhưng DW1 không dùng được",
  refused: "DW1 không nhận đề xuất của mô hình",
  other: "Lý do khác",
  incomplete_proposal: "Đề xuất của mô hình thiếu phần",
  label_not_found: "Không thấy nhãn trên mẫu",
  label_repeated: "Nhãn xuất hiện hơn một lần trên mẫu",
  columns_not_on_one_row: "Tên cột không nằm trên cùng một dòng",
  unreadable: "Không đọc được tệp theo đề xuất",
  no_total: "Không thấy tổng của PO",
  line_total_mismatch: "Tổng dòng không khớp tổng PO",
  quantity_not_whole: "Số lượng không phải số nguyên",
  price_out_of_quoted_range: "Đơn giá ngoài khoảng đã báo",
  requested_before_po_date: "Ngày yêu cầu trước ngày PO",
  requested_is_po_date: "Ngày yêu cầu trùng ngày PO",
  requested_date_empty: "Cột ngày giao không có ngày nào",
  no_item_known: "Không mã hàng nào của khách được biết",
  part_unknown: "Mô hình chỉ tới phần không có trong thư",
  line_unanchored: "Không xác định được vị trí dòng trong tệp",
  quantity_unit_unknown: "Số lượng không có đơn vị DW1 báo giá",
};

/** The fields an activity entry or a refusal names that `FIELD` does not. */
export const ACTIVITY_FIELD = {
  kind: "Loại thư",
  language: "Ngôn ngữ",
  stated_target_price: "Giá khách nêu",
  new_quantity: "Số lượng mới",
  new_date: "Ngày giao mới",
  so_no: "Số đơn bán (SO)",
  lot: "Số lô",
  line: "Dòng",
  item: "Mặt hàng mẫu",
  quote: "Câu khách viết",
} as const;

/** A status that waits on nobody (`STATUS_BUCKETS` has no holder): done. */
export const NO_HOLDER = "Đã xong";

/** A case kind's lane, as the process page names its tabs. */
export const CASE_KIND = {
  order: "Đơn hàng",
  quote: "Báo giá",
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
  quote_signed: "Bản báo giá đã ký (tải lên)",
} as const;

/** The language a draft is written in (`Customer.language`). */
export const LANGUAGE = {
  vi: "tiếng Việt",
  en: "tiếng Anh",
  ja: "tiếng Nhật",
} as const;

/** A customer's standing in the master data (`Customer.status`). */
export const CUSTOMER_STATUS = {
  official: "Chính thức",
  temporary: "Mã tạm thời",
} as const;

/** Where a customer's order confirmation goes (`ConfirmationChannel`). */
export const CONFIRMATION_CHANNEL = {
  email: "Thư",
  portal: "Cổng khách hàng",
} as const;

/** An item's cable family (`Item.family`). */
export const CABLE_FAMILY = {
  hook_up_wire: "Dây đơn",
  multi_core_cable: "Cáp nhiều lõi",
} as const;

/** A label for `code` from `table`; an unknown code shows as itself. */
export function label<T extends Record<string, string>>(
  table: T,
  code: string | null | undefined,
): string {
  if (!code) return "";
  return (table as Record<string, string>)[code] ?? code;
}
