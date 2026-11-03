import type {
  PurchasingListChange,
  PurchasingMasterImport,
} from "@dw/api-client";
import type { StatusTone } from "@dw/ui";

/** An import's status, in words and tone (`MasterImport.status`). */
export const IMPORT_STATUS: Record<
  PurchasingMasterImport["status"],
  { label: string; tone: StatusTone }
> = {
  queued: { label: "Đang đọc", tone: "pri" },
  parsed: { label: "Đã đọc, chờ gửi duyệt", tone: "warn" },
  failed: { label: "Không đọc được", tone: "err" },
  submitted: { label: "Đã gửi duyệt", tone: "ok" },
};

/** The workbook a page accepts; the server checks the bytes again. */
export const WORKBOOK_ACCEPT = ".xlsx,.xls";
export const MAX_WORKBOOK_BYTES = 10 * 1024 * 1024;

/** "Mới 3 · Bỏ 1 · Đổi 2", or how a list left out of the file stays. */
export function changeWords(change: PurchasingListChange): string {
  if (!change.in_file)
    return `Giữ nguyên ${change.rows} dòng (không có trong tệp)`;
  return `${change.rows} dòng · Mới ${change.added} · Bỏ ${change.removed} · Đổi ${change.changed}`;
}

/** Why "Gửi duyệt" cannot be pressed now, in words; null when it can. */
export function submitBlocked(
  item: PurchasingMasterImport,
  proposes: boolean,
): string | null {
  if (!proposes)
    return "Chỉ người cấu hình DW2 gửi duyệt được; bạn chỉ xem và duyệt.";
  if (item.status !== "parsed") return null;
  return item.blocked ?? null;
}

/** A file's bytes as base64, in chunks (a large file overflows one call). */
export function toBase64(bytes: Uint8Array): string {
  let text = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk)
    text += String.fromCharCode(...bytes.subarray(i, i + chunk));
  return btoa(text);
}
