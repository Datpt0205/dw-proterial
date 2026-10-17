import type { SalesSchemas } from "@dw/api-client";

type Line = SalesSchemas["OrderLineView"];

/**
 * A line's value as it is entered: what Sales typed for it (ticket 15), else
 * as read. DW1's checks run on the entered line (`OrderLine.effective`), so a
 * screen that compares a line against something reads these, not the line's
 * fields as read, or it says lệch where the check passed.
 */
function typed(line: Line, field: string): string | null {
  const value = line.corrections.find((c) => c.field === field)?.value;
  return typeof value === "string" ? value : null;
}

/** The line's unit as it is entered. */
export function enteredUom(line: Line): string {
  return typed(line, "uom") ?? line.uom;
}

/** The line's quantity as it is entered. */
export function enteredQuantity(line: Line): string {
  return typed(line, "quantity") ?? line.quantity;
}
