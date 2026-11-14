import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { UiProvider } from "@dw/ui";
import { SalesOrderReplay } from "../../_components/salesorder-replay";
import {
  changedCustomers,
  replaySummary,
  ruleWords,
  submitBlocked,
  type SalesOrderExample,
} from "../salesorder-examples";

/**
 * A customer's SalesOrder rules learned from a worked example (ticket 38):
 * "Gửi duyệt" is open only for a replay that matched, and every cell that
 * did not is listed with what was expected, what came out and why. The
 * server refuses the same; this only says it.
 */
const replayed: SalesOrderExample = {
  example_id: "e-1",
  customer_code: "KHB",
  status: "replayed",
  requested_by: "u-1",
  requested_at: "2026-11-14T02:00:00Z",
  received_on: "2026-11-06",
  po_file_name: "po.xlsx",
  salesorder_file_name: "SalesOrder.xlsx",
  rules: {
    columns: [
      {
        column: "AF",
        field: "requested_date",
        customer: null,
        steps: [{ step: "shift_days", days: -9 }],
      },
    ],
  },
  replay: {
    layout_ref: "sales_bravo_upload@2.0.0",
    rows_expected: 2,
    rows_got: 2,
    cells_compared: 36,
    differences_total: 1,
    differences: [
      {
        cell: "AF4",
        column: "AF",
        header: "Ngày KH yêu cầu",
        expected: "2026-12-10",
        got: "2026-12-11",
        source: "rule",
        problem: "value_differs",
        step: null,
      },
    ],
    left_blank: [{ column: "AG", header: "Ngày XN giao hàng", filled_rows: 2 }],
  },
  submittable: false,
  problems: [],
  error: null,
  prompt_ref: "sales.salesorder_rules_proposal@1.0.0",
  model_profile: "onprem",
  version_id: null,
};

afterEach(cleanup);

describe("a worked example's replay (ticket 38)", () => {
  it("closes Gửi duyệt for a replay that differs, and says why", () => {
    expect(submitBlocked(replayed)).toMatch(/chưa khớp/);
    expect(submitBlocked({ ...replayed, submittable: true })).toBeNull();
    expect(submitBlocked({ ...replayed, status: "submitted" })).toMatch(
      /đã được gửi/,
    );
    expect(
      submitBlocked({ ...replayed, rules: null, submittable: false }),
    ).toMatch(/không cần quy tắc riêng/);
    expect(replaySummary(replayed.replay!)).toBe(
      "35 ô khớp · 1 ô khác · 2 dòng",
    );
  });

  it("lists each cell that differs, the rule in words and what is left to a person", () => {
    render(
      <UiProvider>
        <SalesOrderReplay example={replayed} />
      </UiProvider>,
    );
    expect(screen.getByText("AF4")).toBeTruthy();
    expect(screen.getByText("2026-12-10")).toBeTruthy();
    expect(screen.getByText("2026-12-11")).toBeTruthy();
    expect(screen.getByText("AF ← requested_date: lùi 9 ngày")).toBeTruthy();
    expect(
      screen.getByText(/AG \(Ngày XN giao hàng\): PIC điền 2 dòng/),
    ).toBeTruthy();
    // The rules are the model's proposal until a person approves them.
    expect(screen.getByText("Máy đề xuất")).toBeTruthy();
  });

  it("says each step of the closed set in words, and which customers changed", () => {
    expect(
      ruleWords({
        column: "V",
        field: "customer_item_code",
        customer: null,
        steps: [
          { step: "lookup", table: "convert_list", key: null },
          { step: "lookup", table: "item_colour", key: null },
        ],
      }),
    ).toBe(
      "V ← customer_item_code: tra convert list của khách, tra màu của mã hàng",
    );
    expect(
      changedCustomers(
        { customers: { KHA: { columns: [] } } },
        { customers: { KHA: { columns: [] }, KHB: { columns: [] } } },
      ),
    ).toEqual(["KHB"]);
  });
});
