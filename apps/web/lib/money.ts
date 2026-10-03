/**
 * The one place an amount of money is turned into text for the screen.
 *
 * Vietnamese grouping everywhere ("18.450.000.000", decimal comma), and the
 * unit written the way the briefs write it: "đ" after a dong amount, not the
 * "₫" `Intl`'s currency style prints, and "USD" after a dollar amount. The
 * number of decimals shown is the currency's, never fewer than the amount
 * carries up to that limit: a unit price below a cent is shown, not rounded
 * into a different price.
 */

export type Currency = "VND" | "USD";

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
};

/**
 * "18.450.000.000 đ", "1.234,50 USD". The space before the unit does not
 * break, so a narrow cell never puts the unit on a line of its own.
 */
export function formatMoney(amount: number, currency: Currency): string {
  const { format, unit } = FORMATS[currency];
  return `${format.format(amount)}\u00a0${unit}`;
}
