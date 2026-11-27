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
  due_soon: false,
  assigned_to: null,
  owner,
});
let items: WorkItem[] = [];
let unread: string[] = [];
const api = {
  // No case holds an answer the person has not seen unless a test says so (ticket 46).
  assistantUnread: vi.fn(async (): Promise<string[]> => unread),
  myWork: vi.fn(async () => items),
  orders: vi.fn(async () => []),
  quotes: vi.fn(async () => []),
  inbox: vi.fn(async () => []),
  openYcbg: vi.fn(async () => []),
  today: vi.fn(async () => ({ brief: null, reminders: [], hidden: 0 })),
  customers: vi.fn(async () => ({ items: [] })),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import MyWorkPage from "../../page";
import { SalesFrameProvider } from "../../_components/sales-frame";

const desk = window.matchMedia;
afterEach(() => {
  cleanup();
  items = [];
  unread = [];
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

describe("a case with an answer not seen (ticket 46)", () => {
  it("is marked in its row, from one read for the whole list", async () => {
    const order: WorkItem = {
      ...mail("ca5e0000-0000-4000-8000-000000000001", AN),
      kind: "order",
      status: "in_review",
      action: "self_check",
    };
    items = [order, mail("m-1", AN)];
    unread = [order.id, "m-1"];
    page();
    const marks = await screen.findAllByRole("img", {
      name: "Có trả lời của DW1 chưa xem",
    });
    // The order's; a mail is no case, whatever id a read returns.
    expect(marks).toHaveLength(1);
    expect(api.assistantUnread).toHaveBeenCalledTimes(1);
  }, 20_000);
});

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

  it("counts and names only Sales' approvals the list does not already carry", async () => {
    // Giang's page during the full review (2026-11-27): DW2's requests, and
    // a cross-check my-work lists on its order, were counted here as rules.
    scopes = ["sales.case.read", "approvals.read", "approvals.decide"];
    const of = (id: string, type: string) => ({
      ...approval(id, true),
      approval_type: type,
    });
    listApprovals.mockResolvedValueOnce({
      items: [
        of("p-1", "purchasing.request"),
        of("p-2", "purchasing.request"),
        of("c-1", "sales.order.cross_check"),
        of("q-1", "sales.quote"),
        of("r-1", "sales.rules"),
        of("l-1", "sales.layout"),
        of("r-2", "sales.rules"),
      ],
      next_cursor: null,
    });
    page();
    expect(await screen.findByText("3 yêu cầu chờ bạn duyệt")).toBeTruthy();
    expect(screen.getByText("Phiên bản quy tắc · Mẫu PO")).toBeTruthy();
  }, 20_000);

  it("asks for no approvals of someone who may not decide them", async () => {
    page();
    await screen.findByText(/Không có việc nào đang chờ bạn/);
    expect(listApprovals).not.toHaveBeenCalled();
    expect(screen.queryByText(/yêu cầu chờ bạn duyệt/)).toBeNull();
  }, 20_000);
});
