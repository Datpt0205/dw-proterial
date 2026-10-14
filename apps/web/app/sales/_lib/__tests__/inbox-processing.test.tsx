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
      page();

      fireEvent.click(
        await screen.findByRole("button", { name: "DW xử lý thư M02" }),
      );
      await waitFor(() => expect(api.processMessage).toHaveBeenCalledTimes(1));
      expect(api.processMessage.mock.calls[0]![0]).toBe("M02");

      // The API answered with the job; the worker has it now.
      inbox = [
        message("M02", { processing: job("M02", { status: "running" }) }),
      ];
      await waitFor(() =>
        expect(within(row("M02")).getByRole("status").textContent).toContain(
          "DW1 đang xử lý",
        ),
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
