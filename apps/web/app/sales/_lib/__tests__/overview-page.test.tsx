import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { SalesSchemas } from "@dw/api-client";

type Overview = SalesSchemas["OverviewView"];

vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: "u-ha",
    displayName: "Hà",
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => scope === "sales.overview.read",
  }),
}));

const none = { cases: 0, median_seconds: null, max_seconds: null };
const overview: Overview = {
  as_of: "2026-10-27T03:00:00Z",
  kpi_policy: "sales_kpi@1.0.0",
  worker: { paused: false } as Overview["worker"],
  steps: [],
  messages: {
    total: 20,
    without_disposition: 2,
    oldest_waiting_seconds: null,
    routed_to_sales: 5,
    routed_without_owner: 1,
  },
  times: {
    dw: { cases: 3, median_seconds: 90, max_seconds: 300 },
    sales: none,
    design: none,
    approver: none,
    customer: none,
  },
  order_confirmation: { target_seconds: 3600, measured: none },
  quotation_time: {
    target_seconds: 86400,
    measured: { cases: 2, median_seconds: 7200, max_seconds: 9000 },
  },
  lines_printed: 10,
  lines_read: 10,
  mapping: { convert_list: 7, confirmed_candidate: 2, unresolved: 1 },
  findings_by_code: {},
  orders_prepared_without_correction: 0,
  quotes_sent_as_first_drafted: 0,
  a3_shadow: 0,
  export: [],
};
vi.mock("../../_components/sales-frame", () => ({
  SCOPE: { overview: "sales.overview.read" },
  useSalesFrame: () => ({
    overview: { data: overview, loading: false, error: null, reload: vi.fn() },
  }),
}));

import OverviewPage from "../../overview/page";

afterEach(cleanup);

describe("Tổng quan quy trình (2026-10-27)", () => {
  it(
    "names no mock set, splits the PRV counts, and says no case went through a holder",
    async () => {
      render(
        <UiProvider>
          <OverviewPage />
        </UiProvider>,
      );
      expect(screen.queryByText(/giả lập/)).toBeNull();
      expect(screen.getByText("Thư chưa có hướng xử lý")).toBeTruthy();
      expect(screen.getByText("Mã PRV khớp convert list")).toBeTruthy();
      expect(screen.getByText("Mã PRV chưa giải quyết")).toBeTruthy();

      // A holder no case has been through reads "none yet", not "unknown".
      const sales = screen.getByText("Sales quyết định").closest("tr")!;
      expect(within(sales).getAllByText("Chưa có hồ sơ")).toHaveLength(2);
      expect(screen.queryByText(/Không rõ/)).toBeNull();
      // A target with nothing measured says so; one with cases counts them.
      expect(screen.getByText(/· Chưa có hồ sơ$/)).toBeTruthy();
      expect(screen.getByText(/\(2 báo giá\)$/)).toBeTruthy();
    },
    20_000,
  );
});
