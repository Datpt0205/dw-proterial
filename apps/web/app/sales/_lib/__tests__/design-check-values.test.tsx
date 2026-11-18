import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { UiProvider } from "@dw/ui";
import type { SalesSchemas } from "@dw/api-client";
import { DesignCheckPanel } from "../../quotes/[caseId]/design-check";

type Check = SalesSchemas["DesignCheck"];

const CHECK: Check = {
  ycbg_no: "RFQ261110-003",
  file_sha256: "0".repeat(64),
  read_by: "u-1",
  read_at: "2026-11-17T02:00:00Z",
  lines: [
    {
      line_no: 1,
      verdict: "quote",
      bp_code: "BP003833",
      reason: null,
      spec_no: "SPV-02-1788",
      copper_kg_per_bp_unit: "5.59",
      bp_unit: "km",
      row: 5,
    },
    {
      line_no: 2,
      verdict: "decline",
      bp_code: null,
      reason: "không làm được",
      spec_no: null,
      copper_kg_per_bp_unit: null,
      bp_unit: null,
      row: 6,
    },
  ],
};

afterEach(cleanup);

describe("ticket 11: Design's spec and copper read from Bravo's export", () => {
  it("shows the spec number and copper per BP unit on a QUOTE line", () => {
    render(
      <UiProvider>
        <DesignCheckPanel check={CHECK} readBy={() => "Diệu"} prices={null} />
      </UiProvider>,
    );
    expect(screen.getByText("SPV-02-1788")).toBeTruthy();
    expect(screen.getByText(/Cu 5,59 kg\/km/)).toBeTruthy();
  });
});
