import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { SalesSchemas } from "@dw/api-client";
import { AN, DIEU, finding, order } from "./fixtures";

type Order = SalesSchemas["OrderCaseView"];

// The order a customer without a valid NOC/ESF sent (M03), cross-checked by
// Diệu: confirmation is the next step, and the case refuses it while the
// export-control finding is open (contract acceptance row 3).
const SCOPES = ["sales.case.read", "sales.price.read", "sales.order.prepare"];
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
  useParams: () => ({ caseId: order().case_id }),
}));

const ACCEPTED = {
  kind: "accepted",
  reason: "Đã nhận NOC và ESF năm nay",
  value: null,
  source: null,
  by: AN,
  at: "2026-10-05T05:00:00Z",
} as const;

function crossChecked(
  noc: Partial<SalesSchemas["OrderFindingView"]> = {},
): Order {
  return order({
    status: "cross_checked",
    case_version: 8,
    prepared_by: AN,
    bravo_so_no: "SO-2610-0001",
    bravo_recorded_by: AN,
    bravo_entry_compared: true,
    cross_checked_by: DIEU,
    makers: [AN],
    findings: [
      finding({
        key: "missing_noc_esf:-",
        code: "missing_noc_esf",
        line_no: null,
        allowed: ["accepted"],
        ...noc,
      }),
    ],
  });
}

let shown: Order = crossChecked();
const api = {
  order: vi.fn(async () => shown),
  myWork: vi.fn(async () => []),
  history: vi.fn(async () => []),
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
const HELD = "Đơn đang bị giữ: chờ PIC kiểm soát xuất khẩu xác nhận NOC/ESF.";
const BLOCKED =
  "Quy tắc kiểm soát xuất khẩu đang chặn xác nhận đơn có cờ Thiếu NOC/ESF.";

afterEach(() => {
  cleanup();
  shown = crossChecked();
});

describe("an order held for export control (contract acceptance row 3)", () => {
  it(
    "says in words, as a status, that it is held and cannot be confirmed yet",
    async () => {
      page();
      const title = await screen.findByText(HELD, undefined, {
        timeout: 5000,
      });
      const notice = title.closest("[role='status']");
      expect(notice).not.toBeNull();
      expect(notice!.textContent).toContain("Chưa thể gửi xác nhận cho khách.");
      // The confirm button agrees, with the same reason in words.
      expect(
        screen
          .getByRole("button", { name: "Đã gửi xác nhận" })
          .hasAttribute("disabled"),
      ).toBe(true);
    },
    SLOW,
  );

  it(
    "says nothing of a hold once the export-control PIC accepted NOC/ESF",
    async () => {
      shown = crossChecked({ disposition: ACCEPTED });
      page();
      expect(
        (
          await screen.findAllByText("Đã kiểm chéo", undefined, {
            timeout: 5000,
          })
        )[0],
      ).toBeTruthy();
      expect(screen.queryByText(HELD)).toBeNull();
    },
    SLOW,
  );

  it(
    "says the rule holds it when the case's mode blocks confirmation, accepted or not",
    async () => {
      shown = {
        ...crossChecked({ disposition: ACCEPTED }),
        export_control_mode: "block_confirmation",
      };
      page();
      const title = await screen.findByText(BLOCKED, undefined, {
        timeout: 5000,
      });
      expect(title.closest("[role='status']")).not.toBeNull();
      expect(screen.queryByText(HELD)).toBeNull();
      expect(
        screen
          .getByRole("button", { name: "Đã gửi xác nhận" })
          .hasAttribute("disabled"),
      ).toBe(true);
    },
    SLOW,
  );

  it(
    "says nothing of a hold on a closed case",
    async () => {
      shown = { ...crossChecked(), status: "closed" };
      page();
      expect(
        (
          await screen.findAllByText(/Hồ sơ đã đóng/, undefined, {
            timeout: 5000,
          })
        )[0],
      ).toBeTruthy();
      expect(screen.queryByText(HELD)).toBeNull();
    },
    SLOW,
  );
});
