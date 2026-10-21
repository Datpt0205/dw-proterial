import { execSync } from "node:child_process";
import path from "node:path";
import {
  expect as baseExpect,
  test,
  type APIRequestContext,
  type Browser,
  type Locator,
  type Page,
} from "@playwright/test";

/**
 * End-user walks of what happens when people (and DW1) move at once: two
 * people on one quote, the export-control hold on an order, DW1 paused and
 * resumed, and the DW1 bar's progress while the mailbox is processed.
 *
 * Black box through the UI; the API is read only to find a case's id and to
 * check that a refused write did not land. Each test starts from the demo
 * start state (`dw_sales.testing.demo_reset`), so none depends on another.
 * Needs a worker beside the API with the inbox lane off (demo.md section 1).
 */

const expect = baseExpect.configure({ timeout: 60_000 });

const API_URL = process.env.E2E_API_URL ?? "http://127.0.0.1:8000";
const SALES = `${API_URL}/api/v1/sales`;
const REPO_ROOT = path.resolve(__dirname, "../../..");

const AN = "dev|an.nguyen"; // PIC đơn hàng, export control
const DIEU = "dev|dieu.hoang"; // PIC báo giá
const GIANG = "dev|giang.do"; // Trưởng bộ phận

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

/** A second person in their own browser context (own session). */
async function secondPerson(
  browser: Browser,
  request: APIRequestContext,
  subject: string,
): Promise<Page> {
  const context = await browser.newContext({
    locale: "vi-VN",
    timezoneId: "Asia/Ho_Chi_Minh",
  });
  const page = await context.newPage();
  await signIn(page, request, subject);
  return page;
}

