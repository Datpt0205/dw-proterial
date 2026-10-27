import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { ROUTING_ADVICE, ROUTING_REASON } from "../labels";

/** The reasons DW1 routes a message to Sales with (`RoutingReason`). */
function reasons(): string[] {
  const py = readFileSync(
    resolve(
      __dirname,
      "../../../../../../packages/python/dw_sales/src/dw_sales/domain/dispositions.py",
    ),
    "utf8",
  );
  const start = py.indexOf("class RoutingReason");
  const block = py.slice(start, py.indexOf("\n\n\n", start));
  return [...block.matchAll(/= "([a-z_]+)"/g)].map((m) => m[1]!);
}

describe("a routed message says what to do, in Vietnamese (2026-10-27)", () => {
  it("names every reason the server routes with, and says what Sales does", () => {
    const all = reasons();
    expect(all).toContain("attachment_unreadable");
    for (const reason of all) {
      expect(ROUTING_REASON, reason).toHaveProperty(reason);
      expect(ROUTING_ADVICE, reason).toHaveProperty(reason);
    }
  });
});
