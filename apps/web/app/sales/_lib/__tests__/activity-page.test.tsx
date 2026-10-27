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
import { ApiError, type SalesSchemas } from "@dw/api-client";
import { AN } from "./fixtures";

type Summary = SalesSchemas["ActivitySummaryView"];
type StepSummary = SalesSchemas["StepSummaryView"];
type ModelStep = SalesSchemas["ModelStep"];
type Lane = SalesSchemas["CaseKind"] | null;

let scopes = ["sales.overview.read", "sales.case.read"];
vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: AN,
    displayName: "An",
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => scopes.includes(scope),
  }),
}));
vi.mock("../../../../lib/session", () => ({
  apiClient: () => ({ listWorkspaceMembers: vi.fn().mockResolvedValue([]) }),
}));
// 10:00 on 23/10/2026 in Vietnam.
const NOW = Date.parse("2026-10-23T03:00:00Z");
vi.mock("../../../../lib/use-now", () => ({ useNow: () => NOW }));

// The URL the pages read and write.
const nav = vi.hoisted(() => {
  const listeners = new Set<() => void>();
  let path = "/sales/activity";
  let current = new URLSearchParams();
  const go = (url: string) => {
    const [p, q] = url.split("?");
    path = p!;
    current = new URLSearchParams(q ?? "");
    listeners.forEach((l) => l());
  };
  return {
    reset(url: string) {
      const [p, q] = url.split("?");
      path = p!;
      current = new URLSearchParams(q ?? "");
    },
    get: () => current,
    path: () => path,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => void listeners.delete(listener);
    },
    replace: vi.fn((url: string) => go(url)),
    push: vi.fn((url: string) => go(url)),
  };
});
vi.mock("next/navigation", async () => {
  const { useSyncExternalStore } = await import("react");
  return {
    useSearchParams: () => useSyncExternalStore(nav.subscribe, nav.get),
    usePathname: () => nav.path(),
    useRouter: () => ({ push: nav.push, replace: nav.replace, back: vi.fn() }),
  };
});

const STEPS: ModelStep[] = [
  "description_attributes",
  "message_intent",
  "rfq_extraction",
  "reply_intent",
  "request_handoff",
  "layout_proposal",
];

/** The summary as `ActivityService.summary` answers it for the window and lane. */
function summary(from: string, to: string, lane: Lane, busy = true): Summary {
  const filter = (step: ModelStep, extra: object = {}) => ({
    step,
    lane,
    from,
    to,
    handled_by: null,
    result: null,
    reason_code: null,
    ...extra,
  });
  const row = (step: ModelStep): StepSummary => {
    const counted = busy && step === "description_attributes";
    return {
      step,
      process_steps: step === "description_attributes" ? ["O2", "Q2"] : ["O1"],
      handled: { count: counted ? 10 : 0, filter: filter(step) },
      automatic: {
        count: counted ? 6 : 0,
        filter: filter(step, { handled_by: "dw1" }),
      },
      to_person: {
        count: counted ? 4 : 0,
        filter: filter(step, { handled_by: "person" }),
      },
      automatic_share: counted ? 0.6 : null,
      model_unavailable: {
        count: counted ? 1 : 0,
        filter: filter(step, { result: "unavailable" }),
      },
      top_reasons: counted
        ? [
            {
              reason_code: "no_item_fits",
              count: 3,
              filter: filter(step, { reason_code: "no_item_fits" }),
            },
          ]
        : [],
      latency: counted
        ? { p50_ms: 850, p95_ms: 2_400, samples: 9 }
        : { p50_ms: null, p95_ms: null, samples: 0 },
    };
  };
  return {
    from,
    to,
    lane,
    as_of: "2026-10-23T03:00:00Z",
    steps: STEPS.map(row),
    days: [
      {
        day: to,
        steps: STEPS.map((step) => ({
          step,
          handled: busy && step === "description_attributes" ? 5 : 0,
          automatic: busy && step === "description_attributes" ? 3 : 0,
          to_person: busy && step === "description_attributes" ? 2 : 0,
        })),
      },
    ],
  };
}

const api = {
  activity: vi.fn(async (query: { from?: string; to?: string; lane?: Lane }) =>
    summary(query.from!, query.to!, query.lane ?? null),
  ),
  orders: vi.fn(async (...args: unknown[]) => (void args, [])),
  quotes: vi.fn(async (...args: unknown[]) => (void args, [])),
  customers: vi.fn(async () => ({ items: [] })),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import ActivityPage from "../../activity/page";
import OrdersPage from "../../orders/page";
import QuotesPage from "../../quotes/page";

const SLOW = 30_000;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  scopes = ["sales.overview.read", "sales.case.read"];
});

function renderAt(url: string, page = <ActivityPage />) {
  nav.reset(url);
  render(<UiProvider>{page}</UiProvider>);
}

const row = (label: string) =>
  screen.getByText(label).closest("tr") as HTMLElement;
