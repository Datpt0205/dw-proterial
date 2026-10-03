import { describe, expect, it } from "vitest";
import { NAV, NAV_ITEMS } from "../nav/registry";
import { isNavGroup, type NavEntry } from "../nav/types";
import {
  currentPage,
  navPages,
  visibleNav,
  type NavViewer,
} from "../nav/visible";

function viewer(scopes: string[], roles: string[] = ["member"]): NavViewer {
  return {
    isPlatformOperator: false,
    roles,
    hasScope: (scope) => scopes.includes(scope),
  };
}

function labels(entries: NavEntry[]): string[] {
  return entries.flatMap((entry) =>
    isNavGroup(entry)
      ? [
          entry.label,
          ...entry.items.map((item) => `${entry.label} › ${item.label}`),
        ]
      : [entry.label],
  );
}

const SALES_PAGES = [
  "/sales",
  "/sales/inbox",
  "/sales/orders",
  "/sales/quotes",
  "/sales/master-data",
];

describe("the nav registry", () => {
  it("carries the Sales pages as one group", () => {
    const sales = NAV.find(
      (entry) => isNavGroup(entry) && entry.key === "sales",
    );
    expect(
      sales && isNavGroup(sales) && sales.items.map((item) => item.href),
    ).toEqual(SALES_PAGES);
  });

  it("lists every page once, groups opened up, for what lists pages", () => {
    const hrefs = NAV_ITEMS.map((item) => item.href);
    expect(hrefs).toEqual(
      expect.arrayContaining([...SALES_PAGES, "/", "/admin/feedback"]),
    );
    expect(new Set(hrefs).size).toBe(hrefs.length);
  });
});

describe("visibleNav", () => {
  it("shows the Sales group to someone who may read sales, and not otherwise", () => {
    expect(labels(visibleNav(NAV, viewer(["sales.read"])))).toEqual(
      expect.arrayContaining(["Sales", "Sales › Đơn hàng", "Sales › Báo giá"]),
    );
    expect(labels(visibleNav(NAV, viewer(["approvals.read"])))).not.toContain(
      "Sales",
    );
  });

  it("keeps only the items a group's viewer may see, and drops an empty group", () => {
    const admin = (scopes: string[]) =>
      visibleNav(NAV, viewer(scopes)).find(
        (entry) => isNavGroup(entry) && entry.key === "admin",
      );
    const shown = admin(["platform.members.read"]);
    expect(
      shown && isNavGroup(shown) && shown.items.map((item) => item.href),
    ).toEqual(["/admin", "/admin/feedback"]);
    expect(admin([])).toBeUndefined();
  });

  it("shows the provisioning area to a Platform Operator only", () => {
    const operator = { ...viewer([]), isPlatformOperator: true };
    expect(
      navPages(visibleNav(NAV, operator)).map((item) => item.href),
    ).toContain("/platform");
    expect(
      navPages(visibleNav(NAV, viewer([]))).map((item) => item.href),
    ).not.toContain("/platform");
  });
});

describe("currentPage", () => {
  it.each([
    ["/sales", "/sales"],
    ["/sales/orders", "/sales/orders"],
    ["/sales/orders/PO-123", "/sales/orders"],
    ["/admin", "/admin"],
    ["/admin/workspaces", "/admin/workspaces"],
    ["/", "/"],
    ["/approvals", "/approvals"],
  ])("puts %s on %s", (path, href) => {
    expect(currentPage(NAV_ITEMS, path)?.href).toBe(href);
  });

  it("does not stretch an exact page over the pages under it", () => {
    expect(currentPage(NAV_ITEMS, "/sales/unknown")).toBeUndefined();
    expect(currentPage(NAV_ITEMS, "/nowhere")).toBeUndefined();
  });
});
