import type { SalesSchemas } from "@dw/api-client";

type RulesView = SalesSchemas["RulesInForceView"];
export type RuleKey = SalesSchemas["RuleKey"];
export type RuleVersion = SalesSchemas["RuleVersionView"];

/**
 * The words for each key a tenant may hold its own version of (ticket 19).
 * Typed by the generated `RuleKey`, so a key the API adds or drops is a
 * compile error here, not a raw code on the screen.
 */
export const RULE_KEY: Record<RuleKey, string> = {
  sales_order_rules: "Quy tắc kiểm tra đơn hàng",
  sales_kpi: "Chỉ tiêu KPI",
  sales_quote_rules: "Quy tắc báo giá",
  sales_pricing: "Chính sách giá",
  sales_emails: "Nội dung email",
  sales_documents: "Nội dung chứng từ",
  sales_bravo_upload: "Mẫu tệp nhập Bravo",
  sales_handoffs: "Nội dung chuyển giao",
  sales_followups: "Nhắc việc và tóm tắt buổi sáng",
};

export const RULE_STATUS: Record<RuleVersion["status"], string> = {
  proposed: "Chờ duyệt",
  approved: "Đã duyệt",
  rejected: "Đã từ chối",
  superseded: "Đã thay bằng phiên bản mới",
};

export const RULE_LAYER: Record<RuleVersion["layer"], string> = {
  platform: "Của nền tảng",
  tenant: "Riêng của công ty",
};

export interface KeyRow {
  key: RuleKey;
  /** `id@version` of what applies now. */
  inForce: string;
  layer: RuleVersion["layer"];
  /** What the platform ships for the key. */
  platform: string;
  /** Versions of this key waiting on their approval. */
  waiting: number;
}

/** One row per key, in the order the server lists the platform's. */
export function keyRows(view: RulesView): KeyRow[] {
  return view.platform.map(({ key, ref }) => ({
    key,
    inForce: view.in_force[key] ?? ref,
    layer: view.layers[key] ?? "platform",
    platform: ref,
    waiting: view.versions.filter(
      (v) => v.key === key && v.status === "proposed",
    ).length,
  }));
}

/**
 * Where a proposal's editor starts: the tenant's version in force, else its
 * latest version of the key, else nothing. The platform's own document is
 * not served to the browser, so a first version is written whole.
 * `inForce` says which of the two it is, for the words above the editor.
 */
export function startingDocument(
  view: RulesView,
  key: RuleKey,
): { document: Record<string, unknown>; inForce: boolean } | null {
  const own = view.versions.filter((v) => v.key === key);
  const inForce = own.find((v) => v.ref === view.in_force[key]);
  if (inForce) return { document: inForce.document, inForce: true };
  const latest = [...own].sort((a, b) =>
    b.proposed_at.localeCompare(a.proposed_at),
  )[0];
  return latest ? { document: latest.document, inForce: false } : null;
}

export type Parsed =
  | { ok: true; document: Record<string, unknown> }
  | { ok: false; error: string };

/**
 * The editor's text as the document a proposal sends: one JSON object. The
 * server validates it against the key's own schema and says what is wrong;
 * this only refuses text that is not an object at all.
 */
export function parseDocument(text: string): Parsed {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    return {
      ok: false,
      error: "Tài liệu phải là JSON hợp lệ (kiểm tra dấu ngoặc và dấu phẩy).",
    };
  }
  if (typeof value !== "object" || value === null || Array.isArray(value))
    return { ok: false, error: "Tài liệu phải là một đối tượng JSON { … }." };
  return { ok: true, document: value as Record<string, unknown> };
}
