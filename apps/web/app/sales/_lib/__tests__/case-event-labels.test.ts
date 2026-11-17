// @vitest-environment node
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { CASE_EVENT } from "../labels";

/**
 * Every event `dw_sales` writes on a case's history has words, so the
 * history never shows a raw code (DW's own "order.mapping_applied" did,
 * 2026-11-17). The actions are read from where the server makes them:
 * `person_event(...)`, `worker_event(...)` and `CaseEvent(action=...)` with
 * a literal. Each pattern must still find something, so a moved source fails
 * here instead of passing on nothing.
 */

const SRC = resolve(
  __dirname,
  "../../../../../../packages/python/dw_sales/src/dw_sales",
);

function pythonFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory())
      return name === "__pycache__" || name === "testing"
        ? []
        : pythonFiles(path);
    return name.endsWith(".py") ? [path] : [];
  });
}

const SOURCES = pythonFiles(SRC).map((path) => readFileSync(path, "utf8"));
const PATTERNS = {
  "person_event / worker_event":
    /\b(?:person|worker)_event\(\s*"([a-z_]+\.[a-z_.]+)"/g,
  "CaseEvent(action=...)": /\bCaseEvent\(\s*action="([a-z_]+\.[a-z_.]+)"/g,
};

describe("the case history's words cover every event the server writes", () => {
  it.each(Object.entries(PATTERNS))("%s", (_, pattern) => {
    const actions = new Set(
      SOURCES.flatMap((text) => [...text.matchAll(pattern)].map((m) => m[1]!)),
    );
    expect(actions.size).toBeGreaterThan(0);
    const unlabelled = [...actions].filter((a) => !(a in CASE_EVENT)).sort();
    expect(unlabelled).toEqual([]);
  });
});
