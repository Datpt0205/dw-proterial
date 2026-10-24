import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  act,
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
import { AN, GIANG } from "./fixtures";
import { PROCESS } from "./process-fixture";
import { EDGE_ACTION, EDGE_GUARD } from "../labels";
import { layoutLane, type Lane } from "../process-graph";
import { laneGeometry } from "../process-geometry";
import type { PlatformDocument, RuleVersion } from "../rules";

type View = SalesSchemas["ProcessSettingsView"];
type RulesView = SalesSchemas["RulesInForceView"];

const SCHEMAS = JSON.parse(
  readFileSync(
    resolve(
      __dirname,
      "../../../../../../contracts/jsonschema/sales_rules.json",
    ),
    "utf-8",
  ),
) as Record<string, Record<string, unknown>>;

const PRICE_KEYS = ["sales_order_rules", "sales_quote_rules", "sales_pricing"];

let scopes = ["sales.case.read", "sales.rules.propose", "sales.price.read"];
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

// The URL the page reads and writes, with a history Back can walk.
const nav = vi.hoisted(() => {
  let history = [""];
  const listeners = new Set<() => void>();
  let current = new URLSearchParams();
  const go = (url: string) => {
    current = new URLSearchParams(url.split("?")[1] ?? "");
    listeners.forEach((l) => l());
  };
  return {
    reset(query = "") {
      history = [query];
      current = new URLSearchParams(query);
    },
    get: () => current,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => void listeners.delete(listener);
    },
    push: vi.fn((url: string) => {
      history.push(url.split("?")[1] ?? "");
      go(url);
    }),
    replace: vi.fn((url: string) => {
      history[history.length - 1] = url.split("?")[1] ?? "";
      go(url);
    }),
    back: vi.fn(() => {
      history.pop();
      go(`?${history[history.length - 1] ?? ""}`);
    }),
  };
});
vi.mock("next/navigation", async () => {
  const { useSyncExternalStore } = await import("react");
  return {
    useSearchParams: () => useSyncExternalStore(nav.subscribe, nav.get),
    usePathname: () => "/sales/rules/process",
    useRouter: () => ({
      push: nav.push,
      replace: nav.replace,
      back: nav.back,
    }),
  };
});

const KPI_DOC = {
  schema_version: "1.0",
  policy_id: "sales_kpi",
  policy_version: "1.0.1",
  order_confirmation_target_hours: 8,
  quotation_target_days: 1,
  manual_baseline_minutes: { O1: 5, Q1: 10 },
};

const FOLLOWUPS_DOC = {
  schema_version: "1.0",
  policy_id: "sales_followups",
  policy_version: "1.0.0",
  working_hours: {
    time_zone: "Asia/Ho_Chi_Minh",
    days: ["mon", "tue"],
    start: "08:00",
    end: "17:30",
  },
};

const KPI_VERSION: RuleVersion = {
  version_id: "0aa10aa0-c939-7000-8539-31fd3e621700",
  key: "sales_kpi",
  version: "1.0.1",
  ref: "sales_kpi@1.0.1",
  layer: "tenant",
  status: "approved",
  proposed_by: AN,
  proposed_at: "2026-10-10T02:00:00Z",
  decided_by: GIANG,
  decided_at: "2026-10-10T03:00:00Z",
  comment: null,
  document: KPI_DOC,
  approval_id: "0aa10aa0-c939-7000-8539-31fd3e621701",
};

/** What `/rules` answers someone who reads no price: no price key at all. */
const RULES: RulesView = {
  in_force: {
    sales_kpi: "sales_kpi@1.0.1",
    sales_followups: "sales_followups@1.0.0",
  },
  layers: { sales_kpi: "tenant", sales_followups: "platform" },
  platform: [
    { key: "sales_kpi", ref: "sales_kpi@1.0.0" },
    { key: "sales_followups", ref: "sales_followups@1.0.0" },
  ],
  versions: [KPI_VERSION],
  draftable: [],
};

const PLATFORM: Record<string, PlatformDocument[]> = {
  sales_kpi: [
    {
      key: "sales_kpi",
      ref: "sales_kpi@1.0.0",
      version: "1.0.0",
      current: true,
      document: { ...KPI_DOC, policy_version: "1.0.0" },
    },
  ],
  sales_followups: [
    {
      key: "sales_followups",
      ref: "sales_followups@1.0.0",
      version: "1.0.0",
      current: true,
      document: FOLLOWUPS_DOC,
    },
  ],
};

/**
 * The view as the server leaves it for a caller without `sales.price.read`:
 * no price key, and no model step (their switches are in the order rules).
 */
