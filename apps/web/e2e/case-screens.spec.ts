import { execSync } from "node:child_process";
import path from "node:path";
import {
  expect as baseExpect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";
import { signIn } from "./dev-login";

/**
 * Screenshots of the pages the nav registry does not reach, for the same
 * visual review as `screens.spec.ts`: a case page, the PO-layout onboarding,
 * the quote screening and the rules editor drawer. It asserts only that each
 * page drew its heading; the pictures are for a person to look at.
 *
 * Named `case-screens.spec.ts`, not `screens-cases.spec.ts`: the viewport
 * projects in `playwright.config.ts` match `/screens\.spec\.ts/`, which a file
 * named `screens-cases.spec.ts` does not.
 *
 * Two switches, both off by default:
 * - `DW_SCREENS_SETUP=1` (project `chromium`): resets the demo, has An press
 *   "DW xử lý tất cả" until the mailbox is done, and prepares M01, so the
 *   lists are not empty and a case has history.
 * - `DW_SCREENS=1` (projects `wide-1440`, `phone-320`): writes
 *   `<DW_SCREENS_DIR or ./screens>/<project>/<persona>/case-*.png`.
 */

const expect = baseExpect.configure({ timeout: 60_000 });

const SETUP = process.env.DW_SCREENS_SETUP === "1";
const ENABLED = process.env.DW_SCREENS === "1";
const OUT_DIR = process.env.DW_SCREENS_DIR ?? "screens";
const API_URL = process.env.E2E_API_URL ?? "http://127.0.0.1:8000";
const REPO_ROOT = path.resolve(__dirname, "../../..");
const AN = "dev|an.nguyen";
const PERSONAS = ["dev|an.nguyen", "dev|giang.do"];

interface InboxRow {
  message_id: string;
  attachments?: { attachment_id: string }[];
  disposition: { case_id: string | null };
}

/** The demo tenant's inbox as An reads it through the API. */
async function inbox(request: APIRequestContext): Promise<InboxRow[]> {
  const session = await (
    await request.post(`${API_URL}/api/v1/dev/session`, {
      data: { subject: AN },
    })
  ).json();
  const response = await request.get(`${API_URL}/api/v1/sales/inbox`, {
    headers: {
      Authorization: `Bearer ${session.token}`,
      "X-Tenant-Id": session.tenant_id,
      "X-Workspace-Id": session.workspace_id,
    },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json();
}

function caseOf(rows: InboxRow[], messageId: string): string {
  const id = rows.find((m) => m.message_id === messageId)?.disposition.case_id;
  expect(id, `${messageId} is on a case`).toBeTruthy();
  return id as string;
}

// ------------------------------------------------------------------ setup --

test("setup: reset, An processes the whole mailbox", async ({
  page,
}, testInfo) => {
  test.skip(!SETUP, "DW_SCREENS_SETUP=1 turns the setup on");
  test.skip(testInfo.project.name !== "chromium", "setup runs once");
  test.setTimeout(900_000);
  execSync("uv run python -m dw_sales.testing.demo_reset", {
    cwd: REPO_ROOT,
    stdio: "inherit",
    env: process.env,
  });

  await signIn(page, AN);
  await page.goto("/sales/inbox");
  await page
    .getByRole("button", { name: /DW xử lý tất cả \([1-9]\d*\)/ })
    .click();
  await expect(
    page.getByText(/^\d+ thư · 0 chưa xử lý · \d+ chuyển Sales/),
  ).toBeVisible({ timeout: 720_000 });
  await expect(
    page.getByRole("button", { name: "DW xử lý tất cả (0)", exact: true }),
  ).toBeDisabled();
});

test("setup: An prepares M01 (open the source, Chuẩn bị xong)", async ({
  page,
  request,
}, testInfo) => {
  test.skip(!SETUP, "DW_SCREENS_SETUP=1 turns the setup on");
  test.skip(testInfo.project.name !== "chromium", "setup runs once");
  await signIn(page, AN);
  // M01 is a clean Excel PO: open its source, then "Chuẩn bị xong".
  const m01 = caseOf(await inbox(request), "M01");
  await page.goto(`/sales/orders/${m01}`);
  await page
    .getByRole("button", { name: "Mở bản gốc", exact: true })
    .first()
    .click();
  const drawer = page.getByRole("dialog").filter({ hasText: "Bản gốc" });
  await expect(drawer.getByText("Đã mở lúc")).toBeVisible();
  await drawer
    .getByRole("button", { name: "Đóng", exact: true })
    .first()
    .click();
  await page
    .getByRole("button", { name: "Chuẩn bị xong", exact: true })
    .click();
  await expect(page.getByText("PIC đã tự kiểm").first()).toBeVisible();
});

// ---------------------------------------------------------------- capture --

async function settle(page: Page): Promise<void> {
  // A region still loading is not what a reviewer should see.
  await page
    .waitForLoadState("networkidle", { timeout: 15_000 })
    .catch(() => undefined);
}

for (const subject of PERSONAS) {
  test(`case screens as ${subject}`, async ({ page, request }, testInfo) => {
    test.skip(!ENABLED, "DW_SCREENS=1 turns the screenshot run on");
    test.skip(
      testInfo.project.name === "chromium",
      "captured at the viewport projects",
    );
    test.setTimeout(300_000);
    const persona = subject.replace(/^dev\|/, "").replace(/[^\w.-]/g, "_");
    const shot = (name: string) =>
      page.screenshot({
        path: path.join(
          OUT_DIR,
          testInfo.project.name,
          persona,
          `case-${name}.png`,
        ),
        fullPage: true,
      });

    const rows = await inbox(request);
    const m43 = rows
      .find((m) => m.message_id === "M43")
      ?.attachments?.find(Boolean)?.attachment_id;
    expect(m43, "M43 has an attachment").toBeTruthy();
    // Each page's PageHeader <h1>: an order is "PO <số>", a quote is
    // quoteTitle() ("RFQ <số>" or "Yêu cầu trong thư <ngày>").
    const pages: [string, string, RegExp | string][] = [
      ["order-M01", `/sales/orders/${caseOf(rows, "M01")}`, /^PO /],
      ["order-M03", `/sales/orders/${caseOf(rows, "M03")}`, /^PO /],
      [
        "quote-M10",
        `/sales/quotes/${caseOf(rows, "M10")}`,
        /^(RFQ |Yêu cầu trong thư )/,
      ],
      ["layouts-new", "/sales/layouts/new", "Thiết lập mẫu PO"],
      [
        "layouts-new-M43",
        `/sales/layouts/new?message=M43&attachment=${encodeURIComponent(m43!)}`,
        "Thiết lập mẫu PO",
      ],
      ["quotes-screening", "/sales/quotes/screening", "Rà soát báo giá năm"],
    ];

    await signIn(page, subject);
    for (const [name, href, heading] of pages) {
      await test.step(name, async () => {
        await page.goto(href);
        await expect(
          page.getByRole("heading", { level: 1, name: heading }).first(),
        ).toBeVisible();
        await settle(page);
        await shot(name);
      });
    }

    await test.step("rules-drawer-bravo", async () => {
      await page.goto("/sales/rules");
      const open = page.getByRole("button", {
        name: "Đề xuất phiên bản mới: Mẫu tệp nhập Bravo",
        exact: true,
      });
      await expect(open).toBeVisible();
      await open.click();
      const drawer = page
        .getByRole("dialog")
        .filter({ hasText: "Đề xuất phiên bản mới: Mẫu tệp nhập Bravo" });
      await expect(
        drawer.getByRole("button", { name: "Xem thay đổi", exact: true }),
      ).toBeVisible();
      await settle(page);
      await shot("rules-drawer-bravo");
    });
  });
}
