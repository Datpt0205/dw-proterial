import type { SalesSchemas } from "@dw/api-client";
import { formatDate, formatDayMonth, formatMonth } from "../../../lib/dates";

type Order = SalesSchemas["OrderCaseView"];
type Basis = SalesSchemas["LineBasisView"];

/**
 * The coverage statement (spec decision 12): what was read and checked on one
 * order, so a clean result says what it covered (ui-quality §7).
 * "Đã đọc 3/3 dòng trên 1 sheet; tổng khớp ô TOTAL (F12); 21 lượt kiểm tra × 3
 * dòng; 1 cờ".
 */
export function coverageStatement(order: Order): string {
  const c = order.coverage;
  const pages = c.regions.every((r) => /^page \d+$/.test(r));
  const where = `${c.regions.length} ${pages ? "trang" : "sheet"}`;
  const totalMismatch = order.findings.some(
    (f) => f.code === "line_total_mismatch",
  );
  const totalCell =
    order.total_anchor?.cell_ref?.split("!").pop() ??
    (order.total_anchor?.page ? `trang ${order.total_anchor.page}` : null);
  const total =
    order.total_anchor === null
      ? "PO không in tổng"
      : totalMismatch
        ? `tổng KHÔNG khớp ô TOTAL${totalCell ? ` (${totalCell})` : ""}`
        : `tổng khớp ô TOTAL${totalCell ? ` (${totalCell})` : ""}`;
  return `Đã đọc ${c.lines_read}/${c.lines_printed} dòng trên ${where}; ${total}; ${c.checks_run} lượt kiểm tra × ${c.lines_read} dòng; ${c.findings} cờ`;
}

/**
 * What one line was checked against, as stamped on the case when the check
 * ran (spec decision 11): never re-read from master data. "Đối chiếu với báo
 * giá Q26-0181 (hiệu lực 01/07–31/12), LME tháng 09/2026; dữ liệu đến ngày
 * 02/10".
 */
export function basisStatement(
  basis: Basis,
  catalogAsOf: string | null,
): string {
  const parts: string[] = [];
  if (basis.quotation) {
    const q = basis.quotation;
    parts.push(
      `Đối chiếu với báo giá ${q.quote_no} (hiệu lực ${formatDayMonth(q.valid_from)}–${formatDayMonth(q.valid_to)}/${q.valid_to.slice(0, 4)})`,
    );
  } else parts.push("Không có báo giá còn hiệu lực để đối chiếu");
  if (basis.lme) parts.push(`LME tháng ${formatMonth(basis.lme.month)}`);
  if (basis.lead_time_days !== null)
    parts.push(
      `lead time ${basis.lead_time_days} ngày (${basis.lead_time_source === "item_standard" ? "chuẩn của mã hàng" : (basis.lead_time_source ?? "không rõ nguồn")})`,
    );
  const head = parts.join(", ");
  return catalogAsOf
    ? `${head}; dữ liệu đến ngày ${formatDate(catalogAsOf)}`
    : head;
}