function withoutPrices(view: View): View {
  const keep = (s: { key: string }) => !PRICE_KEYS.includes(s.key);
  return {
    ...view,
    steps: view.steps.map((s) => ({
      ...s,
      settings: s.settings.filter(keep),
      models: [],
    })),
    lane_settings: Object.fromEntries(
      Object.entries(view.lane_settings).map(([k, v]) => [k, v.filter(keep)]),
    ),
    process_settings: view.process_settings.filter(keep),
  };
}

const api = {
  rulesProcess: vi.fn(async (): Promise<View> => PROCESS),
  rules: vi.fn(async (): Promise<RulesView> => RULES),
  ruleSchema: vi.fn(async (key: string) => ({
    key,
    json_schema: SCHEMAS[key]!,
  })),
  rulePlatformDocuments: vi.fn(async (key: string) => PLATFORM[key] ?? []),
  proposeRule: vi.fn(async (...args: unknown[]) => (void args, KPI_VERSION)),
};
vi.mock("../api", () => ({ salesApi: () => api }));
// Whether the canvas's module was ever loaded: a narrow screen must not.
const flow = vi.hoisted(() => ({ loaded: vi.fn() }));
vi.mock("../../_components/process-flow", async (original) => {
  flow.loaded();
  return original();
});

import ProcessPage from "../../rules/process/page";
import RulesPage from "../../rules/page";

const SLOW = 30_000;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  nav.reset();
  scopes = ["sales.case.read", "sales.rules.propose", "sales.price.read"];
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: media(false),
  });
});

/** A `matchMedia` for a wide screen (every antd `min-width` up to xl) or a phone. */
function media(wide: boolean) {
  return (query: string) => {
    const min = /min-width:\s*(\d+)px/.exec(query);
    return {
      matches: wide && min !== null && Number(min[1]) <= 1200,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    };
  };
}

function renderPage(query = "") {
  nav.reset(query);
  render(
    <UiProvider>
      <ProcessPage />
    </UiProvider>,
  );
}

/** A status card: a link named by its whole card, its status first. */
const status = (words: string) =>
  screen.findByRole("link", {
    name: new RegExp(`^${words.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`),
  });

const drawer = (title: string) =>
  screen
    .getAllByRole("dialog")
    .find((d) => within(d).queryByText(title)) as HTMLElement;

/** Opens the KPI section of the order lane's "Đã nhận" status (step O1). */
async function openReceivedKpi() {
  renderPage("node=order.received");
  await screen.findByText("Đơn hàng · Đã nhận");
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Xem và đề xuất thay đổi: Chỉ tiêu KPI",
    }),
  );
  return (await screen.findByRole("spinbutton", {
    name: "Số phút: Đơn hàng, bước 1 (O1)",
  })) as HTMLInputElement;
}

