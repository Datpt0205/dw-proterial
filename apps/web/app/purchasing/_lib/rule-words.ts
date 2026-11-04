import type { PurchasingRuleKey } from "@dw/api-client";
import { money } from "./format";
import { FINDING, LEVEL, STEP } from "./labels";

/**
 * A rule document read as words: the settings page never shows a field code,
 * JSON or YAML (Đạt, 2026-11-01). A path is named by the part of the company's
 * process it sets ("Bậc duyệt 2 · Hạn mức đến"), a value in the words a person
 * uses for it ("20.000.000 đ", "AI tự làm", "không giới hạn").
 *
 * A path this table does not know is named "một mục khác của quy tắc", never
 * dropped: a change nobody can read must still show that it is there.
 */
export const RULE_NAME: Record<PurchasingRuleKey, string> = {
  purchasing_rules: "Quy tắc mua hàng",
  purchasing_automation: "Công tắc tự động",
  purchasing_master_data: "Dữ liệu chủ",
};

const REQUIRED: Record<string, string> = {
  budget_code: "mã ngân sách",
  need_by: "ngày cần hàng",
  estimated_unit_price: "giá ước tính",
};

const DATE_FORMAT: Record<string, string> = {
  "dd/mm/yyyy": "ngày/tháng/năm",
  "yyyy-mm-dd": "năm-tháng-ngày",
  "mm/dd/yyyy": "tháng/ngày/năm",
};

const BRAVO_FIELD: Record<string, string> = {
  po_ref: "số PO của DW2",
  pr_no: "số yêu cầu mua hàng",
  order_date: "ngày đặt hàng",
  supplier_code: "mã nhà cung cấp",
  supplier_name: "tên nhà cung cấp",
  item_code: "mã vật tư",
  description: "diễn giải",
  quantity: "số lượng",
  unit: "đơn vị tính",
  unit_price: "đơn giá",
  currency: "loại tiền",
  amount: "thành tiền",
  need_by: "ngày cần",
  budget_code: "mã ngân sách",
  department: "bộ phận",
};

const TIER_SCOPE: Record<string, string> = {
  "purchasing.approve.tier1": "quyền duyệt bậc 1",
  "purchasing.approve.tier2": "quyền duyệt bậc 2",
  "purchasing.approve.tier3": "quyền duyệt bậc 3",
};

type Words = (value: unknown, document: Record<string, unknown>) => string;

const list =
  (table?: Record<string, string>): Words =>
  (value) =>
    Array.isArray(value)
      ? value.length === 0
        ? "không có"
        : value
            .map((v) => (table ? (table[String(v)] ?? String(v)) : String(v)))
            .join(", ")
      : String(value);
const named =
  (table: Record<string, string>): Words =>
  (value) =>
    table[String(value)] ?? String(value);
/** The brief's days, as `domain.brief.Weekday` names them. */
const WEEKDAY: Record<string, string> = {
  mon: "thứ Hai",
  tue: "thứ Ba",
  wed: "thứ Tư",
  thu: "thứ Năm",
  fri: "thứ Sáu",
  sat: "thứ Bảy",
  sun: "Chủ nhật",
};

const plain: Words = (value) => String(value);
const percent: Words = (value) => `${String(value).replace(".", ",")}%`;
const days: Words = (value) => `${String(value)} ngày`;
const years: Words = (value) => `${String(value)} năm`;
const yesNo: Words = (value) => (value ? "có" : "không");
const limit: Words = (value, document) => {
  if (value === null || value === undefined) return "không giới hạn";
  const approval = document.approval as { currency?: string } | undefined;
  return money(value as string, approval?.currency ?? "VND");
};

/** Each known path, its pattern with `#` for an index, its name and its value's words. */
const PATHS: [RegExp, (index: number) => string, Words][] = [
  [/^policy_version$/, () => "Số phiên bản", plain],
  [
    /^pr_form\.required$/,
    () => "Yêu cầu mua hàng · Thông tin bắt buộc",
    list(REQUIRED),
  ],
  [
    /^pr_form\.max_lines$/,
    () => "Yêu cầu mua hàng · Số dòng hàng tối đa",
    plain,
  ],
  [
    /^pr_form\.currencies$/,
    () => "Yêu cầu mua hàng · Loại tiền được dùng",
    list(),
  ],
  [
    /^pr_form\.default_currency$/,
    () => "Yêu cầu mua hàng · Loại tiền khi không ghi",
    plain,
  ],
  [/^internal_domains$/, () => "Tên miền thư của công ty", list()],
  [/^approval\.currency$/, () => "Duyệt · Loại tiền của hạn mức", plain],
  [
    /^approval\.tiers\.(\d+)\.up_to$/,
    (i) => `Bậc duyệt ${i + 1} · Hạn mức đến`,
    limit,
  ],
  [
    /^approval\.tiers\.(\d+)\.label$/,
    (i) => `Bậc duyệt ${i + 1} · Người duyệt`,
    plain,
  ],
  [
    /^approval\.tiers\.(\d+)\.scope$/,
    (i) => `Bậc duyệt ${i + 1} · Quyền`,
    named(TIER_SCOPE),
  ],
  [
    /^approval\.price_tolerance_percent$/,
    () => "Duyệt · Giá ước tính được cao hơn giá tham chiếu",
    percent,
  ],
  [
    /^approval\.escalate$/,
    () => "Duyệt · Phát hiện đưa thẳng lên bậc cuối",
    list(FINDING),
  ],
  [
    /^approval\.reapproval_tolerance_percent$/,
    () => "Duyệt lại · Được vượt hạn mức đã duyệt",
    percent,
  ],
  [
    /^rfq\.max_suppliers_per_line$/,
    () => "Hỏi giá · Số nhà cung cấp tối đa mỗi dòng",
    plain,
  ],
  [/^rfq\.reply_days$/, () => "Hỏi giá · Thời gian chờ trả lời", days],
  [/^retention\.case_years$/, () => "Lưu trữ · Hồ sơ mua hàng", years],
  [/^retention\.mail_outcome_days$/, () => "Lưu trữ · Kết quả xử lý thư", days],
  [/^retention\.mailbox_days$/, () => "Lưu trữ · Thư đã lưu", days],
  [/^brief\.at$/, () => "Bản tin sáng · Giờ gửi", plain],
  [/^brief\.days$/, () => "Bản tin sáng · Ngày gửi", list(WEEKDAY)],
  [/^bravo_po\.mock$/, () => "File Bravo · Mẫu dựng sẵn của nền tảng", yesNo],
  [/^bravo_po\.sheet$/, () => "File Bravo · Tên trang tính", plain],
  [
    /^bravo_po\.date_format$/,
    () => "File Bravo · Cách ghi ngày",
    named(DATE_FORMAT),
  ],
  [
    /^bravo_po\.columns\.(\d+)\.header$/,
    (i) => `File Bravo · Cột ${i + 1} · Tiêu đề`,
    plain,
  ],
  [
    /^bravo_po\.columns\.(\d+)\.field$/,
    (i) => `File Bravo · Cột ${i + 1} · Dữ liệu`,
    named(BRAVO_FIELD),
  ],
  [
    /^steps\.(mail_sorting|pr_drafting|submission|rfq|po_drafting|quote_reading|confirmation_reading)$/,
    () => "",
    named(LEVEL),
  ],
];

