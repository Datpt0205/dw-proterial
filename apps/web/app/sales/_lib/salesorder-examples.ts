import type { SalesSchemas } from "@dw/api-client";

/**
 * A customer's SalesOrder rules learned from a worked example (ticket 38,
 * dw_sales ADR 0013): the words the customer's screen and the approval use
 * for an example, its replay and why "Gửi duyệt" is closed. The server
 * decides every one of them; these only say it.
 */
export type SalesOrderExample = SalesSchemas["SalesOrderExampleView"];
export type CellDifference = SalesSchemas["CellDifference"];

/** The most a file of the pair may weigh, as the service holds it. */
export const MAX_EXAMPLE_BYTES = 5 * 1024 * 1024;

export const EXAMPLE_STATUS: Record<SalesOrderExample["status"], string> = {
  queued: "Đang đọc",
  replayed: "Đã chạy lại",
  refused: "Không nhận đề xuất",
  unavailable: "Chưa có đề xuất",
  failed: "Không đọc được",
  submitted: "Đã gửi duyệt",
};

export const EXAMPLE_PROBLEM: Record<
  SalesSchemas["LearnProblem"]["code"],
  string
> = {
  header_differs: "Tệp của PIC không theo mẫu tệp nhập Bravo của công ty",
  column_outside_layout: "Quy tắc nêu cột mẫu không có",
  rule_invalid: "Quy tắc ngoài các bước DW biết",
  constant_not_alone: "Chữ cố định phải là bước duy nhất của cột",
  constant_not_in_file: "Chữ cố định không có trên mọi dòng của tệp PIC",
  constant_from_po: "Chữ cố định là giá trị của chính PO này",
  model_unavailable: "Mô hình không trả lời được",
  model_not_configured: "Máy chủ này chưa có mô hình",
  model_quota: "Đã hết lượt dùng mô hình trong ngày",
};

export const DIFFERENCE_PROBLEM: Record<CellDifference["problem"], string> = {
  value_differs: "Khác giá trị",
  row_missing: "Thiếu dòng",
  row_extra: "Thừa dòng",
  row_refused: "Dòng không tạo được",
  value_missing: "Không có giá trị",
  not_text: "Không phải chữ",
  not_a_number: "Không phải số",
  not_a_date: "Không phải ngày",
  lookup_missing: "Dữ liệu chủ không có",
};

export const DIFFERENCE_SOURCE: Record<CellDifference["source"], string> = {
  layout: "Mẫu tệp nhập",
  rule: "Quy tắc của khách",
  row: "Cả dòng",
};

/** Why "Gửi duyệt" is closed for ``example``; null when it is open. */
export function submitBlocked(example: SalesOrderExample): string | null {
  if (example.status === "submitted") return "Ví dụ này đã được gửi duyệt.";
  if (example.status === "queued")
    return "DW đang đọc hai tệp và chạy lại; chờ kết quả.";
  if (example.status !== "replayed")
    return "Chưa có quy tắc nào chạy lại khớp: xem lý do bên dưới.";
  if (!example.rules)
    return "Mẫu tệp nhập đã ra đúng tệp của PIC: khách không cần quy tắc riêng.";
  if (!example.submittable)
    return "Chạy lại chưa khớp tệp của PIC: chỉ gửi duyệt khi không còn ô nào khác.";
  return null;
}

/** "36 ô khớp · 0 ô khác · 2 dòng", or what the replay found. */
export function replaySummary(replay: SalesSchemas["Replay"]): string {
  const rows =
    replay.rows_expected === replay.rows_got
      ? `${replay.rows_got} dòng`
      : `${replay.rows_got}/${replay.rows_expected} dòng`;
  const differing = replay.differences_total;
  return `${replay.cells_compared - Math.min(differing, replay.cells_compared)} ô khớp · ${differing} ô khác · ${rows}`;
}

/** The columns the PIC filled that DW leaves for the person who pastes. */
export function leftForPerson(replay: SalesSchemas["Replay"]): string[] {
  return replay.left_blank
    .filter((b) => b.filled_rows > 0)
    .map((b) => `${b.column} (${b.header}): PIC điền ${b.filled_rows} dòng`);
}

type ColumnRule = SalesSchemas["ColumnRule"];
type Step = ColumnRule["steps"][number];

const TABLE: Record<SalesSchemas["Lookup"]["table"], string> = {
  convert_list: "convert list của khách",
  item_name: "tên mã hàng",
  item_specification: "spec của mã hàng",
  item_standard_length: "chiều dài chuẩn của mã hàng",
  item_unit: "đơn vị của mã hàng",
  item_category: "nhóm hàng",
  item_colour: "màu của mã hàng",
};

const ROUNDING: Record<SalesSchemas["Round"]["mode"], string> = {
  half_up: "làm tròn",
  down: "làm tròn xuống",
  up: "làm tròn lên",
};

/** One step of a column's rule, in words. */
export function stepWords(step: Step): string {
  switch (step.step) {
    case "copy":
      return "giữ nguyên";
    case "constant":
      return `chữ cố định “${step.value}”`;
    case "lookup":
      return `tra ${TABLE[step.table]}${step.key ? ` theo ${step.key}` : ""}`;
    case "unit_factor":
      return `đổi ${step.from} → ${step.to}`;
    case "shift_days":
      return step.days < 0
        ? `lùi ${-step.days} ngày`
        : `cộng ${step.days} ngày`;
    case "round":
      return `${ROUNDING[step.mode]} ${step.places} số lẻ`;
    case "cut":
      return `lấy ký tự ${step.start ?? 0} đến ${step.end ?? "hết"}`;
    case "concat":
      return `nối ${step.sources.join(", ")}${step.separator ? ` (cách “${step.separator}”)` : ""}`;
    case "multiply":
      return `nhân ${step.source}`;
  }
}

/** "AF ← requested_date: lùi 10 ngày". */
export function ruleWords(rule: ColumnRule): string {
  const start = rule.field ?? rule.customer ?? "";
  const steps = rule.steps.map(stepWords).join(", ");
  return `${rule.column}${start ? ` ← ${start}` : ""}${steps ? `: ${steps}` : ""}`;
}

/** The customers whose rules a version changes, against the version in force. */
export function changedCustomers(
  before: Record<string, unknown>,
  after: Record<string, unknown>,
): string[] {
  const was = (before.customers ?? {}) as Record<string, unknown>;
  const now = (after.customers ?? {}) as Record<string, unknown>;
  return [...new Set([...Object.keys(was), ...Object.keys(now)])]
    .filter((code) => JSON.stringify(was[code]) !== JSON.stringify(now[code]))
    .sort();
}
