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

/**
 * Kiểm soát xuất khẩu, WIV-03-032 (ticket 45): each customer with what it
 * still owes; a customer opens in a drawer at its own URL, where the
 * export-control PIC records each step. Without `sales.compliance.ack` the
 * forms say why they are closed (the server refuses anyway).
 */
let scopes = ["sales.case.read", "sales.compliance.ack"];
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

const nav = vi.hoisted(() => {
  const listeners = new Set<() => void>();
  let path = "/sales/export-control";
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

type Row = SalesSchemas["CustomerScreeningView"];

function row(overrides: Partial<Row>): Row {
  return {
    customer_code: "VLX",
    customer_name: "Công ty Vĩnh Lộc (mẫu)",
    status: "official",
    noc_confirmed: true,
    esf_fiscal_year: 2026,
    denial_list_checked_on: "2026-10-01",
    denial_list_match: false,
    red_flag_escalated: false,
    traded_recently: true,
    needs: [],
    ...overrides,
  };
}

const owing = row({
  customer_code: "NRV",
  customer_name: "Nam Răng (mẫu)",
  noc_confirmed: false,
  esf_fiscal_year: null,
  denial_list_checked_on: null,
  needs: ["denial_due", "red_flag_missing", "noc_missing", "esf_due"],
});

const api = {
  exportControl: vi.fn(async () => ({
    fiscal_year: 2026,
    denial_list_max_age_days: 365,
    policy_ref: "sales_export_control@0.1.0",
    sample: true,
    customers: [owing, row({})],
  })),
  exportControlCustomer: vi.fn(async () => ({
    summary: owing,
    screenings: [],
    products: [{ prv_code: "CB-2007", classification: null }],
    red_flags: [
      { id: "rf01", text: "Khách ngại nói mục đích sử dụng cuối?" },
      { id: "rf02", text: "Địa chỉ giao hàng khác nước của khách?" },
    ],
    esf_approvers: ["Trưởng bộ phận Sales", "Giám đốc"],
    sample: true,
  })),
  recordScreening: vi.fn(async () => ({})),
  exportControlFile: vi.fn(),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import ExportControlPage from "../../export-control/page";

function page(url = "/sales/export-control") {
  nav.reset(url);
  return render(
    <UiProvider>
      <ExportControlPage />
    </UiProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  scopes = ["sales.case.read", "sales.compliance.ack"];
});

describe("the export-control page", () => {
  it("lists what each customer still owes, and links each to its drawer", async () => {
    page();
    const link = await screen.findByRole("link", { name: "NRV" });
    expect(link.getAttribute("href")).toBe(
      "/sales/export-control?customer=NRV",
    );
    const tableRow = link.closest("tr")!;
    for (const need of [
      "Cần kiểm danh sách cấm",
      "Chưa trả lời red flag",
      "Chưa có NOC",
      "ESF năm nay chưa duyệt",
    ])
      expect(within(tableRow).getByText(need)).toBeTruthy();
    expect(screen.getByText("Đủ các bước")).toBeTruthy();
    expect(screen.getByText(/1 khách còn bước phải làm/)).toBeTruthy();
  }, 20_000);

  it("records the red-flag answers only once every question is answered", async () => {
    page("/sales/export-control?customer=NRV");
    const record = await screen.findByRole("button", {
      name: "Ghi câu trả lời",
    });
    expect(record.hasAttribute("disabled")).toBe(true);
    expect(screen.getByText("Còn 2 câu chưa trả lời.")).toBeTruthy();

    const [first, second] = screen
      .getAllByRole("radiogroup")
      .filter((g) => g.getAttribute("aria-label")?.includes("?"));
    fireEvent.click(within(first!).getByRole("radio", { name: "Không" }));
    fireEvent.click(within(second!).getByRole("radio", { name: "Có" }));
    await waitFor(() =>
      expect(screen.queryByText("Còn 1 câu chưa trả lời.")).toBeNull(),
    );
    expect(screen.queryByText(/Còn d câu/)).toBeNull();
    fireEvent.click(
      await screen.findByRole("button", { name: "Ghi câu trả lời" }),
    );

    await waitFor(() => expect(api.recordScreening).toHaveBeenCalledTimes(1));
    const [code, step, body] = api.recordScreening.mock.calls[0] as unknown as [
      string,
      string,
      { answers: Record<string, boolean> },
    ];
    expect([code, step]).toEqual(["NRV", "red-flag"]);
    expect(body.answers).toEqual({ rf01: false, rf02: true });
  }, 20_000);

  it("closes every form to someone without the compliance permission, saying why", async () => {
    scopes = ["sales.case.read"];
    page("/sales/export-control?customer=NRV");
    const buttons = await screen.findAllByRole("button", {
      name: "Ghi kết quả",
    });
    expect(buttons.length).toBe(3);
    for (const button of buttons)
      expect(button.hasAttribute("disabled")).toBe(true);
    expect(
      screen.getAllByText(/cần quyền xác nhận tuân thủ/).length,
    ).toBeGreaterThan(0);
  }, 20_000);
});
