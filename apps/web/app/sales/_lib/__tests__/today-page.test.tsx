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
import { AN, order } from "./fixtures";
import { bySla, slaOf } from "../sla";

type WorkItem = SalesSchemas["WorkItem"];
type Today = SalesSchemas["TodayView"];

/**
 * The one place for a person's work (tickets 47, 48): the brief on top, the
 * work ordered by its SLA and decided in its row with the case page's own
 * buttons, the reminders with their three answers, a push's deep link
 * opening its item.
 */

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
  apiClient: () => ({
    listWorkspaceMembers: vi.fn().mockResolvedValue([]),
    listApprovals: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
  }),
}));
let search = new URLSearchParams();
vi.mock("next/navigation", () => ({
  usePathname: () => "/sales",
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => search,
}));

const NOW = Date.parse("2026-10-05T03:00:00Z");
vi.mock("../../../../lib/server-clock", () => ({ serverNow: () => NOW }));

const waiting = order({ status: "correction_requested" });
const item = (
  id: string,
  warn: string | null,
  due: string | null,
  kind: WorkItem["kind"] = "order",
): WorkItem => ({
  kind,
  id,
  status: "in_review",
  action: "self_check",
  customer_code: "VLX",
  received_at: "2026-10-04T01:00:00Z",
  due: null,
  due_soon: false,
  assigned_to: AN,
  owner: null,
  sla_warn_at: warn,
  sla_due_at: due,
});

const day = (): Today => ({
  brief: {
    notification_id: "b-1",
    title: "Tóm tắt sáng 05/10: 2 hồ sơ mới",
    opening: "Xử lý PO quá hạn trước.",
    counts: ["Đang chờ: Sales 2."],
    at: "2026-10-05T00:30:00Z",
  },
  reminders: [
    {
      notification_id: "r-term",
      followup: "quote_deadline",
      stage: "warn",
      case_id: "q-1",
      title: "Sắp đến hạn báo giá RFQ-1",
      body: "Báo giá RFQ-1 đến hạn ngày 06/10/2026 mà chưa gửi khách.",
      link: "/sales/quotes/q-1",
      at: "2026-10-05T01:00:00Z",
      customer_term: true,
    },
    {
      notification_id: "r-pc",
      followup: "waiting_pc",
      stage: "remind",
      case_id: "o-9",
      title: "Nhắc: PO 9 đang chờ PC trả ngày giao",
      body: "Đã hỏi PC ngày giao.",
      link: "/sales/orders/o-9",
      at: "2026-10-05T02:00:00Z",
      customer_term: false,
    },
  ],
  hidden: 0,
});

