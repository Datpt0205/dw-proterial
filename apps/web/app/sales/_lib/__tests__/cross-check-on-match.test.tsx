import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { SalesSchemas } from "@dw/api-client";
import { AN, DIEU, GIANG, orderInBravo, pcRequest } from "./fixtures";

type Order = SalesSchemas["OrderCaseView"];

// Tickets 80 and 81 on the order page and its actions: a password file's
// values, a cross-check DW passed on Bravo's read-back and why it did not,
// and taking a pass back.

const PIC = [
  "sales.case.read",
  "sales.price.read",
  "sales.order.prepare",
  "sales.order.cross_check",
];
let principalId = GIANG;
let scopes = PIC;
vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId,
    displayName: "Người xem",
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => scopes.includes(scope),
  }),
}));
vi.mock("../../../../lib/session", () => ({
  apiClient: () => ({ listWorkspaceMembers: vi.fn().mockResolvedValue([]) }),
}));
vi.mock("next/navigation", () => ({
  useParams: () => ({ caseId: orderInBravo().case_id }),
}));

const LANE = "5607c9a9-ef33-5e39-964f-302d8002b0e3";

/** An order whose cross-check DW passed on Bravo's matching read-back. */
function passedByDw(): Order {
  return {
    ...orderInBravo(),
    status: "cross_checked",
    case_version: 8,
    decision: null,
    cross_check_on_match: true,
    cross_checked_by: LANE,
    cross_checked_at: "2026-11-27T03:00:00Z",
    cross_checked_on_read_back: "e".repeat(64),
  };
}

