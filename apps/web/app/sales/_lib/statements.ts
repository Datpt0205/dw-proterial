import type { SalesSchemas } from "@dw/api-client";
import { formatDate, formatDayMonth, formatMonth } from "../../../lib/dates";

type Order = SalesSchemas["OrderCaseView"];
type Quote = SalesSchemas["QuoteCaseView"];
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

/** "page 2" → "trang 2", "message_text" → "nội dung thư", else a sheet. */
function quoteRegion(region: string): string {
  if (region === "message_text") return "nội dung thư";
  const page = /^page (\d+)$/.exec(region);
  return page ? `trang ${page[1]}` : `sheet ${region}`;
}

/**
 * The request's coverage statement (`QuoteCaseView.coverage`), the quote's
 * counterpart of the order's: what was read, how many values a model read and
 * how many a person confirmed, and the findings. Never "N/N": the request's
 * reader counts no printed rows, so there is nothing to divide by.
 * "Đã đọc 3 dòng từ sheet RFQ; 4 giá trị mô hình đọc, 1 đã xác nhận; 1 cờ".
 */
export function quoteCoverageStatement(quote: Quote): string {
  const c = quote.coverage;
  const where = c.regions.length
    ? `từ ${c.regions.map(quoteRegion).join(", ")}`
    : "(không rõ vùng nào)";
  const model = c.model_read
    ? `${c.model_read} giá trị mô hình đọc, ${c.model_read_confirmed} đã xác nhận`
    : "không giá trị nào do mô hình đọc";
  return `Đã đọc ${c.lines_read} dòng ${where}; ${model}; ${c.findings} cờ`;
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
