import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import { ApiError, type SalesSchemas } from "@dw/api-client";
import { DIEU, orderInBravo, pendingQuote, pcRequest } from "./fixtures";

/**
 * A case page that can no longer read its case (full review, 2026-11-27):
 * Diệu's own "Ghi kiểm chéo đạt" takes the order out of what she sees, and
 * the page read again used to land on "Không tìm thấy" with the server's
 * English "no such order case" under it.
 */
type Order = SalesSchemas["OrderCaseView"];
type Quote = SalesSchemas["QuoteCaseView"];

const SCOPES = [
  "sales.case.read",
  "sales.price.read",
  "sales.order.cross_check",
  "sales.quote.approve",
];
vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: DIEU,
    displayName: "Diệu",
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => SCOPES.includes(scope),
  }),
}));
vi.mock("../../../../lib/session", () => ({
  apiClient: () => ({ listWorkspaceMembers: vi.fn().mockResolvedValue([]) }),
}));
let caseId = "";
vi.mock("next/navigation", () => ({
  useParams: () => ({ caseId }),
}));
const decided = vi.hoisted(() => ({ decideApproval: vi.fn(async () => ({})) }));
vi.mock("../../../../lib/approvals/registry", async (importOriginal) => ({
  ...(await importOriginal<
    typeof import("../../../../lib/approvals/registry")
  >()),
  approvalClient: () => decided,
}));

const ENGLISH = "no such order case";
const gone = (message: string) =>
  new ApiError(404, { code: "not_found", message, details: {} });

let order: Order = orderInBravo();
const api = {
  pcRequest: vi.fn(async () => pcRequest()),
  order: vi.fn(async (): Promise<Order> => order),
  bravoWrites: vi.fn(async () => []),
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
  quote: vi.fn(async (): Promise<Quote> => pendingQuote()),
  myWork: vi.fn(async () => []),
  history: vi.fn(async () => []),
  caseActivity: vi.fn(async () => ({ entries: [] })),
  customers: vi.fn(async () => ({ items: [] })),
  lme: vi.fn(async () => ({ items: [] })),
  orderSource: vi.fn(() => new Promise(() => {})),
  quoteSource: vi.fn(() => new Promise(() => {})),
  artifacts: vi.fn(async () => ({
    case_version: 3,
    available: [],
    artifacts: [],
  })),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import OrderPage from "../../orders/[caseId]/page";
import QuotePage from "../../quotes/[caseId]/page";
import { SalesFrameProvider } from "../../_components/sales-frame";
import {
  CASE_LEFT_VIEW,
  CASE_NOT_FOUND,
} from "../../_components/case-load-error";
import { markMailServed, markServed, unopenedSources } from "../served";

function show(page: "order" | "quote") {
  caseId = page === "order" ? order.case_id : pendingQuote().case_id;
  return render(
    <UiProvider>
      <SalesFrameProvider>
        {page === "order" ? <OrderPage /> : <QuotePage />}
      </SalesFrameProvider>
    </UiProvider>,
  );
}

const SLOW = 20_000;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  order = orderInBravo();
});

describe("a case page that cannot read its case", () => {
  it(
    "after the checker's own cross-check, says the case left their work and leads back",
    async () => {
      // The original opened, as the cross-checker must before deciding.
      markMailServed(order.case_id, order.case_version);
      for (const region of unopenedSources(order).regions)
        markServed(order.case_id, order.case_version, region);
      show("order");
      fireEvent.click(
        await screen.findByRole(
          "button",
          { name: "Kiểm chéo đạt" },
          { timeout: 5000 },
        ),
      );
      fireEvent.change(await screen.findByLabelText("Ghi chú kiểm chéo"), {
        target: { value: "Đã đối chiếu SO với PO" },
      });
      // Decided: the case no longer waits on her, so it reads as not found.
      api.order.mockRejectedValue(gone(ENGLISH));
      fireEvent.click(
        screen.getByRole("button", { name: "Ghi kiểm chéo đạt" }),
      );
      await waitFor(() => expect(decided.decideApproval).toHaveBeenCalled());
      expect(
        await screen.findByText(CASE_LEFT_VIEW, undefined, { timeout: 5000 }),
      ).toBeTruthy();
      expect(
        screen.getByRole("link", { name: "Về Việc cần làm" }),
      ).toBeTruthy();
      expect(screen.queryByText(ENGLISH)).toBeNull();
    },
    SLOW,
  );

  it(
    "opened by a link it cannot read, says so in words without saying it exists",
    async () => {
      api.quote.mockRejectedValue(gone("no such quote case"));
      show("quote");
      expect(
        await screen.findByText(CASE_NOT_FOUND, undefined, { timeout: 5000 }),
      ).toBeTruthy();
      expect(screen.queryByText("no such quote case")).toBeNull();
      expect(screen.queryByText(CASE_LEFT_VIEW)).toBeNull();
    },
    SLOW,
  );

  it(
    "draws any other failure as before",
    async () => {
      api.order.mockRejectedValue(
        new ApiError(500, {
          code: "internal",
          message: "Lỗi máy chủ",
          details: {},
          request_id: "req-1",
        }),
      );
      show("order");
      expect(
        await screen.findByText("Không tải được dữ liệu", undefined, {
          timeout: 5000,
        }),
      ).toBeTruthy();
      expect(screen.queryByText(CASE_NOT_FOUND)).toBeNull();
    },
    SLOW,
  );
});
