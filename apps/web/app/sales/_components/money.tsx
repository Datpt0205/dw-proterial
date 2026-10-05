"use client";

import type { Amount, Hidden, Words } from "@dw/api-client";
import { MaskedValue } from "@dw/ui";
import { formatMoney, formatQuantity, type Currency } from "../../../lib/money";
import { UNKNOWN_TIME } from "../../../lib/dates";
import { label, SALES_ROLE } from "../_lib/labels";

/**
 * Who may see an amount, said once per region (ui-quality §6). The words name
 * the glossary's roles and permission sets, so a renamed set is renamed here
 * too; who actually holds them is the platform's to say.
 */
export const PRICE_SENTENCE = `Giá và số tiền chỉ ${label(SALES_ROLE, "sales_pic")} và ${label(SALES_ROLE, "sales_head")} xem được; vai của bạn không gồm quyền xem giá.`;
export const OTHER_CUSTOMERS_SENTENCE = `Giá đã báo cho khách khác chỉ người có quyền "${label(SALES_ROLE, "sales_price_evidence")}" và ${label(SALES_ROLE, "sales_head")} xem được.`;

export function isHidden(value: unknown): value is Hidden {
  return (
    typeof value === "object" &&
    value !== null &&
    (value as Hidden).hidden === true
  );
}

/**
 * An amount from the API: the figure in its currency, the lock when the API
 * marked it hidden, and "Không rõ" when there is none. Never "0", never "—".
 */
export function Money({
  value,
  currency,
  sentence = PRICE_SENTENCE,
}: {
  value: Amount | null | undefined;
  currency: Currency;
  sentence?: string;
}) {
  if (isHidden(value)) return <MaskedValue sentence={sentence} />;
  if (value === null || value === undefined) return <span>{UNKNOWN_TIME}</span>;
  return (
    <span className="whitespace-nowrap tabular-nums">
      {formatMoney(value, currency)}
    </span>
  );
}

/** A USD-per-tonne figure (LME, a copper band): an amount like any other. */
export function UsdPerTonne({ value }: { value: Amount | null | undefined }) {
  if (isHidden(value)) return <MaskedValue sentence={PRICE_SENTENCE} />;
  if (value === null || value === undefined) return <span>{UNKNOWN_TIME}</span>;
  return (
    <span className="whitespace-nowrap tabular-nums">
      {formatMoney(value, "USD")}/tấn
    </span>
  );
}

/**
 * A finding's expected or actual value: words, or the lock for a
 * price-bearing code the viewer may not read (spec "price-bearing codes").
 */
export function FindingWords({ value }: { value: Words | null | undefined }) {
  if (isHidden(value)) return <MaskedValue sentence={PRICE_SENTENCE} />;
  if (value === null || value === undefined || value === "")
    return <span>Không có</span>;
  return <span>{value}</span>;
}

export function Quantity({
  value,
  uom,
}: {
  value: string | number | null | undefined;
  uom?: string | null;
}) {
  if (value === null || value === undefined) return <span>{UNKNOWN_TIME}</span>;
  return (
    <span className="whitespace-nowrap tabular-nums">
      {formatQuantity(value)}
      {uom ? ` ${uom}` : ""}
    </span>
  );
}
