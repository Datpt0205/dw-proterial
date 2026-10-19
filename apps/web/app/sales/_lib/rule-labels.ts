import type { RuleKey } from "./rules";
import { ARTIFACT_KIND, FIELD, FINDING_CODE, LANGUAGE } from "./labels";
import { nodeAt, type DocPath, type RuleNode } from "./rule-schema";

/**
 * The words of the rules editor (ticket 40): a label, a short help and a unit
 * for every field of every key's schema, keyed by key and label path
 * (`rule-schema.ts` `labelPath`: a map key is `*`, a list position `[]`).
 *
 * The schema decides what a document holds; this table only names it. A
 * field the API adds later is drawn under its humanised name until it is
 * labelled here, and `__tests__/rule-labels.test.ts` fails CI meanwhile: it
 * walks `contracts/jsonschema/sales_rules.json`, which
 * `scripts/generate_contracts.py` writes from the models.
 */
export interface FieldWords {
  label: string;
  help?: string;
  /** Shown after a number: "giờ", "ngày", "USD/tấn". */
  unit?: string;
  /** A list item's or map entry's heading: "Mức LME", "Tuyến cước". */
  item?: string;
  /** A map entry's value, when it is one control: "Mức độ", "Số phút". */
  value?: string;
}

/** Fields every key's documents carry. A key's own table wins over this. */
const COMMON: Record<string, FieldWords> = {
  schema_version: {
    label: "Phiên bản lược đồ",
    help: "Do hệ thống quy định, không sửa.",
  },
  policy_id: { label: "Mã quy tắc", help: "Do hệ thống quy định, không sửa." },
  copy_id: { label: "Mã bộ nội dung", help: "Do hệ thống quy định, không sửa." },
  policy_version: {
    label: "Số phiên bản mới",
    help: "Ba số cách nhau bằng dấu chấm (1.2.0). Không được trùng số nền tảng đã phát hành hay số công ty đã dùng.",
  },
  version: {
    label: "Số phiên bản mới",
    help: "Ba số cách nhau bằng dấu chấm (1.2.0). Không được trùng số nền tảng đã phát hành hay số công ty đã dùng.",
  },
  mock: {
    label: "Đánh dấu là mẫu giả lập",
    help: "Bật khi nội dung chưa phải của công ty: mọi tệp tạo từ nó ghi rõ là mẫu giả lập.",
  },
  description: { label: "Ghi chú về phiên bản" },
};

const TEMPLATE_HELP =
  "Giá trị trong ${…} do hệ thống điền từ hồ sơ; chỉ dùng giá trị mà mẫu này có.";

