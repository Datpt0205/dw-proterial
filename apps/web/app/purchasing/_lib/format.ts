import {
  CURRENCIES,
  formatMoney,
  formatQuantity,
  type Currency,
} from "../../../lib/money";

/**
 * An amount in the currency DW2 names it in, through `lib/money.ts`. A
 * currency that file has no format for is still shown with its code, never
 * as a bare number that reads as dong.
 */
export function money(amount: string | number, currency: string): string {
  return (CURRENCIES as string[]).includes(currency)
    ? formatMoney(amount, currency as Currency)
    : `${formatQuantity(amount)} ${currency}`;
}