let items: WorkItem[] = [];
const api = {
  // No case holds an answer the person has not seen (ticket 46).
  assistantUnread: vi.fn(async (): Promise<string[]> => []),
  myWork: vi.fn(async () => items),
  orders: vi.fn(async () => []),
  quotes: vi.fn(async () => []),
  inbox: vi.fn(async () => []),
  openYcbg: vi.fn(async () => ({ items: [], as_of: "2026-10-05" })),
  customers: vi.fn(async () => ({ items: [] })),
  today: vi.fn(async () => day()),
  markReminder: vi.fn(async () => ({
    ...day(),
    reminders: [day().reminders[0]!],
    hidden: 1,
  })),
  order: vi.fn(async () => waiting),
  resumeReview: vi.fn(async () => waiting),
  artifacts: vi.fn(async () => ({
    case_version: waiting.case_version,
    available: [],
    artifacts: [],
  })),
  // The item's case conversation (ticket 79).
  assistantConversation: vi.fn(async () => ({
    case: { kind: "order", case_id: waiting.case_id, label: "PO" },
    turns: [] as unknown[],
  })),
  assistantConfirm: vi.fn(async () => ({
    answer: "Đã giao hồ sơ cho Hoàng Thị Diệu.",
    case_version: waiting.case_version + 1,
  })),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import MyWorkPage from "../../page";
import { SalesFrameProvider } from "../../_components/sales-frame";
import { AssistantWidget } from "../../_components/assistant-widget";

// jsdom draws no layout: a row scrolled to is a call, not a movement.
Element.prototype.scrollIntoView = vi.fn();

afterEach(() => {
  cleanup();
  items = [];
  search = new URLSearchParams();
  vi.clearAllMocks();
});

function page() {
  return render(
    <UiProvider>
      <SalesFrameProvider>
        <AssistantWidget>
          <MyWorkPage />
        </AssistantWidget>
      </SalesFrameProvider>
    </UiProvider>,
  );
}

const SLOW = 20_000;

describe("SLA order", () => {
  it("puts late first, then about to be late, then by when each is late", () => {
    const late = item("late", "2026-10-04T05:00:00Z", "2026-10-05T01:00:00Z");
    const soon = item("soon", "2026-10-05T02:00:00Z", "2026-10-05T09:00:00Z");
    const later = item("later", "2026-10-05T08:00:00Z", "2026-10-05T20:00:00Z");
    const early = item("early", "2026-10-05T04:00:00Z", "2026-10-05T10:00:00Z");
    const none = item("none", null, null);
    expect(slaOf(late, NOW).state).toBe("late");
    expect(slaOf(soon, NOW).state).toBe("soon");
    expect(slaOf(early, NOW).state).toBe("on_time");
    expect(slaOf(none, NOW).state).toBe("none");
    expect(slaOf(late, NOW).relative).toBe("quá hạn 2 giờ");
    expect(
      bySla([none, later, early, soon, late], NOW).map((i) => i.id),
    ).toEqual(["late", "soon", "early", "later", "none"]);
  });
});

describe("Việc cần làm, one place", () => {
  it(
    "opens with today's brief, DW1's opening marked as DW1's and the counts on click",
    async () => {
      page();
      expect(await screen.findByText("Xử lý PO quá hạn trước.")).toBeTruthy();
      expect(screen.getByText("DW1 viết")).toBeTruthy();
      expect(screen.queryByText("Đang chờ: Sales 2.")).toBeNull();
      fireEvent.click(screen.getByRole("button", { name: "Xem số liệu" }));
      expect(screen.getByText("Đang chờ: Sales 2.")).toBeTruthy();
    },
    SLOW,
  );

  it(
    "never offers to hide a customer's term, and marks another as asked",
    async () => {
      page();
      const term = (
        await screen.findByText("Sắp đến hạn báo giá RFQ-1")
      ).closest("li")!;
      const later = within(term).getByRole("button", { name: "Không cần" });
      expect((later as HTMLButtonElement).disabled).toBe(true);
      const pc = screen
        .getByText("Nhắc: PO 9 đang chờ PC trả ngày giao")
        .closest("li")!;
      fireEvent.click(within(pc).getByRole("button", { name: "Không cần" }));
      await waitFor(() => expect(api.markReminder).toHaveBeenCalled());
      expect(api.markReminder.mock.calls[0]!.slice(0, 2)).toEqual([
        "r-pc",
        { mark: "dismissed" },
      ]);
      // The day as the server answered it: the dismissed one is gone.
      await waitFor(() =>
        expect(
          screen.queryByText("Nhắc: PO 9 đang chờ PC trả ngày giao"),
        ).toBeNull(),
      );
    },
    SLOW,
  );

  it(
    "opens a push's item expanded and decides it in its row",
    async () => {
      items = [
        item(waiting.case_id, "2026-10-04T05:00:00Z", "2026-10-05T01:00:00Z"),
      ];
      search = new URLSearchParams({ item: `order:${waiting.case_id}` });
      page();
      // The case page's own button, in the row, without opening the case
      // (by text: a role query over the whole table is too slow in jsdom).
      const resume = (
        await screen.findByText("Khách giữ PO: xem xét lại", undefined, {
          timeout: 8000,
        })
      ).closest("button")!;
      expect(resume.closest(".ant-table-expanded-row")).toBeTruthy();
      expect(api.order).toHaveBeenCalledWith(waiting.case_id);
      fireEvent.click(resume);
      await waitFor(() => expect(api.resumeReview).toHaveBeenCalled());
      expect(api.resumeReview.mock.calls[0]!.slice(0, 2)).toEqual([
        waiting.case_id,
        waiting.case_version,
      ]);
      // The list is read again after the decision.
      await waitFor(() =>
        expect(api.myWork.mock.calls.length).toBeGreaterThan(1),
      );
    },
    SLOW,
  );

  it(
    "draws an order seen through its NOC/ESF hold with no step the server refuses",
    async () => {
      // Ticket 78: the held order is the export PIC's item whoever is
      // assigned; the item narrows the viewer as the case page does.
      api.order.mockResolvedValueOnce({ ...waiting, export_hold_only: true });
      items = [
        item(waiting.case_id, "2026-10-04T05:00:00Z", "2026-10-05T01:00:00Z"),
      ];
      search = new URLSearchParams({ item: `order:${waiting.case_id}` });
      page();
      const resume = (
        await screen.findByText("Khách giữ PO: xem xét lại", undefined, {
          timeout: 8000,
        })
      ).closest("button")!;
      expect(resume.disabled).toBe(true);
    },
    SLOW,
  );

  it(
    "says when a push's item no longer waits on the person",
    async () => {
      search = new URLSearchParams({ item: "order:gone-1" });
      page();
      expect(
        await screen.findByText("Việc này không còn chờ bạn."),
      ).toBeTruthy();
      expect(
        screen.getByRole("link", { name: "Mở hồ sơ" }).getAttribute("href"),
      ).toBe("/sales/orders/gone-1");
    },
    SLOW,
  );
});

const TITLE = "Hỏi DW1 về hồ sơ này";
const HASH = "ab12cd34".repeat(8);
const ON_CASE = { kind: "order", caseId: waiting.case_id };

/** The order's item, opened by a push's deep link: its chat's button. */
async function openItemChat() {
  items = [
    item(waiting.case_id, "2026-10-04T05:00:00Z", "2026-10-05T01:00:00Z"),
  ];
  search = new URLSearchParams({ item: `order:${waiting.case_id}` });
  page();
  return (await screen.findByText(TITLE, undefined, { timeout: 8000 })).closest(
    "button",
  )!;
}

describe("The item's case conversation (ticket 79)", () => {
  it(
    "opens the case's own conversation from the item, read only once opened",
    async () => {
      const button = await openItemChat();
      expect(button.closest(".ant-table-expanded-row")).toBeTruthy();
      // Opening the item does not read the conversation, so nothing is
      // marked seen that nobody saw.
      expect(api.assistantConversation).not.toHaveBeenCalled();
      fireEvent.click(button);
      await waitFor(() =>
        expect(api.assistantConversation).toHaveBeenCalledWith(ON_CASE),
      );
    },
    SLOW,
  );

  it(
    "answers a step with the case page's own control at this point of the case",
    async () => {
      api.assistantConversation.mockResolvedValueOnce({
        case: { kind: "order", case_id: waiting.case_id, label: "PO" },
        turns: [
          {
            seq: 1,
            asked_at: "2026-10-05T02:00:00+00:00",
            question: "Nhắc khách",
            kind: "remind_customer",
            answer: "Bấm nút dưới đây để DW1 soạn thư nhắc khách.",
            cites: [],
            answered_by: "code",
            offer: "customer_reminder",
          },
        ],
      });
      fireEvent.click(await openItemChat());
      // The order waits on the customer's corrected PO: the reminder is the
      // case page's own control, not the chat's "no control here".
      expect(
        await screen.findByText("DW1 soạn thư nhắc khách", undefined, {
          timeout: 8000,
        }),
      ).toBeTruthy();
      expect(
        screen.queryByText(
          "Ở bước hiện tại, trang hồ sơ không có nút cho việc này.",
        ),
      ).toBeNull();
    },
    SLOW,
  );

  it(
    "gives the case from the item's chat only once pressed, then reads the work again",
    async () => {
      api.assistantConversation.mockResolvedValueOnce({
        case: { kind: "order", case_id: waiting.case_id, label: "PO" },
        turns: [
          {
            seq: 3,
            asked_at: "2026-10-05T02:00:00+00:00",
            question: "giao cho Diệu nhé",
            kind: "assign_case",
            answer:
              "Giao hồ sơ cho Hoàng Thị Diệu? Bấm Xác nhận để giao; người nhận được báo ngay.",
            cites: [],
            answered_by: "code",
            proposal: {
              action: "assign",
              assignee_name: "Hoàng Thị Diệu",
              case_version: waiting.case_version,
              content_hash: HASH,
            },
          },
        ],
      });
      fireEvent.click(await openItemChat());
      const give = (
        await screen.findByText("Giao cho Hoàng Thị Diệu", undefined, {
          timeout: 8000,
        })
      ).closest("button")!;
      expect(api.assistantConfirm).not.toHaveBeenCalled();
      const reads = api.myWork.mock.calls.length;
      fireEvent.click(give);
      await waitFor(() =>
        expect(api.assistantConfirm.mock.calls[0]!.slice(0, 3)).toEqual([
          ON_CASE,
          3,
          HASH,
        ]),
      );
      // The list is read again: the case is no longer this person's.
      await waitFor(() =>
        expect(api.myWork.mock.calls.length).toBeGreaterThan(reads),
      );
    },
    SLOW,
  );

  it(
    "hides the general widget while the item's chat is open, and gives it back",
    async () => {
      const button = await openItemChat();
      expect(screen.getByRole("button", { name: "Hỏi DW1" })).toBeTruthy();
      fireEvent.click(button);
      await waitFor(() =>
        expect(screen.queryByRole("button", { name: "Hỏi DW1" })).toBeNull(),
      );
      fireEvent.click(document.querySelector(".ant-drawer-close")!);
      await waitFor(() =>
        expect(screen.getByRole("button", { name: "Hỏi DW1" })).toBeTruthy(),
      );
    },
    SLOW,
  );

  it(
    "keeps a mail's item to its link in the inbox, with no case conversation",
    async () => {
      items = [
        item("m-1", "2026-10-04T05:00:00Z", "2026-10-05T01:00:00Z", "message"),
      ];
      search = new URLSearchParams({ item: "message:m-1" });
      page();
      expect(
        await screen.findByText("Mở thư trong Hộp thư để xử lý", undefined, {
          timeout: 8000,
        }),
      ).toBeTruthy();
      expect(screen.queryByText(TITLE)).toBeNull();
      expect(api.assistantConversation).not.toHaveBeenCalled();
    },
    SLOW,
  );
});