describe("the DW1 process page (2026-10-22)", () => {
  it(
    "draws every status the server serves, a status it adds included, and none of its own",
    async () => {
      const order = PROCESS.lanes[0]!;
      api.rulesProcess.mockResolvedValueOnce({
        ...PROCESS,
        lanes: [
          {
            ...order,
            nodes: [
              ...order.nodes,
              { status: "on_hold", steps: [], holder: "sales" },
            ],
            edges: [
              ...order.edges,
              {
                from: "in_review",
                to: "on_hold",
                action: "edit",
                actor: "sales",
                guards: [],
              },
              {
                from: "on_hold",
                to: "in_review",
                action: "edit",
                actor: "sales",
                guards: [],
              },
            ],
          },
          PROCESS.lanes[1]!,
        ],
      });
      renderPage();
      expect(await status("on_hold")).toBeTruthy();
      for (const words of ["Chờ PIC tự kiểm", "Đã nhập Bravo", "Đã đóng"])
        expect(await status(words)).toBeTruthy();
      // Each card is a real link to its drawer, so it opens in a new tab too.
      expect((await status("Đã nhận")).getAttribute("href")).toBe(
        "/sales/rules/process?node=order.received",
      );
      // The ways back and the exits are written, not drawn.
      expect(
        screen.getByText(
          "Có thể đóng từ: Đã nhận, Đã kiểm tra, Chờ PIC tự kiểm, Chờ khách sửa PO, PIC đã tự kiểm",
        ),
      ).toBeTruthy();
      expect(
        screen.getAllByText("Có thể quay lại: Chờ PIC tự kiểm").length,
      ).toBeGreaterThan(0);
      // Steps no status stands for follow the statuses.
      expect(
        screen.getByRole("button", { name: /^Đơn hàng, bước 4 \(O4\)/ }),
      ).toBeTruthy();
      // The list alone: React Flow is never downloaded below lg.
      expect(flow.loaded).not.toHaveBeenCalled();
    },
    SLOW,
  );

  it(
    "on a wide screen, draws the statuses on a canvas, every move but the exits labelled",
    async () => {
      Object.defineProperty(window, "matchMedia", {
        writable: true,
        value: media(true),
      });
      renderPage();
      const card = await status("Chờ PIC tự kiểm");
      expect(card.textContent).toContain("O6 · DW1 làm");
      // Loaded when drawn (next/dynamic).
      expect(flow.loaded).toHaveBeenCalled();
      expect(card.textContent).toContain("Đến lượt: Sales quyết định");
      // The ways back are drawn, so the card does not write them too.
      expect(card.textContent).not.toContain("Có thể quay lại");
      // The order lane draws 18 of its 23 moves: 11 forward, 7 back; the
      // 5 closing ones stay words on "Đã đóng".
      const canvas = screen.getByRole("application", {
        name: "Sơ đồ quy trình Đơn hàng",
      });
      const moves = [...canvas.querySelectorAll("[data-move]")];
      expect(moves.map((m) => m.getAttribute("data-move")).sort()).toEqual(
        [
          ...PROCESS.lanes[0]!.edges.filter((e) => e.to !== "closed").map(
            (e) => `${e.from}->${e.to}`,
          ),
        ].sort(),
      );
      expect(moves.length).toBe(18);
      const move = (id: string) =>
        moves.find((m) => m.getAttribute("data-move") === id)!;
      // Each move says its action, and its guards as tags.
      expect(move("received->checked").textContent).toBe("DW1 đọc và kiểm tra");
      const prepare = move("in_review->prepared");
      expect(prepare.textContent).toContain("Tự kiểm xong");
      expect(
        [...prepare.querySelectorAll(".ant-tag")].map((t) => t.textContent),
      ).toEqual(["Không còn cờ chặn"]);
      // A move back is said as one, to a screen reader too.
      expect(
        canvas
          .querySelector('[aria-label^="Chờ PIC tự kiểm → Đã kiểm tra"]')
          ?.getAttribute("aria-label"),
      ).toBe(
        "Chờ PIC tự kiểm → Đã kiểm tra; Khách gửi PO sửa đổi (Khách hàng); quay lại",
      );
      // Each line is the placement's own (process-geometry.ts): a move back
      // dashed on a lane over its band, every run horizontal or vertical.
      const geometry = laneGeometry(
        layoutLane(PROCESS.lanes[0] as Lane),
        (m) => ({
          action: EDGE_ACTION[m.action],
          guards: m.guards.map((g) => EDGE_GUARD[g]),
        }),
      );
      const drawn = (id: string) =>
        canvas.querySelector(`[data-testid="rf__edge-${id}"] path`)!;
      for (const m of geometry.moves) {
        expect(drawn(m.id).getAttribute("d"), m.id).toBe(
          m.points.map(([x, y], i) => `${i ? "L" : "M"} ${x} ${y}`).join(" "),
        );
        expect(
          (drawn(m.id) as SVGPathElement).style.strokeDasharray,
          m.id,
        ).toBe(m.back ? "6 4" : "");
      }
      expect(
        screen.getByText(
          "Có thể đóng từ: Đã nhận, Đã kiểm tra, Chờ PIC tự kiểm, Chờ khách sửa PO, PIC đã tự kiểm",
        ),
      ).toBeTruthy();
      // The controls speak Vietnamese.
      for (const name of ["Phóng to", "Thu nhỏ", "Xem cả quy trình"])
        expect(screen.getByRole("button", { name })).toBeTruthy();
    },
    SLOW,
  );

  it(
    "says per status whether its model steps run, in words",
    async () => {
      const steps = PROCESS.steps.map((s) =>
        s.step_id === "O2"
          ? {
              ...s,
              models: s.models.map((m) => ({
                ...m,
                effective: false,
                latest: m.latest && { ...m.latest, value: 0.6, passed: false },
              })),
            }
          : s.step_id === "O3"
            ? {
                ...s,
                models: s.models.map((m) => ({
                  ...m,
                  enabled: false,
                  effective: false,
                })),
              }
            : s,
      );
      api.rulesProcess.mockResolvedValueOnce({ ...PROCESS, steps });
      renderPage();
      expect((await status("Đã nhận")).textContent).toContain(
        "AI bật · đạt (3 bước)",
      );
      expect((await status("Đã kiểm tra")).textContent).toContain(
        "AI bật · chưa đạt — người làm",
      );
      expect((await status("Đã nhập Bravo")).textContent).toContain("AI tắt");
      // A status none of whose steps has a model step says nothing of AI.
      expect((await status("Đã đóng")).textContent).not.toContain("AI");
    },
    SLOW,
  );

  it(
    "opens a status from a link, and its close button takes the link away",
    async () => {
      renderPage("node=order.in_review");
      expect(
        await screen.findByText("Đơn hàng · Chờ PIC tự kiểm"),
      ).toBeTruthy();
      expect(
        screen.getByText(
          "Thay đổi chỉ áp dụng cho hồ sơ được kiểm sau khi phiên bản mới được duyệt.",
        ),
      ).toBeTruthy();
      const open = drawer("Đơn hàng · Chờ PIC tự kiểm");
      expect(
        within(open).getByText("Có thể quay lại: Đã kiểm tra"),
      ).toBeTruthy();
      // On to: the ways back are not among them.
      const onward = within(open).getByText(/^Chuyển tiếp sang:/);
      expect(onward.textContent).not.toContain("Đã kiểm tra");
      expect(document.title).toBe(
        "Quy trình DW1 · Đơn hàng · Chờ PIC tự kiểm · Sales",
      );
      fireEvent.click(document.querySelector(".ant-drawer-close")!);
      await waitFor(() => expect(nav.get().get("node")).toBeNull());
      expect(nav.replace).toHaveBeenCalledTimes(1);
      expect(nav.back).not.toHaveBeenCalled();
    },
    SLOW,
  );

  it(
    "puts the open status in the URL, and Back closes it",
    async () => {
      renderPage();
      fireEvent.click(await status("Đã nhận"));
      expect(nav.push).toHaveBeenCalledWith(
        "/sales/rules/process?node=order.received",
        { scroll: false },
      );
      expect(await screen.findByText("Đơn hàng · Đã nhận")).toBeTruthy();
      fireEvent.click(document.querySelector(".ant-drawer-close")!);
      expect(nav.back).toHaveBeenCalledTimes(1);
      // Closed as a drawer, focus back on the card that opened it.
      await waitFor(() =>
        expect(document.activeElement?.getAttribute("data-node")).toBe(
          "order.received",
        ),
      );
    },
    SLOW,
  );

  it(
    "edits only the step's fields, and proposes the whole document with a diff of what changed",
    async () => {
      const minutes = await openReceivedKpi();
      expect(minutes.value).toBe("5");
      // The key's other fields are not drawn: not the target, not Q1's minutes.
      expect(
        screen.queryByRole("spinbutton", {
          name: "Mục tiêu xác nhận đơn hàng",
        }),
      ).toBeNull();
      expect(
        screen.queryByRole("spinbutton", {
          name: "Số phút: Báo giá, bước 1 (Q1)",
        }),
      ).toBeNull();
      expect(
        screen.queryByRole("button", { name: /^Xóa/ }),
        "an entry the step holds keeps its key",
      ).toBeNull();
      expect(
        (
          screen.getByRole("textbox", {
            name: "Số phiên bản mới",
          }) as HTMLInputElement
        ).value,
      ).toBe("1.0.2");
      // Limited to a step, no JSON: it would edit the fields drawn read-only.
      expect(screen.queryByText("JSON nâng cao")).toBeNull();
      expect(nav.get().get("edit")).toBe("sales_kpi");

      fireEvent.change(minutes, { target: { value: "7" } });
      fireEvent.blur(minutes);
      fireEvent.click(screen.getByRole("button", { name: "Xem thay đổi" }));
      expect(
        await screen.findByText("2 thay đổi so với sales_kpi@1.0.1."),
      ).toBeTruthy();
      fireEvent.click(screen.getByRole("button", { name: "Gửi duyệt" }));
      await waitFor(() => expect(api.proposeRule).toHaveBeenCalledTimes(1));
      const [key, body] = api.proposeRule.mock.calls[0] as [string, unknown];
      expect([key, body]).toEqual([
        "sales_kpi",
        {
          document: {
            ...KPI_DOC,
            policy_version: "1.0.2",
            manual_baseline_minutes: { O1: 7, Q1: 10 },
          },
        },
      ]);
    },
    SLOW,
  );

  it(
    "lists a refusal of a field outside the step above the form, and puts one inside on its field",
    async () => {
      api.proposeRule.mockRejectedValueOnce(
        new ApiError(422, {
          code: "validation_failed",
          message: "the document is not a valid version of this key",
          details: {
            key: "sales_kpi",
            errors:
              "['order_confirmation_target_hours', 'manual_baseline_minutes.O1']",
          },
          request_id: "r-1",
        }),
      );
      await openReceivedKpi();
      fireEvent.click(screen.getByRole("button", { name: "Xem thay đổi" }));
      fireEvent.click(await screen.findByRole("button", { name: "Gửi duyệt" }));

      expect(await screen.findByText("Còn 2 trường cần sửa.")).toBeTruthy();
      expect(
        screen.getByText(
          /^Mục tiêu xác nhận đơn hàng: Máy chủ không nhận giá trị này/,
        ),
      ).toBeTruthy();
      const minutes = screen.getByRole("spinbutton", {
        name: "Số phút: Đơn hàng, bước 1 (O1)",
      });
      // antd draws a field's error after its motion starts, so it is awaited.
      expect(
        await within(
          minutes.closest(".ant-form-item") as HTMLElement,
        ).findByText(/Máy chủ không nhận giá trị này/),
      ).toBeTruthy();
    },
    SLOW,
  );

  it(
    "shows why a proposal waiting on the key refused this one, keeps what was typed, and does not send it again",
    async () => {
      const reason =
        "Quy tắc này đã có phiên bản 1.0.5 chờ duyệt, do Giang đề xuất lúc 09:00 14/10/2026 (giờ Việt Nam), và mỗi quy tắc chỉ có một phiên bản chờ duyệt.";
      api.proposeRule.mockRejectedValueOnce(
        new ApiError(409, {
          code: "conflict",
          message: reason,
          details: {
            key: "sales_kpi",
            rule: "one_open_proposal",
            version: "1.0.5",
          },
          request_id: "r-2",
        }),
      );
      const minutes = await openReceivedKpi();
      fireEvent.change(minutes, { target: { value: "9" } });
      fireEvent.blur(minutes);
      fireEvent.click(screen.getByRole("button", { name: "Xem thay đổi" }));
      fireEvent.click(await screen.findByRole("button", { name: "Gửi duyệt" }));

      expect(await screen.findByText(reason)).toBeTruthy();
      expect(
        (
          screen.getByRole("spinbutton", {
            name: "Số phút: Đơn hàng, bước 1 (O1)",
          }) as HTMLInputElement
        ).value,
      ).toBe("9");
      // The form started from a version a decision may since have replaced:
      // it is not sent again, and the page asks for the versions again.
      expect(screen.getByText(/^Biểu mẫu này không gửi lại được/)).toBeTruthy();
      await waitFor(() => expect(api.rules).toHaveBeenCalledTimes(2));
      fireEvent.click(screen.getByRole("button", { name: "Xem thay đổi" }));
      const send = await screen.findByRole("button", { name: "Gửi duyệt" });
      expect((send as HTMLButtonElement).disabled).toBe(true);
      expect(api.proposeRule).toHaveBeenCalledTimes(1);
    },
    SLOW,
  );

  it(
    "says a version is waiting on the key before anyone edits, and sends nothing while it waits",
    async () => {
      api.rules.mockImplementation(async () => ({
        ...RULES,
        versions: [
          {
            ...KPI_VERSION,
            version_id: "0aa10aa0-c939-7000-8539-31fd3e621702",
            version: "1.0.5",
            ref: "sales_kpi@1.0.5",
            status: "proposed",
            proposed_by: GIANG,
            proposed_at: "2026-10-14T02:00:00Z",
            decided_by: null,
            decided_at: null,
            approval_id: "0aa10aa0-c939-7000-8539-31fd3e621703",
          },
          KPI_VERSION,
        ],
      }));
      renderPage("node=order.received");
      const notice = await screen.findByText(
        /^Phiên bản sales_kpi@1\.0\.5 đang chờ duyệt, do .+ đề xuất lúc 09:00 14\/10\/2026 \(giờ Việt Nam\)\.$/,
      );
      expect(notice).toBeTruthy();
      expect(
        screen
          .getByRole("link", { name: "Mở yêu cầu duyệt" })
          .getAttribute("href"),
      ).toBe("/approvals/0aa10aa0-c939-7000-8539-31fd3e621703");
      // Still viewable; the editor says it too, and does not send.
      fireEvent.click(
        screen.getByRole("button", {
          name: "Xem và đề xuất thay đổi: Chỉ tiêu KPI",
        }),
      );
      await screen.findByRole("spinbutton", {
        name: "Số phút: Đơn hàng, bước 1 (O1)",
      });
      fireEvent.click(screen.getByRole("button", { name: "Xem thay đổi" }));
      const send = await screen.findByRole("button", { name: "Gửi duyệt" });
      expect((send as HTMLButtonElement).disabled).toBe(true);
      expect(api.proposeRule).not.toHaveBeenCalled();
      api.rules.mockImplementation(async () => RULES);
    },
    SLOW,
  );

  it(
    "puts the editor in the URL: Back closes it, and with unsent changes asks first",
    async () => {
      renderPage("node=order.received");
      await screen.findByText("Đơn hàng · Đã nhận");
      fireEvent.click(
        await screen.findByRole("button", {
          name: "Xem và đề xuất thay đổi: Chỉ tiêu KPI",
        }),
      );
      expect(nav.push).toHaveBeenLastCalledWith(
        "/sales/rules/process?node=order.received&edit=sales_kpi",
        { scroll: false },
      );
      const minutes = (await screen.findByRole("spinbutton", {
        name: "Số phút: Đơn hàng, bước 1 (O1)",
      })) as HTMLInputElement;
      fireEvent.change(minutes, { target: { value: "7" } });

      // Back, with a change not sent: the editor stays, and the page asks.
      const asked = () => document.querySelectorAll(".ant-modal-confirm");
      act(() => nav.back());
      await waitFor(() => expect(asked().length).toBe(1));
      expect(asked()[0]!.textContent).toContain("Bỏ tài liệu đang sửa?");
      expect(nav.get().get("edit")).toBe("sales_kpi");
      fireEvent.click(screen.getByRole("button", { name: "Tiếp tục sửa" }));
      expect(
        (
          screen.getByRole("spinbutton", {
            name: "Số phút: Đơn hàng, bước 1 (O1)",
          }) as HTMLInputElement
        ).value,
      ).toBe("7");

      // Back again, and the change thrown away: the editor closes, the
      // status stays open.
      const before = screen.getAllByRole("button", { name: "Bỏ thay đổi" });
      act(() => nav.back());
      await waitFor(() =>
        expect(
          screen.getAllByRole("button", { name: "Bỏ thay đổi" }).length,
        ).toBeGreaterThan(before.length),
      );
      expect(nav.get().get("edit")).toBe("sales_kpi");
      const leave = screen.getAllByRole("button", { name: "Bỏ thay đổi" });
      fireEvent.click(leave[leave.length - 1]!);
      await waitFor(() => expect(nav.get().get("edit")).toBeNull());
      await waitFor(() =>
        expect(
          screen.queryByRole("spinbutton", {
            name: "Số phút: Đơn hàng, bước 1 (O1)",
          }),
        ).toBeNull(),
      );
      expect(nav.get().get("node")).toBe("order.received");
    },
    SLOW,
  );

  it(
    "draws a locked field read-only with why, beside the fields it may edit",
    async () => {
      renderPage("node=process");
      fireEvent.click(
        await screen.findByRole("button", {
          name: "Xem và đề xuất thay đổi: Nhắc việc và tóm tắt buổi sáng",
        }),
      );
      const zone = (await screen.findByRole("textbox", {
        name: "Múi giờ",
      })) as HTMLInputElement;
      expect(zone.disabled).toBe(true);
      expect(screen.getByText("Chỉ xem ở trang này.")).toBeTruthy();
      expect(screen.getByText(/giờ Việt Nam cố định/)).toBeTruthy();
      expect(
        (screen.getByRole("textbox", { name: "Bắt đầu" }) as HTMLInputElement)
          .disabled,
      ).toBe(false);
    },
    SLOW,
  );

  it("draws the forbidden state, and asks nothing, without sales.rules.propose", () => {
    scopes = ["sales.case.read", "sales.price.read"];
    renderPage();
    expect(
      screen.getByText(/Quyền của bạn trong không gian làm việc này/),
    ).toBeTruthy();
    expect(api.rulesProcess).not.toHaveBeenCalled();
  });

  it(
    "draws a failure with its request id, and an empty process as empty",
    async () => {
      api.rulesProcess.mockRejectedValueOnce(
        new ApiError(500, {
          code: "internal",
          message: "Máy chủ gặp lỗi.",
          details: {},
          request_id: "req-process-1",
        }),
      );
      renderPage();
      expect(await screen.findByText(/req-process-1/)).toBeTruthy();
      cleanup();

      api.rulesProcess.mockResolvedValueOnce({ ...PROCESS, lanes: [] });
      renderPage();
      expect(
        await screen.findByText("Máy chủ chưa trả về quy trình nào."),
      ).toBeTruthy();
    },
    SLOW,
  );
});

