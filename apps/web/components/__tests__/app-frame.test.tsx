import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";

let pathname = "/sales/orders";
vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

// The bell polls the inbox; an empty one keeps it quiet.
vi.mock("../../lib/session", () => ({
  apiClient: () => ({
    listNotifications: vi.fn().mockResolvedValue({ items: [], unread: 0 }),
    markNotificationRead: vi.fn(),
    markAllNotificationsRead: vi.fn(),
  }),
}));

let auth: Record<string, unknown> = {};
vi.mock("../../lib/auth/auth-context", () => ({ useAuth: () => auth }));

import { AppFrame } from "../app-frame";

/** A signed-in member of one workspace, holding `scopes` through `roles`. */
function signIn(scopes: string[], roles: string[] = ["sales"]) {
  const active = {
    tenantId: "t-1",
    tenantSlug: "alpha",
    tenantName: "Công ty Alpha",
    workspaceId: "w-1",
    workspaceSlug: "sales",
    workspaceName: "Phòng Kinh doanh",
    roles,
    scopes,
  };
  auth = {
    status: "ready",
    error: null,
    displayName: "Nguyễn Văn An",
    active,
    memberships: [active],
    roles,
    scopes,
    isPlatformOperator: false,
    hasScope: (scope: string) =>
      roles.includes("platform_admin") || scopes.includes(scope),
    hasRole: (role: string) => roles.includes(role),
    logout: vi.fn(),
    selectWorkspace: vi.fn(),
  };
}

/** A Sales PIC's role scopes, as the sales migration grants them. */
const PIC = [
  "sales.overview.read",
  "sales.case.read",
  "sales.price.read",
  "sales.inbox.process",
  "sales.order.prepare",
  "sales.order.cross_check",
  "sales.quote.prepare",
  "sales.worker.pause",
];

function renderShell() {
  return render(
    <UiProvider>
      <AppFrame>
        <p>Nội dung trang</p>
      </AppFrame>
    </UiProvider>,
  );
}

function openDrawer() {
  fireEvent.click(screen.getByRole("button", { name: "Mở menu" }));
  return screen.getByRole("dialog", { name: "Menu" });
}

afterEach(() => {
  cleanup();
  pathname = "/sales/orders";
});

describe("the shell's navbar", () => {
  it("shows the Sales group, whose pages the drawer lists as links", () => {
    signIn(PIC);
    renderShell();

    expect(screen.getByText("Nội dung trang")).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: /Sales/ })).toBeTruthy();

    const drawer = openDrawer();
    const pages = [
      ["Việc cần làm", "/sales"],
      ["Hộp thư", "/sales/inbox"],
      ["Đơn hàng", "/sales/orders"],
      ["Báo giá", "/sales/quotes"],
      ["Kiểm chéo & duyệt", "/sales/review"],
      ["Dữ liệu giả lập", "/sales/master-data"],
      ["Tổng quan quy trình", "/sales/overview"],
    ];
    for (const [name, href] of pages) {
      expect(
        within(drawer).getByRole("link", { name }).getAttribute("href"),
      ).toBe(href);
    }
  });

  it("marks the page on screen as the current one", () => {
    signIn(PIC);
    renderShell();
    const drawer = openDrawer();
    expect(
      within(drawer)
        .getByRole("link", { name: "Đơn hàng" })
        .getAttribute("aria-current"),
    ).toBe("page");
    expect(
      within(drawer)
        .getByRole("link", { name: "Việc cần làm" })
        .getAttribute("aria-current"),
    ).toBeNull();
  });

  it("leaves Sales out for someone who may not read it", () => {
    signIn(["approvals.read"], ["member"]);
    pathname = "/approvals";
    renderShell();

    expect(screen.queryByRole("menuitem", { name: /Sales/ })).toBeNull();
    const drawer = openDrawer();
    expect(within(drawer).queryByRole("link", { name: "Đơn hàng" })).toBeNull();
    expect(
      within(drawer)
        .getByRole("link", { name: "Approvals" })
        .getAttribute("href"),
    ).toBe("/approvals");
  });

  it("points the brand at the first page the person can open", () => {
    signIn(PIC);
    renderShell();
    expect(
      screen.getByRole("link", { name: "Digital Worker" }).getAttribute("href"),
    ).toBe("/sales");

    cleanup();
    signIn([], ["member"]);
    pathname = "/";
    renderShell();
    expect(
      screen.getByRole("link", { name: "Digital Worker" }).getAttribute("href"),
    ).toBe("/");
  });
});