const OTHER = "Một mục khác của quy tắc";

/** The name of what a path sets, in words. */
export function pathName(path: string): string {
  const step = /^steps\.([a-z_]+)$/.exec(path);
  if (step && step[1]! in STEP)
    return `Công tắc · ${STEP[step[1] as keyof typeof STEP]}`;
  for (const [pattern, name] of PATHS) {
    const match = pattern.exec(path);
    if (match) return name(match[1] === undefined ? 0 : Number(match[1]));
  }
  return OTHER;
}

/** What a path holds in `document`, in words; "chưa có" where it holds nothing. */
export function valueWords(
  path: string,
  document: Record<string, unknown>,
): string {
  const value = at(document, path);
  if (value === undefined) return "chưa có";
  for (const [pattern, , words] of PATHS)
    if (pattern.test(path)) return words(value, document);
  return Array.isArray(value) || (value !== null && typeof value === "object")
    ? "đã đổi"
    : String(value);
}

export function at(document: unknown, path: string): unknown {
  let node: unknown = document;
  for (const part of path.split(".")) {
    if (node === null || typeof node !== "object") return undefined;
    node = Array.isArray(node)
      ? node[Number(part)]
      : (node as Record<string, unknown>)[part];
  }
  return node;
}

/**
 * The paths where two documents differ, a list of scalars counting as one
 * value (a person reads "VND, USD" as one setting), in document order.
 */
export function changedPaths(
  before: unknown,
  after: unknown,
  prefix = "",
): string[] {
  const isObject = (v: unknown): v is Record<string, unknown> =>
    v !== null && typeof v === "object";
  const scalars = (v: unknown) =>
    Array.isArray(v) && v.every((x) => !isObject(x));
  if (
    !isObject(before) ||
    !isObject(after) ||
    scalars(before) ||
    scalars(after)
  )
    return JSON.stringify(before) === JSON.stringify(after) ? [] : [prefix];
  const keys = [...new Set([...Object.keys(before), ...Object.keys(after)])];
  return keys.flatMap((key) =>
    changedPaths(before[key], after[key], prefix ? `${prefix}.${key}` : key),
  );
}

/** What every version carries and nobody sets: its number and its name. */
const BOOKKEEPING = new Set([
  "policy_version",
  "version",
  "policy_id",
  "schema_version",
]);

export interface Change {
  path: string;
  name: string;
  before: string;
  after: string;
}

/** Each difference between the version in force and a draft, in words. */
export function changesInWords(
  before: Record<string, unknown>,
  after: Record<string, unknown>,
): Change[] {
  return changedPaths(before, after)
    .filter((path) => !BOOKKEEPING.has(path))
    .map((path) => ({
      path,
      name: pathName(path),
      before: valueWords(path, before),
      after: valueWords(path, after),
    }));
}

/**
 * Why the platform's checks gave no draft, in words: a problem is a code and
 * a path (`path_unknown:approver`), never a word of the model's.
 */
export function problemWords(problem: string): string {
  const [code, path] = problem.split(/:(.*)/s) as [string, string | undefined];
  const part = path ? pathName(path) : null;
  const where = part && part !== OTHER ? ` (${part})` : "";
  switch (code) {
    case "nothing_understood":
      return "DW2 chưa hiểu cần đổi gì: viết rõ hơn, ví dụ “hạn mức bậc 1 lên 50 triệu”.";
    case "path_unknown":
      return "DW2 muốn đổi một mục quy tắc không có, nên không có bản nháp.";
    case "type_changed":
      return `Giá trị DW2 đề xuất không đúng loại của mục đó${where}.`;
    case "document_invalid":
      return `Bản nháp không qua được kiểm tra của quy tắc${where}: một mục vượt giới hạn cho phép, chẳng hạn công tắc vượt mức cao nhất của bước.`;
    case "placeholder_changed":
    case "digit_invented":
      return `DW2 đưa vào một con số không có trong lời bạn viết${where}, nên không có bản nháp.`;
    default:
      return "Bản nháp không qua được kiểm tra của quy tắc.";
  }
}
