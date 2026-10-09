import type { SalesCurrency } from "@dw/api-client";

/**
 * The one place an amount of money is turned into text for the screen.
 *
 * Vietnamese grouping everywhere ("18.450.000.000", decimal comma), and the
 * unit written the way the briefs write it: "đ" after a dong amount, not the
 * "₫" `Intl`'s currency style prints, and the ISO code after any other
 * ("USD", "JPY"). The number of decimals shown is the currency's, never fewer
 * than the amount carries up to that limit: a unit price below a cent (or a
 * fraction of a yen) is shown, not rounded into a different price.
 *
 * The currencies are the API's enum (`SalesCurrency`, generated from
 * OpenAPI), so a currency the API adds fails to compile here until it has a
 * format; `__tests__/money.test.ts` walks the enum in the OpenAPI snapshot.
 */
export type Currency = SalesCurrency;

const FORMATS: Record<Currency, { format: Intl.NumberFormat; unit: string }> = {
  VND: {
    format: new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }),
    unit: "đ",
  },
  USD: {
    format: new Intl.NumberFormat("vi-VN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 4,
    }),
    unit: "USD",
  },
  // The yen has no minor unit; a unit price of cable per metre can still
  // carry a fraction, which is shown rather than rounded away.
  JPY: {
    format: new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }),
    unit: "JPY",
  },
};

/** The currencies this file formats, for whatever lists them. */
export const CURRENCIES = Object.keys(FORMATS) as Currency[];

/**
 * A decimal as the API writes it ("1150", "0.6150") or a number. A string
 * goes to `Intl` as a string, so a long amount is grouped digit for digit
 * instead of through a float.
 */
type Decimal = number | string;

function numeric(value: Decimal): number | `${number}` {
  return typeof value === "number" ? value : (value.trim() as `${number}`);
}

/**
 * "18.450.000.000 đ", "1.234,50 USD", "12.300 JPY". The space before the unit
 * does not break, so a narrow cell never puts the unit on a line of its own.
 */
export function formatMoney(amount: Decimal, currency: Currency): string {
  const { format, unit } = FORMATS[currency];
  return `${format.format(numeric(amount) as number)} ${unit}`;
}

const QUANTITY = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 4 });

/** A quantity, a MOQ, a weight: Vietnamese grouping, decimal comma, no unit. */
export function formatQuantity(value: Decimal): string {
  return QUANTITY.format(numeric(value) as number);
}

// ------------------------------------------------------------- money input --

/**
 * What a person typed or pasted into an amount field, as the decimal string
 * the API takes ("18450000000", "0.615"), or null when it cannot be read
 * without guessing. Either grouping is read: "18.450.000.000",
 * "18,450,000,000", "18450000000 đ", and a decimal comma ("12,5") or a dot
 * decimal ("0.6150"). A lone separator followed by exactly three digits
 * ("1.150", "1,150") is read the Vietnamese way, as grouping, unless it
 * starts with 0 ("0.615" is a decimal); anything that
 * mixes them inconsistently is refused rather than scaled by 1 000.
 */
export function parseAmountInput(
  text: string | null | undefined,
): string | null {
  if (text === null || text === undefined) return null;
  const raw = text.replace(/[^\d.,-]/g, "");
  if (!/\d/.test(raw) || raw.indexOf("-") > 0) return null;
  const sign = raw.startsWith("-") ? "-" : "";
  const body = raw.replace(/^-/, "");
  const dots = (body.match(/\./g) ?? []).length;
  const commas = (body.match(/,/g) ?? []).length;
  let integer: string;
  let fraction = "";
  if (dots && commas) {
    // The separator that comes last is the decimal one; it appears once.
    const decimal = body.lastIndexOf(".") > body.lastIndexOf(",") ? "." : ",";
    const group = decimal === "." ? "," : ".";
    if ((decimal === "." ? dots : commas) !== 1) return null;
    [integer, fraction] = body.split(decimal) as [string, string];
    if (!/^\d{1,3}([,.]\d{3})*$/.test(integer) || integer.includes(decimal))
      return null;
    integer = integer.split(group).join("");
  } else if (dots + commas === 0) {
    integer = body;
  } else {
    const separator = dots ? "." : ",";
    const parts = body.split(separator);
    // A group never starts with 0: "0.615" is a decimal, "1.150" is grouping.
    const grouping =
      parts.length > 2 ||
      (parts[1]!.length === 3 && /^[1-9]\d{0,2}$/.test(parts[0]!));
    if (grouping) {
      if (
        !parts.slice(1).every((p) => /^\d{3}$/.test(p)) ||
        !/^[1-9]\d{0,2}$/.test(parts[0]!)
      )
        return null;
      integer = parts.join("");
    } else {
      [integer, fraction] = parts as [string, string];
    }
  }
  if (!/^\d+$/.test(integer) || !/^\d*$/.test(fraction)) return null;
  const digits = integer.replace(/^0+(?=\d)/, "");
  return `${sign}${digits}${fraction ? `.${fraction}` : ""}`;
}

