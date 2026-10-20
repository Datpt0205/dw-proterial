import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { SalesSchemas } from "@dw/api-client";

type Board = SalesSchemas["PipelineView"];

const DIEU = "00000000-0000-4000-8000-0000000000d1";
const AN = "00000000-0000-4000-8000-0000000000a1";

vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: DIEU,
    displayName: "Diệu",
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => scope === "sales.case.read",
  }),
}));
vi.mock("../../../../lib/session", () => ({
  apiClient: () => ({ listWorkspaceMembers: vi.fn().mockResolvedValue([]) }),
}));
let search = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useSearchParams: () => search,
  usePathname: () => "/sales/pipeline",
  useRouter: () => ({ replace: vi.fn() }),
}));

const column = (
  kind: "order" | "quote",
  status: string,
  holder: SalesSchemas["PipelineColumn"]["holder"],
  cases: number,
  steps: string[] = [],
) => ({ kind, status, holder, steps, cases, hidden: 0 });

const card = (
  overrides: Partial<SalesSchemas["PipelineCard"]>,
): SalesSchemas["PipelineCard"] => ({
  kind: "order",
  case_id: "11111111-1111-4111-8111-111111111111",
  status: "uploaded_to_bravo",
  reference: "PO-ALPHA-001",
  customer_code: "C-ALPHA",
  assigned_to: AN,
  received_at: "2026-10-20T01:00:00Z",
  status_since: "2026-10-20T02:00:00Z",
  due: null,
  overdue: false,
  open_findings: 0,
  blocking_findings: 0,
  awaits_cross_check: true,
  my_action: null,
  ...overrides,
});

let shown: Board;
const api = {
  pipeline: vi.fn(async () => shown),
  customers: vi.fn(async () => ({ items: [] })),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import { PipelineBoard } from "../../_components/pipeline-board";

function board(): Board {
  return {
    as_of: "2026-10-20T03:00:00Z",
    columns: [
      column("order", "in_review", "sales", 1, ["O6"]),
      column("order", "uploaded_to_bravo", "sales", 1, ["O3", "O7"]),
      column("order", "confirmed", null, 0, ["O10"]),
      column("quote", "pending_approval", "approver", 1, ["Q9"]),
    ],
    cards: [
      card({ my_action: "cross_check" }),
      card({
        case_id: "22222222-2222-4222-8222-222222222222",
        status: "in_review",
        reference: "PO-ALPHA-002",
        blocking_findings: 2,
        open_findings: 3,
        awaits_cross_check: false,
      }),
      card({
        kind: "quote",
        case_id: "33333333-3333-4333-8333-333333333333",
        status: "pending_approval",
        reference: "RFQ-ALPHA-009",
        awaits_cross_check: false,
        overdue: true,
        due: "2026-10-18",
      }),
    ],
  };
}

function show() {
  return render(
    <UiProvider>
      <PipelineBoard />
    </UiProvider>,
  );
}

afterEach(() => {
  cleanup();
  search = new URLSearchParams();
});

describe("the pipeline board", () => {
  it("lays every case in its status's column, each a link to its page", async () => {
    shown = board();
    show();

    const bravo = await screen.findByRole("group", {
      name: "Đã nhập Bravo: 1 hồ sơ",
    });
    const link = within(bravo).getByRole("link", { name: "PO PO-ALPHA-001" });
    expect(link.getAttribute("href")).toBe(
      "/sales/orders/11111111-1111-4111-8111-111111111111",
    );
    const review = screen.getByRole("group", {
      name: "Chờ PIC tự kiểm: 1 hồ sơ",
    });
    expect(within(review).getByText("2 cờ chặn")).toBeTruthy();
    expect(within(review).getByText("1 cờ cần xem")).toBeTruthy();
    // Whose turn the column is, and the surveyed steps it stands for.
    expect(within(review).getByText("Sales quyết định · O6")).toBeTruthy();
    const approval = screen.getByRole("group", { name: "Chờ duyệt: 1 hồ sơ" });
    expect(
      within(approval).getByRole("link", { name: "RFQ RFQ-ALPHA-009" }),
    ).toBeTruthy();
    expect(within(approval).getByText(/Quá hạn/)).toBeTruthy();
    // An empty column is still drawn, so the pipeline keeps its shape.
    expect(
      screen.getByRole("group", { name: "Đã xác nhận: 0 hồ sơ" }),
    ).toBeTruthy();
  });

  it("names the viewer's own step on the cards that are theirs", async () => {
    shown = board();
    show();

    const bravo = await screen.findByRole("group", {
      name: "Đã nhập Bravo: 1 hồ sơ",
    });
    expect(
      within(bravo).getByText("Việc của bạn: Kiểm chéo với Bravo"),
    ).toBeTruthy();
    expect(screen.getAllByText(/Việc của bạn/)).toHaveLength(1);
    expect(screen.getByText("Việc của tôi (1)")).toBeTruthy();
  });

  it("keeps only the viewer's cards under Việc của tôi", async () => {
    shown = board();
    search = new URLSearchParams("tab=mine");
    show();

    await screen.findByRole("link", { name: "PO PO-ALPHA-001" });
    expect(screen.queryByRole("link", { name: "PO PO-ALPHA-002" })).toBeNull();
    expect(
      screen.queryByRole("link", { name: "RFQ RFQ-ALPHA-009" }),
    ).toBeNull();
  });

  it("says so when nothing waits on the viewer", async () => {
    shown = {
      ...board(),
      cards: board().cards.map((c) => ({ ...c, my_action: null })),
    };
    search = new URLSearchParams("tab=mine");
    show();

    expect(
      await screen.findByText("Không có hồ sơ nào đang chờ bạn"),
    ).toBeTruthy();
  });
});
