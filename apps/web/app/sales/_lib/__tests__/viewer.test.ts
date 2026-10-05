// @vitest-environment node
import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { PERMISSION_SET_SCOPES } from "../viewer";

/** The migration that declares the Sales permission sets is the owner. */
const VERSIONS = resolve(__dirname, "../../../../../../db/migrations/versions");
const migration = readdirSync(VERSIONS).find((name) =>
  name.startsWith("68305ebe4a83_"),
);

describe("the interim permission-set scopes", () => {
  it("equal what the sales migration declares, set for set", () => {
    expect(migration, "the sales roles migration exists").toBeDefined();
    const source = readFileSync(resolve(VERSIONS, migration!), "utf8");
    const block = source.slice(
      source.indexOf("_PERMISSION_SETS"),
      source.indexOf("_RULE_KEY"),
    );
    const declared = Object.fromEntries(
      [
        ...block.matchAll(/\(\s*"(sales_[a-z_]+)",\s*"[^"]*",\s*\(([^)]*)\)/g),
      ].map(([, key, scopes]) => [
        key,
        [...scopes!.matchAll(/"([^"]+)"/g)].map(([, scope]) => scope),
      ]),
    );
    expect(Object.keys(declared).length).toBeGreaterThan(0);
    expect(PERMISSION_SET_SCOPES).toEqual(declared);
  });
});