export const RULE_FIELDS: Record<RuleKey, Record<string, FieldWords>> = {
  sales_order_rules: {
    price: { label: "Đơn giá" },
    "price.relative_tolerance": {
      label: "Sai lệch đơn giá cho phép",
      help: "Tỷ lệ so với đơn giá báo giá: 0 là phải bằng đúng, 0,02 là lệch tối đa 2%.",
      unit: "phần",
    },
    lme_band: { label: "Mức LME" },
    "lme_band.months_before_po_date": {
      label: "Tháng LME dùng để đối chiếu",
      help: "Số tháng trước tháng của ngày PO: 0 là chính tháng đó, 1 là tháng trước.",
      unit: "tháng trước",
    },
    short_lead_time: { label: "Ngày yêu cầu ngắn hơn lead time" },
    "short_lead_time.from": {
      label: "Tính lead time từ",
    },
    "short_lead_time.lead_time": { label: "Lead time lấy theo" },
    "short_lead_time.day_basis": {
      label: "Cách đếm ngày",
      help: "Hiện chỉ đếm theo ngày lịch (chưa có lịch nghỉ).",
    },
    cross_check_required: {
      label: "Bắt buộc kiểm chéo trước khi xác nhận",
      help: "Tắt: đơn đã nhập Bravo được xác nhận ngay, không cần người thứ hai kiểm.",
    },
    export_control_mode: {
      label: "Cờ thiếu NOC/ESF",
      help: "Cảnh báo: xác nhận được sau khi người phụ trách kiểm soát xuất khẩu ghi nhận. Chặn: không xác nhận được dù đã ghi nhận.",
    },
    export_control: { label: "Kiểm soát xuất khẩu" },
    "export_control.denial_list_max_age_days": {
      label: "Tuổi tối đa của kết quả rà danh sách cấm",
      help: "Kết quả cũ hơn số ngày này vào ngày nhận PO coi như chưa rà.",
      unit: "ngày",
    },
    intake: {
      label: "Giới hạn tệp đính kèm",
      help: "Tệp vượt một giới hạn không được đọc; thư chuyển cho Sales là không đọc được.",
    },
    "intake.max_attachment_bytes": {
      label: "Dung lượng tối đa một tệp",
      help: "10 000 000 byte ≈ 10 MB.",
      unit: "byte",
    },
    "intake.max_unpacked_bytes": {
      label: "Dung lượng tối đa sau giải nén",
      unit: "byte",
    },
    "intake.max_sheets": { label: "Số sheet tối đa", unit: "sheet" },
    "intake.max_pages": { label: "Số trang tối đa", unit: "trang" },
    "intake.max_cells": { label: "Số ô tối đa", unit: "ô" },
    fiscal_year_start_month: {
      label: "Tháng bắt đầu năm tài chính",
      help: "4: năm tài chính 2026 từ tháng 4/2026 đến tháng 3/2027. ESF được đối chiếu theo năm tài chính của ngày PO.",
      unit: "tháng",
    },
    model_assist: {
      label: "Bước có mô hình hỗ trợ",
      help: "Nền tảng tắt tất cả. Chỉ bật một bước khi đánh giá thực tế của bước đó đạt yêu cầu; mọi giá trị mô hình đọc vẫn cần Sales xác nhận.",
    },
    "model_assist.description_attributes": {
      label: "Đọc mô tả hàng chưa có trong convert list",
    },
    "model_assist.message_intent": {
      label: "Phân loại thư không có tài liệu đọc được",
    },
    "model_assist.rfq_extraction": {
      label: "Đọc yêu cầu báo giá không theo mẫu",
    },
    "model_assist.unread_retry_hours": {
      label: "Thời gian thử đọc lại thư",
      help: "Trong thời gian này, thư mô hình chưa đọc được sẽ được thử lại; sau đó chuyển Sales với ghi chú DW1 chưa hiểu.",
      unit: "giờ",
    },
    "model_assist.reply_intent": {
      label: "Đọc thư trả lời của khách trong hồ sơ",
    },
    "model_assist.request_handoff": {
      label: "Soạn nháp chuyển giao cho PC/QA từ thư",
    },
    "model_assist.layout_proposal": {
      label: "Đề xuất ánh xạ cho mẫu PO mới",
    },
    layout_onboarding: { label: "Mẫu PO mới duyệt" },
    "layout_onboarding.uncertain_first_pos": {
      label: "Số PO đầu cần xác nhận từng giá trị",
      help: "Các PO đầu tiên đọc qua một mẫu PO mới hoặc vừa sửa giữ mọi giá trị ở trạng thái chưa chắc chắn.",
      unit: "PO",
    },
    findings: {
      label: "Mức độ của từng cờ",
      help: "Chặn: lỗi phải xử lý. Cảnh báo: hiển thị và ghi nhận. Mọi cờ đều phải được quyết định trước khi chuẩn bị đơn; phải có đủ mọi mã cờ.",
      item: "Cờ",
      value: "Mức độ",
    },
  },
  sales_kpi: {
    order_confirmation_target_hours: {
      label: "Mục tiêu xác nhận đơn hàng",
      help: "Từ lúc nhận PO đến lúc đơn được xác nhận.",
      unit: "giờ",
    },
    quotation_target_days: {
      label: "Mục tiêu gửi báo giá",
      help: "Từ lúc nhận yêu cầu đến lúc gửi báo giá.",
      unit: "ngày",
    },
    manual_baseline_minutes: {
      label: "Thời gian làm tay của từng bước",
      help: "Một lần làm bước đó bằng tay hôm nay mất bao lâu; phải có đủ mọi bước khảo sát.",
      unit: "phút",
      item: "Bước",
      value: "Số phút",
    },
  },
  sales_quote_rules: {
    reference_price: {
      label: "Giá tham chiếu",
      help: "Tắt: bằng chứng giá chỉ đưa dữ kiện, không đưa con số tham chiếu.",
    },
    "reference_price.band_below_percent": {
      label: "Biên dưới giá tham chiếu",
      unit: "%",
    },
    "reference_price.band_above_percent": {
      label: "Biên trên giá tham chiếu",
      unit: "%",
    },
    copper_basis: { label: "Giá theo đồng" },
    validity_days: {
      label: "Thời hạn hiệu lực của báo giá",
      help: "Tính cả ngày phát hành báo giá.",
      unit: "ngày",
    },
    design_mailboxes: {
      label: "Hộp thư của Design",
      help: "Chỉ thư từ các địa chỉ này và đã được hệ thống thư xác thực mới được đọc là trả lời của Design. Danh sách trống: không nhận trả lời nào.",
      item: "Địa chỉ",
    },
  },
  sales_pricing: {
    copper_adders: {
      label: "Phụ phí đồng theo mức LME",
      help: "Các mức phải liền nhau và theo thứ tự; giá LME ngoài bảng thì không tính được phần đồng.",
      item: "Mức LME",
    },
    "copper_adders[].band": { label: "Khoảng giá LME" },
    "copper_adders[].band.kind": {
      label: "Loại khoảng",
      help: "Do hệ thống quy định, không sửa.",
    },
    "copper_adders[].band.low_usd_per_tonne": {
      label: "Từ (gồm)",
      unit: "USD/tấn",
    },
    "copper_adders[].band.high_usd_per_tonne": {
      label: "Đến (không gồm)",
      unit: "USD/tấn",
    },
    "copper_adders[].adder_usd_per_tonne": {
      label: "Phụ phí cộng vào giá LME",
      unit: "USD/tấn",
    },
    floor_margin: {
      label: "Biên giá sàn",
      help: "Giá sàn = phần đồng × (1 + biên). 0,18 là 18%.",
      unit: "phần",
    },
    freight: {
      label: "Cước vận chuyển",
      help: "Tuyến không có trong bảng thì không có cước, và bằng chứng giá ghi rõ.",
      item: "Tuyến",
    },
    "freight[].incoterm": { label: "Điều kiện giao hàng" },
    "freight[].destination": {
      label: "Vùng đến",
      help: "Mã vùng: chữ thường không dấu, số và dấu gạch dưới (domestic_north).",
    },
    "freight[].usd_per_km": { label: "Cước", unit: "USD/km cáp" },
  },
  sales_emails: {
    sender: { label: "Người gửi" },
    "sender.from": {
      label: "Thư cho khách gửi từ",
      help: "Trả lời của khách luôn về hộp thư chung của Sales.",
    },
    "sender.shared_sales": { label: "Hộp thư chung của Sales" },
    "sender.shared_sales.address": { label: "Địa chỉ" },
    "sender.shared_sales.display_name": { label: "Tên hiển thị" },
    emails: {
      label: "Mẫu thư",
      help: "Theo loại thư, rồi theo ngôn ngữ. Loại thư thiếu mẫu ở ngôn ngữ của khách thì không soạn được, không tự lấy ngôn ngữ khác.",
      item: "Loại thư",
    },
    "emails.*": { label: "Theo ngôn ngữ", item: "Ngôn ngữ" },
    "emails.*.*.subject": {
      label: "Tiêu đề",
      help: `Một dòng. ${TEMPLATE_HELP}`,
    },
    "emails.*.*.body": { label: "Nội dung", help: TEMPLATE_HELP },
    "emails.*.*.line": {
      label: "Mẫu một dòng hàng",
      help: `Mỗi dòng hàng viết theo mẫu này rồi ghép vào \${lines} của nội dung. ${TEMPLATE_HELP}`,
    },
    "emails.*.*.words": {
      label: "Cụm từ cố định",
      help: "Cụm từ hệ thống chèn theo mã; thiếu một mã thì thư không soạn được.",
      item: "Cụm từ",
    },
  },
  sales_documents: {
    documents: {
      label: "Mẫu chứng từ",
      help: "Theo loại chứng từ, rồi theo ngôn ngữ.",
      item: "Loại chứng từ",
    },
    "documents.*": { label: "Theo ngôn ngữ", item: "Ngôn ngữ" },
    "documents.*.*.title": { label: "Tiêu đề" },
    "documents.*.*.labels": {
      label: "Nhãn đầu phiếu",
      help: "Thiếu một nhãn phiếu cần thì phiếu không tạo được.",
      item: "Nhãn",
    },
    "documents.*.*.columns": {
      label: "Tên cột",
      help: "Thiếu một tên cột phiếu cần thì phiếu không tạo được.",
      item: "Cột",
    },
    "documents.*.*.words": {
      label: "Cụm từ cố định",
      help: TEMPLATE_HELP,
      item: "Cụm từ",
    },
  },
  sales_bravo_upload: {
    sheet_name: {
      label: "Tên sheet nhập",
      help: "Tối đa 31 ký tự, không dùng [ ] : * ? / \\ '.",
    },
    columns: {
      label: "Các cột của tệp nhập Bravo",
      help: "Theo thứ tự trong tệp. Giá trị mỗi cột do hệ thống điền từ đơn hàng.",
      item: "Cột",
    },
    "columns[].field": { label: "Giá trị" },
    "columns[].header": { label: "Tiêu đề cột" },
  },
  sales_handoffs: {
    unknown: {
      label: "Chữ thay cho giá trị chưa rõ",
      help: "Viết vào chỗ một giá trị hệ thống không lấy được từ thư.",
    },
    line: { label: "Mẫu một dòng thay đổi" },
    quote: { label: "Mẫu một câu trích của khách" },
    templates: {
      label: "Mẫu chuyển giao",
      help: "Theo loại yêu cầu của khách.",
      item: "Loại",
    },
    "templates.*.to": { label: "Chuyển cho" },
    "templates.*.subject": { label: "Tiêu đề" },
    "templates.*.body": { label: "Nội dung" },
  },
};

