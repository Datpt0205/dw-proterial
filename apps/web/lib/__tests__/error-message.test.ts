import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { ApiError } from "@dw/api-client";
import { SALES_REFUSALS } from "../../app/sales/_meta/refusals";
import { errorMessage, toRegionError } from "../error-message";

function refusal(
  message: string,
  details: Record<string, unknown>,
  code = "conflict",
): ApiError {
  return new ApiError(409, { code, message, details });
}

describe("errorMessage: a refusal in Vietnamese", () => {
  it("reads a Sales rule's Vietnamese, not the server's English", () => {
    const error = refusal("the proposer of a version does not decide it", {
      rule: "maker_checker",
    });
    expect(errorMessage(error)).toBe(SALES_REFUSALS.maker_checker);
    expect(errorMessage(error)).toMatch(/^Tách nhiệm/);
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

describe("the Sales refusal words", () => {
  it("name only codes dw_sales actually refuses with", () => {
    // A code nothing raises is a sentence nobody reads (failure-modes #1),
    // and usually a rule that was renamed on the server.
    const source = pythonFiles(
      join(__dirname, "../../../../packages/python/dw_sales/src"),
    )
      .map((file) => readFileSync(file, "utf-8"))
      .join("\n");
    const unknown = Object.keys(SALES_REFUSALS).filter(
      (code) => !source.includes(`"${code}"`),
    );
    expect(unknown).toEqual([]);
  });
});