/** GET /api/v1/sales/* as `subject` (to find ids and check what landed). */
async function apiGet(
  request: APIRequestContext,
  subject: string,
  p: string,
): Promise<unknown> {
  const session = await (
    await request.post(`${API_URL}/api/v1/dev/session`, { data: { subject } })
  ).json();
  const response = await request.get(`${SALES}${p}`, {
    headers: {
      Authorization: `Bearer ${session.token}`,
      "X-Tenant-Id": session.tenant_id,
      "X-Workspace-Id": session.workspace_id,
    },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json();
}

async function caseOf(
  request: APIRequestContext,
  messageId: string,
): Promise<string> {
  const inbox = (await apiGet(request, AN, "/inbox")) as {
    message_id: string;
    disposition: { case_id: string | null };
  }[];
  const id = inbox.find((m) => m.message_id === messageId)?.disposition.case_id;
  expect(id, `${messageId} is on a case`).toBeTruthy();
  return id!;
}

function dialog(page: Page, title: string): Locator {
  return page.getByRole("dialog").filter({ hasText: title });
}

/**
 * The DW1 bar on top of every Sales page (role=status). Found by its pause /
 * resume button, not by its headline: defect C's fix rewords the headline.
 */
function bar(page: Page): Locator {
  return page
    .getByRole("status")
    .filter({
      has: page.getByRole("button", { name: /^(Tạm dừng|Tiếp tục) DW1$/ }),
    })
    .first();
}

/** Press "DW xử lý" on one message and wait for its outcome. */
async function processMessage(
  page: Page,
  messageId: string,
  outcome: string,
  again = false,
): Promise<void> {
  await page.goto("/sales/inbox");
  const name = again
    ? `DW xử lý lại thư ${messageId}`
    : `DW xử lý thư ${messageId}`;
  await page.getByRole("button", { name, exact: true }).click();
  const row = page
    .getByRole("row")
    .filter({ has: page.getByText(messageId, { exact: true }) });
  await expect(row.getByText(outcome).first()).toBeVisible({
    timeout: 180_000,
  });
}

/** Open the original from the case header, wait until it is drawn, close it. */
async function openSource(page: Page, button = "Mở bản gốc"): Promise<void> {
  await page.getByRole("button", { name: button, exact: true }).first().click();
  const drawer = dialog(page, "Bản gốc");
  await expect(drawer.getByText("Đã mở lúc")).toBeVisible();
  await drawer
    .getByRole("button", { name: "Đóng", exact: true })
    .first()
    .click();
  await expect(drawer).toBeHidden();
}

function finding(page: Page, name: string): Locator {
  return page.locator(`[aria-label="${name}"]`);
}

async function accept(page: Page, name: string, reason: string): Promise<void> {
  const card = finding(page, name);
  await card.locator("label").filter({ hasText: "Chấp nhận + lý do" }).click();
  await card.getByLabel("Lý do chấp nhận").fill(reason);
  await card
    .getByRole("button", { name: "Ghi quyết định", exact: true })
    .click();
  await expect(card.getByText("Bỏ quyết định")).toBeVisible();
}

/** A disabled control with its reason written beside it (GuardedButton). */
async function expectRefused(
  page: Page,
  button: string,
  reason: string,
): Promise<void> {
  await expect(
    page.getByRole("button", { name: button, exact: true }).first(),
  ).toBeDisabled();
  await expect(
    page.getByRole("note").filter({ hasText: reason }).first(),
  ).toBeVisible();
}

/** A disabled control whose reason is in its tooltip only. */
async function expectTooltipReason(
  page: Page,
  button: Locator,
  reason: string,
): Promise<void> {
  await expect(button).toBeDisabled();
  // A disabled button takes no pointer events: antd wraps it; hover the wrapper.
  await button.locator("xpath=..").hover();
  await expect(
    page.getByRole("tooltip").filter({ hasText: reason }),
  ).toBeVisible();
}

async function expectStatus(
  request: APIRequestContext,
  kind: "orders" | "quotes",
  caseId: string,
  status: string,
): Promise<void> {
  await expect
    .poll(
      async () =>
        (
          (await apiGet(request, AN, `/${kind}/${caseId}`)) as {
            status: string;
          }
        ).status,
      { timeout: 60_000 },
    )
    .toBe(status);
}

/**
 * Bring M10 to pricing as Diệu (process it, YCBG to Design, Design's reply
 * M25), then Diệu and Giang, each in their own browser, price it at once:
 * Diệu records 0.6890 first, Giang then records 0.7400 on the version Diệu
 * replaced. Returns Giang's page and the conflict notice it shows.
 */
async function pricingConflict(
  page: Page,
  request: APIRequestContext,
  browser: Browser,
): Promise<{ m10: string; giang: Page; conflict: Locator }> {
  await signIn(page, request, DIEU);
  await processMessage(page, "M10", "Đã tạo hồ sơ");
  const m10 = await caseOf(request, "M10");
  await page.goto(`/sales/quotes/${m10}`);
  // M10's source is not opened: no quote step below requires it.
  await page.getByRole("button", { name: "Soạn YCBG", exact: true }).click();
  await expectStatus(request, "quotes", m10, "ycbg_drafted");
  // The page has settled the draft step (its toast follows the step's own
  // dialog reset): a dialog opened before that was closed under the test once.
  await expect(page.getByText("DW1 đã soạn YCBG").first()).toBeVisible();
  await page.getByRole("button", { name: "Đã lập YCBG", exact: true }).click();
  const record = dialog(page, "Ghi số YCBG Bravo đã cấp");
  await record.getByLabel("Số YCBG trên Bravo").fill("YCBG-2609-030");
  await record
    .getByRole("button", { name: "Ghi số YCBG", exact: true })
    .click();
  await expectStatus(request, "quotes", m10, "ycbg_recorded");
  await expect(
    page.getByRole("button", { name: "Gửi Design", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Gửi Design", exact: true }).click();
  await expectStatus(request, "quotes", m10, "sent_to_design");
  await processMessage(page, "M25", "Đã gắn vào hồ sơ");

  // Both open the quote, each in their own browser.
  const giang = await secondPerson(browser, request, GIANG);
  await page.goto(`/sales/quotes/${m10}`);
  await giang.goto(`/sales/quotes/${m10}`);
  for (const p of [page, giang])
    await expect(p.getByLabel("Đơn giá dòng 1")).toBeVisible();

  const fill = async (p: Page, price: string) => {
    await p.getByLabel("Đơn giá dòng 1").fill(price);
    await p.getByLabel("MOQ dòng 1").fill("3000");
    await p.getByLabel("Lead time dòng 1").fill("45");
  };
  await fill(page, "0.6890");
  await fill(giang, "0.7400");

  // Diệu records first.
  await page.getByRole("button", { name: "Ghi giá", exact: true }).click();
  await expect(
    page.getByText("Đã định giá", { exact: true }).first(),
  ).toBeVisible();

  // Giang, on the version Diệu just replaced, records his.
  await giang.getByRole("button", { name: /^Ghi giá/ }).click();
  // Expected (ui-quality §4 "conflict"): "someone changed this", Giang's
  // typed value kept, Diệu's price not silently overwritten.
  const conflict = giang
    .getByRole("alert")
    .or(giang.locator(".ant-alert-warning"))
    .filter({ hasText: /thay đổi|phiên bản|người khác|Chưa làm được/i })
    .first();
  await expect(conflict).toBeVisible({ timeout: 20_000 });
  return { m10, giang, conflict };
}

// ----------------------------------------------------------- the walks --

test.describe.configure({ timeout: 900_000 });

test.beforeEach(() => {
  execSync("uv run python -m dw_sales.testing.demo_reset", {
    cwd: REPO_ROOT,
    stdio: "inherit",
    env: process.env,
  });
});

test("1. Diệu and Giang price the same quote at once: the second sees the conflict, typed values kept", async ({
  page,
  request,
  browser,
}) => {
  const { m10, giang, conflict } = await pricingConflict(
    page,
    request,
    browser,
  );
  await expect(giang.getByLabel("Đơn giá dòng 1")).toHaveValue(/0[.,]74/);
  const after = (await apiGet(request, DIEU, `/quotes/${m10}`)) as {
    pricing: { lines: { unit_price: string }[]; decided_by: string } | null;
  };
  expect(after.pricing?.lines[0]?.unit_price).toMatch(/^0\.689/);
  // The alert names that someone else changed the case (not only "refused").
  await expect(conflict).toContainText(/thay đổi|người khác|phiên bản mới/i);
  // Showing Diệu's saved price beside Giang's is known defect E, its own test.
  await giang.screenshot({
    path: test.info().outputPath("giang-conflict.png"),
    fullPage: true,
  });
  await giang.context().close();
});

test("2. Export-control hold on M03: held and confirm refused until An accepts NOC/ESF", async ({
  page,
  request,
}) => {
  await signIn(page, request, AN);
  await processMessage(page, "M03", "Đã tạo hồ sơ");
  const m03 = await caseOf(request, "M03");
  const po = (
    (await apiGet(request, AN, `/orders/${m03}`)) as { po_no: string }
  ).po_no;

  await page.goto(`/sales/orders/${m03}`);
  const held = page.getByText(
    "Đơn đang bị giữ: chờ PIC kiểm soát xuất khẩu xác nhận NOC/ESF.",
  );
  await expect(held).toBeVisible();

  // The pipeline card carries the blocking flag.
  await page.goto("/sales/pipeline");
  const card = page
    .locator(".ant-card")
    .filter({ has: page.getByRole("link", { name: `PO ${po}`, exact: true }) });
  await expect(card.getByText(/\d+ cờ chặn/)).toBeVisible();

  // An prepares without accepting NOC/ESF (it holds only the confirmation).
  await page.goto(`/sales/orders/${m03}`);
  await accept(
    page,
    "Không có báo giá còn hiệu lực, dòng 2",
    "Khách xác nhận giá theo thư ngày 22/09",
  );
  await expect(held).toBeVisible();
  await openSource(page, "Mở nguồn");
  await page
    .getByRole("button", { name: "Chuẩn bị xong", exact: true })
    .click();
  await expectStatus(request, "orders", m03, "prepared");
  await page
    .getByRole("button", { name: "Đã nhập Bravo", exact: true })
    .click();
  const bravo = dialog(page, "Ghi số đơn Bravo");
  await bravo.getByLabel("Số đơn bán hàng trên Bravo").fill("SO26-2001");
  await bravo
    .getByText("Tôi đã đối chiếu các dòng đơn trên Bravo với PO")
    .click();
  await bravo
    .getByRole("button", { name: "Ghi số đơn Bravo", exact: true })
    .click();
  await expect(bravo).toBeHidden();
  await expectStatus(request, "orders", m03, "uploaded_to_bravo");
  await expect(held).toBeVisible();

  // Diệu cross-checks.
  await signIn(page, request, DIEU);
  await page.goto(`/sales/orders/${m03}`);
  await openSource(page);
  await page
    .getByRole("button", { name: "Kiểm chéo đạt", exact: true })
    .click();
  const check = dialog(page, "Kiểm chéo đạt");
  await check
    .getByLabel("Ghi chú kiểm chéo")
    .fill("Đã đối chiếu các dòng trên Bravo với PO");
  await check
    .getByRole("button", { name: "Ghi kiểm chéo đạt", exact: true })
    .click();
  await expect(check).toBeHidden();
  await expectStatus(request, "orders", m03, "cross_checked");

  // At the confirm step: still held, confirm refused with the reason.
  await signIn(page, request, AN);
  await page.goto(`/sales/orders/${m03}`);
  await expect(held).toBeVisible();
  await expectRefused(
    page,
    "Đã gửi xác nhận",
    '"Thiếu NOC/ESF" chưa được PIC kiểm soát xuất khẩu xác nhận.',
  );

  // An, holder of export control, accepts the finding with a reason.
  await accept(
    page,
    "Thiếu NOC/ESF",
    "Đã kiểm tra danh sách cấm, chờ ESF năm nay",
  );
  await expect(held).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Đã gửi xác nhận", exact: true }),
  ).toBeEnabled();
  expect(
    ((await apiGet(request, AN, `/orders/${m03}`)) as { status: string })
      .status,
  ).toBe("cross_checked");

  // And the pipeline card no longer carries a blocking flag.
  await page.goto("/sales/pipeline");
  await expect(card.getByText(`PO ${po}`)).toBeVisible();
  await expect(card.getByText(/\d+ cờ chặn/)).toHaveCount(0);
});

test("3. An pauses DW1 with a reason; the inbox refuses DW xử lý; Giang resumes", async ({
  page,
  request,
  browser,
}) => {
  await signIn(page, request, AN);
  await page.goto("/sales/inbox");
  await expect(bar(page)).toBeVisible();
  await page.getByRole("button", { name: "Tạm dừng DW1", exact: true }).click();
  const pause = dialog(page, "DW1 ngừng xử lý thư mới");
  await pause.getByLabel("Lý do").fill("Kiểm tra cấu hình máy quét");
  await pause
    .getByRole("button", { name: "Tạm dừng DW1", exact: true })
    .click();
  await expect(pause).toBeHidden();

  const paused = page
    .getByRole("status")
    .filter({ hasText: "DW1 đang tạm dừng" })
    .first();
  await expect(paused).toBeVisible();
  await expect(paused).toContainText("bởi Nguyễn Văn An");
  await expect(paused).toContainText("Lý do: Kiểm tra cấu hình máy quét");

  // "DW xử lý" is refused with the paused reason, per message and for all.
  const reason =
    "DW1 đang tạm dừng: chỉ Trưởng bộ phận Sales cho DW1 chạy lại.";
  await expectTooltipReason(
    page,
    page.getByRole("button", { name: "DW xử lý thư M01", exact: true }),
    reason,
  );
  await expectRefused(
    page,
    (await page
      .getByRole("button", { name: /^DW xử lý tất cả/ })
      .textContent())!.trim(),
    reason,
  );
  // An may not resume.
  await expectTooltipReason(
    page,
    page.getByRole("button", { name: "Tiếp tục DW1", exact: true }),
    "Chỉ Trưởng bộ phận Sales cho DW1 chạy lại.",
  );

  // Giang resumes, in his own browser.
  const giang = await secondPerson(browser, request, GIANG);
  await giang.goto("/sales/inbox");
  await giang
    .getByRole("button", { name: "Tiếp tục DW1", exact: true })
    .click();
  const again = dialog(giang, "Cho DW1 chạy lại");
  await again.getByLabel("Lý do").fill("Máy quét đã chạy lại");
  await again
    .getByRole("button", { name: "Cho DW1 chạy lại", exact: true })
    .click();
  await expect(again).toBeHidden();
  await expect(bar(giang)).toBeVisible();
  await expect(bar(giang)).not.toContainText("đang tạm dừng");
  await expect(bar(giang)).not.toContainText("đang chạy");
  await expect(
    giang.getByRole("button", { name: "DW xử lý thư M01", exact: true }),
  ).toBeEnabled();

  // An's open page learns it on reload.
  await page.reload();
  await expect(bar(page)).not.toContainText("đang tạm dừng");
  await expect(
    page.getByRole("button", { name: "DW xử lý thư M01", exact: true }),
  ).toBeEnabled();
  await giang.context().close();
});

test("4. The DW1 bar follows 'DW xử lý tất cả' to the end of the mailbox", async ({
  page,
  request,
}) => {
  test.setTimeout(900_000);
  await signIn(page, request, AN);
  await page.goto("/sales/inbox");
  const status = bar(page);
  await expect(status).toContainText(/đã xử lý 0\/\d+ thư/);
  // The headline at 0 processed is known defect C, its own test.
  const total = Number(
    /đã xử lý 0\/(\d+) thư/.exec((await status.textContent()) ?? "")![1],
  );

  await page.getByRole("button", { name: /^DW xử lý tất cả \(\d+\)/ }).click();
  // The inbox itself shows the work queued...
  await expect(
    page.getByText(/^\d+ thư · \d+ chưa xử lý \(\d+ DW1 đang xử lý\)/),
  ).toBeVisible({ timeout: 30_000 });
  // The bar following the press without a reload is known defect D, its own
  // test. Reload (what a user would do) to follow the run.
  await page.reload();
  await expect(status).toContainText(/DW1 (đang đọc|sắp đọc \d+ thư)/);

  // The count rises.
  const done = async () =>
    Number(
      new RegExp(`đã xử lý (\\d+)/${total} thư`).exec(
        (await status.textContent()) ?? "",
      )?.[1] ?? "-1",
    );
  await expect.poll(done, { timeout: 300_000 }).toBeGreaterThan(0);
  const first = await done();
  await expect.poll(done, { timeout: 300_000 }).toBeGreaterThan(first);

  // It ends with every message processed. The long wait is on the count, the
  // real end condition: the headline alone can claim "hết thư" early (defect C).
  await expect(status).toContainText(`đã xử lý ${total}/${total} thư`, {
    timeout: 600_000,
  });
  // Only then: DW1 says it is waiting for new mail.
  await expect(status).toContainText("DW1 đã xử lý hết thư, đang chờ thư mới");
});

// ------------------------------------------------------- known defects --
// Each asserts the correct behaviour and is marked test.fail: it reports as
// an expected failure until the defect is fixed, then as an unexpected pass.

test("C. Right after a reset the DW1 bar does not claim every message is processed at 0 processed", async ({
  page,
  request,
}) => {
  test.fail(
    true,
    "known defect C: at 0/45 after a reset the bar says 'DW1 đã xử lý hết thư, đang chờ thư mới' (sales-frame.tsx headline())",
  );
  await signIn(page, request, AN);
  await page.goto("/sales/inbox");
  const status = bar(page);
  await expect(status).toContainText(/đã xử lý 0\/\d+ thư/);
  await expect(status).not.toContainText("DW1 đã xử lý hết thư", {
    timeout: 10_000,
  });
});

test("D. The DW1 bar follows 'DW xử lý tất cả' without a reload", async ({
  page,
  request,
}) => {
  test.fail(
    true,
    "known defect D: after 'DW xử lý tất cả' the bar does not refresh until reload (useWorkerProgress polls only once its own fetch saw work)",
  );
  await signIn(page, request, AN);
  await page.goto("/sales/inbox");
  const status = bar(page);
  await expect(status).toContainText(/đã xử lý 0\/\d+ thư/);
  await page.getByRole("button", { name: /^DW xử lý tất cả \(\d+\)/ }).click();
  try {
    // The press landed: the inbox shows the work queued.
    await expect(
      page.getByText(/^\d+ thư · \d+ chưa xử lý \(\d+ DW1 đang xử lý\)/),
    ).toBeVisible({ timeout: 30_000 });
    await expect(status).toContainText(/DW1 (đang đọc|sắp đọc \d+ thư)/, {
      timeout: 30_000,
    });
  } finally {
    // Do not leave the mailbox running into the next test's reset: pause DW1
    // (queued jobs then settle as "paused") and wait until none is left. A
    // cleanup failure is logged, never thrown: under test.fail it would read
    // as the expected failure and hide the day defect D is fixed.
    await settleMailbox(page, request).catch((error: unknown) =>
      console.warn(`D cleanup did not settle the mailbox: ${String(error)}`),
    );
  }
});

async function settleMailbox(page: Page, request: APIRequestContext) {
  await page.getByRole("button", { name: "Tạm dừng DW1", exact: true }).click();
  const pause = dialog(page, "DW1 ngừng xử lý thư mới");
  await pause.getByLabel("Lý do").fill("Dừng sau kiểm thử lỗi D");
  await pause
    .getByRole("button", { name: "Tạm dừng DW1", exact: true })
    .click();
  await expect(pause).toBeHidden();
  await expect
    .poll(
      async () =>
        (
          (await apiGet(request, AN, "/inbox")) as {
            processing?: { status: string } | null;
          }[]
        ).filter(
          (m) =>
            m.processing?.status === "queued" ||
            m.processing?.status === "running",
        ).length,
      { timeout: 300_000, intervals: [5_000] },
    )
    .toBe(0);
}

test("E. On a pricing conflict the second person is shown the price the first one saved", async ({
  page,
  request,
  browser,
}) => {
  test.fail(
    true,
    "known defect E: the conflict notice says the case changed but not Diệu's saved 0,689 (_lib/errors.tsx ActionError for conflict)",
  );
  const { giang, conflict } = await pricingConflict(page, request, browser);
  try {
    // ui-quality §4 "conflict": both values, Diệu's beside Giang's typed one.
    await expect(conflict).toContainText(/0,689/, { timeout: 5_000 });
  } finally {
    await giang.context().close();
  }
});
