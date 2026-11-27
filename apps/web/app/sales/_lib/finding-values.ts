import { formatDate } from "../../../lib/dates";
import { formatQuantity } from "../../../lib/money";

/**
 * A finding's `expected` or `actual` as a person reads it (full review,
 * 2026-11-27: "Mong đợi: lme_band · Thực tế: fixed", "<= 0.65" beside
 * "0,705 USD", the NOC/ESF hold in English).
 *
 * The server writes these values (`domain/order_checks.py`,
 * `domain/quotes.py`) and compares them as written when a case is checked
 * again (`orders._carried` keeps a decision only while they are unchanged),
 * so they stay as they are stored and are put into words here, at display.
 * Only the machine words and the shapes those modules write are read; any
 * other value shows as written, never guessed at.
 */

/** Machine words a value is made of, by the finding codes that write them. */
const WORDS: Readonly<Record<string, Readonly<Record<string, string>>>> = {
  // `_basis_mismatch`: the basis prescribed and the one priced.
  price_basis_mismatch: {
    lme_band: "Theo dải LME",
    fixed: "Cố định",
  },
  // `_unknown_floor_factors`: why the floor cannot be computed.
  price_floor_unknown: {
    floor: "Giá sàn tính được",
    copper_weight: "thiếu khối lượng đồng",
    lme: "thiếu giá LME",
    copper_adder: "thiếu phụ phí đồng của dải LME",
    usd_rate: "thiếu tỷ giá USD",
  },
  customer_temporary: {
    official: "Khách chính thức",
    temporary: "Khách tạm",
  },
};

/** The parts `_compliance_finding` joins, in the order it writes them. */
const COMPLIANCE: readonly [RegExp, (...groups: string[]) => string][] = [
  [/^NOC confirmed$/, () => "NOC đã xác nhận"],
  [/^no NOC$/, () => "chưa có NOC"],
  [/^ESF FY(\d{4})$/, (year) => `ESF năm tài chính ${year}`],
  [/^no ESF$/, () => "chưa có ESF"],
  [
    /^denial-list check within (\d+) days$/,
    (days) => `kiểm danh sách cấm trong ${days} ngày`,
  ],
  [
    /^denial-list check (\d{4}-\d{2}-\d{2})$/,
    (day) => `kiểm danh sách cấm ngày ${formatDate(day)}`,
  ],
  [/^no denial-list check$/, () => "chưa kiểm danh sách cấm"],
];

// The price codes whose values are a price or a bound on one (`quotes.py`):
// an amount with a decimal comma, as the page writes every other price. No
// other code's number is touched (a PO number is an identifier).
const PRICED = new Set(["price_below_policy_floor", "above_target_price"]);
const NUMBER = /^-?\d+(\.\d+)?$/;
const COMPARED = /^(<=|>=) (-?\d+(?:\.\d+)?)$/;
// `_basis_mismatch`'s band and month: "10500-11000 @2026-09", "@2026-09",
// "none @2026-09".
const BAND = /^(?:(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)|(none))? ?@(\d{4})-(\d{2})$/;

function compliance(value: string): string | null {
  const parts = value.split(", ").map((part) => {
    for (const [shape, words] of COMPLIANCE) {
      const found = shape.exec(part);
      if (found) return words(...found.slice(1));
    }
    return null;
  });
  return parts.every((p) => p !== null) ? parts.join(", ") : null;
}

function band(value: string): string | null {
  const found = BAND.exec(value);
  if (!found) return null;
  const [, low, high, none, year, month] = found;
  const lme = `LME tháng ${month}/${year}`;
  if (none) return `Không có dải · ${lme}`;
  if (low && high)
    return `${formatQuantity(low)}–${formatQuantity(high)} USD/tấn · ${lme}`;
  return lme;
}

/** `value` of a finding coded `code`, in words; as written when unknown. */
export function findingValueWords(code: string, value: string): string {
  const words = WORDS[code];
  if (words) {
    const parts = value.split(",");
    if (parts.every((p) => Object.hasOwn(words, p)))
      return parts.map((p) => words[p]).join(", ");
  }
  if (code === "missing_noc_esf") return compliance(value) ?? value;
  if (code === "price_basis_mismatch") return band(value) ?? value;
  if (!PRICED.has(code)) return value;
  const compared = COMPARED.exec(value);
  if (compared)
    return `${compared[1] === "<=" ? "≤" : "≥"} ${formatQuantity(compared[2]!)}`;
  return NUMBER.test(value) ? formatQuantity(value) : value;
}