/**
 * The words for a value a choice or a closed map key may take: a severity,
 * a mode, a finding code, a step, a language. Collected once: these values
 * mean the same wherever they appear.
 */
const VALUES: Record<string, string> = {
  error: "Chặn",
  warning: "Cảnh báo",
  warn: "Cảnh báo, xác nhận được sau khi ghi nhận",
  block_confirmation: "Chặn xác nhận",
  received_date: "Ngày nhận PO",
  item_standard: "Lead time chuẩn của mã hàng",
  quotation: "Lead time trong báo giá",
  calendar: "Ngày lịch",
  fixed: "Giá cố định",
  lme_band: "Theo mức LME",
  EXW: "EXW (giao tại xưởng)",
  FCA: "FCA (giao cho người chở)",
  FOB: "FOB (giao lên tàu)",
  CIF: "CIF (gồm cước và bảo hiểm)",
  DAP: "DAP (giao tại nơi đến)",
  DDP: "DDP (giao đã nộp thuế)",
  drafting_pic: "Hộp thư của PIC soạn thư",
  shared_sales: "Hộp thư chung của Sales",
  delivery_change: "Đổi lịch giao",
  complaint: "Phản ánh chất lượng",
  sample_request: "Xin hàng mẫu",
  pc: "PC (kế hoạch sản xuất)",
  qa: "QA (chất lượng)",
  customer_code: "Mã khách hàng",
  suggested_delivery_date: "Ngày giao DW1 đề xuất",
  common: "Phần chung của mọi phiếu",
  ...FIELD,
  ...LANGUAGE,
  ...FINDING_CODE,
};

