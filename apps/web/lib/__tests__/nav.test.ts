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
  "/sales/pipeline",
  "/sales/orders",
  "/sales/quotes",
  "/sales/review",
  "/sales/layouts",
  "/sales/rules",
  "/sales/rules/process",
  "/sales/master-data",
  "/sales/export-control",
  "/sales/overview",
  "/sales/activity",
];

// A PIC works to the company's settings (2026-10-28): no rules pages.
const PIC_PAGES = SALES_PAGES.filter(
  (page) => page !== "/sales/rules" && page !== "/sales/rules/process",
);

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
      "sales.rules.propose",
      "sales.rules.approve",
    ],
  },
  "ha.vu (sales_viewer)": {
    roles: ["executive", "sales_viewer"],
    scopes: [...MEMBER, "sales.overview.read"],
  },
  "binh.tran (no sales.*)": { roles: ["member"], scopes: MEMBER },
  // The admin with the set `sales_rules_editor` (2026-10-21, kept for the
  // admin on 2026-10-28): the rules pages and no other Sales page.
  "tam.ngo (org_admin + sales_rules_editor)": {
    roles: ["org_admin"],
    scopes: [
      "directory.read",
      "platform.members.read",
      "platform.members.write",
      "sales.rules.propose",
    ],
  },
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
      "Sales › Hồ sơ › Pipeline hồ sơ",
      "Sales › Hồ sơ › Đơn hàng",
      "Sales › Hồ sơ › Báo giá",
      "Sales › Hồ sơ › Kiểm chéo & duyệt",
      "Sales › Quản lý",
      "Sales › Quản lý › Mẫu PO",
      "Sales › Quản lý › Quy tắc",
      "Sales › Quản lý › Quy trình DW1",
      "Sales › Quản lý › Dữ liệu chủ",
      "Sales › Quản lý › Kiểm soát xuất khẩu",
      "Sales › Quản lý › Tổng quan quy trình",
      "Sales › Quản lý › Hoạt động DW1",
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
    ["an.nguyen (sales_pic)", PIC_PAGES],
    ["dieu.hoang (sales_pic)", PIC_PAGES],
    ["giang.do (sales_head)", SALES_PAGES],
    // The viewer reads aggregates only: the overview and DW1's activity
    // (counts, no case), and no other Sales page.
    ["ha.vu (sales_viewer)", ["/sales/overview", "/sales/activity"]],
    ["binh.tran (no sales.*)", []],
    // Tenant IT: the rules, and the activity of the steps it turns on.
    [
      "tam.ngo (org_admin + sales_rules_editor)",
      ["/sales/rules", "/sales/rules/process", "/sales/activity"],
    ],
  ])("gives %s the Sales pages %j", (persona, pages) => {
    expect(salesPages(persona)).toEqual(pages);
  });

  it("keys every Sales page to a scope the API checks on its reads", () => {
    const scopes = navPages([SALES]).flatMap(
      (item) => item.anyScope ?? [item.scope],
    );
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
    expect(pages([...PIC, "sales.rules.propose"])).toContain("/sales/rules");
    expect(pages(PIC)).not.toContain("/sales/rules");
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
      "Quản lý › Quy trình DW1",
      "Quản lý › Tổng quan quy trình",
      "Quản lý › Hoạt động DW1",
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

  it("shows a viewer holding only sales.rules.propose the rules pages and the activity alone", () => {
    expect(salesBar(["sales.rules.propose"])).toEqual([
      "Quản lý",
      "Quản lý › Quy tắc",
      "Quản lý › Quy trình DW1",
      "Quản lý › Hoạt động DW1",
    ]);
  });

  it("shows the activity page to either of the scopes its API reads with", () => {
    const pages = (scopes: string[]) =>
      navPages(visibleNav(NAV, viewer(scopes))).map((item) => item.href);
    expect(pages(["sales.overview.read"])).toContain("/sales/activity");
    expect(pages(["sales.rules.propose"])).toContain("/sales/activity");
    expect(pages(["sales.case.read"])).not.toContain("/sales/activity");
  });

  it("draws a submenu left with one page as that page, never a submenu of one", () => {
    // Since "Hoạt động DW1" no Sales persona sees one page alone in a
    // submenu, so a context of two pages stands in for one.
    const icon = () => null;
    const nav: NavEntry[] = [
      {
        key: "ctx",
        label: "Ngữ cảnh",
        icon,
        context: { product: "Ngữ cảnh", roleKeyPrefix: "ctx_" },
        items: [
          {
            key: "ctx-manage",
            label: "Quản lý",
            icon,
            items: [
              { href: "/ctx/a", label: "A", hint: "", icon, scope: "ctx.a" },
              { href: "/ctx/b", label: "B", hint: "", icon, scope: "ctx.b" },
            ],
          },
        ],
      },
    ];
    expect(labels(barNav(visibleNav(nav, viewer(["ctx.a"]))).entries)).toEqual([
      "A",
    ]);
    expect(salesBar(PERSONAS["ha.vu (sales_viewer)"]!.scopes)).toEqual([
      "Quản lý",
      "Quản lý › Tổng quan quy trình",
      "Quản lý › Hoạt động DW1",
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
    ["an.nguyen (sales_pic)", PIC_PAGES],
    ["giang.do (sales_head)", SALES_PAGES],
    ["ha.vu (sales_viewer)", ["/sales/overview", "/sales/activity"]],
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

describe("a platform page kept on a context's bar", () => {
  const SALES_HEAD = ["sales.case.read", "approvals.read", "approvals.decide"];
  const SALES_PIC = ["sales.case.read", "approvals.read"];

  it("adds Duyệt to the Sales bar for whoever decides approvals", () => {
    const viewing = viewer(SALES_HEAD);
    expect(labels(barNav(visibleNav(NAV, viewing), viewing).entries)).toContain(
      "Duyệt",
    );
  });

  it("leaves it off for someone who only reads approvals, and off a bar built without the viewer", () => {
    const pic = viewer(SALES_PIC);
    expect(labels(barNav(visibleNav(NAV, pic), pic).entries)).not.toContain(
      "Duyệt",
    );
    const head = viewer(SALES_HEAD);
    expect(labels(barNav(visibleNav(NAV, head)).entries)).not.toContain(
      "Duyệt",
    );
  });
});
