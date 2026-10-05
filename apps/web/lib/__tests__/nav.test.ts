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
  "/sales/review",
  "/sales/master-data",
  "/sales/overview",
];

/**
 * Each persona's scopes as `/auth/bootstrap` hands them to the session (seed
 * of ticket 11, sales migration 68305ebe4a83): their platform role's scopes
 * plus their Sales role's. Permission sets add no nav item.
 */
const MEMBER = [
  "approvals.read",
  "directory.read",
  "integrations.read",
  "knowledge.read",
  "knowledge.write",
  "memory.read",
  "runs.read",
];
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
const PERSONAS: Record<string, { roles: string[]; scopes: string[] }> = {
  "an.nguyen (sales_pic)": {
    roles: ["member", "sales_pic"],
    scopes: [...MEMBER, ...PIC],
  },
  "dieu.hoang (sales_pic)": {
    roles: ["member", "sales_pic"],
    scopes: [...MEMBER, ...PIC],
  },
  "giang.do (sales_head)": {
    roles: ["director", "sales_head"],
    scopes: [
      ...MEMBER,
      ...PIC,
      "sales.price.other_customers.read",
      "sales.quote.approve",
      "sales.worker.resume",
    ],
  },
  "ha.vu (sales_viewer)": {
    roles: ["executive", "sales_viewer"],
    scopes: [...MEMBER, "sales.overview.read"],
  },
  "binh.tran (no sales.*)": { roles: ["member"], scopes: MEMBER },
};

function salesPages(persona: string): string[] {
  const { roles, scopes } = PERSONAS[persona]!;
  const sales = visibleNav(NAV, viewer(scopes, roles)).find(
    (entry) => isNavGroup(entry) && entry.key === "sales",
  );
  return sales && isNavGroup(sales) ? sales.items.map((item) => item.href) : [];
}

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
  it("shows the Sales group to someone who may read sales cases, and not otherwise", () => {
    expect(labels(visibleNav(NAV, viewer(PIC)))).toEqual(
      expect.arrayContaining([
        "Sales",
        "Sales › Việc cần làm",
        "Sales › Đơn hàng",
        "Sales › Báo giá",
      ]),
    );
    expect(labels(visibleNav(NAV, viewer(["approvals.read"])))).not.toContain(
      "Sales",
    );
  });

  it.each([
    ["an.nguyen (sales_pic)", SALES_PAGES],
    ["dieu.hoang (sales_pic)", SALES_PAGES],
    ["giang.do (sales_head)", SALES_PAGES],
    // The viewer reads aggregates only: the overview, and no other Sales page.
    ["ha.vu (sales_viewer)", ["/sales/overview"]],
    ["binh.tran (no sales.*)", []],
  ])("gives %s the Sales pages %j", (persona, pages) => {
    expect(salesPages(persona)).toEqual(pages);
  });

  it("keys every Sales page to a scope the API checks on its reads", () => {
    const sales = NAV.find(
      (entry) => isNavGroup(entry) && entry.key === "sales",
    );
    const scopes =
      sales && isNavGroup(sales) ? sales.items.map((item) => item.scope) : [];
    expect(new Set(scopes)).toEqual(
      new Set(["sales.case.read", "sales.overview.read"]),
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
