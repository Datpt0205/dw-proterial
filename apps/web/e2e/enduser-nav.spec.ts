import { execSync } from "node:child_process";
import path from "node:path";
import {
  expect as baseExpect,
  test,
  type APIRequestContext,
  type Locator,
  type Page,
} from "@playwright/test";

/**
 * End-user navigation checks, black box through the UI: the pipeline home and
 * the orders list keep their view in the URL (Back restores it), a case's
 * "Hành trình hồ sơ", what a viewer without case access sees on direct URLs,
 * a 320 px phone, a reload mid-form, a keyboard-only finding decision, and
 * the offline state on an order.
 *
 * One serial file on the shared demo database: the demo tenants are reset
 * first (`dw_sales.testing.demo_reset`, as sales-demo.spec.ts does), then An
 * has DW1 process the five messages the scenarios use. The API is used only
 * to find a case's id and to read a case's state after a reload.
 */

const expect = baseExpect.configure({ timeout: 60_000 });

const API_URL = process.env.E2E_API_URL ?? "http://127.0.0.1:8000";
const SALES = `${API_URL}/api/v1/sales`;
const REPO_ROOT = path.resolve(__dirname, "../../..");

const AN = "dev|an.nguyen";
const DIEU = "dev|dieu.hoang";
const HA = "dev|ha.vu";

/** Prices as the screen writes them (decimal comma), from the mock data. */
const SCREEN_PRICES = ["0,689", "0,712", "0,698"];
const OFFLINE_REASON =
  "Đang mất kết nối mạng: thao tác này mở lại khi có mạng.";
const FORBIDDEN = "Bạn không có quyền xem mục này";

// ------------------------------------------------------------- helpers --

let roster: string[] | null = null;

async function signIn(
  page: Page,
  request: APIRequestContext,
  subject: string,
): Promise<void> {
  roster ??= (
    (await (await request.get(`${API_URL}/api/v1/dev/demo-users`)).json()) as {
      subject: string;
    }[]
  ).map((u) => u.subject);
  const index = roster.indexOf(subject);
  expect(index, `${subject} is on the demo roster`).toBeGreaterThanOrEqual(0);
  await page.goto("/dev-login");
  const buttons = page.getByRole("button", { name: "Đăng nhập", exact: true });
  await buttons.first().waitFor({ state: "visible" });
  await buttons.nth(index).click();
  await page.waitForURL("**/");
}

