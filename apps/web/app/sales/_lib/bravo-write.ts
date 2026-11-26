import { formatDate } from "../../../lib/dates";
import { formatQuantity } from "../../../lib/money";
import { BRAVO_WRITE_FIELD } from "./labels";

/** What a Bravo write changes on an SO line (`BravoLineWriteView.field`). */
export type BravoWriteField = keyof typeof BRAVO_WRITE_FIELD;

/**
 * A proposed Bravo write's value as a person reads it, on the order page's
 * panel and on the approval alike: a day, a quantity, or a cancel, whose
 * `after` reads "Hủy: <reason>" and whose `before` is the quantity it ends.
 */
export function bravoWriteValue(
  field: BravoWriteField,
  value: string | null,
): string {
  if (value === null) return "—";
  if (field === "confirmed_date") return formatDate(value);
  if (field === "cancel" && value.startsWith("Hủy")) return value;
  return formatQuantity(value);
}
