import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { SalesSchemas } from "@dw/api-client";
import { AN, DIEU, orderInBravo } from "./fixtures";

type Order = SalesSchemas["OrderCaseView"];

// An, who recorded the Bravo entry, opens his order.
const SCOPES = [
  "sales.case.read",
  "sales.price.read",
  "sales.order.prepare",
  "sales.order.cross_check",
];
vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: AN,
    displayName: "An",
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => SCOPES.includes(scope),
  }),
}));
vi.mock("../../../../lib/session", () => ({
  apiClient: () => ({ listWorkspaceMembers: vi.fn().mockResolvedValue([]) }),
}));
vi.mock("next/navigation", () => ({
  useParams: () => ({ caseId: orderInBravo().case_id }),
}));

let shown: Order = orderInBravo();
const api = {
  order: vi.fn(async () => shown),
  myWork: vi.fn(async () => []),
  customers: vi.fn(async () => ({ items: [] })),
  artifacts: vi.fn(async () => ({
    case_version: shown.case_version,
    available: [],
    artifacts: [],
  })),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import OrderPage from "../../orders/[caseId]/page";
import { SalesFrameProvider } from "../../_components/sales-frame";

function page() {
  return render(
    <UiProvider>
      <SalesFrameProvider>
        <OrderPage />
      </SalesFrameProvider>
    </UiProvider>,
  );
}

const SLOW = 20_000;
const NOT_APPLIED = "Quyết định kiểm chéo trước chưa được áp dụng vào đơn";

afterEach(() => {
  cleanup();
  shown = orderInBravo();
});

describe("an order whose cross-check decision was not applied (ticket 14)", () => {
  it(
    "says so, who decided which way, why, and offers to raise it again",
    async () => {
      shown = {
        ...orderInBravo(),
        case_version: 9,
        decision: null,
        cross_check_stalled: true,
        unapplied_decision: {
          approval_id: "01a10aa0-fe9a-7000-a7de-ed21190d4c0c",
          run_id: "01a10aa0-fe9a-7000-a7de-ed21190d4c0d",
          decided_by: DIEU,
          approved: true,
          decided_on: 7,
          reason_code: "stale_case_version",
          at: "2026-10-05T04:00:00Z",
        },
      };
      page();
      expect(
        await screen.findByText(NOT_APPLIED, undefined, { timeout: 5000 }),
      ).toBeTruthy();
      const why = screen.getByText(/Lý do: Hồ sơ đã đổi phiên bản/);
      expect(why.textContent).toContain("kiểm chéo đạt trên phiên bản 7");
      expect(why.textContent).toContain("ở phiên bản 9");
      expect(
        screen
          .getByRole("button", { name: "Gửi kiểm chéo lại" })
          .hasAttribute("disabled"),
      ).toBe(false);
    },
    SLOW,
  );

  it(
    "says nothing of it while a cross-check request is pending",
    async () => {
      page();
      expect(
        await screen.findByText("Đã nhập Bravo", undefined, { timeout: 5000 }),
      ).toBeTruthy();
      expect(screen.queryByText(NOT_APPLIED)).toBeNull();
      expect(
        screen.queryByRole("button", { name: "Gửi kiểm chéo lại" }),
      ).toBeNull();
    },
    SLOW,
  );
});
