import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { Approval } from "@dw/contracts";

vi.mock("../../../../lib/session", () => ({ apiClient: () => ({}) }));

import {
  approvalDetail,
  approvalInbox,
} from "../../../../lib/approvals/registry";
import { ApprovalHostDetail } from "../../../../components/approval-host-detail";

const CASE = "6f1c2a40-0d3e-4b8a-9f55-1c2d3e4f5a6b";
const HASH = "ab12cd34" + "0".repeat(56);

function asked(payload: Record<string, unknown> = {}): Approval {
  return {
    id: "a-1",
    approval_type: "bravo_write.sales_order",
    reason: "Ghi thay đổi dòng SO vào Bravo, dưới user Bravo của người duyệt",
    status: "pending",
    run_id: null,
    payload: {
      approval_type: "bravo_write.sales_order",
      case_id: CASE,
      so_no: "SO2611-000161",
      line_no: 2,
      item_code: "PRV-2",
      field: "cancel",
      before: "6100",
      after: "Hủy: khách bỏ dòng",
      content_hash: HASH,
      ...payload,
    },
    created_at: "2026-11-26T02:00:00Z",
    decided_at: null,
    requires_comment: false,
    required_scope: "sales.bravo.write",
    can_decide: true,
    requested_by_me: true,
  } as Approval;
}

afterEach(cleanup);

describe("a Bravo write's approval where it is decided (tickets 53, 71)", () => {
  it("is decided on /approvals, with DW1's own drawing of it", () => {
    expect(approvalInbox(asked())).toBeNull();
    expect(approvalDetail(asked())).not.toBeNull();
  });

  it("shows the SO line, Bravo's value and the cancel, and links to the case", () => {
    render(
      <UiProvider>
        <ApprovalHostDetail approval={asked()} />
      </UiProvider>,
    );
    expect(screen.getByText("SO2611-000161")).toBeTruthy();
    expect(screen.getByText("PRV-2")).toBeTruthy();
    expect(screen.getByText("Hủy dòng")).toBeTruthy();
    expect(screen.getByText("6.100 → Hủy: khách bỏ dòng")).toBeTruthy();
    expect(screen.getByText("ab12cd34")).toBeTruthy();
    expect(screen.getByText(/Bravo đưa số lượng và thành tiền/)).toBeTruthy();
    expect(
      screen
        .getByRole("link", { name: "Mở hồ sơ đơn hàng" })
        .getAttribute("href"),
    ).toBe(`/sales/orders/${CASE}`);
  });

  it("shows a date change as days, without the cancel's warning", () => {
    render(
      <UiProvider>
        <ApprovalHostDetail
          approval={asked({
            field: "confirmed_date",
            before: "2026-12-01",
            after: "2026-12-08",
          })}
        />
      </UiProvider>,
    );
    expect(screen.getByText("01/12/2026 → 08/12/2026")).toBeTruthy();
    expect(screen.queryByText(/Bravo đưa số lượng/)).toBeNull();
  });

  it("never builds a link from a case id it does not recognise", () => {
    render(
      <UiProvider>
        <ApprovalHostDetail approval={asked({ case_id: "../../admin" })} />
      </UiProvider>,
    );
    expect(screen.queryByRole("link")).toBeNull();
  });
});
