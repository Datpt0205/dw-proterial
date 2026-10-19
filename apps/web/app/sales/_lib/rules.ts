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

export type PlatformDocument = SalesSchemas["PlatformDocumentView"];

/** A version a proposal may start from: the company's or the platform's. */
export interface StartOption {
  /** `tenant:<version_id>` or `platform:<ref>`. */
  id: string;
  ref: string;
  layer: RuleVersion["layer"];
  /** The company's version's state; none for the platform's. */
  status?: RuleVersion["status"];
  /** What applies to the company now. */
  inForce: boolean;
  document: Record<string, unknown>;
}

/**
 * Every version of the key a proposal may start from (ticket 40,
 * "Dùng lại phiên bản này"): what applies now first, then the company's
 * versions newest first, then every version the platform released (ticket
 * 37 keeps them readable). Starting from one is a proposal like any other.
 */
export function startOptions(
  view: RulesView,
  key: RuleKey,
  platform: readonly PlatformDocument[],
): StartOption[] {
  const inForce = view.in_force[key];
  const own = view.versions
    .filter((v) => v.key === key)
    .sort((a, b) => b.proposed_at.localeCompare(a.proposed_at))
    .map(
      (v): StartOption => ({
        id: `tenant:${v.version_id}`,
        ref: v.ref,
        layer: "tenant",
        status: v.status,
        inForce: view.layers[key] === "tenant" && v.ref === inForce,
        document: v.document,
      }),
    );
  const shipped = platform.map(
    (p): StartOption => ({
      id: `platform:${p.ref}`,
      ref: p.ref,
      layer: "platform",
      inForce: view.layers[key] !== "tenant" && p.ref === inForce,
      document: p.document,
    }),
  );
  const all = [...own, ...shipped];
  return [...all.filter((o) => o.inForce), ...all.filter((o) => !o.inForce)];
}

function semver(ref: string): number[] {
  return (ref.split("@")[1] ?? "").split(".").map((n) => Number(n) || 0);
}

/**
 * The number a new version is offered: one patch above every number the key
 * has used, the company's and the platform's, since the server refuses both.
 */
export function nextVersion(refs: readonly string[]): string {
  const highest = refs
    .map(semver)
    .reduce(
      (best, v) => {
        for (let i = 0; i < 3; i++) {
          if ((v[i] ?? 0) !== (best[i] ?? 0))
            return (v[i] ?? 0) > (best[i] ?? 0) ? v : best;
        }
        return best;
      },
      [0, 0, 0],
    );
  return `${highest[0] ?? 0}.${highest[1] ?? 0}.${(highest[2] ?? 0) + 1}`;
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