describe("a step's drawer: its AI, the data it reads, who acts (2026-10-23)", () => {
  /** The drawer of the order lane's "Đã nhận" (step O1). */
  async function openReceived(view: View = PROCESS) {
    api.rulesProcess.mockResolvedValueOnce(view);
    renderPage("node=order.received");
    await screen.findByText("Đơn hàng · Đã nhận");
    return drawer("Đơn hàng · Đã nhận");
  }
  const section = (open: HTMLElement, title: string) =>
    within(open).getByText(title).closest(".ant-card") as HTMLElement;

  it(
    "opens as a bottom sheet on a phone, from the right on a wider screen (ui-quality §9)",
    async () => {
      const phone = await openReceived();
      expect(
        phone.closest(".ant-drawer")?.classList.contains("ant-drawer-bottom"),
      ).toBe(true);
      cleanup();
      Object.defineProperty(window, "matchMedia", {
        writable: true,
        value: media(true),
      });
      const wide = await openReceived();
      expect(
        wide.closest(".ant-drawer")?.classList.contains("ant-drawer-right"),
      ).toBe(true);
    },
    SLOW,
  );

  it(
    "shows each model step's switch, bar, latest measurement and use, read-only",
    async () => {
      const open = await openReceived();
      const ai = section(open, "AI ở bước này");
      expect(ai.textContent).toContain(
        "Một bước chỉ bật được khi lần đo gần nhất",
      );
      const intent = within(ai).getByRole("region", {
        name: "Phân loại thư không có tài liệu đọc được",
      });
      expect(intent.textContent).toContain("AI bật · đạt");
      // The bar and the week's share are two numbers on two scales.
      expect(intent.textContent).toContain("Điểm đạt đo trên bộ thử90%");
      expect(intent.textContent).toContain("Thực tế 7 ngàychưa có dữ liệu");
      expect(intent.textContent).not.toContain("Tự động 7 ngày qua");
      expect(intent.textContent).toContain("90% · đạt");
      expect(intent.textContent).toContain(
        "qwen3.5-9b-dw · sales.message_intent@1.0.0 · 10:00 05/10/2026 (giờ Việt Nam)",
      );
      expect(intent.textContent).toContain("Đang dùng mô hình");
      // Read-only: nothing in the section switches a step.
      expect(within(ai).queryByRole("switch")).toBeNull();
      expect(within(ai).queryByRole("button")).toBeNull();
    },
    SLOW,
  );

  it(
    "says the week's share beside the bar, and a step never measured or failing in words",
    async () => {
      const steps = PROCESS.steps.map((s) =>
        s.step_id !== "O1"
          ? s
          : {
              ...s,
              models: s.models.map((m, i) =>
                i === 0
                  ? {
                      ...m,
                      live_share: {
                        handled: 10,
                        automatic: 6,
                        share: 0.6,
                        window_days: 7,
                      },
                    }
                  : i === 1
                    ? { ...m, latest: null, effective: false }
                    : { ...m, enabled: false, effective: false },
              ),
            },
      );
      const open = await openReceived({ ...PROCESS, steps });
      const ai = section(open, "AI ở bước này");
      const region = (name: string) => within(ai).getByRole("region", { name });
      expect(
        region("Phân loại thư không có tài liệu đọc được").textContent,
      ).toContain(
        "Thực tế 7 ngàyDW1 tự xử lý 60% số mục (6/10)Đếm trên việc thật, không cùng thước với điểm đạt.",
      );
      const reply = region("Đọc thư trả lời của khách trong hồ sơ");
      expect(reply.textContent).toContain("Chưa đo");
      expect(reply.textContent).toContain("AI bật · chưa đạt — người làm");
      expect(reply.textContent).toContain(
        "Chưa dùng mô hình: lần đo chưa đạt, người làm bước này",
      );
      const handoff = region("Soạn nháp chuyển giao cho PC/QA từ thư");
      expect(handoff.textContent).toContain("AI tắt");
      expect(handoff.textContent).toContain("Tắt: người làm bước này");
    },
    SLOW,
  );

  it(
    "links the lists and the PO layouts the step reads, and names who acts on it",
    async () => {
      const open = await openReceived();
      const uses = section(open, "Dữ liệu bước này dùng");
      expect(
        within(uses)
          .getByRole("link", { name: "Khách hàng" })
          .getAttribute("href"),
      ).toBe("/sales/master-data?tab=customers");
      expect(
        within(uses).getByRole("link", { name: "Mẫu PO" }).getAttribute("href"),
      ).toBe("/sales/layouts");
      const people = section(open, "Ai làm, ai duyệt");
      expect(people.textContent).toContain("Vai trò: DW1");
      expect(people.textContent).toContain("Quyền: sales.inbox.process");
      // Who may change the members is pointed to them; nobody else is.
      expect(within(people).queryByRole("link")).toBeNull();
    },
    SLOW,
  );

  it(
    "points who may change the members to the roles page",
    async () => {
      scopes = [...scopes, "platform.members.write"];
      const open = await openReceived();
      expect(
        within(section(open, "Ai làm, ai duyệt"))
          .getByRole("link", {
            name: "Đổi người giữ vai trò ở trang Vai trò và quyền",
          })
          .getAttribute("href"),
      ).toBe("/admin");
    },
    SLOW,
  );

  it(
    "draws no AI, data or people section for a lane's or the process's settings",
    async () => {
      renderPage("node=order");
      await screen.findByText("Đơn hàng · Thiết lập của cả luồng");
      for (const title of [
        "AI ở bước này",
        "Dữ liệu bước này dùng",
        "Ai làm, ai duyệt",
      ])
        expect(screen.queryByText(title)).toBeNull();
    },
    SLOW,
  );
});

