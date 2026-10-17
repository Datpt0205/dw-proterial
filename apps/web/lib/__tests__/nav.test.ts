import { describe, expect, it } from "vitest";
import { NAV, NAV_ITEMS } from "../nav/registry";
import { isNavGroup, type NavEntry } from "../nav/types";
import {
  barNav,
  currentPage,
  navPages,
  visibleNav,
  type NavViewer,
} from "../nav/visibility";

function viewer(scopes: string[], roles: string[] = ["member"]): NavViewer {
  return {
    isPlatformOperator: false,
    isSupportStaff: false,
    roles,
    hasScope: (scope) => scopes.includes(scope),
  };
}

/** Every label in order, an entry inside a group as "Group › Entry". */
function labels(entries: readonly NavEntry[]): string[] {
  return entries.flatMap((entry) =>
    isNavGroup(entry)
      ? [
          entry.label,
          ...labels(entry.items).map((label) => `${entry.label} › ${label}`),
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
  "/sales/layouts",
  "/sales/rules",
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
  "sales.rules.propose",
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
  return sales ? navPages([sales]).map((item) => item.href) : [];
}

const SALES = NAV.find((entry) => isNavGroup(entry) && entry.key === "sales")!;

describe("the nav registry", () => {
  it("carries the Sales pages as one group", () => {
    expect(navPages([SALES]).map((item) => item.href)).toEqual(SALES_PAGES);
  });

  it("folds the Sales pages into submenus by the work, counts kept on the bar", () => {
    // Sales ticket 39: nine pages overflowed the bar at every desktop width.
    expect(labels([SALES])).toEqual([
      "Sales",
      "Sales › Việc cần làm",
      "Sales › Hộp thư",
      "Sales › Hồ sơ",
      "Sales › Hồ sơ › Đơn hàng",
      "Sales › Hồ sơ › Báo giá",
      "Sales › Hồ sơ › Kiểm chéo & duyệt",
      "Sales › Quản lý",
      "Sales › Quản lý › Mẫu PO",
      "Sales › Quản lý › Quy tắc",
      "Sales › Quản lý › Dữ liệu giả lập",
      "Sales › Quản lý › Tổng quan quy trình",
    ]);
    // A count inside a closed submenu is a count nobody sees.
    const top = isNavGroup(SALES) ? SALES.items : [];
    const counted = navPages([SALES]).filter((page) => page.badgeKey);
    expect(counted.length).toBeGreaterThan(0);
    for (const page of counted) expect(top).toContain(page);
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
        "Sales › Hồ sơ › Đơn hàng",
        "Sales › Hồ sơ › Báo giá",
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
    const scopes = navPages([SALES]).map((item) => item.scope);
    expect(new Set(scopes)).toEqual(
      new Set([
        "sales.case.read",
        "sales.overview.read",
        "sales.rules.propose",
      ]),
    );
  });

  it("shows the rules page only to who may propose a version, as GET /sales/rules does", () => {
    const pages = (scopes: string[]) =>
      navPages(visibleNav(NAV, viewer(scopes))).map((item) => item.href);
    expect(pages(PIC)).toContain("/sales/rules");
    expect(
      pages(PIC.filter((scope) => scope !== "sales.rules.propose")),
    ).not.toContain("/sales/rules");
  });

  it("keeps only the items a group's viewer may see, and drops an empty group", () => {
    const admin = (scopes: string[]) =>
      visibleNav(NAV, viewer(scopes)).find(
        (entry) => isNavGroup(entry) && entry.key === "admin",
      );
    const shown = admin(["platform.members.read"]);
    expect(shown && navPages([shown]).map((item) => item.href)).toEqual([
      "/admin",
      "/admin/feedback",
    ]);
    expect(admin([])).toBeUndefined();
  });

  /** The bar for these scopes: labels, a submenu's pages as "Group › Page". */
  function salesBar(scopes: string[]): string[] {
    return labels(barNav(visibleNav(NAV, viewer(scopes))).entries);
  }

  it("hides a submenu whose pages are all hidden", () => {
    // Overview and rules but no case page: "Quản lý" with two, no "Hồ sơ".
    const bar = barNav(
      visibleNav(NAV, viewer(["sales.overview.read", "sales.rules.propose"])),
    );
    expect(bar.context?.key).toBe("sales");
    expect(labels(bar.entries)).toEqual([
      "Quản lý",
      "Quản lý › Quy tắc",
      "Quản lý › Tổng quan quy trình",
    ]);
  });

  it("shows a submenu while one of its pages is visible", () => {
    // Without sales.case.read the case pages go and "Hồ sơ" with them;
    // without sales.overview.read "Quản lý" keeps its other pages.
    const shown = salesBar(PIC.filter((s) => s !== "sales.overview.read"));
    expect(shown).toEqual(
      expect.arrayContaining([
        "Hồ sơ",
        "Hồ sơ › Đơn hàng",
        "Quản lý",
        "Quản lý › Mẫu PO",
      ]),
    );
    expect(shown).not.toContain("Quản lý › Tổng quan quy trình");
    const noRules = salesBar(PIC.filter((s) => s !== "sales.rules.propose"));
    expect(noRules).toContain("Quản lý");
    expect(noRules).not.toContain("Quản lý › Quy tắc");
  });

  it("draws a submenu left with one page as that page, never a submenu of one", () => {
    // ha.vu sees the overview alone: on the bar, not behind "Quản lý".
    expect(salesBar(PERSONAS["ha.vu (sales_viewer)"]!.scopes)).toEqual([
      "Tổng quan quy trình",
    ]);
  });

  it("keeps a top-level group a group, even with one page left", () => {
    // barNav reads `context` and `administration` from it.
    const shown = visibleNav(NAV, viewer(["platform.workspaces.write"]));
    const admin = shown.find((e) => isNavGroup(e) && e.key === "admin");
    expect(admin && navPages([admin]).map((p) => p.href)).toEqual([
      "/admin/workspaces",
    ]);
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

describe("barNav", () => {
  function bar(persona: string) {
    const { roles, scopes } = PERSONAS[persona]!;
    return barNav(visibleNav(NAV, viewer(scopes, roles)));
  }

  it.each([
    ["an.nguyen (sales_pic)", SALES_PAGES],
    ["giang.do (sales_head)", SALES_PAGES],
    ["ha.vu (sales_viewer)", ["/sales/overview"]],
  ])("is the Sales pages alone for %s", (persona, pages) => {
    const { entries, context } = bar(persona);
    expect(context?.key).toBe("sales");
    expect(navPages(entries).map((page) => page.href)).toEqual(pages);
  });

  it("keeps the platform's nav for someone without a context", () => {
    const { entries, context } = bar("binh.tran (no sales.*)");
    expect(context).toBeNull();
    expect(navPages(entries).map((item) => item.href)).toContain("/approvals");
  });

  it("keeps every entry for someone who administers the tenant", () => {
    const admin = viewer([...PIC, "platform.members.read"], ["org_admin"]);
    const { entries, context } = barNav(visibleNav(NAV, admin));
    expect(context).toBeNull();
    expect(labels(entries)).toEqual(
      expect.arrayContaining(["Sales", "Quản trị", "Trang chủ"]),
    );
  });
});
