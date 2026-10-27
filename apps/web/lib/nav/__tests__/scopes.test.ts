import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { scopeLabel } from "../scopes";

const ROOT = resolve(__dirname, "../../../../..");

/** The scopes the platform's reference data grants (`platform.roles`). */
function seededScopes(): string[] {
  const sql = readFileSync(
    resolve(ROOT, "db/migrations/sql/0001_platform_reference.sql"),
    "utf8",
  );
  const start = sql.indexOf("INSERT INTO platform.roles");
  expect(start).toBeGreaterThanOrEqual(0);
  const block = sql.slice(start, sql.indexOf(";", start));
  return [...new Set([...block.matchAll(/"([a-z_.]+)"/g)].map((m) => m[1]!))];
}

/** The scopes Sales declares (`SalesScopes`). */
function salesScopes(): string[] {
  const py = readFileSync(
    resolve(
      ROOT,
      "packages/python/dw_sales/src/dw_sales/application/access.py",
    ),
    "utf8",
  );
  const start = py.indexOf("class SalesScopes");
  const block = py.slice(start, py.indexOf("\n\n\n", start));
  return [...block.matchAll(/= "(sales\.[a-z_.]+)"/g)].map((m) => m[1]!);
}

describe("scope labels (2026-10-27)", () => {
  it("names every scope the platform seeds and Sales declares, never by its code", () => {
    const scopes = [...seededScopes(), ...salesScopes()];
    expect(scopes).toContain("approvals.decide");
    expect(scopes).toContain("sales.quote.approve");
    for (const scope of scopes)
      expect(scopeLabel(scope), scope).not.toBe(scope);
  });

  it("shows a scope it does not name as its code", () => {
    expect(scopeLabel("xx.unlisted")).toBe("xx.unlisted");
  });
});