/** The text an amount field shows for a decimal string: grouped, decimal comma. */
export function formatAmountInput(
  value: string | number | null | undefined,
): string {
  if (value === null || value === undefined || value === "") return "";
  const [integer, fraction] = String(value).split(".");
  const grouped = (integer ?? "").replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return fraction !== undefined ? `${grouped},${fraction}` : grouped;
}

// ------------------------------------------------------- dong, in short --

/** No-break space: the unit never wraps onto a line of its own. */
const NBSP = " ";

/**
 * `18,45 tỷ`. Not for a value being compared with a threshold or being
 * corrected: 14.995.000.000 and 15.000.000.000 both read "15 tỷ".
 */
export function formatMoneyShort(amount: number): string {
  const billions = Math.round((amount / 1_000_000_000) * 100) / 100;
  return `${String(billions).replace(".", ",")}${NBSP}tỷ`;
}

// ---------------------------------------------------------- bằng chữ --

const DIGITS = [
  "không",
  "một",
  "hai",
  "ba",
  "bốn",
  "năm",
  "sáu",
  "bảy",
  "tám",
  "chín",
];
const SCALES = ["", "nghìn", "triệu"];

/** One group of three digits; `full` when a higher group precedes it. */
function readTriple(n: number, full: boolean): string {
  const hundreds = Math.floor(n / 100);
  const tens = Math.floor((n % 100) / 10);
  const units = n % 10;
  const words: string[] = [];
  if (full || hundreds > 0) words.push(DIGITS[hundreds]!, "trăm");
  if (tens === 0) {
    if (units > 0 && words.length > 0) words.push("linh");
  } else if (tens === 1) {
    words.push("mười");
  } else {
    words.push(DIGITS[tens]!, "mươi");
  }
  if (units > 0) {
    if (units === 1 && tens >= 2) words.push("mốt");
    else if (units === 5 && tens >= 1) words.push("lăm");
    else words.push(DIGITS[units]!);
  }
  return words.join(" ");
}

/** Below a billion; `full` when a higher part was already read. */
function readUnderBillion(n: number, full: boolean): string {
  const groups = [n % 1000, Math.floor(n / 1000) % 1000, Math.floor(n / 1e6)];
  const parts: string[] = [];
  for (let at = 2; at >= 0; at -= 1) {
    const group = groups[at]!;
    if (group === 0) continue;
    const triple = readTriple(group, full || parts.length > 0);
    parts.push(SCALES[at] ? `${triple} ${SCALES[at]}` : triple);
  }
  return parts.join(" ");
}

/** Billions repeat the scale: 1.234.000.000.000 is "một nghìn hai trăm ba
 * mươi bốn tỷ", not "một nghìn tỷ hai trăm ba mươi bốn tỷ". */
function readNumber(n: number, full: boolean): string {
  if (n < 1e9) return readUnderBillion(n, full);
  const billions = Math.floor(n / 1e9);
  const rest = n % 1e9;
  const head = `${readNumber(billions, full)} tỷ`;
  return rest > 0 ? `${head} ${readUnderBillion(rest, true)}` : head;
}

/**
 * "Bằng chữ": `Mười tám tỷ bốn trăm năm mươi triệu đồng` for 18.450.000.000.
 * The wording of a legal document stays its context's to decide; this is the
 * reading a form prints under an amount.
 */
export function moneyInWords(amount: number): string {
  if (!Number.isSafeInteger(amount)) {
    throw new RangeError("Số tiền phải là số nguyên trong giới hạn");
  }
  if (amount === 0) return "Không đồng";
  const text = `${amount < 0 ? "âm " : ""}${readNumber(Math.abs(amount), false)} đồng`;
  return text.charAt(0).toUpperCase() + text.slice(1);
}
