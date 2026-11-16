import type { SalesSchemas } from "@dw/api-client";

/**
 * A customer's notation (ticket 37): how it writes numbers, dates and a bare
 * "$" or "¥", learned from a value Sales confirmed or set by a person. The
 * values each kind takes come from the server (`choices`); this file only
 * says them in words.
 */
export type CustomerNotation = SalesSchemas["CustomerNotationView"];
export type NotationEntry = SalesSchemas["NotationEntryView"];
export type NotationKind = SalesSchemas["CustomerNotationBody"]["kind"];

/** The kinds, in the order a person reads them. */
export const NOTATION_KINDS: readonly NotationKind[] = [
  "decimal_mark",
  "date_order",
  "dollar_sign",
  "yen_sign",
];

export const NOTATION_KIND: Record<NotationKind, string> = {
  decimal_mark: "Số",
  date_order: "Ngày",
  dollar_sign: "Ký hiệu $",
  yen_sign: "Ký hiệu ¥",
};

const VALUE: Record<string, string> = {
  ",": "1.200 = một nghìn hai trăm",
  ".": "1,200 = một nghìn hai trăm",
  day_first: "05/11 = ngày 5 tháng 11",
  month_first: "05/11 = ngày 11 tháng 5",
};

/** One value of a kind, as a person reads it: a currency by its code. */
export function notationValue(kind: NotationKind, value: string): string {
  if (kind === "dollar_sign") return `$ = ${value}`;
  if (kind === "yen_sign") return `¥ = ${value}`;
  return VALUE[value] ?? value;
}

/** The entry of one kind, if the customer has one. */
export function entryOf(
  view: CustomerNotation | undefined,
  kind: NotationKind,
): NotationEntry | undefined {
  return view?.entries.find((e) => e.kind === kind);
}

/** What an entry rests on, in one line: the words, the value kept. */
export function evidenceLine(entry: NotationEntry): string {
  if (entry.source === "set") return "Người dùng đặt trên Dữ liệu chủ";
  return `Khách viết “${entry.written}”, Sales xác nhận ${entry.confirmed}`;
}

/** The case an entry was learned on, where it opens. */
export function caseHref(entry: NotationEntry): string | null {
  if (entry.source !== "confirmed" || !entry.case_id) return null;
  return entry.case_kind === "order"
    ? `/sales/orders/${entry.case_id}`
    : `/sales/quotes/${entry.case_id}`;
}
