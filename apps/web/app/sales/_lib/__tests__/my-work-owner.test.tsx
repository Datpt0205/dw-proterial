import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { SalesSchemas } from "@dw/api-client";
import { AN } from "./fixtures";

type WorkItem = SalesSchemas["WorkItem"];

const SCOPES = ["sales.case.read"];
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
});