/** GET /api/v1/sales/* as `subject` (read-only: ids and states). */
async function salesGet(
  request: APIRequestContext,
  subject: string,
  p: string,
) {
  const response = await request.post(`${API_URL}/api/v1/dev/session`, {
    data: { subject },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  const s = await response.json();
  const got = await request.get(`${SALES}${p}`, {
    headers: {
      Authorization: `Bearer ${s.token}`,
      "X-Tenant-Id": s.tenant_id,
      "X-Workspace-Id": s.workspace_id,
    },
  });
  expect(got.status(), p).toBe(200);
  return got.json();
}

async function caseOf(
  request: APIRequestContext,
  messageId: string,
): Promise<string> {
  const inbox = await salesGet(request, AN, "/inbox");
  const message = inbox.find(
    (m: { message_id: string }) => m.message_id === messageId,
  );
  expect(
    message?.disposition.case_id,
    `${messageId} is on a case`,
  ).toBeTruthy();
  return message.disposition.case_id as string;
}

function inboxRow(page: Page, messageId: string): Locator {
  return page
    .getByRole("row")
    .filter({ has: page.getByText(messageId, { exact: true }) });
}

/** Open the original from the case header, wait until drawn, close it. */
async function openSource(page: Page): Promise<void> {
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
  await expect(drawer).toBeHidden();
}

function leaked(text: string): string[] {
  return SCREEN_PRICES.filter((p) =>
    new RegExp(`(?<![\\d.,])${p.replace(/[.,]/g, "\\$&")}(?!\\d)`).test(text),
  );
}

async function noHorizontalScroll(page: Page): Promise<void> {
  const { scroll, client } = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(
    scroll,
    `scrollWidth ${scroll} vs clientWidth ${client}`,
  ).toBeLessThanOrEqual(client + 1);
}

function historyCard(page: Page): Locator {
  return page.locator(".ant-card").filter({
    has: page.getByText("Hành trình hồ sơ", { exact: true }),
  });
}

/** Accept a finding with a reason (mouse), and wait until it is recorded. */
async function decide(page: Page, name: string, reason: string) {
  const card = page.locator(`[aria-label="${name}"]`);
  await card.locator("label").filter({ hasText: "Chấp nhận + lý do" }).click();
  await card.getByLabel("Lý do chấp nhận").fill(reason);
  await card
    .getByRole("button", { name: "Ghi quyết định", exact: true })
    .click();
  await expect(card.getByText("Bỏ quyết định")).toBeVisible();
}

/**
 * Every status tile and move label of a process canvas lies inside it, and
 * none under its controls or its minimap.
 */
async function expectLaneInside(canvas: Locator): Promise<void> {
  await expect(canvas).toBeVisible();
  await expect
    .poll(() =>
      canvas.evaluate((frame) => {
        const outer = frame.getBoundingClientRect();
        const drawn = [
          ...frame.querySelectorAll(".react-flow__node, [data-move]"),
        ];
        if (!drawn.some((e) => e.matches(".react-flow__node")))
          return ["no card drawn"];
        const panels = [
          ...frame.querySelectorAll(
            ".react-flow__controls, .react-flow__minimap",
          ),
        ].map((p) => p.getBoundingClientRect());
        if (panels.length !== 2) return ["no controls or minimap"];
        return drawn
          .filter((element) => {
            const box = element.getBoundingClientRect();
            return (
              box.top < outer.top - 1 ||
              box.bottom > outer.bottom + 1 ||
              box.left < outer.left - 1 ||
              box.right > outer.right + 1 ||
              panels.some(
                (p) =>
                  box.left < p.right &&
                  p.left < box.right &&
                  box.top < p.bottom &&
                  p.top < box.bottom,
              )
            );
          })
          .map((element) => (element.textContent ?? "").slice(0, 40));
      }),
    )
    .toEqual([]);
}

/** An orders-list row by the PO it shows (its link is named by customer). */
function orderRow(page: Page, po: string): Locator {
  return page.getByRole("row").filter({ hasText: po });
}

/** The pipeline card link of a case, by its reference. */
function card(page: Page, text: string): Locator {
  return page.getByRole("link", { name: text, exact: true });
}

// --------------------------------------------------------------- setup --

test.describe.configure({ mode: "serial", timeout: 600_000 });

const ids = {} as {
  m01: string;
  m03: string;
  m04: string;
  m10: string;
  m14: string;
};

test.beforeAll(() => {
  execSync("uv run python -m dw_sales.testing.demo_reset", {
    cwd: REPO_ROOT,
    stdio: "inherit",
    env: process.env,
  });
});

test("0. setup: An has DW1 process M01, M03, M04, M10 and M14 from the inbox", async ({
  page,
  request,
}) => {
  await signIn(page, request, AN);
  await page.goto("/sales/inbox");
  const messages = ["M01", "M03", "M04", "M10", "M14"];
  for (const m of messages)
    await page
      .getByRole("button", { name: `DW xử lý thư ${m}`, exact: true })
      .click();
  for (const m of messages)
    await expect(inboxRow(page, m).getByText("Đã tạo hồ sơ")).toBeVisible({
      timeout: 300_000,
    });
  ids.m01 = await caseOf(request, "M01");
  ids.m03 = await caseOf(request, "M03");
  ids.m04 = await caseOf(request, "M04");
  ids.m10 = await caseOf(request, "M10");
  ids.m14 = await caseOf(request, "M14");
});

// ----------------------------------------------------------- scenarios --

async function pipelineFilterAndBack(page: Page): Promise<void> {
  // Home sends someone who works Sales to their work list (2026-10-26).
  await page.goto("/");
  await page.waitForURL(/\/sales$/);
  await page.goto("/sales/pipeline");
  // One lane at a time, orders first; the quotes behind their switch.
  await expect(page.getByRole("region", { name: "Đơn hàng" })).toBeVisible();
  await expect(card(page, "PO NRV-PO-26-0457")).toBeVisible();
  await page.getByText(/^Báo giá \(\d+\)$/).click();
  await page.waitForURL(/[?&]lane=quote/);
  await expect(page.getByRole("region", { name: "Báo giá" })).toBeVisible();
  // Everything, mine or not: Diệu's KMH request is on the board.
  await expect(card(page, "RFQ KMH-RFQ-260930-02")).toBeVisible();
  await page.getByText(/^Đơn hàng \(\d+\)$/).click();
  await expect(card(page, "PO NRV-PO-26-0457")).toBeVisible();

  await page.getByText(/^Việc của tôi \(\d+\)$/).click();
  await page.waitForURL(/[?&]tab=mine/);
  await expect(card(page, "PO NRV-PO-26-0457")).toBeVisible();

  const search = page.getByLabel("Tìm theo số PO, RFQ hoặc khách");
  await search.fill("VLX");
  await search.press("Enter");
  await page.waitForURL(/[?&]q=VLX/);
  await expect(card(page, "PO NRV-PO-26-0457")).toHaveCount(0);
  const vlx = card(page, "PO VLX-PO-2609-0118");
  await expect(vlx).toBeVisible();

  const before = page.url();
  await vlx.click();
  await page.waitForURL(`**/sales/orders/${ids.m01}`);
  await expect(
    page.getByRole("heading", { name: "PO VLX-PO-2609-0118" }),
  ).toBeVisible();

  await page.goBack();
  await page.waitForURL(before);
  await expect(search).toHaveValue("VLX");
  await expect(card(page, "PO VLX-PO-2609-0118")).toBeVisible();
  await expect(card(page, "PO NRV-PO-26-0457")).toHaveCount(0);
}

test("1. Home pipeline as An: lanes, Việc của tôi + search filter cards, a card opens its case, Back restores the view", async ({
  page,
  request,
}) => {
  await signIn(page, request, AN);
  await pipelineFilterAndBack(page);
});

test("3. Case history: An prepares M03 and its Hành trình hồ sơ lists the statuses in order with who did what; fresh M04 shows its first events", async ({
  page,
  request,
}) => {
  await signIn(page, request, AN);

  // A fresh case: DW1's reading is its first event.
  await page.goto(`/sales/orders/${ids.m04}`);
  const fresh = historyCard(page);
  await expect(fresh.getByText("DW1 đọc và kiểm tra PO")).toBeVisible();
  await expect(
    fresh
      .locator(".ant-timeline-item")
      .filter({ hasText: "DW1 đọc và kiểm tra PO" }),
  ).toContainText("· DW1");
  await expect(fresh.getByLabel("Các trạng thái hồ sơ đã qua")).toContainText(
    "Chờ PIC tự kiểm",
  );

  // M03 (a text PDF): decide both findings, open the source, prepare.
  await page.goto(`/sales/orders/${ids.m03}`);
  await decide(
    page,
    "Không có báo giá còn hiệu lực, dòng 2",
    "Khách xác nhận giá theo thư ngày 22/09",
  );
  await decide(
    page,
    "Thiếu NOC/ESF",
    "Đã kiểm tra danh sách cấm, chờ ESF năm nay",
  );
  await openSource(page);
  await page
    .getByRole("button", { name: "Chuẩn bị xong", exact: true })
    .click();
  await expect(page.getByText("PIC đã tự kiểm").first()).toBeVisible();

  const history = historyCard(page);
  const steps = history.getByLabel("Các trạng thái hồ sơ đã qua");
  await expect(steps).toContainText("PIC đã tự kiểm");
  const titles = await steps.locator(".ant-steps-item-title").allInnerTexts();
  const review = titles.indexOf("Chờ PIC tự kiểm");
  const prepared = titles.indexOf("PIC đã tự kiểm");
  expect(review, `steps ${titles.join(" > ")}`).toBeGreaterThanOrEqual(0);
  expect(prepared, `steps ${titles.join(" > ")}`).toBe(titles.length - 1);
  expect(review).toBeLessThan(prepared);

  // Who did what: DW1 read it, An decided the findings and prepared it.
  const item = (text: string) =>
    history.locator(".ant-timeline-item").filter({ hasText: text });
  await expect(item("DW1 đọc và kiểm tra PO")).toContainText("· DW1");
  await expect(item("Quyết định một cờ")).toHaveCount(2);
  await expect(item("Quyết định một cờ").first()).toContainText(
    "Nguyễn Văn An",
  );
  await expect(item("Tự kiểm xong")).toContainText("Nguyễn Văn An");
});

test("2. Orders list: a status filter survives opening a case and Back", async ({
  page,
  request,
}) => {
  await signIn(page, request, AN);
  await page.goto("/sales/orders");
  await expect(page.getByRole("heading", { name: "Đơn hàng" })).toBeVisible();
  await expect(orderRow(page, "PO BRN-PO-2609-031")).toBeVisible();

  const filter = page.getByLabel("Lọc theo trạng thái");
  await filter.click();
  await page
    .locator(".ant-select-dropdown")
    .getByText("Chờ PIC tự kiểm", { exact: true })
    .click();
  await page.keyboard.press("Escape");
  await page.waitForURL(/[?&]status=in_review/);
  // M03 was prepared in scenario 3; M01/M04 wait on An's self-check.
  await expect(orderRow(page, "PO BRN-PO-2609-031")).toHaveCount(0);
  const m04 = orderRow(page, "PO NRV-PO-26-0457");
  await expect(m04).toBeVisible();

  const before = page.url();
  await m04.getByRole("link").first().click();
  await page.waitForURL(`**/sales/orders/${ids.m04}`);
  await page.goBack();
  await page.waitForURL(before);
  await expect(
    page.getByRole("button", { name: "Bỏ lọc trạng thái Chờ PIC tự kiểm" }),
  ).toBeVisible();
  await expect(orderRow(page, "PO NRV-PO-26-0457")).toBeVisible();
  await expect(orderRow(page, "PO BRN-PO-2609-031")).toHaveCount(0);
});

test("4. Hà (viewer) opens forbidden Sales URLs directly: forbidden state, no price; the overview works", async ({
  page,
  request,
}) => {
  await signIn(page, request, HA);
  for (const url of [
    "/sales/rules",
    "/sales/master-data",
    "/sales/layouts",
    "/sales/pipeline",
    "/sales/review",
    "/sales/orders",
  ]) {
    await page.goto(url);
    await expect(page.getByText(FORBIDDEN), url).toBeVisible();
    expect(leaked(await page.locator("body").innerText()), url).toEqual([]);
  }
  await page.goto("/sales/overview");
  await expect(
    page.getByRole("heading", { name: "Tổng quan quy trình" }),
  ).toBeVisible();
  await expect(page.getByText(FORBIDDEN)).toHaveCount(0);
  expect(leaked(await page.locator("body").innerText())).toEqual([]);
});

test.describe("5. Phone width 320 px", () => {
  test.use({ viewport: { width: 320, height: 640 }, hasTouch: true });

  test("5a. the home pipeline filters and Back without horizontal page scroll", async ({
    page,
    request,
  }) => {
    await signIn(page, request, AN);
    await page.goto("/sales/pipeline");
    await expect(page.getByRole("region", { name: "Đơn hàng" })).toBeVisible();
    await noHorizontalScroll(page);
    await pipelineFilterAndBack(page);
    await noHorizontalScroll(page);
  });

  test("5b. an order page: no horizontal page scroll, the next step reachable", async ({
    page,
    request,
  }) => {
    await signIn(page, request, AN);
    await page.goto(`/sales/orders/${ids.m01}`);
    await expect(
      page.getByRole("heading", { name: "PO VLX-PO-2609-0118" }),
    ).toBeVisible();
    await noHorizontalScroll(page);
    const source = page
      .getByRole("button", { name: "Mở bản gốc", exact: true })
      .first();
    await source.scrollIntoViewIfNeeded();
    await expect(source).toBeInViewport();
    const close = page.getByRole("button", { name: "Đóng hồ sơ", exact: true });
    await close.scrollIntoViewIfNeeded();
    await expect(close).toBeInViewport();
    await expect(close).toBeEnabled();
    await noHorizontalScroll(page);
  });
});

test("6. Reload mid-flow as Diệu: a half-typed YCBG number and a half-typed price are not saved", async ({
  page,
  request,
}) => {
  test.setTimeout(600_000);
  await signIn(page, request, DIEU);
  await page.goto(`/sales/quotes/${ids.m10}`);
  await page.getByRole("button", { name: "Soạn YCBG", exact: true }).click();
  await expect
    .poll(
      async () => (await salesGet(request, DIEU, `/quotes/${ids.m10}`)).status,
    )
    .toBe("ycbg_drafted");
  await expect(
    page.getByText("Đã soạn YCBG", { exact: true }).first(),
  ).toBeVisible();

  // The dialog: type the number, reload before pressing "Ghi số YCBG".
  await page.getByRole("button", { name: "Đã lập YCBG", exact: true }).click();
  const record = page
    .getByRole("dialog")
    .filter({ hasText: "Ghi số YCBG Bravo đã cấp" });
  await record.getByLabel("Số YCBG trên Bravo").fill("YCBG-2609-030");
  await page.reload();
  await expect(
    page.getByText("Đã soạn YCBG", { exact: true }).first(),
  ).toBeVisible();
  await expect(record).toHaveCount(0);
  await expect(
    page.getByText("YCBG YCBG-2609-030", { exact: true }),
  ).toHaveCount(0);
  expect((await salesGet(request, DIEU, `/quotes/${ids.m10}`)).status).toBe(
    "ycbg_drafted",
  );

  // Finish the step for real, send to Design, and let DW1 match M25's reply.
  await page.getByRole("button", { name: "Đã lập YCBG", exact: true }).click();
  await record.getByLabel("Số YCBG trên Bravo").fill("YCBG-2609-030");
  await record
    .getByRole("button", { name: "Ghi số YCBG", exact: true })
    .click();
  await expect(record).toBeHidden();
  await expect(
    page.getByText("YCBG YCBG-2609-030", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Gửi Design", exact: true }).click();
  await expect
    .poll(
      async () => (await salesGet(request, DIEU, `/quotes/${ids.m10}`)).status,
    )
    .toBe("sent_to_design");
  await page.goto("/sales/inbox");
  await page
    .getByRole("button", { name: "DW xử lý thư M25", exact: true })
    .click();
  await expect(inboxRow(page, "M25").getByText("Đã gắn vào hồ sơ")).toBeVisible(
    {
      timeout: 300_000,
    },
  );

  // The pricing form: type a price, reload before pressing "Ghi giá".
  await page.goto(`/sales/quotes/${ids.m10}`);
  const price = page.getByLabel("Đơn giá dòng 1");
  await price.fill("0.6890");
  await page.getByLabel("MOQ dòng 1").fill("3000");
  await page.reload();
  await expect(page.getByLabel("Đơn giá dòng 1")).toBeVisible();
  await expect(page.getByLabel("Đơn giá dòng 1")).not.toHaveValue(/0[.,]689/);
  await expect(
    page.getByRole("button", { name: "Ghi giá", exact: true }),
  ).toBeVisible();
  const after = await salesGet(request, DIEU, `/quotes/${ids.m10}`);
  expect(after.status).toBe("design_replied");
  expect(after.pricing ?? null).toBeNull();
});

test("7. Keyboard only: An records a finding decision with Tab/Space/Enter, focus visible", async ({
  page,
  request,
}) => {
  await signIn(page, request, AN);
  await page.goto(`/sales/orders/${ids.m04}`);
  const finding = page.locator('[aria-label="Đơn giá lệch báo giá, dòng 2"]');
  await expect(finding).toBeVisible();

  // Start from the card's first control, then keyboard only.
  await finding.getByRole("button").first().focus();
  const accept = finding.getByRole("radio", { name: "Chấp nhận + lý do" });
  for (
    let i = 0;
    i < 6 && !(await accept.evaluate((e) => e === document.activeElement));
    i++
  )
    await page.keyboard.press("Tab");
  await expect(accept).toBeFocused();
  const radioRing = await accept.evaluate((e) => {
    const wrapper = e.closest(".ant-radio-button-wrapper") ?? e;
    const s = getComputedStyle(wrapper);
    return {
      outline: s.outlineStyle,
      width: s.outlineWidth,
      shadow: s.boxShadow,
    };
  });
  expect
    .soft(
      radioRing.outline !== "none" || radioRing.shadow !== "none",
      `radio focus ring ${JSON.stringify(radioRing)}`,
    )
    .toBeTruthy();
  await page.keyboard.press("Space");
  await expect(accept).toBeChecked();

  const reason = finding.getByLabel("Lý do chấp nhận");
  await page.keyboard.press("Tab");
  await expect(reason).toBeFocused();
  await page.keyboard.type("Khách xác nhận giá qua điện thoại");
  await page.keyboard.press("Tab");
  const submit = finding.getByRole("button", {
    name: "Ghi quyết định",
    exact: true,
  });
  await expect(submit).toBeFocused();
  const ring = await submit.evaluate((e) => {
    const s = getComputedStyle(e);
    return {
      visible: e.matches(":focus-visible"),
      outline: s.outlineStyle,
      shadow: s.boxShadow,
    };
  });
  expect(ring.visible).toBe(true);
  expect(
    ring.outline !== "none" || ring.shadow !== "none",
    `button focus ring ${JSON.stringify(ring)}`,
  ).toBeTruthy();
  await page.keyboard.press("Enter");
  await expect(finding.getByText("Bỏ quyết định")).toBeVisible();
  await expect(finding).toContainText("Khách xác nhận giá qua điện thoại");
});

test("8. Offline on an order page: mutating buttons disabled with the offline reason; back online they return", async ({
  page,
  context,
  request,
}) => {
  await signIn(page, request, AN);
  await page.goto(`/sales/orders/${ids.m04}`);
  const close = page.getByRole("button", { name: "Đóng hồ sơ", exact: true });
  await expect(close).toBeEnabled();
  const before = await salesGet(request, AN, `/orders/${ids.m04}`);

  // A finding decision half-made while online.
  const finding = page.locator(
    '[aria-label="Mã chưa có trong convert list, dòng 3"]',
  );
  await finding
    .locator("label")
    .filter({ hasText: "Yêu cầu khách sửa" })
    .click();

  await context.setOffline(true);
  await expect(
    page.getByText(
      /^Mất kết nối mạng\. Các thao tác thay đổi dữ liệu tạm khóa/,
    ),
  ).toBeVisible();
  await expect(close).toBeDisabled();
  await close.hover({ force: true });
  await expect(
    page.getByRole("tooltip").filter({ hasText: OFFLINE_REASON }),
  ).toBeVisible();

  // "Ghi quyết định" is refused in words while offline, and nothing is saved.
  await finding
    .getByRole("button", { name: "Ghi quyết định", exact: true })
    .click();
  await expect(finding.getByText(OFFLINE_REASON)).toBeVisible();
  await expect(finding.getByText("Bỏ quyết định")).toHaveCount(0);

  await context.setOffline(false);
  await expect(
    page.getByText(
      /^Mất kết nối mạng\. Các thao tác thay đổi dữ liệu tạm khóa/,
    ),
  ).toHaveCount(0);
  await expect(close).toBeEnabled();
  const after = await salesGet(request, AN, `/orders/${ids.m04}`);
  expect(after.case_version).toBe(before.case_version);
});

// With a healthy reader the sheet opens. This does not reach defect A (a 500
// carries no CORS headers, so the UI says "Mất kết nối mạng"): nothing here
// makes the source answer 500.
test("9. The Excel source of an order opens: the sheet is drawn, never 'Mất kết nối mạng'", async ({
  page,
  request,
}) => {
  await signIn(page, request, AN);
  await page.goto(`/sales/orders/${ids.m01}`);
  await page
    .getByRole("button", { name: "Mở bản gốc", exact: true })
    .first()
    .click();
  const drawer = page.getByRole("dialog").filter({ hasText: "Bản gốc" });
  await expect(
    drawer
      .getByText("Đã mở lúc")
      .or(drawer.getByRole("button", { name: "Thử lại" }))
      .first(),
  ).toBeVisible();
  await page.screenshot({
    path: test.info().outputPath("source-drawer.png"),
  });
  await expect(drawer.getByText("Mất kết nối mạng")).toHaveCount(0);
  await expect(drawer.getByText("Đã mở lúc")).toBeVisible({ timeout: 5_000 });
});

// Slices 2 and 3 (2026-10-23): the React Flow map and DW1's activity, under
// the page's real Content-Security-Policy (React Flow writes style attributes
// and ships its own stylesheet; `lib/csp.ts` allows inline styles, never
// inline scripts), and at a 320 px phone.
test("10. Quy trình DW1 draws on its canvas and Hoạt động DW1 opens, with no CSP violation; Hà reads the activity, no price", async ({
  page,
  request,
}) => {
  const violations: string[] = [];
  const errors: string[] = [];
  page.on("console", (message) => {
    if (/Content Security Policy|Refused to/i.test(message.text()))
      violations.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  await signIn(page, request, AN);
  const response = await page.goto("/sales/rules/process");
  expect(response?.headers()["content-security-policy"] ?? "").toMatch(
    /style-src [^;]*'unsafe-inline'/,
  );
  const canvas = page.getByRole("application", {
    name: "Sơ đồ quy trình Đơn hàng",
  });
  await expect(canvas).toBeVisible();
  await expect(canvas.getByText("DW1 đọc và kiểm tra")).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("process-map.png") });
  // A tile's details open on keyboard focus, not only on hover.
  const review = canvas.getByRole("link", { name: /^Chờ PIC tự kiểm/ });
  await review.focus();
  await expect(page.getByRole("tooltip")).toContainText(
    "Đến lượt: Sales quyết định",
  );
  await page.keyboard.press("Escape");
  await expect(page.getByRole("tooltip")).toBeHidden();
  await review.click();
  await expect(page).toHaveURL(/node=order\.in_review/);
  await page.goBack();
  await expect(page).not.toHaveURL(/node=/);
  // The row opens from its start and pans; "Xem cả quy trình" brings every
  // tile and label inside the frame, none under its controls or minimap.
  const fit = (lane: Locator) =>
    lane.getByRole("button", { name: "Xem cả quy trình" }).click();
  await fit(canvas);
  await expectLaneInside(canvas);
  // The ways back and the exits: drawn while the switch is on, kept in the
  // URL, and gone again when it is off.
  const back = page
    .getByRole("tabpanel")
    .getByRole("switch", { name: /Hiện đường quay lại/ });
  const wayBack = canvas.locator('[data-move="in_review->checked"]');
  await expect(wayBack).toHaveCount(0);
  await back.click();
  await expect(page).toHaveURL(/back=1/);
  await expect(wayBack).toBeVisible();
  await fit(canvas);
  await expectLaneInside(canvas);
  await back.click();
  await expect(page).not.toHaveURL(/back=1/);
  await expect(wayBack).toHaveCount(0);
  await page.getByRole("tab", { name: "Báo giá", exact: true }).click();
  const quotes = page.getByRole("application", {
    name: "Sơ đồ quy trình Báo giá",
  });
  await expect(quotes).toBeVisible();
  await fit(quotes);
  await expectLaneInside(quotes);

  await page.goto("/sales/activity?lane=order");
  await expect(
    page.getByRole("heading", { level: 1, name: "Hoạt động DW1" }),
  ).toBeVisible();
  // The summary has answered once its as-of time prints. The mails tests 1-9
  // process are read by code, no model step among them, so the page may
  // rightly draw its empty state instead of the table.
  await expect(page.getByText(/số liệu lúc/)).toBeVisible();
  await expect(
    page
      .getByRole("table")
      .first()
      .or(page.getByText(/^DW1 chưa xử lý mục nào ở bước có mô hình/)),
  ).toBeVisible();
  expect(violations).toEqual([]);
  expect(errors).toEqual([]);

  await signIn(page, request, HA);
  await page.goto("/sales/activity");
  await expect(
    page.getByRole("heading", { level: 1, name: "Hoạt động DW1" }),
  ).toBeVisible();
  await expect(page.getByText(FORBIDDEN)).toHaveCount(0);
  expect(leaked(await page.locator("body").innerText())).toEqual([]);
});

test.describe("11. Phone width 320 px, slices 2 and 3", () => {
  test.use({ viewport: { width: 320, height: 640 }, hasTouch: true });

  test("11a. the process page is a list, the activity page fits", async ({
    page,
    request,
  }) => {
    await signIn(page, request, AN);
    await page.goto("/sales/rules/process");
    await expect(
      page.getByRole("link", { name: /^Chờ PIC tự kiểm/ }),
    ).toBeVisible();
    await expect(page.getByRole("application")).toHaveCount(0);
    await noHorizontalScroll(page);
    await page.goto("/sales/activity");
    await expect(
      page.getByRole("heading", { level: 1, name: "Hoạt động DW1" }),
    ).toBeVisible();
    await noHorizontalScroll(page);
  });
});
