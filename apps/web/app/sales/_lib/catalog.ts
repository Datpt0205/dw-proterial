import type { SalesSchemas } from "@dw/api-client";
import { formatDateTime } from "../../../lib/dates";

/**
 * Master-data imports (ticket 41): the words and the small decisions the
 * master-data page draws them with, one owner each.
 */
export type CatalogList = SalesSchemas["CatalogList"];
export type CatalogListState = SalesSchemas["CatalogListStateView"];
export type CatalogImport = SalesSchemas["CatalogImportView"];
export type CatalogPreview = SalesSchemas["CatalogPreviewView"];
export type InForce = SalesSchemas["CatalogInForceView"];

/** The tab each list lives on, by the list the API names. */
export const TAB_OF: Record<CatalogList, string> = {
  customers: "customers",
  items: "items",
  convert_list: "convert-list",
  quotations: "quotations",
  lme: "lme",
};

export const IMPORT_STATUS: Record<CatalogImport["status"], string> = {
  queued: "Đang đọc tệp",
  parsed: "Đã đọc, chưa gửi duyệt",
  failed: "Không đọc được",
  submitted: "Chờ duyệt",
  approved: "Đang áp dụng",
  rejected: "Bị từ chối",
  superseded: "Đã thay bằng bản mới hơn",
  discarded: "Đã bỏ (có bản nhập sau)",
};

export const IMPORT_TONE: Record<
  CatalogImport["status"],
  "ok" | "warn" | "err" | "unk" | "gray"
> = {
  queued: "unk",
  parsed: "warn",
  failed: "err",
  submitted: "warn",
  approved: "ok",
  rejected: "err",
  superseded: "gray",
  discarded: "gray",
};

/** What the API takes in one upload (`MAX_IMPORT_BYTES`); it refuses more. */
export const MAX_IMPORT_BYTES = 2 * 1024 * 1024;
export const IMPORT_ACCEPT = ".xlsx,.xls,.csv";

/**
 * Where the list's rows come from now, in words: the sample data, or the
 * import approved, when and by whom.
 */
export function sourceLabel(
  inForce: InForce,
  name: (id: string | null | undefined) => string,
): { tone: "warn" | "ok"; text: string } {
  const snapshot = inForce.snapshot;
  if (inForce.source === "mock" || !snapshot)
    return {
      tone: "warn",
      text: `Dữ liệu mẫu (hư cấu), đến ${formatDateTime(inForce.as_of)}`,
    };
  const from = inForce.source === "erp" ? "đồng bộ từ Bravo" : "bản nhập";
  const approved = snapshot.decided_by
    ? `, ${name(snapshot.decided_by)} duyệt`
    : "";
  return {
    tone: "ok",
    text: `${from[0]!.toUpperCase()}${from.slice(1)} ngày ${formatDateTime(snapshot.as_of)} bởi ${name(snapshot.imported_by)}${approved}`,
  };
}

/**
 * Why a new file cannot be imported now, or null: the viewer lacks the
 * scopes (the server refuses the same), or an import of this list is
 * waiting on its approval.
 */
export function uploadBlocked(state: CatalogListState): string | null {
  if (!state.can_import)
    return state.catalog_list === "quotations" || state.catalog_list === "lme"
      ? "Danh mục này có giá: chỉ người được nhập dữ liệu chủ và xem giá (Trưởng bộ phận Sales) nhập được."
      : "Bạn chưa có quyền nhập dữ liệu chủ (Sales phụ trách hoặc Trưởng bộ phận Sales).";
  if (state.open?.status === "submitted")
    return "Đang có bản nhập chờ duyệt: chờ quyết định rồi nhập tiếp.";
  return null;
}

/**
 * The import the panel shows: the open one, else the newest in the history
 * when it failed (so a person sees why the file they just sent was refused).
 */
export function shownImport(state: CatalogListState): CatalogImport | null {
  if (state.open) return state.open;
  const latest = state.history[0];
  return latest && latest.status === "failed" ? latest : null;
}

/** A file's bytes as base64, in chunks (a 2 MB file overflows one call). */
export function toBase64(bytes: Uint8Array): string {
  let text = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk)
    text += String.fromCharCode(...bytes.subarray(i, i + chunk));
  return btoa(text);
}

/** "Thêm 1 · Sửa 2 · Bỏ 0 · Giữ nguyên 5 · Bị loại 1". */
export function diffSummary(preview: CatalogPreview): string {
  return [
    `Thêm ${preview.added.length}`,
    `Sửa ${preview.changed.length}`,
    `Bỏ ${preview.removed.length}`,
    `Giữ nguyên ${preview.unchanged}`,
    `Bị loại ${preview.rejected_count} dòng`,
  ].join(" · ");
}
