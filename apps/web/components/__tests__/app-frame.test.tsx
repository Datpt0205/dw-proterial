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

// The Sales counts beside the nav items.
const myWork = vi.fn();
const salesInbox = vi.fn();
vi.mock("../../app/sales/_lib/api", () => ({
  salesApi: () => ({ myWork, inbox: salesInbox }),
}));

import { AppFrame } from "../app-frame";

/** The role catalogue's names, as `/auth/bootstrap` sends them. */
const ROLE_NAMES: Record<string, string> = {
  member: "Member",
  director: "Director",
  platform_admin: "Platform admin",
  sales_pic: "Sales phụ trách (PIC)",
  sales_head: "Trưởng bộ phận Sales",
};

/** A signed-in member of one workspace, holding `scopes` through `roles`. */
function signIn(scopes: string[], roles: string[] = ["member", "sales_pic"]) {
  const active = {
    tenantId: "t-1",
    tenantSlug: "alpha",
    tenantName: "Công ty Alpha",
    workspaceId: "w-1",
    workspaceSlug: "sales",
    workspaceName: "Phòng Kinh doanh",
    roles,
    scopes,
    roleNames: Object.fromEntries(
      roles.map((key) => [key, ROLE_NAMES[key] ?? key]),
    ),
  };
  auth = {
    status: "ready",
    error: null,
    displayName: "Nguyễn Văn An",
    email: "an.nguyen@alpha.local",
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

/** The platform member role's scopes. */
const MEMBER = [
  "approvals.read",
  "directory.read",
  "integrations.read",
  "knowledge.read",
  "memory.read",
  "runs.read",
];

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

/** The horizontal bar (the drawer holds a second navigation once open). */
function theBar() {
  return screen.getAllByRole("navigation", { name: "Điều hướng chính" })[0]!;
}

function quietSales() {
  myWork.mockResolvedValue([]);
  salesInbox.mockResolvedValue([]);
}

afterEach(() => {
  cleanup();
  pathname = "/sales/orders";
  myWork.mockReset();
  salesInbox.mockReset();
});

describe("the shell's navbar", () => {
  it("is the Sales pages for a PIC, the platform's own pages left off", () => {
    quietSales();
    signIn([...MEMBER, ...PIC]);
    renderShell();

    expect(screen.getByText("Nội dung trang")).toBeTruthy();
    const bar = theBar();
    expect(
      within(bar)
        .getByRole("link", { name: "Việc cần làm" })
        .getAttribute("href"),
    ).toBe("/sales");
    expect(within(bar).queryByRole("menuitem", { name: /^Sales$/ })).toBeNull();
    expect(within(bar).queryByRole("link", { name: "Approvals" })).toBeNull();
    expect(within(bar).queryByRole("link", { name: "Home" })).toBeNull();

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
    expect(
      within(drawer).queryByRole("link", { name: "Approvals" }),
    ).toBeNull();
  });

  it("names the brand after the product and points it at the first page", () => {
    quietSales();
    signIn([...MEMBER, ...PIC]);
    renderShell();
    expect(
      screen
        .getByRole("link", { name: "Digital Worker · Sales, về trang đầu" })
        .getAttribute("href"),
    ).toBe("/sales");

    cleanup();
    signIn([], ["member"]);
    pathname = "/";
    renderShell();
    expect(
      screen
        .getByRole("link", { name: "Digital Worker, về trang đầu" })
        .getAttribute("href"),
    ).toBe("/");
  });

  it("names the PIC's role in Vietnamese, from the role catalogue", () => {
    quietSales();
    signIn([...MEMBER, ...PIC]);
    renderShell();
    const account = screen.getByRole("button", {
      name: "Tài khoản: Nguyễn Văn An, Sales phụ trách (PIC)",
    });
    expect(account.textContent).toContain("Sales phụ trách (PIC)");
    expect(account.textContent).toContain("NA");
    expect(screen.queryByText("Staff")).toBeNull();
  });

  it("takes the role's name from the session, not from a copy of its own", () => {
    quietSales();
    signIn([...MEMBER, ...PIC], ["director", "sales_head"]);
    (
      auth.active as { roleNames: Record<string, string> }
    ).roleNames.sales_head = "Tên do danh mục vai đặt";
    renderShell();
    expect(
      screen.getByRole("button", {
        name: "Tài khoản: Nguyễn Văn An, Tên do danh mục vai đặt",
      }),
    ).toBeTruthy();
  });

  it("counts the waiting work and the unprocessed messages beside their pages", async () => {
    myWork.mockResolvedValue([{ kind: "order" }, { kind: "quote" }]);
    salesInbox.mockResolvedValue([
      { disposition: { kind: "not_yet_processed" } },
      { disposition: { kind: "case_created" } },
    ]);
    signIn([...MEMBER, ...PIC]);
    renderShell();
    expect(
      await within(theBar()).findByRole("link", { name: "Việc cần làm (2)" }),
    ).toBeTruthy();
    expect(
      await within(theBar()).findByRole("link", { name: "Hộp thư (1)" }),
    ).toBeTruthy();
  });

  it("marks the page on screen as the current one", () => {
    quietSales();
    signIn([...MEMBER, ...PIC]);
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

  it("keeps the platform's menus, Sales as one group, for an administrator", () => {
    quietSales();
    signIn([...MEMBER, ...PIC], ["platform_admin", "member"]);
    pathname = "/approvals";
    renderShell();

    expect(screen.getByRole("menuitem", { name: /Sales/ })).toBeTruthy();
    const drawer = openDrawer();
    expect(
      within(drawer)
        .getByRole("link", { name: "Approvals" })
        .getAttribute("href"),
    ).toBe("/approvals");
    expect(
      screen.getByRole("button", {
        name: "Tài khoản: Nguyễn Văn An, Tenant Admin",
      }),
    ).toBeTruthy();
  });

  it("leaves Sales out for someone who may not read it", () => {
    signIn(["approvals.read"], ["member"]);
    pathname = "/approvals";
    renderShell();

    expect(screen.queryByRole("menuitem", { name: /Sales/ })).toBeNull();
    expect(myWork).not.toHaveBeenCalled();
    const drawer = openDrawer();
    expect(within(drawer).queryByRole("link", { name: "Đơn hàng" })).toBeNull();
    expect(
      within(drawer)
        .getByRole("link", { name: "Approvals" })
        .getAttribute("href"),
    ).toBe("/approvals");
  });
});