describe("the DW1 process page for a proposer who reads no price", () => {
  /** Opens each status, step and lane of both lanes, and every key's editor. */
  async function openEverything() {
    await status("Đã nhận");
    const view = (await api.rulesProcess.mock.results[0]!.value) as View;
    const ids = [
      "process",
      ...view.lanes.flatMap((lane) => [
        lane.kind,
        ...lane.nodes.map((n) => `${lane.kind}.${n.status}`),
        ...lane.stateless_steps.map((s) => `${lane.kind}.${s}`),
      ]),
    ];
    for (const id of ids) {
      cleanup();
      renderPage(`node=${id}`);
      await screen.findByText(
        "Thay đổi chỉ áp dụng cho hồ sơ được kiểm sau khi phiên bản mới được duyệt.",
      );
      for (const button of screen.queryAllByRole("button", {
        name: /^Xem và đề xuất thay đổi: /,
      }))
        fireEvent.click(button);
      await waitFor(() =>
        expect(screen.queryAllByText(/Đang tải/)).toEqual([]),
      );
    }
  }

  const askedFor = () =>
    new Set(
      [
        ...api.ruleSchema.mock.calls,
        ...api.rulePlatformDocuments.mock.calls,
      ].map(([key]) => key),
    );

  it("never asks for a price key's schema or documents, and names none", async () => {
    scopes = ["sales.rules.propose"];
    api.rulesProcess.mockImplementation(async () => withoutPrices(PROCESS));
    renderPage();
    await openEverything();
    // Served no model step, the drawer draws no AI section, not an empty one.
    expect(screen.queryByText("AI ở bước này")).toBeNull();
    expect([...askedFor()].sort()).toEqual(["sales_followups", "sales_kpi"]);
    for (const words of [
      "Quy tắc kiểm tra đơn hàng",
      "Quy tắc báo giá",
      "Chính sách giá",
    ])
      expect(screen.queryByText(words), words).toBeNull();
    api.rulesProcess.mockReset();
  }, 120_000);

  it("the search can fail: served the price keys, the page asks for them", async () => {
    api.rulesProcess.mockImplementation(async () => PROCESS);
    renderPage();
    await openEverything();
    expect([...askedFor()]).toEqual(expect.arrayContaining(PRICE_KEYS));
    api.rulesProcess.mockReset();
  }, 120_000);
});

describe("/sales/rules after the editor moved out", () => {
  it(
    "still proposes a whole key from its own drawer",
    async () => {
      render(
        <UiProvider>
          <RulesPage />
        </UiProvider>,
      );
      fireEvent.click(
        await screen.findByRole("button", {
          name: "Đề xuất phiên bản mới: Chỉ tiêu KPI",
        }),
      );
      // The whole key: the target and every step's minutes.
      expect(
        await screen.findByRole("spinbutton", {
          name: "Mục tiêu xác nhận đơn hàng",
        }),
      ).toBeTruthy();
      expect(
        screen.getByRole("spinbutton", {
          name: "Số phút: Báo giá, bước 1 (Q1)",
        }),
      ).toBeTruthy();
      expect(drawer("Đề xuất phiên bản mới: Chỉ tiêu KPI")).toBeTruthy();
      // The whole key, so JSON too.
      expect(screen.getByText("JSON nâng cao")).toBeTruthy();
    },
    SLOW,
  );
});