let shown: Order = orderInBravo();
const api = {
  pcRequest: vi.fn(async () => pcRequest()),
  order: vi.fn(async () => shown),
  bravoWrites: vi.fn(async () => []),
  // The Bravo the write panel names (ticket 85).
  bravoTargets: vi.fn(async () => ({
    connected: true,
    current: "uat" as const,
    uat: true,
    production: false,
  })),
  bravoReadBack: vi.fn(async () => ({
    read_back: null,
    stale: false,
    prices_hidden: false,
  })),
  myWork: vi.fn(async () => []),
  history: vi.fn(async () => []),
  caseActivity: vi.fn(async () => ({ entries: [] })),
  customers: vi.fn(async () => ({ items: [] })),
  artifacts: vi.fn(async () => ({
    case_version: shown.case_version,
    available: [],
    artifacts: [],
  })),
  reopenCrossCheck: vi.fn(async () => ({})),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import OrderPage from "../../orders/[caseId]/page";
import { OrderActions } from "../../orders/[caseId]/actions";
import { SalesFrameProvider } from "../../_components/sales-frame";
import { orderOffers, STALLED_CROSS_CHECK } from "../order-actions";
import { DW_PASS_COVERS } from "../statements";

function as(id: string, held: string[]) {
  principalId = id;
  scopes = held;
  return { principalId: id, hasScope: (scope: string) => held.includes(scope) };
}

function ui(node: ReactNode) {
  return render(<UiProvider>{node}</UiProvider>);
}

function page() {
  return ui(
    <SalesFrameProvider>
      <OrderPage />
    </SalesFrameProvider>,
  );
}

const FACTS = "Căn cứ và dấu vết của hồ sơ";

/** The page, with its facts panel opened as a person clicks it. */
async function facts() {
  page();
  fireEvent.click(await screen.findByText(FACTS, undefined, { timeout: 5000 }));
}

const SLOW = 20_000;

afterEach(() => {
  cleanup();
  shown = orderInBravo();
  as(GIANG, PIC);
  api.reopenCrossCheck.mockClear();
});

describe("taking back a cross-check DW passed (ticket 81)", () => {
  it("is offered to whoever may cross-check and made none of the order", () => {
    const offers = orderOffers(passedByDw(), as(GIANG, PIC), {
      sourceOpened: true,
    });
    expect(offers.reopenCrossCheck).toEqual({ reason: null });
  });

  it("is refused to a maker, saying why", () => {
    const offers = orderOffers(passedByDw(), as(AN, PIC), {
      sourceOpened: true,
    });
    expect(offers.reopenCrossCheck?.reason).toBe(
      "Bạn đã chuẩn bị đơn này nên không tự kiểm chéo được (tách nhiệm, WIV-03-012 bước 9).",
    );
  });

  it("is refused to someone without the cross-check scope, saying why", () => {
    const viewer = as(
      DIEU,
      PIC.filter((s) => s !== "sales.order.cross_check"),
    );
    const offers = orderOffers(passedByDw(), viewer, { sourceOpened: true });
    expect(offers.reopenCrossCheck?.reason).toMatch(
      /^Bạn không có quyền kiểm chéo đơn/,
    );
  });

  it("is not offered on a cross-check a person decided", () => {
    const byHand = {
      ...passedByDw(),
      cross_checked_by: DIEU,
      cross_checked_on_read_back: null,
    };
    const offers = orderOffers(byHand, as(GIANG, PIC), { sourceOpened: true });
    expect(offers.reopenCrossCheck).toBeUndefined();
  });

  it(
    "says after it who must raise the cross-check again, not that it was",
    async () => {
      const order = passedByDw();
      ui(
        <OrderActions
          order={order}
          viewer={as(GIANG, PIC)}
          sourceOpened
          onChanged={() => {}}
        />,
      );
      fireEvent.click(screen.getByRole("button", { name: "Mở lại kiểm chéo" }));
      await waitFor(() => expect(api.reopenCrossCheck).toHaveBeenCalled());
      expect(api.reopenCrossCheck.mock.calls[0]?.slice(0, 2)).toEqual([
        order.case_id,
        order.case_version,
      ]);
      expect(
        await screen.findByText(`Đã mở lại kiểm chéo. ${STALLED_CROSS_CHECK}`),
      ).toBeTruthy();
    },
    SLOW,
  );
});

describe("the order page (tickets 80 and 81)", () => {
  it(
    "says what a DW pass compared and what it did not",
    async () => {
      shown = passedByDw();
      await facts();
      const row = await screen.findByText(
        (text) => text.startsWith(DW_PASS_COVERS),
        undefined,
        { timeout: 5000 },
      );
      expect(row.textContent).toContain("không có người kiểm");
      expect(row.textContent).toContain("số SO và từng dòng");
      expect(row.textContent).toContain("đầu SO");
      expect(row.textContent).toContain("chưa đối chiếu");
    },
    SLOW,
  );

  it(
    "tells the cross-checker why DW did not pass it",
    async () => {
      shown = {
        ...orderInBravo(),
        cross_check_on_match: true,
        cross_check_on_match_exceptions: ["so_no_differs", "finding"],
      };
      page();
      // On the page itself, not in a collapsed panel: it is what the
      // cross-checker looks at (ui-quality section 2).
      expect(
        await screen.findByText("DW không tự kiểm chéo đơn này", undefined, {
          timeout: 5000,
        }),
      ).toBeTruthy();
      expect(
        screen.getByText(
          "Cần xem: Số SO trong Bravo khác số SO đã ghi; Có cờ kiểm tra.",
        ),
      ).toBeTruthy();
    },
    SLOW,
  );

  it(
    "says nothing of it when DW gave no reason",
    async () => {
      await facts();
      expect(screen.getByText("Kiểm chéo")).toBeTruthy();
      expect(screen.queryByText("DW không tự kiểm chéo đơn này")).toBeNull();
      expect(screen.queryByText("Tệp có mật khẩu")).toBeNull();
    },
    SLOW,
  );

  it.each([
    ["every_value", "mọi giá trị chờ xác nhận"],
    ["failed_checks_only", "chỉ giá trị kiểm không đạt chờ xác nhận"],
  ] as const)(
    "names a file opened with a password (%s)",
    async (mode, words) => {
      shown = { ...orderInBravo(), password_file: mode };
      await facts();
      expect(
        await screen.findByText("Tệp có mật khẩu", undefined, {
          timeout: 5000,
        }),
      ).toBeTruthy();
      expect(
        screen.getByText(`Mở bằng mật khẩu trong thư · ${words}`),
      ).toBeTruthy();
    },
    SLOW,
  );
});
