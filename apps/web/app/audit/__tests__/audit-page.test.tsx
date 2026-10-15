import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { App } from "antd";
import type { AuditEvent } from "@dw/contracts";

let search = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useSearchParams: () => search,
}));

// The cache behind the list is keyed by workspace, so each test gets its own.
let workspace = 0;
vi.mock("../../../lib/auth/auth-context", () => ({
  useAuth: () => ({ active: { workspaceId: `ws-${workspace}` } }),
}));

const listAuditEvents = vi.fn();
vi.mock("../../../lib/session", () => ({
  apiClient: () => ({ listAuditEvents }),
}));

import AuditPage from "../page";

const GRANT = "5b0e6c2a-0000-4000-8000-0000000000aa";

beforeAll(() => {
  // antd's responsive helpers ask for media queries jsdom does not implement.
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});

afterEach(() => {
  cleanup();
  listAuditEvents.mockReset();
  search = new URLSearchParams();
});

function event(overrides: Partial<AuditEvent>): AuditEvent {
  return {
    actor_id: "11111111-0000-4000-8000-000000000001",
    actor_display_name: "Lan Phạm",
    actor_kind: "user",
    action: "approval.decided",
    resource_type: "approval",
    resource_id: "r-1",
    policy_decision: null,
    trace_id: null,
    occurred_at: "2026-10-12T03:00:00Z",
    details: {},
    ...overrides,
  };
}

function renderPage() {
  workspace += 1;
  return render(
    <App>
      <AuditPage />
    </App>,
  );
}

describe("the /audit page", () => {
  it("names the actor the server names, and marks the support team", async () => {
    listAuditEvents.mockResolvedValue({
      items: [
        event({}),
        event({
          actor_id: "22222222-0000-4000-8000-000000000002",
          actor_display_name: "Minh Hỗ Trợ",
          actor_kind: "support",
          action: "support.access",
          resource_id: GRANT,
          details: { support_grant_id: GRANT, code: "HT-7Q2K" },
        }),
      ],
      next_cursor: null,
    });
    renderPage();

    const support = (await screen.findByText("Minh Hỗ Trợ")).closest("tr");
    expect(support).not.toBeNull();
    expect(within(support!).getByText("Đội hỗ trợ")).toBeTruthy();
    const customer = screen.getByText("Lan Phạm").closest("tr");
    expect(within(customer!).queryByText("Đội hỗ trợ")).toBeNull();
    // The whole trail is asked for, with no grant filter.
    expect(listAuditEvents).toHaveBeenCalledWith({
      cursor: null,
      supportGrantId: undefined,
    });
    // A grant's row links to that grant's own trail.
    const link = within(support!).getByRole("link", {
      name: "Chỉ xem quyền hỗ trợ này",
    });
    expect(link.getAttribute("href")).toBe(`/audit?support_grant_id=${GRANT}`);
  });

  it("an actor with no name (a lane) shows its short id, not a blank", async () => {
    listAuditEvents.mockResolvedValue({
      items: [
        event({
          actor_id: "99999999-aaaa-4000-8000-000000000009",
          actor_display_name: null,
        }),
      ],
      next_cursor: null,
    });
    renderPage();
    expect(await screen.findByText("99999999…")).toBeTruthy();
  });

  it("reads one grant's trail from the URL and names the filter", async () => {
    search = new URLSearchParams({ support_grant_id: GRANT });
    listAuditEvents.mockResolvedValue({
      items: [
        event({
          actor_kind: "support",
          action: "support.access",
          details: { support_grant_id: GRANT, code: "HT-7Q2K" },
        }),
      ],
      next_cursor: null,
    });
    renderPage();

    expect(await screen.findByText("Quyền hỗ trợ HT-7Q2K")).toBeTruthy();
    expect(listAuditEvents).toHaveBeenCalledWith({
      cursor: null,
      supportGrantId: GRANT,
    });
    expect(
      screen.getByRole("link", { name: "Xóa bộ lọc" }).getAttribute("href"),
    ).toBe("/audit");
    // Inside the grant's own trail, no row offers the same filter again.
    expect(
      screen.queryByRole("link", { name: "Chỉ xem quyền hỗ trợ này" }),
    ).toBeNull();
  });
});
