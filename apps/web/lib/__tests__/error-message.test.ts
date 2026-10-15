import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { ApiError } from "@dw/api-client";
import { SALES_REFUSALS } from "../../app/sales/_meta/refusals";
import { REFUSAL_TABLES, errorMessage, toRegionError } from "../error-message";

function refusal(
  message: string,
  details: Record<string, unknown>,
  code = "conflict",
): ApiError {
  return new ApiError(409, { code, message, details });
}

describe("errorMessage: a refusal in Vietnamese", () => {
  it("reads a Sales rule's Vietnamese, not the server's English", () => {
    const error = refusal("the platform now ships this version number", {
      rule: "platform_version_reused",
    });
    expect(errorMessage(error)).toBe(SALES_REFUSALS.platform_version_reused);
  });

  it("reads the server's own sentence for a separation-of-duties refusal", () => {
    // `maker_checker` is raised by the platform's strict approvals as well as
    // by Sales: each words its own refusal, and no context table speaks for it.
    const said =
      "tách nhiệm: người đề xuất phiên bản quy tắc không tự quyết được";
    expect(errorMessage(refusal(said, { rule: "maker_checker" }))).toBe(said);
  });

  it("reads a code named as details.reason too", () => {
    const error = refusal(
      "the case was opened under quote rules that no longer apply",
      { reason: "rules_version_gone", rules_version: "q@1.0.0" },
    );
    expect(errorMessage(error)).toBe(SALES_REFUSALS.rules_version_gone);
  });

  it.each([
    ["platform_version_reused", "the platform now ships this version number"],
    ["stale_case_version", "the case changed since it was read"],
    ["layout_decided", "the layout was decided meanwhile"],
    ["message_already_processed", "the message is already on a case"],
    ["case_closed", "a closed case is not reassigned"],
  ])("%s, worded in English by the server, reads Vietnamese", (rule, said) => {
    const shown = errorMessage(refusal(said, { rule }));
    expect(shown).not.toBe(said);
    expect(shown).toBe(SALES_REFUSALS[rule]);
  });

  it("keeps the server's sentence where the server words it in Vietnamese", () => {
    const said = "phiên bản quy tắc không còn chờ quyết định này";
    expect(errorMessage(refusal(said, { rule: "decision_stale" }))).toBe(said);
    const gone = "mẫu của các tệp đã tạo ở phiên bản hồ sơ này không còn";
    expect(
      errorMessage(refusal(gone, { reason: "template_version_gone" })),
    ).toBe(gone);
  });

  it("falls back to the server's sentence for a code it has no words for", () => {
    expect(
      errorMessage(refusal("Không đủ quyền", { rule: "toString" }, "x")),
    ).toBe("Không đủ quyền");
    expect(errorMessage(refusal("Không đủ quyền", {}))).toBe("Không đủ quyền");
  });

  it("is what the shared error state shows", () => {
    const state = toRegionError(
      refusal("a closed case is not reassigned", { rule: "case_closed" }),
    );
    expect(state).not.toBe("offline");
    expect((state as { message: string }).message).toBe(
      SALES_REFUSALS.case_closed,
    );
  });
});

/** Every Python source file under `dir`. */
function pythonFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return pythonFiles(path);
    return name.endsWith(".py") ? [path] : [];
  });
}

/** The Python source under each `dir`, joined. */
function pythonSource(...dirs: string[]): string {
  return dirs
    .flatMap(pythonFiles)
    .map((file) => readFileSync(file, "utf-8"))
    .join("\n");
}

const REPO = join(__dirname, "../../../..");

describe("the refusal tables", () => {
  it("give each code one owner among the contexts", () => {
    // Merged into one lookup, a code in two tables reads whichever came last,
    // with nothing to say so (failure-modes #2).
    const owners = new Map<string, string[]>();
    for (const [context, table] of Object.entries(REFUSAL_TABLES))
      for (const code of Object.keys(table))
        owners.set(code, [...(owners.get(code) ?? []), context]);
    const shared = [...owners].filter(([, by]) => by.length > 1);
    expect(shared).toEqual([]);
  });

  it("never speak for a code the platform raises", () => {
    // The platform words its own refusals (approval_flow's `maker_checker`
    // is read on /approvals, for every context's strict approvals): a
    // context's sentence for one of its codes would read on every one of them.
    const contexts = new Set(
      Object.keys(REFUSAL_TABLES).map((context) => `dw_${context}`),
    );
    const platform = pythonSource(
      ...readdirSync(join(REPO, "packages/python"))
        .filter((name) => !contexts.has(name))
        .map((name) => join(REPO, "packages/python", name, "src")),
      ...["api", "worker"].map((app) => join(REPO, "apps", app, "src")),
    );
    const raised = Object.entries(REFUSAL_TABLES).flatMap(([context, table]) =>
      Object.keys(table)
        .filter((code) => platform.includes(`"${code}"`))
        .map((code) => `${context}:${code}`),
    );
    expect(raised).toEqual([]);
  });
});

describe("the Sales refusal words", () => {
  it("name only codes dw_sales actually refuses with", () => {
    // A code nothing raises is a sentence nobody reads (failure-modes #1),
    // and usually a rule that was renamed on the server.
    const source = pythonSource(join(REPO, "packages/python/dw_sales/src"));
    const unknown = Object.keys(SALES_REFUSALS).filter(
      (code) => !source.includes(`"${code}"`),
    );
    expect(unknown).toEqual([]);
  });
});
