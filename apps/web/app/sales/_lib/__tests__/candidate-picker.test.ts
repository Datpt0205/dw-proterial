import { describe, expect, it } from "vitest";
import type { SalesSchemas } from "@dw/api-client";
import { comparisonRows } from "../../orders/[caseId]/candidate-picker";
import { order } from "./fixtures";

type Line = SalesSchemas["OrderLineView"];
type Item = SalesSchemas["ItemView"];

const item = (code: string, overrides: Partial<Item> = {}): Item => ({
  prv_code: code,
  family: "multi_core_cable",
  spec_no: "PRV-S-210",
  cores: 4,
  gauge: "AWG22",
  uom: "m",
  moq: "300",
  pack_multiple: "300",
  standard_lead_time_days: 21,
  ...overrides,
});

const ITEMS = new Map([
  ["CB-2005", item("CB-2005")],
  ["CB-2006", item("CB-2006", { cores: 2 })],
]);

function line(stated: Line["basis"]["stated_attributes"]): Line {
  const base = order().lines[0]!;
  return { ...base, basis: { ...base.basis, stated_attributes: stated } };
}

const row = (rows: ReturnType<typeof comparisonRows>, key: string) =>
  rows.find((r) => r.key === key)!;

describe("the candidate picker's PO column (G13, ticket 28)", () => {
  it("shows what DW1 read from the description and whether each candidate fits it", () => {
    const rows = comparisonRows(
      line({ spec_no: null, family: null, cores: 4, gauge: "AWG22" }),
      ["CB-2005", "CB-2006"],
      ITEMS,
    );

    // Each is marked as DW1's reading, never drawn as a printed PO field.
    expect(row(rows, "cores").po).toBe("4 (DW1 đọc từ mô tả)");
    expect(row(rows, "cores").values["CB-2005"]!.fits).toBe(true);
    expect(row(rows, "cores").values["CB-2006"]!.fits).toBe(false);
    expect(row(rows, "gauge").po).toBe("AWG22 (DW1 đọc từ mô tả)");
    expect(row(rows, "gauge").values["CB-2005"]!.fits).toBe(true);
    // Not stated on the PO: nothing to compare, and it says so.
    expect(row(rows, "spec").po).toBe("Không ghi (DW1 đọc từ mô tả)");
    expect(row(rows, "spec").values["CB-2005"]!.fits).toBeNull();
    expect(row(rows, "family").values["CB-2005"]!.fits).toBeNull();
    // The PO's own fields are printed values, not a reading.
    expect(row(rows, "uom").po).toBe("m");
  });

  it("keeps the attributes in the description for a line DW1 did not read", () => {
    const rows = comparisonRows(line(null), ["CB-2005"], ITEMS);

    for (const key of ["spec", "family", "cores", "gauge"]) {
      expect(row(rows, key).po).toBe("Trong mô tả");
      expect(row(rows, key).values["CB-2005"]!.fits).toBeNull();
    }
  });
});
