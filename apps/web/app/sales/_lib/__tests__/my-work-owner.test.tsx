import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { SalesSchemas } from "@dw/api-client";
import { AN } from "./fixtures";

type WorkItem = SalesSchemas["WorkItem"];

let scopes = ["sales.case.read"];
vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: AN,
    displayName: "An",
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => scopes.includes(scope),
  }),
}));
const approval = (id: string, canDecide: boolean) => ({
  id,
  approval_type: "sales.rules",
  status: "pending",
  can_decide: canDecide,
});
const listApprovals = vi.fn(async () => ({
  items: [approval("a-1", true), approval("a-2", false)],
  next_cursor: null,
}));
vi.mock("../../../../lib/session", () => ({
  apiClient: () => ({
    listWorkspaceMembers: vi.fn().mockResolvedValue([]),
    listApprovals,
  }),
}));
vi.mock("next/navigation", () => ({
  usePathname: () => "/sales",
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const mail = (id: string, owner: string): WorkItem => ({
  kind: "message",
  id,
  status: "routed_to_sales",
  action: "triage",
  customer_code: null,
  received_at: "2026-10-27T01:00:00Z",
  due: null,
  assigned_to: null,
  owner,
});
let items: WorkItem[] = [];
const api = {
  myWork: vi.fn(async () => items),
  orders: vi.fn(async () => []),
  quotes: vi.fn(async () => []),
  inbox: vi.fn(async () => []),
  openYcbg: vi.fn(async () => []),
  customers: vi.fn(async () => ({ items: [] })),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import MyWorkPage from "../../page";
import { SalesFrameProvider } from "../../_components/sales-frame";

const desk = window.matchMedia;
afterEach(() => {
  cleanup();
  items = [];
  scopes = ["sales.case.read"];
  window.matchMedia = desk;
});

/** A 390 px phone: antd's `xs` query matches, every `min-width` does not. */
function phoneWidth() {
  window.matchMedia = ((query: string) => ({
    matches: /max-width:\s*575/.test(query),
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}

function page() {
  return render(
    <UiProvider>
      <SalesFrameProvider>
        <MyWorkPage />
      </SalesFrameProvider>
    </UiProvider>,
  );
}

describe("a routed mail on Việc cần làm (2026-10-27)", () => {
  it("names its owner as the inbox does: a person, or the team", async () => {
    items = [mail("m-1", AN), mail("m-2", "role:sales_admin")];
    page();
    expect(
      await screen.findByRole("img", { name: "Phụ trách: An (bạn)" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("img", { name: /^Phụ trách: Cả nhóm / }),
    ).toBeTruthy();
    expect(screen.queryByText("Chưa giao")).toBeNull();
  }, 20_000);

  it("on a phone, draws the work column alone with the state and deadline under it", async () => {
    phoneWidth();
    items = [mail("m-1", AN)];
    page();
    expect(await screen.findByText("Không đặt hạn")).toBeTruthy();
    // The work list's other columns are gone (the YCBG list below keeps its).
    const headers = screen
      .getAllByRole("columnheader")
      .map((h) => h.textContent);
    expect(headers).toContain("Việc");
    for (const gone of ["Trạng thái", "Hạn (giờ Việt Nam)", "Phụ trách"])
      expect(headers).not.toContain(gone);
    expect(screen.getByText("Chuyển Sales xử lý")).toBeTruthy();
  }, 20_000);

  it("names the approvals waiting on a head, which my-work does not carry", async () => {
    scopes = ["sales.case.read", "approvals.read", "approvals.decide"];
    page();
    // One of the two is the head's to decide; the other is not.
    const line = await screen.findByText("1 yêu cầu chờ bạn duyệt");
    expect(line.closest("a")?.getAttribute("href")).toBe("/approvals");
  }, 20_000);

  it("asks for no approvals of someone who may not decide them", async () => {
    page();
    await screen.findByText(/Không có việc nào đang chờ bạn/);
    expect(listApprovals).not.toHaveBeenCalled();
    expect(screen.queryByText(/yêu cầu chờ bạn duyệt/)).toBeNull();
  }, 20_000);
});
