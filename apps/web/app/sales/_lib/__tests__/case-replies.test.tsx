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
import { AN, finding, order, pcRequest } from "./fixtures";

type Order = SalesSchemas["OrderCaseView"];
type Reply = SalesSchemas["CaseReplyView"];
type Sent = SalesSchemas["SentMessageView"];

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
    intents: [{ intent: "rejects", quotes: [KEEP] }],
    prompt: "sales.reply_intent@2.0.0",
    proposal: "resume_review",
    ...overrides,
  };
}

const ASK = "Could you confirm the unit price on line 2?";

/** A mail An sent the customer from Outlook (ticket 25), read as asking. */
function sent(overrides: Partial<Sent> = {}): Sent {
  return {
    message_id: "S1",
    received_at: "2026-10-01T03:00:00Z",
    subject: "RE: PO NRV-PO-26-0457",
    outcome: "read",
    intents: [{ intent: "asks", quotes: [ASK] }],
    prompt: "sales.reply_intent@2.0.0",
    proposal: "request_correction",
    ...overrides,
  };
}

/** M04 sent back to the customer, and M42's reply in its thread. */
function waiting(replies: Reply[], status = "correction_requested"): Order {
  return order({
    status,
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
  pcRequest: vi.fn(async () => pcRequest()),
  order: vi.fn(async () => shown),
  myWork: vi.fn(async () => []),
  history: vi.fn(async () => []),
  caseActivity: vi.fn(async () => ({ entries: [] })),
  customers: vi.fn(async () => ({ items: [] })),
  artifacts: vi.fn(async () => ({
    case_version: shown.case_version,
    available: [],
    artifacts: [],
  })),
  requestCorrection: vi.fn(),
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
      expect(screen.getByText("Mô hình đọc: Không đồng ý")).toBeTruthy();
      expect(screen.getByText("Đề xuất từ luồng thư")).toBeTruthy();
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
    "a reply the thread agent could not read says why, and shows the one-call reading (tickets 30, 31)",
    async () => {
      shown = waiting([reply({ fallback: "calls" })]);
      page();

      expect(await screen.findByText(/quá số lượt tra cứu/)).toBeTruthy();
      expect(screen.getByText("Mô hình đọc: Không đồng ý")).toBeTruthy();
    },
    SLOW,
  );

  it(
    "a reply nobody read proposes nothing, and the step is still Sales' to take",
    async () => {
      shown = waiting([
        reply({
          outcome: null,
          intents: [],
          prompt: null,
          proposal: null,
        }),
      ]);
      page();

      expect(
        await screen.findByText("Chưa đọc: bước mô hình đang tắt"),
      ).toBeTruthy();
      expect(screen.queryByText("Đề xuất từ luồng thư")).toBeNull();
      expect(
        screen.getByRole("button", { name: "Khách giữ PO: xem xét lại" }),
      ).toBeTruthy();
    },
    SLOW,
  );

  it(
    "shows the customer's mails before the PO, each opening in the inbox, and a picked reply as Sales'",
    async () => {
      shown = {
        ...waiting([
          reply({
            outcome: null,
            intents: [],
            prompt: null,
            proposal: null,
            picked_by: AN,
          }),
        ]),
        thread_before: [
          {
            message_id: "T0",
            received_at: "2026-09-23T01:00:00Z",
            sender: "hana.westbrook@norvanta.example",
            subject: "Kế hoạch đặt hàng quý 4",
          },
        ],
      };
      page();

      const before = await screen.findByRole("region", {
        name: "Trao đổi trước PO",
      });
      expect(before.textContent).toContain("Kế hoạch đặt hàng quý 4");
      expect(
        screen.getByRole("link", { name: "Thư T0" }).getAttribute("href"),
      ).toBe("/sales/inbox?message=T0");
      expect(screen.getByText("Sales chọn hồ sơ: chưa đọc")).toBeTruthy();
    },
    SLOW,
  );
});

describe("a mail Sales sent in the case's thread (tickets 25 and 26)", () => {
  it(
    "is marked as Sales', shows what it asked and marks, never presses, the wait on the customer",
    async () => {
      shown = { ...waiting([], "in_review"), thread_sent: [sent()] };
      page();

      expect(await screen.findByText("Sales gửi")).toBeTruthy();
      expect(screen.getByText(`“${ASK}”`)).toBeTruthy();
      expect(screen.getByText("Mô hình đọc: Hỏi")).toBeTruthy();
      expect(screen.getByText("Đề xuất từ luồng thư")).toBeTruthy();
      expect(
        screen.getByRole("button", { name: "Gửi yêu cầu khách sửa" }),
      ).toBeTruthy();
      expect(api.requestCorrection).not.toHaveBeenCalled();
    },
    SLOW,
  );

  it(
    "a mail nobody read shows under the thread with no proposal",
    async () => {
      shown = {
        ...waiting([], "in_review"),
        thread_sent: [
          sent({ outcome: null, intents: [], prompt: null, proposal: null }),
        ],
      };
      page();

      expect(await screen.findByText("Sales gửi")).toBeTruthy();
      expect(screen.queryByText(/Mô hình đọc/)).toBeNull();
      expect(screen.queryByText("Đề xuất từ luồng thư")).toBeNull();
    },
    SLOW,
  );
});