const cell = (tr: HTMLElement, index: number) =>
  tr.querySelectorAll("td")[index] as HTMLElement;

describe("Hoạt động DW1 (slice 3)", () => {
  it(
    "draws a row per model step from the server's counts, with no links over both lanes",
    async () => {
      renderAt("/sales/activity");
      await screen.findByText("Đọc mô tả hàng chưa có trong convert list");
      // The last 7 days in Vietnam, today included.
      expect(api.activity).toHaveBeenCalledWith({
        from: "2026-10-17",
        to: "2026-10-23",
      });
      const read = row("Đọc mô tả hàng chưa có trong convert list");
      // Expand, step, handled, automatic, to a person, no answer, latency, reasons.
      expect(cell(read, 2).textContent).toBe("10");
      expect(cell(read, 3).textContent).toBe("660%");
      expect(cell(read, 4).textContent).toBe("4");
      expect(cell(read, 5).textContent).toBe("1");
      expect(cell(read, 6).textContent).toBe("850 ms / 2,4 giây9 lần đo");
      expect(cell(read, 7).textContent).toBe(
        "Đọc được, nhưng không mã hàng nào khớp: 3",
      );
      // A count over both lanes is one number for two lists: no link.
      expect(within(read).queryByRole("link")).toBeNull();
      expect(
        screen.getByText(/Chọn Đơn hàng hoặc Báo giá để mở danh sách/),
      ).toBeTruthy();
      const quiet = row("Đọc yêu cầu báo giá không theo mẫu");
      expect(cell(quiet, 3).textContent).toBe("0chưa có dữ liệu");
      expect(cell(quiet, 6).textContent).toBe("Chưa có");
    },
    SLOW,
  );

  it(
    "links each count of a lane to that lane's list, with the filter the server served",
    async () => {
      renderAt("/sales/activity?lane=order");
      await screen.findByText("Đọc mô tả hàng chưa có trong convert list");
      expect(api.activity).toHaveBeenCalledWith({
        from: "2026-10-17",
        to: "2026-10-23",
        lane: "order",
      });
      const read = row("Đọc mô tả hàng chưa có trong convert list");
      const links = within(read).getAllByRole("link");
      expect(links.map((l) => l.getAttribute("href"))).toEqual([
        "/sales/orders?tab=all&step=description_attributes&lane=order&from=2026-10-17&to=2026-10-23",
        "/sales/orders?tab=all&step=description_attributes&handled_by=dw1&lane=order&from=2026-10-17&to=2026-10-23",
        "/sales/orders?tab=all&step=description_attributes&handled_by=person&lane=order&from=2026-10-17&to=2026-10-23",
        "/sales/orders?tab=all&step=description_attributes&result=unavailable&lane=order&from=2026-10-17&to=2026-10-23",
        "/sales/orders?tab=all&step=description_attributes&reason_code=no_item_fits&lane=order&from=2026-10-17&to=2026-10-23",
      ]);
      // Named by the count it shows, then what it opens.
      expect(links[2]!.getAttribute("aria-label")).toBe(
        "4: mở danh sách đơn hàng, Đọc mô tả hàng chưa có trong convert list · Chuyển cho người · 17/10/2026 – 23/10/2026",
      );
      // A zero opens nothing.
      expect(
        within(row("Đọc yêu cầu báo giá không theo mẫu")).queryByRole("link"),
      ).toBeNull();
    },
    SLOW,
  );

  it(
    "shows a viewer who cannot open cases the counts, with no link and no promise of one (2026-10-27)",
    async () => {
      scopes = ["sales.overview.read"];
      renderAt("/sales/activity?lane=order");
      await screen.findByText("Đọc mô tả hàng chưa có trong convert list");
      const read = row("Đọc mô tả hàng chưa có trong convert list");
      expect(cell(read, 4).textContent).toBe("4");
      expect(within(read).queryByRole("link")).toBeNull();
      expect(screen.queryByText(/mở danh sách hồ sơ/)).toBeNull();
    },
    SLOW,
  );

  it(
    "asks again for 30 days and for another lane, keeping both in the URL",
    async () => {
      renderAt("/sales/activity");
      await screen.findByText("Đọc mô tả hàng chưa có trong convert list");
      fireEvent.click(screen.getByText("30 ngày"));
      expect(nav.replace).toHaveBeenLastCalledWith("/sales/activity?range=30", {
        scroll: false,
      });
      await waitFor(() =>
        expect(api.activity).toHaveBeenLastCalledWith({
          from: "2026-09-24",
          to: "2026-10-23",
        }),
      );
      fireEvent.click(screen.getByText("Báo giá"));
      expect(nav.replace).toHaveBeenLastCalledWith(
        "/sales/activity?range=30&lane=quote",
        { scroll: false },
      );
      await waitFor(() =>
        expect(api.activity).toHaveBeenLastCalledWith({
          from: "2026-09-24",
          to: "2026-10-23",
          lane: "quote",
        }),
      );
      // Back to the defaults: the URL carries neither.
      fireEvent.click(screen.getByText("Tất cả"));
      fireEvent.click(screen.getByText("7 ngày"));
      expect(nav.replace).toHaveBeenLastCalledWith("/sales/activity", {
        scroll: false,
      });
    },
    SLOW,
  );

  it(
    "opens a step's days under it, the share in words",
    async () => {
      renderAt("/sales/activity");
      await screen.findByText("Đọc mô tả hàng chưa có trong convert list");
      const read = row("Đọc mô tả hàng chưa có trong convert list");
      fireEvent.click(within(read).getByRole("button"));
      const days = await screen.findByRole("table", {
        name: "Theo ngày: Đọc mô tả hàng chưa có trong convert list",
      });
      const day = within(days).getByText("23/10/2026").closest("tr")!;
      expect(day.textContent).toBe("23/10/2026532" + "60%");
    },
    SLOW,
  );

  it(
    "says when DW1 did nothing in the window",
    async () => {
      api.activity.mockImplementationOnce(async (query) =>
        summary(query.from!, query.to!, null, false),
      );
      renderAt("/sales/activity");
      expect(
        await screen.findByText(
          "DW1 chưa xử lý mục nào ở bước có mô hình trong 7 ngày qua.",
        ),
      ).toBeTruthy();
    },
    SLOW,
  );

  it(
    "draws a failure with its request id",
    async () => {
      api.activity.mockRejectedValueOnce(
        new ApiError(500, {
          code: "internal",
          message: "Máy chủ gặp lỗi.",
          details: {},
          request_id: "req-summary-1",
        }),
      );
      renderAt("/sales/activity");
      expect(await screen.findByText(/req-summary-1/)).toBeTruthy();
    },
    SLOW,
  );

  it("opens to either scope the API reads with, and asks nothing without both", async () => {
    scopes = ["sales.rules.propose"];
    renderAt("/sales/activity");
    await screen.findByText("Đọc mô tả hàng chưa có trong convert list");
    cleanup();
    vi.clearAllMocks();

    scopes = ["sales.case.read"];
    renderAt("/sales/activity");
    expect(
      screen.getByText(/Vai của bạn trong không gian làm việc này/),
    ).toBeTruthy();
    expect(api.activity).not.toHaveBeenCalled();
  });
});

