import { execFileSync, execSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import {
  expect as baseExpect,
  test,
  type APIRequestContext,
  type APIResponse,
  type Locator,
  type Page,
} from "@playwright/test";

/**
 * End-user walks over the data a Sales team maintains (master-data imports,
 * the company's rule versions, the Bravo template draft, PO layouts) and the
 * decisions on them (`/approvals`, `/sales/layouts`), clicked as a person
 * clicks them. Black box: the API is used only to set up a precondition a
 * person would have reached by other screens (a rule proposal to reject, a
 * processed message to open a case), never to assert behaviour the screen
 * owns.
 *
 * One ordered story on one database, like `sales-demo.spec.ts`: the demo
 * tenants are reset first (`dw_sales.testing.demo_reset`), then each test is
 * one scenario. Needs the API, the web and a worker (reader sandbox, inbox
 * lane off) already running.
 */

// The worker reads every file in the reader sandbox; give it room.
const expect = baseExpect.configure({ timeout: 30_000 });

const API_URL = process.env.E2E_API_URL ?? "http://127.0.0.1:8000";
const SALES = `${API_URL}/api/v1/sales`;
const REPO_ROOT = path.resolve(__dirname, "../../..");

const AN = "dev|an.nguyen"; // PIC đơn hàng
const GIANG = "dev|giang.do"; // Trưởng bộ phận Sales
const TAM = "dev|tam.ngo"; // IT: proposes rules, nothing else in Sales

// ------------------------------------------------------------- helpers --

interface Persona {
  get: (p: string) => Promise<APIResponse>;
  post: (p: string, data?: unknown) => Promise<APIResponse>;
}

/** A dev session for `subject`, calling `/api/v1/sales/*` as that person. */
async function persona(
  request: APIRequestContext,
  subject: string,
): Promise<Persona> {
  const response = await request.post(`${API_URL}/api/v1/dev/session`, {
    data: { subject },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  const session = await response.json();
  const headers = {
    Authorization: `Bearer ${session.token}`,
    "X-Tenant-Id": session.tenant_id,
    "X-Workspace-Id": session.workspace_id,
  };
  return {
    get: (p) => request.get(`${SALES}${p}`, { headers }),
    post: (p, data = {}) =>
      request.post(`${SALES}${p}`, {
        headers: {
          ...headers,
          "Content-Type": "application/json",
          "Idempotency-Key": randomUUID(),
        },
        data,
      }),
  };
}

let roster: string[] | null = null;

/** Sign in on /dev-login by pressing that persona's "Đăng nhập". */
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

/** Press `button` and hand the file chooser `file`. */
async function chooseFile(page: Page, button: Locator, file: string) {
  const [chooser] = await Promise.all([
    page.waitForEvent("filechooser"),
    button.click(),
  ]);
  await chooser.setFiles(file);
}

/** The visible antd dropdown's option whose text is exactly `text`. */
function option(page: Page, text: string): Locator {
  return page
    .locator(".ant-select-dropdown:not(.ant-select-dropdown-hidden)")
    .locator(".ant-select-item-option")
    .filter({
      hasText: new RegExp(`^${text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`),
    })
    .first();
}

/** An antd Select with search, labelled `label`: type and pick `text`. */
async function pick(page: Page, label: string, text: string) {
  const box = page.getByLabel(label, { exact: true });
  await box.click();
  await box.fill(text);
  await option(page, text).click();
}

/** A pending approval's card on /approvals, by the approval's id. */
function approvalCard(page: Page, approvalId: string): Locator {
  return page
    .locator(".ant-card")
    .filter({ has: page.locator(`a[href="/approvals/${approvalId}"]`) });
}

/** The migrator's URL for the reset, from the environment or the repo's .env. */
function resetEnv(): NodeJS.ProcessEnv {
  const env = { ...process.env };
  if (!env.DW_DATABASE_URL) {
    try {
      for (const line of readFileSync(
        path.join(REPO_ROOT, ".env"),
        "utf8",
      ).split(/\r?\n/)) {
        const match = /^(DW_DATABASE_URL|DW_API_PROFILE)=(.*)$/.exec(line);
        if (match) env[match[1]!] = match[2]!.trim();
      }
    } catch {
      // No .env: the reset says what is missing.
    }
  }
  return env;
}

/** A small fictional Bravo upload template, written by openpyxl. */
function bravoTemplate(file: string) {
  const script = [
    "import sys, openpyxl",
    "wb = openpyxl.Workbook()",
    "ws = wb.active",
    "ws.title = 'Mau'",
    "ws.append(['Số PO', 'Dòng', 'Mã hàng', 'Số lượng', 'Ngày giao'])",
    "ws.append(['PO-E2E-001', 1, 'HW-1001', 100, '2026-11-01'])",
    "ws.append(['PO-E2E-001', 2, 'CB-2001', 250, '2026-11-15'])",
    "wb.save(sys.argv[1])",
  ].join("\n");
  execFileSync("uv", ["run", "python", "-c", script, file], {
    cwd: REPO_ROOT,
    stdio: "inherit",
  });
}

// --------------------------------------------------------------- the walk --

// Run in file order (one worker), but a failed scenario does not skip the
// rest: each one sets up what it needs.
test.describe.configure({ mode: "default", timeout: 300_000 });

test.beforeAll(() => {
  // The demo start state: no Sales case, no Sales approval (and with them no
  // PO layout, rule version or submitted import), an unread mailbox.
  execSync("uv run python -m dw_sales.testing.demo_reset", {
    cwd: REPO_ROOT,
    stdio: "inherit",
    env: resetEnv(),
  });
});

test("1. Master data: a PDF and an oversize file are refused; bad rows are listed; submitted, the import blocks the next; Giang's approval makes it live", async ({
  page,
  request,
}, testInfo) => {
  const an = await persona(request, AN);
  // The convert list in force, so the import changes nothing a later walk
  // reads: only the two bad rows differ.
  const live = (await (await an.get("/master-data/convert-list")).json()) as {
    items: {
      customer_code: string;
      customer_item_code: string;
      prv_code: string;
    }[];
  };
  expect(live.items.length).toBeGreaterThan(0);
  const csv = testInfo.outputPath("quy-doi-ma.csv");
  writeFileSync(
    csv,
    [
      "Mã khách hàng,Mã hàng của khách,Mã PRV",
      ...live.items.map(
        (e) => `${e.customer_code},${e.customer_item_code},${e.prv_code}`,
      ),
      "ZZZ,E2E-BAD-1,HW-1001",
      "VLX,E2E-BAD-2,XX-9999",
    ].join("\n"),
    "utf8",
  );
  const badRows = [live.items.length + 2, live.items.length + 3];
  const pdf = testInfo.outputPath("danh-muc.pdf");
  writeFileSync(pdf, "%PDF-1.4\n% e2e: not a list\n%%EOF\n");
  const big = testInfo.outputPath("qua-lon.csv");
  writeFileSync(big, Buffer.alloc(2 * 1024 * 1024 + 1, "a"));

  await signIn(page, request, AN);
  await page.goto("/sales/master-data?tab=convert-list");
  const panel = page.getByRole("tabpanel");
  const importButton = panel.getByRole("button", { name: "Nhập file" });
  await expect(importButton).toBeEnabled();

  // A PDF: the server refuses it, in words.
  await chooseFile(page, importButton, pdf);
  await expect(
    panel.getByText("chỉ nhận tệp .xlsx, .xls hoặc .csv"),
  ).toBeVisible();

  // Over 2 MB: refused before it is sent.
  await chooseFile(page, importButton, big);
  await expect(
    page.getByText("Tệp lớn hơn 2 MB: tách danh mục hoặc bỏ cột thừa."),
  ).toBeVisible();

  // A CSV with two bad rows: read by the worker, the rejected rows listed.
  await chooseFile(page, importButton, csv);
  await expect(
    panel.getByText(/^Đã đọc, chưa gửi duyệt: quy-doi-ma\.csv/),
  ).toBeVisible({ timeout: 120_000 });
  await expect(
    panel.getByText(
      `${live.items.length} dòng hợp lệ, 2 dòng bị loại. Kiểm tra bản xem trước rồi gửi duyệt.`,
    ),
  ).toBeVisible();
  const rejected = panel.getByRole("region", {
    name: "Dòng bị loại (không áp dụng)",
  });
  await expect(
    rejected.getByText("Dòng bị loại (không áp dụng) (2)"),
  ).toBeVisible();
  const rows = rejected.locator("tbody tr.ant-table-row");
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(0)).toContainText(String(badRows[0]));
  await expect(rows.nth(0)).toContainText(
    "khách hàng ZZZ chưa có trong danh mục khách hàng",
  );
  await expect(rows.nth(1)).toContainText(String(badRows[1]));
  await expect(rows.nth(1)).toContainText(
    "mã XX-9999 chưa có trong danh mục mã hàng",
  );

  // Submitted: the next import waits on the decision, and says so.
  await panel.getByRole("button", { name: "Gửi duyệt", exact: true }).click();
  await expect(panel.getByText(/^Chờ duyệt: quy-doi-ma\.csv/)).toBeVisible();
  await expect(panel.getByRole("button", { name: "Nhập file" })).toBeDisabled();
  await expect(
    panel.getByText(
      "Đang có bản nhập chờ duyệt: chờ quyết định rồi nhập tiếp.",
    ),
  ).toBeVisible();
  const href = await panel
    .getByRole("link", { name: "Mở yêu cầu duyệt" })
    .first()
    .getAttribute("href");
  const approvalId = href!.split("/").pop()!;

  // Giang decides it on /approvals: a comment, then "Duyệt".
  await signIn(page, request, GIANG);
  await page.goto("/approvals");
  const card = approvalCard(page, approvalId);
  await expect(card).toBeVisible();
  await card
    .getByLabel("Nhận xét (bắt buộc)")
    .fill("Đã đối chiếu bảng quy đổi mã (e2e)");
  await card.getByRole("button", { name: "Duyệt", exact: true }).click();
  await expect(card).toBeHidden();

  // The import is the list in force now, by whom and approved by whom.
  await page.goto("/sales/master-data?tab=convert-list");
  await expect(async () => {
    await page.reload();
    await expect(
      page.getByRole("tabpanel").getByText(/^Bản nhập ngày /),
    ).toBeVisible({ timeout: 5_000 });
  }).toPass({ timeout: 90_000 });
  await expect(
    page.getByRole("tabpanel").getByText(/^Bản nhập ngày /),
  ).toHaveText(/bởi Nguyễn Văn An, Đỗ Trường Giang( \(bạn\))? duyệt$/);
  await expect(
    page.getByRole("tabpanel").getByText("Dữ liệu thật", { exact: true }),
  ).toBeVisible();
});

test("2. Rules editor: An changes a KPI target, reads it in the diff, goes back, and discarding asks first; invalid JSON is refused in words", async ({
  page,
  request,
}) => {
  await signIn(page, request, AN);
  await page.goto("/sales/rules");
  await expect(
    page.getByRole("heading", { name: "Quy tắc của công ty" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Đề xuất phiên bản mới: Chỉ tiêu KPI" })
    .click();
  const drawer = page
    .getByRole("dialog")
    .filter({ hasText: "Đề xuất phiên bản mới: Chỉ tiêu KPI" });
  const target = drawer.getByRole("spinbutton", {
    name: "Mục tiêu xác nhận đơn hàng",
  });
  await expect(target).toBeVisible();
  await target.fill("12");
  await target.blur();

  await drawer.getByRole("button", { name: "Xem thay đổi" }).click();
  const changed = drawer
    .getByRole("row")
    .filter({ hasText: "Mục tiêu xác nhận đơn hàng" });
  await expect(changed).toBeVisible();
  await expect(changed).toContainText("Đổi");
  await expect(changed).toContainText("12");
  await expect(changed).toContainText("8");

  await drawer.getByRole("button", { name: "Quay lại sửa" }).click();
  await expect(target).toHaveValue("12");

  // "Hủy" with an edit: asks, naming what is lost.
  await drawer.getByRole("button", { name: "Hủy", exact: true }).click();
  const confirm = page
    .getByRole("dialog")
    .filter({ hasText: "Bỏ tài liệu đang sửa?" });
  await expect(confirm).toBeVisible();
  await expect(
    confirm.getByText("Những thay đổi chưa gửi duyệt sẽ mất."),
  ).toBeVisible();
  await confirm.getByRole("button", { name: "Bỏ thay đổi" }).click();
  await expect(drawer).toBeHidden();

  // The JSON tab: text that is not JSON is refused in words.
  await page
    .getByRole("button", { name: "Đề xuất phiên bản mới: Chỉ tiêu KPI" })
    .click();
  await expect(drawer).toBeVisible();
  await drawer.getByText("JSON nâng cao", { exact: true }).click();
  const json = drawer.getByLabel("Tài liệu (JSON)");
  await expect(json).toBeVisible();
  await json.fill('{ "policy_id": "sales_kpi", ');
  await drawer.getByRole("button", { name: "Xem thay đổi" }).click();
  await expect(
    drawer.getByText(
      "Tài liệu phải là JSON hợp lệ (kiểm tra dấu ngoặc và dấu phẩy).",
    ),
  ).toBeVisible();
  // Still editing: no diff was drawn.
  await expect(drawer.getByRole("button", { name: "Gửi duyệt" })).toHaveCount(
    0,
  );
  await drawer.getByRole("button", { name: "Hủy", exact: true }).click();
  await confirm.getByRole("button", { name: "Bỏ thay đổi" }).click();
  await expect(drawer).toBeHidden();
});

test("3. Tạo từ tệp mẫu: a CSV is refused; a Bravo template with no model opens a draft offering its headers", async ({
  page,
  request,
}, testInfo) => {
  const xlsx = testInfo.outputPath("mau-nhap-bravo.xlsx");
  bravoTemplate(xlsx);
  const csv = testInfo.outputPath("mau-nhap-bravo.csv");
  writeFileSync(csv, "Số PO,Dòng,Mã hàng,Số lượng\n", "utf8");

  await signIn(page, request, AN);
  await page.goto("/sales/rules");
  await page
    .getByRole("button", { name: "Đề xuất phiên bản mới: Mẫu tệp nhập Bravo" })
    .click();
  const drawer = page
    .getByRole("dialog")
    .filter({ hasText: "Đề xuất phiên bản mới: Mẫu tệp nhập Bravo" });
  const fromTemplate = drawer.getByRole("button", { name: "Tạo từ tệp mẫu" });
  await expect(fromTemplate).toBeVisible();

  // Not a workbook: refused, in words.
  await chooseFile(page, fromTemplate, csv);
  await expect(
    drawer.getByText("chỉ nhận tệp mẫu .xlsx hoặc .xls"),
  ).toBeVisible();

  // The template: read by the worker; with no model, nothing is guessed and
  // the template's headers are offered.
  await chooseFile(page, fromTemplate, xlsx);
  await expect(
    drawer.getByText(
      /^(Chưa ánh xạ được bằng mô hình|Gợi ý của DW1 không đạt kiểm tra|Đã đọc xong): mau-nhap-bravo\.xlsx$/,
    ),
  ).toBeVisible({ timeout: 120_000 });
  await expect(
    drawer.getByText(
      "Tiêu đề của mẫu (sheet Mau, hàng 1): Số PO · Dòng · Mã hàng · Số lượng · Ngày giao",
    ),
  ).toBeVisible();
  await expect(
    drawer.getByText(
      "Máy chủ này chưa có mô hình: chọn tiêu đề cho từng cột trong danh sách tiêu đề của mẫu.",
    ),
  ).toBeVisible();
  await expect(drawer.getByLabel("Bắt đầu từ phiên bản")).toBeVisible();
  await expect(
    drawer.getByText(/^Bản nháp từ tệp mau-nhap-bravo\.xlsx/),
  ).toBeVisible();

  // A column's header offers the template's headers to choose from.
  const header = drawer.getByRole("combobox", { name: "Tiêu đề cột" }).first();
  await header.click();
  await header.fill("");
  for (const text of ["Số PO", "Dòng", "Mã hàng", "Số lượng"])
    await expect(option(page, text)).toBeVisible();
  await option(page, "Số PO").click();
  await expect(header).toHaveValue("Số PO");

  await drawer.getByRole("button", { name: "Hủy", exact: true }).click();
  const confirm = page
    .getByRole("dialog")
    .filter({ hasText: "Bỏ tài liệu đang sửa?" });
  await confirm.getByRole("button", { name: "Bỏ thay đổi" }).click();
  await expect(drawer).toBeHidden();
});

test("4. PO layouts: An maps M43's form; Giang's 'Từ chối' needs a 'Nhận xét'", async ({
  page,
  request,
}) => {
  test.setTimeout(300_000);
  await signIn(page, request, AN);
  await page.goto("/sales/inbox?message=M43");
  await page
    .getByRole("button", { name: "DW xử lý thư M43", exact: true })
    .click();
  const setUp = page.getByRole("link", {
    name: "Thiết lập mẫu PO",
    exact: true,
  });
  await expect(async () => {
    await page.reload();
    await expect(setUp.first()).toBeVisible({ timeout: 5_000 });
  }).toPass({ timeout: 180_000 });
  await setUp.first().click();
  await page.waitForURL(/\/sales\/layouts\/new\?message=M43&/);
  await expect(page.getByText("Các ô chữ trên mẫu")).toBeVisible();

  const mapping: [string, string][] = [
    ["Số PO", "Order Number"],
    ["Ngày PO", "Order Date"],
    ["Tiền tệ", "Currency"],
    ["Cột số dòng", "Item"],
    ["Cột mã hàng của khách", "Part Number"],
    ["Cột mô tả", "Part Description"],
    ["Cột số lượng", "Order Qty"],
    ["Cột đơn vị tính", "Unit"],
    ["Cột đơn giá", "Price"],
    ["Cột thành tiền", "Extended"],
    ["Cột ngày giao yêu cầu", "Need By"],
    ["Nhãn tổng cộng", "Order Total"],
  ];
  for (const [label, text] of mapping) await pick(page, label, text);
  await page.getByLabel("Cách viết ngày", { exact: true }).click();
  await option(page, "yyyy-mm-dd").click();

  await page.getByRole("button", { name: "Xem thử", exact: true }).click();
  await expect(
    page.getByText(/^Mọi kiểm tra đạt: đọc được PO NRV-PO-26-0502/),
  ).toBeVisible();
  await page.getByRole("button", { name: "Gửi duyệt", exact: true }).click();
  await expect(page.getByText("Đã gửi mẫu để duyệt.")).toBeVisible();

  await signIn(page, request, GIANG);
  await page.goto("/sales/layouts");
  const row = page
    .getByRole("row")
    .filter({ hasText: "NRV" })
    .filter({ hasText: "Chờ duyệt" });
  await expect(row).toHaveCount(1);
  await row.getByRole("button", { name: "Từ chối", exact: true }).click();
  const modal = page
    .getByRole("dialog")
    .filter({ hasText: "Từ chối mẫu PO của NRV" });
  await expect(modal).toBeVisible();
  // Empty: refused, the field says why.
  await modal.getByRole("button", { name: "Từ chối mẫu" }).click();
  await expect(modal.getByText("Nhận xét là bắt buộc")).toBeVisible();
  await expect(modal).toBeVisible();
  // Filled: recorded.
  await modal.getByLabel("Nhận xét").fill("Gán nhầm cột, lập lại mẫu (e2e)");
  await modal.getByRole("button", { name: "Từ chối mẫu" }).click();
  await expect(modal).toBeHidden();
  await expect(
    page.getByText(/^Đã ghi quyết định từ chối mẫu PO của NRV/),
  ).toBeVisible();
  await expect(async () => {
    await page.reload();
    await expect(
      page
        .getByRole("row")
        .filter({ hasText: "NRV" })
        .filter({ hasText: "Đã từ chối" }),
    ).toHaveCount(1, { timeout: 5_000 });
  }).toPass({ timeout: 90_000 });
});

test("5. /approvals: Giang's 'Từ chối' on a Sales rule version waits for a comment, then rejects it", async ({
  page,
  request,
}) => {
  // Precondition a person reaches on /sales/rules: An proposes a KPI version.
  const an = await persona(request, AN);
  const platform = (await (
    await an.get("/rules/sales_kpi/platform")
  ).json()) as { ref: string; document: Record<string, unknown> }[];
  const base = platform[platform.length - 1]!.document;
  const proposed = await an.post("/rules/sales_kpi/versions", {
    document: {
      ...base,
      policy_version: `1.0.${100 + Math.floor(Math.random() * 800)}`,
      order_confirmation_target_hours: 10,
    },
  });
  expect(proposed.status(), await proposed.text()).toBeLessThan(300);
  const approvalId = (await proposed.json()).approval_id as string;
  expect(approvalId).toBeTruthy();

  await signIn(page, request, GIANG);
  await page.goto("/approvals");
  const card = approvalCard(page, approvalId);
  await expect(card).toBeVisible();
  const reject = card.getByRole("button", { name: "Từ chối", exact: true });
  // A Sales approval requires a comment: without one, nothing to press.
  await expect(card.getByText("Nhận xét (bắt buộc)")).toBeVisible();
  await expect(reject).toBeDisabled();
  await card
    .getByLabel("Nhận xét (bắt buộc)")
    .fill("Mục tiêu 10 giờ chưa thống nhất (e2e)");
  await expect(reject).toBeEnabled();
  await reject.click();
  await expect(card).toBeHidden();
  // The approval's own page reads the decision.
  await page.goto(`/approvals/${approvalId}`);
  await expect(
    page
      .locator("main .ant-tag")
      .filter({ hasText: /^Từ chối$/ })
      .first(),
  ).toBeVisible();
});

test("6. Tâm (tenant IT) sees the rules alone: no price-bearing key, a Bravo proposal opens, case pages are forbidden", async ({
  page,
  request,
}) => {
  // A real case to try: An has DW1 process M03.
  const an = await persona(request, AN);
  expect((await an.post("/inbox/M03/process")).status()).toBeLessThan(300);
  let caseId = "";
  await expect
    .poll(
      async () => {
        const inbox = (await (await an.get("/inbox")).json()) as {
          message_id: string;
          disposition: { case_id: string | null };
        }[];
        caseId =
          inbox.find((m) => m.message_id === "M03")?.disposition.case_id ?? "";
        return caseId;
      },
      { timeout: 120_000 },
    )
    .not.toBe("");

  await signIn(page, request, TAM);
  await page.goto("/sales/rules");
  await expect(
    page.getByRole("heading", { name: "Quy tắc của công ty" }),
  ).toBeVisible();
  await expect(page.getByText("Mẫu tệp nhập Bravo").first()).toBeVisible();
  const body = page.locator("main");
  for (const hidden of [
    "Chính sách giá",
    "Quy tắc báo giá",
    "Quy tắc kiểm tra đơn hàng",
    "sales_pricing",
    "sales_quote_rules",
    "sales_order_rules",
  ])
    await expect(body).not.toContainText(hidden);

  // The menu's Sales group offers "Quy tắc".
  await page
    .getByRole("navigation", { name: "Điều hướng chính" })
    .getByRole("menuitem", { name: "Sales" })
    .hover();
  await expect(
    page.getByRole("menuitem", { name: "Quy tắc" }).first(),
  ).toBeVisible();

  await page
    .getByRole("button", { name: "Đề xuất phiên bản mới: Mẫu tệp nhập Bravo" })
    .click();
  const drawer = page
    .getByRole("dialog")
    .filter({ hasText: "Đề xuất phiên bản mới: Mẫu tệp nhập Bravo" });
  await expect(
    drawer.getByRole("button", { name: "Tạo từ tệp mẫu" }),
  ).toBeVisible();
  await expect(
    drawer.getByRole("button", { name: "Xem thay đổi" }),
  ).toBeVisible();
  await drawer.getByRole("button", { name: "Hủy", exact: true }).click();
  await expect(drawer).toBeHidden();

  for (const url of [
    `/sales/orders/${caseId}`,
    "/sales/inbox",
    "/sales/master-data",
  ]) {
    await page.goto(url);
    await expect(
      page.getByText("Bạn không có quyền xem mục này"),
      url,
    ).toBeVisible();
  }
});