/** "O3" → "Đơn hàng, bước 3"; "Q12" → "Báo giá, bước 12". */
function stepLabel(value: string): string | null {
  const step = /^([OQ])(\d{1,2})$/.exec(value);
  if (!step) return null;
  return `${step[1] === "O" ? "Đơn hàng" : "Báo giá"}, bước ${step[2]} (${value})`;
}

/** The words for a value, or null when this table has none. */
export function knownValueLabel(value: string): string | null {
  return (
    VALUES[value] ??
    (ARTIFACT_KIND as Record<string, string>)[value] ??
    stepLabel(value)
  );
}

/** The words for a value, else the value itself. */
export function valueLabel(value: string): string {
  return knownValueLabel(value) ?? value;
}

/** "max_attachment_bytes" → "Max attachment bytes": a field not labelled yet. */
export function humanise(name: string): string {
  const words = name.replace(/[_.]+/g, " ").trim();
  return words ? words[0]!.toUpperCase() + words.slice(1) : name;
}

/** The table's words for a field, or null when it has none. */
export function knownFieldWords(
  key: RuleKey,
  path: string,
): FieldWords | null {
  return RULE_FIELDS[key][path] ?? COMMON[path] ?? null;
}

/** The words for a field, its humanised name when not labelled yet. */
export function fieldWords(key: RuleKey, path: string): FieldWords {
  const known = knownFieldWords(key, path);
  if (known) return known;
  const last = path.replace(/\[\]/g, "").split(".").filter((p) => p !== "*").pop();
  return { label: humanise(last ?? path) };
}

