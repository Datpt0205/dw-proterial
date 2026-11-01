import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { SalesSchemas } from "@dw/api-client";
import { AN } from "./fixtures";

type Message = SalesSchemas["InboxMessageView"];
type Job = SalesSchemas["ProcessingJobView"];

const SCOPES = ["sales.case.read", "sales.inbox.process"];
const OVERVIEW = "sales.overview.read";
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
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/sales/inbox",
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

function job(message_id: string, overrides: Partial<Job> = {}): Job {
  return {
    job_id: `job-${message_id}`,
    message_id,
    status: "queued",
    requested_at: "2026-10-14T03:00:00Z",
    attempts: 0,
    error: null,
    ...overrides,
  };
}

function message(id: string, overrides: Partial<Message> = {}): Message {
  return {
    message_id: id,
    sender: "orders@vlx.example",
    sender_name: "VLX Purchasing",
    subject: `PO ${id}`,
    received_at: "2026-10-01T03:00:00Z",
    body_text: "Kính gửi Sales",
    attachments: [],
    sender_verified: true,
    disposition: { kind: "not_yet_processed" },
    handoff_draft: null,
    processing: null,
    ...overrides,
  };
}

let inbox: Message[] = [];
const api = {
  inbox: vi.fn(async () => inbox),
  processMessage: vi.fn(async (id: string) => job(id)),
  processAll: vi.fn(async () => ({ jobs: [] })),
  overview: vi.fn(async () => ({
    worker: { paused: false, changed_by: null, changed_at: null, reason: null },
  })),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import InboxPage from "../../inbox/page";
import { SalesFrameProvider } from "../../_components/sales-frame";

function page() {
  return render(
    <UiProvider>
      <SalesFrameProvider>
        <InboxPage />
      </SalesFrameProvider>
    </UiProvider>,
  );
}

const row = (id: string) =>
  screen.getAllByRole("row").find((r) => r.textContent?.includes(`PO ${id}`))!;

const SLOW = 20_000;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  if (SCOPES.includes(OVERVIEW)) SCOPES.pop();
});

describe('"DW xử lý" queues and the inbox shows where it stands (ticket 25)', () => {
  it(
    "a queued message says so in a status region, with nothing to press, and is not counted for all",
    async () => {
      inbox = [message("M01", { processing: job("M01") }), message("M02")];
      page();

      await screen.findByText("PO M01");
      const queued = within(row("M01"));
      expect(queued.getByRole("status").textContent).toContain("Đang chờ DW1");
      expect(queued.queryByRole("button", { name: /DW xử lý/ })).toBeNull();
      expect(
        screen.getByRole("button", { name: /DW xử lý tất cả \(1\)/ }),
      ).toBeTruthy();
      expect(
        screen.getByText(/2 chưa xử lý \(1 DW1 đang xử lý\)/),
      ).toBeTruthy();
    },
    SLOW,
  );

  it(
    "pressing queues the message, then the page reads the inbox until the job is done",
    async () => {
      inbox = [message("M02")];
      // As the server does: once the job is queued, the inbox shows it, and
      // the worker has it by the next read. Set inside the call, so the page's
      // own reload after the press can never read the inbox from before it.
      api.processMessage.mockImplementationOnce(async (id: string) => {
        inbox = [
          message("M02", { processing: job("M02", { status: "running" }) }),
        ];
        return job(id);
      });
      page();

      fireEvent.click(
        await screen.findByRole("button", { name: "DW xử lý thư M02" }),
      );
      await waitFor(() => expect(api.processMessage).toHaveBeenCalledTimes(1));
      expect(api.processMessage.mock.calls[0]![0]).toBe("M02");
      // The page reads the inbox every 3 s (POLL_MS): wait one read, not 1 s.
      await waitFor(
        () =>
          expect(within(row("M02")).getByRole("status").textContent).toContain(
            "DW1 đang xử lý",
          ),
        { timeout: 5_000 },
      );

      // Done: the next read shows the case, and the page stops reading.
      inbox = [
        message("M02", {
          processing: job("M02", { status: "done", attempts: 1 }),
          disposition: {
            kind: "case_created",
            case_kind: "order",
            case_id: "c-1",
            processed_at: "2026-10-14T03:00:05Z",
          },
        }),
      ];
      await waitFor(
        () => expect(within(row("M02")).getByText("Đã tạo hồ sơ")).toBeTruthy(),
        { timeout: 10_000 },
      );
      const reads = api.inbox.mock.calls.length;
      await new Promise((resolve) => setTimeout(resolve, 3_500));
      expect(api.inbox.mock.calls.length).toBe(reads);
    },
    SLOW,
  );

  it(
    "a failed job says why, and the button is there to press again",
    async () => {
      inbox = [
        message("M03", {
          processing: job("M03", {
            status: "failed",
            error: "quota",
            attempts: 1,
          }),
        }),
      ];
      page();

      await screen.findByText("PO M03");
      const failed = within(row("M03"));
      expect(failed.getByText("DW1 chưa xử lý được")).toBeTruthy();
      expect(
        failed.getByText("Hết lượt chạy DW1 trong ngày của gói"),
      ).toBeTruthy();
      expect(
        failed.getByRole("button", { name: "DW xử lý thư M03" }),
      ).toBeTruthy();
      expect(
        screen.getByRole("button", { name: /DW xử lý tất cả \(1\)/ }),
      ).toBeTruthy();
    },
    SLOW,
  );

  it(
    "with every waiting message already with DW1, all is disabled and says why",
    async () => {
      inbox = [
        message("M04", { processing: job("M04", { status: "running" }) }),
      ];
      page();

      await screen.findByText("PO M04");
      const all = screen.getByRole("button", {
        name: /DW xử lý tất cả \(0\)/,
      });
      expect(all.hasAttribute("disabled")).toBe(true);
      expect(
        screen.getByText(
          "DW1 đang xử lý các thư đã xếp, chờ xong rồi xem kết quả.",
        ),
      ).toBeTruthy();
    },
    SLOW,
  );
});

