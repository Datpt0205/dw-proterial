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
