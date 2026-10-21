import type { SalesSchemas } from "@dw/api-client";
import { valueLabel } from "./rule-labels";

type RulesView = SalesSchemas["RulesInForceView"];
export type RuleKey = SalesSchemas["RuleKey"];
export type RuleVersion = SalesSchemas["RuleVersionView"];
export type RuleDraft = SalesSchemas["RuleDraftView"];
export type DraftProblem = SalesSchemas["DraftProblem"];

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

/** A version a proposal may start from: the company's or the platform's, or
 * a draft DW1 made from the company's own file. */
export interface StartOption {
  /** `tenant:<version_id>`, `platform:<ref>` or `draft:<draft_id>`. */
  id: string;
  ref: string;
  layer: RuleVersion["layer"];
  /** The company's version's state; none for the platform's. */
  status?: RuleVersion["status"];
  /** What applies to the company now. */
  inForce: boolean;
  document: Record<string, unknown>;
  /** The draft it is, with what the machine read and where. */
  draft?: RuleDraft;
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
    .map((v): StartOption => ({
      id: `tenant:${v.version_id}`,
      ref: v.ref,
      layer: "tenant",
      status: v.status,
      inForce: view.layers[key] === "tenant" && v.ref === inForce,
      document: v.document,
    }));
  const shipped = platform.map((p): StartOption => ({
    id: `platform:${p.ref}`,
    ref: p.ref,
    layer: "platform",
    inForce: view.layers[key] !== "tenant" && p.ref === inForce,
    document: p.document,
  }));
  const all = [...own, ...shipped];
  return [...all.filter((o) => o.inForce), ...all.filter((o) => !o.inForce)];
}

// ---------------------------------------------- "Tạo từ tệp mẫu" (drafts) --

/** What the API takes as a template (`DRAFT_EXTENSIONS`, `MAX_DRAFT_BYTES`). */
export const DRAFT_ACCEPT = ".xlsx,.xls";
export const MAX_DRAFT_BYTES = 2 * 1024 * 1024;

export const DRAFT_STATUS: Record<RuleDraft["status"], string> = {
  queued: "Đang đọc tệp",
  ready: "Đã đọc xong",
  refused: "Gợi ý của DW1 không đạt kiểm tra",
  unavailable: "Chưa ánh xạ được bằng mô hình",
  failed: "Không đọc được tệp",
};

/**
 * A draft as a version to start from, once it has a document: the API drafts
 * one for every outcome but queued and failed (`template_reading.offered`
 * when no mapping was accepted, so nothing is guessed).
 */
export function draftOption(draft: RuleDraft): StartOption | null {
  const document = draft.document;
  if (!document) return null;
  const version = [document.policy_version, document.version].find(
    (v): v is string => typeof v === "string",
  );
  return {
    id: `draft:${draft.draft_id}`,
    ref: `${draft.rule_key}@${version ?? "0.0.0"}`,
    layer: "tenant",
    inForce: false,
    document,
    draft,
  };
}

/** A value the machine filled: where it was read, and what it read. */
export interface MachineRead {
  evidence: string;
  value: unknown;
}

function valueAt(document: unknown, path: string): unknown {
  let current = document;
  for (const step of path.split(".")) {
    if (current === null || typeof current !== "object") return undefined;
    current = (current as Record<string, unknown>)[step];
  }
  return current;
}

/** Every document path the machine filled ("columns.0.header"), with its
 * cell ("Mẫu!C3") and the value it put there. */
export function machineRead(draft: RuleDraft): Record<string, MachineRead> {
  return Object.fromEntries(
    draft.machine_read.map((path) => [
      path,
      {
        evidence: draft.evidence[path] ?? "",
        value: valueAt(draft.document, path),
      },
    ]),
  );
}

/**
 * What a draft's template offers as choices, by the form's label path: its
 * header row's visible headers for each column of the Bravo upload layout,
 * the one key drafted today (`DRAFTABLE`), typed as freely as before.
 */
export function draftChoices(draft: RuleDraft): Record<string, string[]> {
  const headers = draft.template?.headers.map((h) => h.text) ?? [];
  return headers.length ? { "columns[].header": headers } : {};
}

/** One problem of a draft, in words: fields by their label, never a code. */
export function draftProblemText(problem: DraftProblem): string {
  const field = problem.field ? `“${valueLabel(problem.field)}”` : "";
  switch (problem.code) {
    case "column_unmapped":
      return `Cột ${problem.ref ?? ""} “${problem.header ?? ""}” của mẫu không ứng với giá trị nào: tệp nhập Bravo chưa có cột để trống, nên cột này không có trong tệp.`;
    case "header_not_in_template":
      return `${field}: DW1 nêu một tiêu đề không có nguyên văn ở hàng tiêu đề của mẫu, nên không lấy.`;
    case "header_ambiguous":
      return `${field}: tiêu đề DW1 nêu có ở hai cột của mẫu, không biết lấy cột nào.`;
    case "header_twice":
      return `${field}: cột ${problem.ref ?? ""} đã được dùng cho một giá trị khác.`;
    case "required_missing":
      return `Mẫu không có cột cho ${field}: tệp nhập Bravo bắt buộc có giá trị này.`;
    case "layout_invalid":
      return `Bản gợi ý không hợp lệ ở ${problem.where ?? "tài liệu"}.`;
    case "sheet_name_invalid":
      return "Tên sheet của mẫu không dùng được cho tệp nhập (tối đa 31 ký tự, không có [ ] : * ? / \\ '): giữ tên của bản đang áp dụng.";
    case "model_unavailable":
      return "Mô hình không trả lời được: chọn tiêu đề cho từng cột trong danh sách tiêu đề của mẫu.";
    case "model_not_configured":
      return "Máy chủ này chưa có mô hình: chọn tiêu đề cho từng cột trong danh sách tiêu đề của mẫu.";
    case "model_quota":
      return "Gói đã hết lượt dùng mô hình hôm nay: chọn tiêu đề cho từng cột trong danh sách tiêu đề của mẫu.";
    default: {
      const unknown: never = problem.code;
      return String(unknown);
    }
  }
}

function semver(ref: string): number[] {
  return (ref.split("@")[1] ?? "").split(".").map((n) => Number(n) || 0);
}

/**
 * The number a new version is offered: one patch above every number the key
 * has used, the company's and the platform's, since the server refuses both.
 */
export function nextVersion(refs: readonly string[]): string {
  const highest = refs.map(semver).reduce(
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