// ------------------------------------------- a document path, in words --

/**
 * "Phụ phí đồng theo mức LME › Mức LME 2 › Từ (gồm)": a document path as a
 * person reads it, for the diff. A map key is named by its value's words (a
 * finding, a language, a kind of mail), a list position by its item's.
 */
export function pathLabel(
  key: RuleKey,
  root: RuleNode,
  path: DocPath,
): string {
  const parts: string[] = [];
  let node: RuleNode | undefined = root;
  let label = "";
  for (const step of path) {
    if (node && node.nullable && node.kind !== "text") node = { ...node, nullable: false } as RuleNode;
    if (node?.kind === "object") {
      label = label ? `${label}.${String(step)}` : String(step);
      parts.push(fieldWords(key, label).label);
      node = node.fields.find((f) => f.name === step)?.node;
    } else if (node?.kind === "map") {
      parts.push(valueLabel(String(step)));
      label = `${label}.*`;
      node = node.value;
    } else if (node?.kind === "list") {
      parts.push(`${fieldWords(key, label).item ?? "Mục"} ${Number(step) + 1}`);
      label = `${label}[]`;
      node = node.item;
    } else {
      parts.push(String(step));
      node = undefined;
    }
  }
  return parts.join(" › ");
}

/** A number as Vietnamese reads it: "9.000", "0,18". */
function formatNumber(value: number): string {
  return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 6 }).format(
    value,
  );
}

function formatScalar(node: RuleNode | undefined, value: unknown): string {
  if (value === null || value === undefined) return "(không có)";
  if (typeof value === "boolean") return value ? "Bật" : "Tắt";
  if (node?.kind === "choice" || node?.kind === "fixed")
    return valueLabel(String(value));
  if (node?.kind === "number" || typeof value === "number") {
    const number = Number(value);
    return Number.isFinite(number) ? formatNumber(number) : String(value);
  }
  if (typeof value === "string") return value === "" ? "(trống)" : value;
  return JSON.stringify(value);
}

/**
 * A value of the document as text: a scalar in words; a section or a list
 * item added or removed whole, one line per field ("Từ (gồm): 9.000").
 */
export function describeValue(
  key: RuleKey,
  root: RuleNode,
  path: DocPath,
  value: unknown,
): string {
  if (value === null || typeof value !== "object")
    return formatScalar(nodeAt(root, path), value);
  const lines: string[] = [];
  const prefix = pathLabel(key, root, path);
  const walk = (v: unknown, p: DocPath) => {
    if (v !== null && typeof v === "object") {
      const entries: [string | number, unknown][] = Array.isArray(v)
        ? v.map((x, i) => [i, x])
        : Object.entries(v as Record<string, unknown>);
      for (const [k, inner] of entries) walk(inner, [...p, k]);
      return;
    }
    const full = pathLabel(key, root, p);
    const name = full.startsWith(`${prefix} › `)
      ? full.slice(prefix.length + 3)
      : full;
    lines.push(`${name}: ${formatScalar(nodeAt(root, p), v)}`);
  };
  walk(value, path);
  return lines.join("\n") || "(trống)";
}