describe("a case list opened from a count", () => {
  const FROM_COUNT =
    "tab=all&step=description_attributes&handled_by=person&lane=order&from=2026-10-17&to=2026-10-23";
  const CHIP =
    "Lọc theo hoạt động DW1: Đọc mô tả hàng chưa có trong convert list · Chuyển cho người · 17/10/2026 – 23/10/2026";

  it(
    "asks the server for the cases the count stands for, says so, and Xóa drops it",
    async () => {
      scopes = ["sales.case.read"];
      renderAt(`/sales/orders?${FROM_COUNT}`, <OrdersPage />);
      expect(
        await screen.findByText("Không có đơn nào khớp hoạt động DW1 này."),
      ).toBeTruthy();
      expect(api.orders).toHaveBeenCalledWith({
        step: "description_attributes",
        handled_by: "person",
        lane: "order",
        from: "2026-10-17",
        to: "2026-10-23",
      });
      expect(screen.getByText(CHIP)).toBeTruthy();
      fireEvent.click(screen.getByRole("button", { name: "Xóa" }));
      expect(nav.replace).toHaveBeenLastCalledWith("/sales/orders?tab=all", {
        scroll: false,
      });
      await waitFor(() =>
        expect(api.orders).toHaveBeenLastCalledWith(undefined),
      );
      expect(screen.queryByText(CHIP)).toBeNull();
    },
    SLOW,
  );

  it(
    "does the same on the quote list, and reads no filter when the URL has none",
    async () => {
      scopes = ["sales.case.read"];
      renderAt(
        "/sales/quotes?step=rfq_extraction&result=unavailable&from=2026-10-17&to=2026-10-23",
        <QuotesPage />,
      );
      await waitFor(() =>
        expect(api.quotes).toHaveBeenCalledWith({
          step: "rfq_extraction",
          result: "unavailable",
          from: "2026-10-17",
          to: "2026-10-23",
        }),
      );
      expect(
        await screen.findByText(
          "Lọc theo hoạt động DW1: Đọc yêu cầu báo giá không theo mẫu · Model không trả lời · 17/10/2026 – 23/10/2026",
        ),
      ).toBeTruthy();
      cleanup();
      vi.clearAllMocks();

      renderAt("/sales/quotes", <QuotesPage />);
      await waitFor(() => expect(api.quotes).toHaveBeenCalledWith(undefined));
      expect(screen.queryByText(/Lọc theo hoạt động DW1/)).toBeNull();
    },
    SLOW,
  );
});
