import { describe, expect, it } from "vitest";
import { caseSteps } from "../case-history";

const actor = (id: string | null | undefined) =>
  id === "dw2"
    ? { name: "DW2", machine: true }
    : { name: "Khoa", machine: false };

function followed(status: "po_drafted" | "delivered") {
  return {
    status,
    source: "form",
    received_at: "2026-11-01T08:26:00Z",
    received_by: "u-1",
    review: null,
    approval: null,
    decision: null,
    rfq: null,
    offers: [],
    reapproval: null,
    selection: null,
    po: {
      drafted_at: "2026-11-01T08:28:00Z",
      drafted_by: "u-1",
      orders: [{ po_ref: "PR-2611-030-01" }],
    },
    tracking: [
      {
        po_ref: "PR-2611-030-01",
        bravo_no: "PO-26110007",
        bravo_by: "u-1",
        bravo_at: "2026-11-02T01:00:00Z",
        confirmation: {
          read_at: "2026-11-02T02:00:00Z",
          read_by: "dw2",
          accepted_at: "2026-11-02T02:00:01Z",
          accepted_by: "dw2",
          differences: [],
        },
        receipts: [
          {
            line_no: 1,
            quantity: "10",
            received_on: "2026-11-04",
            recorded_by: "u-1",
            recorded_at: "2026-11-04T09:48:00Z",
          },
        ],
      },
    ],
  } as never;
}

describe("a case's history, after its orders are drafted", () => {
  it("names Bravo's number, the confirmation, each receipt and the case delivered", () => {
    const steps = caseSteps(followed("delivered"), actor);
    expect(steps.map((s) => s.what).slice(-5)).toEqual([
      "Ghi số PO Bravo PO-26110007 cho PR-2611-030-01",
      "Đọc xác nhận của nhà cung cấp cho PR-2611-030-01: khớp đơn",
      "Chấp nhận xác nhận cho PR-2611-030-01",
      "Ghi nhận hàng về: PR-2611-030-01 dòng 1, 10",
      "Đã nhận đủ hàng",
    ]);
    const read = steps.find((s) => s.what.startsWith("Đọc xác nhận"));
    expect(read?.mark).toBe("machine_read");
    expect(read?.by?.machine).toBe(true);
  });

  it("says nothing is delivered while an order is still followed", () => {
    const steps = caseSteps(followed("po_drafted"), actor);
    expect(steps.map((s) => s.what)).not.toContain("Đã nhận đủ hàng");
  });
});