describe("the DW1 bar follows a press without a reload (defect D)", () => {
  it(
    "after 'DW xử lý tất cả' the bar reads the mailbox again at once",
    async () => {
      SCOPES.push(OVERVIEW);
      inbox = [message("M01"), message("M02")];
      page();
      expect(
        await screen.findByText("DW1 đang chờ: còn 2 thư chưa xử lý"),
      ).toBeTruthy();

      // The API queued both; nothing was queued when the bar last read, so
      // only the press can tell it to read again.
      inbox = [
        message("M01", { processing: job("M01") }),
        message("M02", { processing: job("M02") }),
      ];
      fireEvent.click(
        screen.getByRole("button", { name: /DW xử lý tất cả \(2\)/ }),
      );
      await waitFor(() => expect(api.processAll).toHaveBeenCalledTimes(1));
      // Well inside both polls (3 s, 5 s): the press itself refreshed it.
      expect(
        await screen.findByText(
          "DW1 sắp đọc 2 thư đang chờ",
          {},
          { timeout: 1_500 },
        ),
      ).toBeTruthy();
    },
    SLOW,
  );
});

describe("what a model read is shown with the case code resolved it to (ticket 31)", () => {
  it(
    "links a PO reference to the order case DW1 holds for it, and no other",
    async () => {
      inbox = [
        message("M40", {
          disposition: {
            kind: "routed_to_sales",
            reason: "reply_to_case",
            processed_at: "2026-10-01T03:05:00Z",
            reading: {
              prompt: "sales.message_intent@1.0.0",
              model_profile: "local-small",
              route: "onprem",
              rules: "sales_order_rules@1.5.2",
              outcome: "read",
              kind: "reply_to_case",
              language: "vi",
              references: [
                {
                  number: "VLX-PO-2609-0118",
                  record: "purchase_order",
                  order_case_id: "c-9",
                },
                {
                  number: "VLX-PO-2609-0119",
                  record: "purchase_order",
                  order_case_id: null,
                },
                { number: "YCBG-2609-030", record: "quote_request" },
              ],
            },
          },
        }),
      ];
      page();

      // What the model read sits in the expanded row since 2026-11-01: the
      // column keeps the outcome and the case link.
      const expand = await waitFor(() => {
        const button = document.querySelector(
          "button.ant-table-row-expand-icon",
        );
        expect(button).not.toBeNull();
        return button as HTMLElement;
      });
      fireEvent.click(expand);
      const link = await screen.findByRole("link", {
        name: "PO VLX-PO-2609-0118",
      });
      expect(link.getAttribute("href")).toBe("/sales/orders/c-9");
      expect(
        screen.queryByRole("link", { name: "PO VLX-PO-2609-0119" }),
      ).toBeNull();
      expect(
        screen.queryByRole("link", { name: "YCBG/RFQ YCBG-2609-030" }),
      ).toBeNull();
      expect(screen.getByText(/YCBG\/RFQ YCBG-2609-030/)).toBeTruthy();
    },
    SLOW,
  );
});
