import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { SalesSchemas } from "@dw/api-client";
import { AN, finding, order } from "./fixtures";

type Order = SalesSchemas["OrderCaseView"];
type Reply = SalesSchemas["CaseReplyView"];

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

const KEEP = "Please keep the PO as it is.";

function reply(overrides: Partial<Reply> = {}): Reply {
  return {
    message_id: "M42",
    processed_at: "2026-10-02T10:50:00Z",
    linked_to: "M04",
    outcome: "read",
    kind: "keeps_po_as_is",
    quotes: [KEEP],
    prompt: "sales.reply_intent@1.0.0",
    proposal: "resume_review",
    ...overrides,
  };
}

/** M04 sent back to the customer, and M42's reply in its thread. */
function waiting(replies: Reply[]): Order {
  return order({
    status: "correction_requested",
    findings: [
      finding({
        key: "price_mismatch:2",
        disposition: {
          kind: "ask_customer",
          by: AN,
          at: "2026-10-01T03:00:00Z",
          reason: null,
          value: null,
          source: null,
        },
      }),
    ],
    replies,
  });
}

let shown: Order = waiting([reply()]);
const api = {
  order: vi.fn(async () => shown),
  myWork: vi.fn(async () => []),
  customers: vi.fn(async () => ({ items: [] })),
  artifacts: vi.fn(async () => ({
    case_version: shown.case_version,
    available: [],
    artifacts: [],
  })),
  resumeReview: vi.fn(async () => ({
    case_kind: "order",
    case_id: shown.case_id,
    case_version: shown.case_version + 1,
    status: "in_review",
  })),
};
vi.mock("../api", () => ({ salesApi: () => api }));
vi.mock("next/navigation", () => ({
  useParams: () => ({ caseId: shown.case_id }),
}));

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

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("a customer's reply in the case's thread (ticket 32)", () => {
  it(
    "shows the sentence the model read and marks, never presses, the step it proposes",
    async () => {
      shown = waiting([reply()]);
      page();

      expect(await screen.findByText(`“${KEEP}”`)).toBeTruthy();
      expect(screen.getByText("Mô hình đọc: Giữ nguyên PO")).toBeTruthy();
      expect(screen.getByText("Đề xuất từ thư khách")).toBeTruthy();
      expect(api.resumeReview).not.toHaveBeenCalled();

      fireEvent.click(
        screen.getByRole("button", { name: "Khách giữ PO: xem xét lại" }),
      );
      await waitFor(() => expect(api.resumeReview).toHaveBeenCalledTimes(1));
      const [caseId, version] = api.resumeReview.mock.calls[0] as unknown as [
        string,
        number,
      ];
      expect([caseId, version]).toEqual([shown.case_id, shown.case_version]);
    },
    SLOW,
  );

  it(
    "a reply nobody read proposes nothing, and the step is still Sales' to take",
    async () => {
      shown = waiting([
        reply({
          outcome: null,
          kind: null,
          quotes: [],
          prompt: null,
          proposal: null,
        }),
      ]);
      page();

      expect(
        await screen.findByText("Chưa đọc: bước mô hình đang tắt"),
      ).toBeTruthy();
      expect(screen.queryByText("Đề xuất từ thư khách")).toBeNull();
      expect(
        screen.getByRole("button", { name: "Khách giữ PO: xem xét lại" }),
      ).toBeTruthy();
    },
    SLOW,
  );
});
