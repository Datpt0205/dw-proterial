import type {
  PurchaseAutomationLevel,
  PurchaseAutomationStep,
  PurchaseCaseStatus,
  PurchaseFindingCode,
  PurchasingSchemas,
} from "@dw/api-client";

/**
 * The DW2 screens' words, one table per code set. `CONTEXT.md` owns them:
 * `__tests__/labels.test.ts` reads the glossary and fails on a label changed,
 * added or dropped on either side (failure-modes.md #2). Each table is keyed
 * by the generated enum, so a code the API adds fails to compile here first.
 */
export const CASE_STATUS: Record<PurchaseCaseStatus, string> = {
  received: "Đã nhận",
  awaiting_approval: "Chờ duyệt",
  approved: "Đã duyệt",
  rejected: "Từ chối",
  rfq_drafted: "Đang hỏi giá",
  awaiting_reapproval: "Chờ duyệt lại",
  supplier_selected: "Đã chọn nhà cung cấp",
  po_drafted: "Đã soạn PO",
};

export const STEP: Record<PurchaseAutomationStep, string> = {
  mail_sorting: "Phân loại thư đến",
  pr_drafting: "Mở yêu cầu từ thư",
  submission: "Gửi người duyệt",
  rfq: "Soạn thư hỏi giá",
  po_drafting: "Soạn PO và file Bravo",
  quote_reading: "Đọc báo giá của nhà cung cấp",
  confirmation_reading: "Đọc thư xác nhận đơn",
};

export const LEVEL: Record<PurchaseAutomationLevel, string> = {
  ai_auto: "AI tự làm",
  ai_review: "AI làm, người duyệt",
  person: "Người làm",
};

export const MODEL_STEP: Record<
  PurchasingSchemas["PurchasingModelStep"],
  string
> = {
  purchasing_pr_mail_reading: "Đọc yêu cầu từ thư",
  purchasing_supplier_quote_reading: "Đọc báo giá",
  purchasing_order_confirmation_reading: "Đọc thư xác nhận đơn",
};

export const LEVEL_WHY: Record<
  PurchasingSchemas["StepLevelView"]["why"],
  string
> = {
  set: "theo quy tắc của công ty",
  not_measured: "chưa đo trên model của nhà máy",
  unreadable: "số đo không đọc được",
};

export const FINDING: Record<PurchaseFindingCode, string> = {
  item_unknown: "mã hàng chưa có trong danh mục",
  no_reference_price: "chưa có giá tham chiếu",
  currency_mismatch: "giá tham chiếu ở loại tiền khác",
  estimate_above_reference: "giá ước tính cao hơn giá tham chiếu",
  need_by_short: "ngày cần hàng sớm hơn thời gian giao",
  budget_missing: "thiếu mã ngân sách",
  budget_unknown: "mã ngân sách không có",
  over_budget: "vượt ngân sách còn lại",
};

export const BASIS: Record<
  NonNullable<PurchasingSchemas["LineCheck"]["basis"]>,
  string
> = {
  quote: "báo giá còn hạn",
  history: "giá đã mua lần trước",
  estimate: "giá ước tính của người yêu cầu",
};

export const SOURCE: Record<PurchasingSchemas["PrSource"], string> = {
  form: "Biểu mẫu",
  mail: "Thư",
  requester: "Người yêu cầu tự viết",
};

export const MAIL_OUTCOME: Record<PurchasingSchemas["Disposition"], string> = {
  opened: "Đã mở hồ sơ",
  to_person: "Cần người xem",
  supplier: "Thư nhà cung cấp",
};

/** Why a mail went to a person. A form rule's `missing:<field>` is worded by {@link mailReason}. */
export const MAIL_REASON: Record<string, string> = {
  sender_not_internal: "người gửi không thuộc công ty",
  sender_unverified: "hệ thống thư không xác thực được người gửi",
  no_pr_number: "thư không có số yêu cầu mua hàng",
  no_department: "thư không nói bộ phận yêu cầu",
  span_not_found: "DW2 đọc ra một giá trị không có trong thư",
  line_unreadable: "DW2 không đọc trọn được một dòng hàng",
  currency_unreadable: "không rõ đơn vị tiền",
  need_by_unreadable: "không đọc được ngày cần hàng",
  value_malformed: "một giá trị trong thư không đúng dạng",
  no_lines: "thư không có dòng hàng nào",
  too_many_lines: "thư có nhiều dòng hàng hơn quy tắc cho phép",
  currency_not_allowed: "loại tiền quy tắc không cho phép",
  attachment_infected: "tệp đính kèm có mã độc",
  several_documents: "thư có nhiều tệp tài liệu",
  document_too_long: "tệp đính kèm quá dài để đọc trọn",
  attachment_unreadable: "DW2 không đọc được tệp đính kèm",
};

/** Where a value or a text came from: a machine's never reads as a person's. */
export type Mark = "machine_read" | "machine_written" | "template" | "person";

export const MARK: Record<Mark, string> = {
  machine_read: "Máy đọc",
  machine_written: "Máy viết",
  template: "Mẫu cố định",
  person: "Người nhập",
};

export const ROLE: Record<string, string> = {
  purchasing_buyer: "Nhân viên mua hàng",
  purchasing_viewer: "Xem yêu cầu mua hàng",
  purchasing_head: "Trưởng phòng Mua hàng",
  purchasing_requester: "Người yêu cầu mua hàng",
  purchasing_configurer: "Người cấu hình DW2",
  purchasing_dw2: "DW2 tài khoản dịch vụ",
};

export function mailReason(reason: string | null | undefined): string {
  if (!reason) return "không rõ lý do";
  if (reason.startsWith("missing:"))
    return `thiếu ${reason.slice("missing:".length)} mà quy tắc của công ty đòi hỏi`;
  return MAIL_REASON[reason] ?? reason;
}

/** The glossary's lines these tables mirror, by the words each line starts with. */
export const GLOSSARY_LINES: Record<string, Record<string, string>> = {
  "**Case status**": CASE_STATUS,
  Steps: STEP,
  Levels: LEVEL,
  "Model steps": MODEL_STEP,
  "Why a level": LEVEL_WHY,
  Findings: FINDING,
  "Reference bases": BASIS,
  Sources: SOURCE,
  "Mail outcomes": MAIL_OUTCOME,
  "Mail reasons": MAIL_REASON,
  Marks: MARK,
};

/** What a supplier's confirmation differs from its order in (`Difference.field`). */
export const DIFFERENCE: Record<string, string> = {
  quantity: "số lượng",
  unit_price: "đơn giá",
  delivery_on: "ngày giao",
  missing: "thiếu dòng",
  not_ordered: "dòng ngoài đơn",
};
