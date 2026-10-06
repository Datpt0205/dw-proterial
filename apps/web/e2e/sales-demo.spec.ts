import { execSync } from "node:child_process";
import { randomUUID } from "node:crypto";
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
 * The DW1 demo (Đơn hàng & Báo giá), walked in a browser as the personas do it
 * in front of the customer: spec `.claude/plans/sales/dw1-portal-demo/spec.md`,
 * "Done when". The API suites prove every rule; they prove nothing about a
 * button. This walk presses the buttons, so a control that is missing, wrongly
 * disabled or posting the wrong thing turns it red before a rehearsal does.
 *
 * It is one ordered story on one database: the demo tenants are reset to the
 * start state first (`dw_sales.testing.demo_reset`), then each `test` is one
 * stage, and a stage builds on the one before. Every action is taken through
 * the UI where the UI offers it; the API is used for the refusal status codes,
 * for the price-string checks, and to find a case's id.
 *
 * One deliberate order: An sends M04 back to the customer before processing
 * the rest of the mailbox. "DW xử lý tất cả" takes the mailbox oldest first, so
 * the customer's Rev.1 (M07) would otherwise join M04's case before anyone
 * asked for it; processing M04 first shows the procedure's order (WIV-03-012
 * step 8, then the revision supersedes it in the same case).
 */

// A dev server compiles each route on its first visit, and the API reads the
// attachments on its first call, so the first screenful of a page can take
// longer than the suite's default; so can a database shared with other
// containers on a busy machine.
const expect = baseExpect.configure({ timeout: 60_000 });

const API_URL = process.env.E2E_API_URL ?? "http://127.0.0.1:8000";
const SALES = `${API_URL}/api/v1/sales`;
const REPO_ROOT = path.resolve(__dirname, "../../..");

const AN = "dev|an.nguyen"; // PIC đơn hàng, export control
const DIEU = "dev|dieu.hoang"; // PIC báo giá, other customers' prices
const GIANG = "dev|giang.do"; // Trưởng bộ phận
const KHOA = "dev|khoa.lam"; // duyệt báo giá thay
const HA = "dev|ha.vu"; // Lãnh đạo (xem tổng hợp)
const BINH = "dev|binh.tran"; // purchasing, no Sales
const TAM = "dev|tam.ngo"; // IT, no Sales
const BAO = "dev|bao.pham"; // tenant-beta PIC

/**
 * Prices the mock data holds and the price this walk decides, as the API
 * writes them and as the screen does (decimal comma): none may reach a persona
 * without the price scope. `PRICE_CONTROL` proves the search can find them.
 */
const API_PRICES = ["0.6890", "0.689", "0.7120", "0.712", "0.6980", "0.698"];
const SCREEN_PRICES = ["0,689", "0,712", "0,698"];

// ------------------------------------------------------------- helpers --

interface Persona {
  get: (
    path: string,
    params?: Record<string, string | number>,
  ) => Promise<APIResponse>;
  post: (path: string, data?: unknown) => Promise<APIResponse>;
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
    get: (p, params) => request.get(`${SALES}${p}`, { headers, params }),
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

/** Sign in on /dev-login by pressing that persona's "Sign in". */
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
  const buttons = page.getByRole("button", { name: "Sign in", exact: true });
  await buttons.first().waitFor({ state: "visible" });
  await buttons.nth(index).click();
  await page.waitForURL("**/");
}

/** The case a processed message opened or joined. */
async function caseOf(as: Persona, messageId: string): Promise<string> {
  const inbox = await (await as.get("/inbox")).json();
  const message = inbox.find(
    (m: { message_id: string }) => m.message_id === messageId,
  );
  expect(
    message?.disposition.case_id,
    `${messageId} is on a case`,
  ).toBeTruthy();
  return message.disposition.case_id as string;
}

async function order(as: Persona, caseId: string) {
  const response = await as.get(`/orders/${caseId}`);
  expect(response.status()).toBe(200);
  return response.json();
}

async function quote(as: Persona, caseId: string) {
  const response = await as.get(`/quotes/${caseId}`);
  expect(response.status()).toBe(200);
  return response.json();
}

/** The order's state as the API holds it, polled until it reads `status`. */
async function expectOrderStatus(as: Persona, caseId: string, status: string) {
  await expect.poll(async () => (await order(as, caseId)).status).toBe(status);
}

async function expectQuoteStatus(as: Persona, caseId: string, status: string) {
  await expect.poll(async () => (await quote(as, caseId)).status).toBe(status);
}

/** A modal or drawer by the title it shows. */
function dialog(page: Page, title: string): Locator {
  return page.getByRole("dialog").filter({ hasText: title });
}

/** Open the original from the case header, wait until it is drawn, close it. */
async function openSource(page: Page, button = "Mở bản gốc"): Promise<void> {
  await page.getByRole("button", { name: button, exact: true }).first().click();
  const drawer = dialog(page, "Bản gốc");
  await expect(drawer.getByText("Đã mở lúc")).toBeVisible();
  await expect(drawer.getByText("Không hiển thị được trang này")).toHaveCount(
    0,
  );
  await drawer
    .getByRole("button", { name: "Đóng", exact: true })
    .first()
    .click();
  await expect(drawer).toBeHidden();
}

/** A finding's card on an order: "<label>, dòng n", or the label alone. */
function finding(page: Page, name: string): Locator {
  return page.locator(`[aria-label="${name}"]`);
}

async function decide(
  page: Page,
  name: string,
  choice: "Chấp nhận + lý do" | "Yêu cầu khách sửa",
  reason?: string,
): Promise<void> {
  const card = finding(page, name);
  await card.locator("label").filter({ hasText: choice }).click();
  if (reason) await card.getByLabel("Lý do chấp nhận").fill(reason);
  await card
    .getByRole("button", { name: "Ghi quyết định", exact: true })
    .click();
  await expect(card.getByText("Bỏ quyết định")).toBeVisible();
}

/** Render a file in "Tệp và thư nháp DW1 soạn" if not yet, then download it. */
async function renderAndDownload(page: Page, kind: string): Promise<string> {
  const render = page.getByRole("button", {
    name: `Soạn ${kind}`,
    exact: true,
  });
  const download = page
    .getByRole("button", { name: `Tải ${kind}`, exact: true })
    .first();
  // The list is read again after the case changes: wait for it to offer one.
  await expect(render.or(download)).toBeVisible();
  if (await render.isVisible()) await render.click();
  await expect(download).toBeEnabled();
  const [file] = await Promise.all([
    page.waitForEvent("download"),
    download.click(),
  ]);
  return file.suggestedFilename();
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

/** Process a routed Design reply again from the inbox, as the PIC. */
async function reprocess(page: Page, messageId: string): Promise<void> {
  await page.goto("/sales/inbox");
  const row = page.getByRole("row").filter({ hasText: messageId });
  await row
    .getByRole("button", { name: `DW xử lý lại thư ${messageId}`, exact: true })
    .click();
  await expect(row.getByText("Đã gắn vào hồ sơ")).toBeVisible();
}

/** Decide one line's price in "Quyết định giá" and submit it for approval. */
async function priceAndSubmit(
  page: Page,
  unitPrice: string,
  quoteNo: string,
): Promise<void> {
  await page.getByLabel("Đơn giá dòng 1").fill(unitPrice);
  await page.getByLabel("MOQ dòng 1").fill("3000");
  await page.getByLabel("Lead time dòng 1").fill("45");
  await page.getByLabel("Căn cứ đồng dòng 1").getByText("Theo dải LME").click();
  await page.getByLabel("LME từ (USD/tấn) dòng 1").fill("10500");
  await page.getByLabel("LME đến (USD/tấn) dòng 1").fill("11000");
  await expect(page.getByLabel("Tháng LME làm căn cứ")).toBeVisible();
  await expect(page.getByText("Tháng 09/2026").first()).toBeVisible();
  await page.getByRole("button", { name: "Ghi giá", exact: true }).click();
  await expect(
    page.getByText("Đã định giá", { exact: true }).first(),
  ).toBeVisible();

  await page.getByRole("button", { name: "Trình duyệt", exact: true }).click();
  const submit = dialog(page, "Trình duyệt báo giá");
  await submit.getByLabel("Số báo giá").fill(quoteNo);
  await submit
    .getByRole("button", { name: "Trình duyệt", exact: true })
    .click();
  await expect(submit).toBeHidden();
  await expect(
    page.getByText(`Duyệt báo giá ${quoteNo}`, { exact: true }),
  ).toBeVisible();
}

/**
 * Draft the YCBG, record its Bravo number, mark it sent to Design. Each press
 * waits for the case to move (and the screen to show it) before the next: on
 * a new request both "Soạn YCBG" and "Đã lập YCBG" are offered, and a press
 * made on the version the draft replaced is refused (409).
 */
async function ycbgToDesign(
  page: Page,
  as: Persona,
  caseId: string,
  ycbgNo: string,
): Promise<void> {
  await page.getByRole("button", { name: "Soạn YCBG", exact: true }).click();
  await expectQuoteStatus(as, caseId, "ycbg_drafted");
  await expect(
    page.getByText("Đã soạn YCBG", { exact: true }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Đã lập YCBG", exact: true }).click();
  const record = dialog(page, "Ghi số YCBG Bravo đã cấp");
  await record.getByLabel("Số YCBG trên Bravo").fill(ycbgNo);
  await record
    .getByRole("button", { name: "Ghi số YCBG", exact: true })
    .click();
  await expect(record).toBeHidden();
  await expectQuoteStatus(as, caseId, "ycbg_recorded");
  await expect(page.getByText(`YCBG ${ycbgNo}`, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Gửi Design", exact: true }).click();
  await expectQuoteStatus(as, caseId, "sent_to_design");
  await expect(
    page.getByText("Đang chờ Design. Phản hồi được ghép bằng số YCBG."),
  ).toBeVisible();
}

function leaked(text: string, prices: string[]): string[] {
  return prices.filter((p) =>
    new RegExp(`(?<![\\d.,])${p.replace(/[.,]/g, "\\$&")}(?!\\d)`).test(text),
  );
}

// --------------------------------------------------------------- the walk --

test.describe.configure({ mode: "serial", timeout: 600_000 });

/** Case ids, found as the walk opens them. */
const ids = {} as { m03: string; m04: string; m10: string; m14: string };

test.beforeAll(() => {
  // The demo start state: no Sales case in the demo tenants, an unread
  // mailbox, DW1 running, every persona seeded as the roster says.
  execSync("uv run python -m dw_sales.testing.demo_reset", {
    cwd: REPO_ROOT,
    stdio: "inherit",
    env: process.env,
  });
});

test("1. An sends M04 back to the customer; prepare is refused while a blocking finding is open", async ({
  page,
  request,
}) => {
  const an = await persona(request, AN);
  await signIn(page, request, AN);
  await page.goto("/sales/inbox");
  await expect(
    page.getByRole("heading", { name: "Hộp thư (giả lập)" }),
  ).toBeVisible();
  const row = page.getByRole("row").filter({ hasText: "M04" });
  await row
    .getByRole("button", { name: "DW xử lý thư M04", exact: true })
    .click();
  await expect(row.getByText("Đã tạo hồ sơ")).toBeVisible();
  await row.getByRole("link", { name: "Mở đơn hàng" }).click();
  ids.m04 = await caseOf(an, "M04");
  await page.waitForURL(`**/sales/orders/${ids.m04}`);

  // Refusal: preparation waits on every blocking finding, in words and at the API.
  await expect(
    page.getByText("Còn 2 cờ chưa quyết định (2 chặn)"),
  ).toBeVisible();
  await expectRefused(page, "Chuẩn bị xong", "Còn 2 cờ chưa quyết định.");
  await openSource(page);
  const open = await order(an, ids.m04);
  const refused = await an.post(`/orders/${ids.m04}/prepare`, {
    case_version: open.case_version,
  });
  expect(refused.status()).toBe(409);
  expect((await refused.json()).details.open_findings).toContain(
    "price_mismatch:2",
  );

  await decide(page, "Đơn giá lệch báo giá, dòng 2", "Yêu cầu khách sửa");
  await decide(
    page,
    "Mã chưa có trong convert list, dòng 3",
    "Yêu cầu khách sửa",
  );
  await page
    .getByRole("button", { name: "Gửi yêu cầu khách sửa", exact: true })
    .click();
  const send = dialog(page, "Gửi yêu cầu khách sửa PO");
  await expect(send.getByText("Đơn giá lệch báo giá (dòng 2)")).toBeVisible();
  await expect(
    send.getByText("Mã chưa có trong convert list (dòng 3)"),
  ).toBeVisible();
  await send
    .getByRole("button", { name: "Gửi yêu cầu sửa", exact: true })
    .click();
  await expect(send).toBeHidden();
  await expectOrderStatus(an, ids.m04, "correction_requested");
  await expect(page.getByText("Chờ khách sửa PO").first()).toBeVisible();
  expect(
    await renderAndDownload(page, "Thư yêu cầu khách sửa PO (nháp)"),
  ).toBeTruthy();
});

test("2. An processes the mailbox: every message ends in one disposition, and M07 supersedes M04 in its case", async ({
  page,
  request,
}) => {
  const an = await persona(request, AN);
  await signIn(page, request, AN);
  await page.goto("/sales/inbox");
  await page.getByRole("button", { name: /DW xử lý tất cả \(31\)/ }).click();
  await expect(
    page.getByText(/^32 thư · 0 chưa xử lý · \d+ chuyển Sales/),
  ).toBeVisible({
    timeout: 480_000,
  });
  await expectRefused(
    page,
    "DW xử lý tất cả (0)",
    "Mọi thư đã có hướng xử lý.",
  );
  await expect(
    page.getByRole("button", { name: /^DW xử lý thư / }),
  ).toHaveCount(0);

  const inbox: {
    message_id: string;
    disposition: {
      kind: string;
      reason: string | null;
      owner: string | null;
      case_id: string | null;
    };
  }[] = await (await an.get("/inbox")).json();
  expect(inbox).toHaveLength(32);
  expect(
    inbox.filter((m) => m.disposition.kind === "not_yet_processed"),
  ).toEqual([]);
  // A routed message always has an owner (spec decision 10).
  for (const m of inbox.filter((m) => m.disposition.kind === "routed_to_sales"))
    expect(m.disposition.owner, m.message_id).toBeTruthy();
  const by = Object.fromEntries(
    inbox.map((m) => [m.message_id, m.disposition]),
  );
  expect(by.M11).toMatchObject({
    kind: "routed_to_sales",
    reason: "delivery_change",
  });
  expect(by.M15).toMatchObject({
    kind: "routed_to_sales",
    reason: "customer_unknown",
  });
  expect(by.M16).toMatchObject({
    kind: "routed_to_sales",
    reason: "attachment_unreadable",
  });
  expect(by.M31).toMatchObject({
    kind: "routed_to_sales",
    reason: "complaint",
  });
  // Design replies that came before their YCBG went to Design wait for it.
  for (const reply of ["M25", "M29", "M32"])
    expect(by[reply], reply).toMatchObject({
      kind: "routed_to_sales",
      reason: "design_reply_unmatched",
    });
  // The customer's Rev.1 joined the case An sent back.
  expect(by.M07).toMatchObject({ kind: "attached_to_case", case_id: ids.m04 });

  const m07 = page.getByRole("row").filter({ hasText: "M07" });
  await expect(m07.getByText("Đã gắn vào hồ sơ")).toBeVisible();
  await m07.getByRole("link", { name: "Mở đơn hàng" }).click();
  await page.waitForURL(`**/sales/orders/${ids.m04}`);
  await expect(page.getByText("Rev.1", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Đang xem Rev.1: bản mới nhất của PO này"),
  ).toBeVisible();
  const revised = await order(an, ids.m04);
  expect(revised.status).toBe("in_review");
  expect(
    revised.superseded.map((s: { message_id: string }) => s.message_id),
  ).toEqual(["M04"]);
  await expect(page.getByText("Chờ PIC tự kiểm").first()).toBeVisible();
});

test("3. An takes M03 from the source to the Bravo number; Diệu may not acknowledge NOC/ESF; An may not cross-check his own order", async ({
  page,
  request,
}) => {
  const an = await persona(request, AN);
  const dieu = await persona(request, DIEU);
  ids.m03 = await caseOf(an, "M03");
  let m03 = await order(an, ids.m03);

  // Refusal: a PIC without sales_export_control acknowledging NOC/ESF.
  const noc = await dieu.post(
    `/orders/${ids.m03}/findings/missing_noc_esf:-/disposition`,
    {
      case_version: m03.case_version,
      disposition: "accepted",
      reason: "Đã xem",
    },
  );
  expect(noc.status()).toBe(403);

  await signIn(page, request, AN);
  await page.goto(`/sales/orders/${ids.m03}`);
  await expect(
    page.getByRole("heading", { name: `PO ${m03.po_no}` }),
  ).toBeVisible();
  // The source: the PDF page drawn with the reader's boxes on it.
  await page.getByRole("button", { name: "Mở bản gốc", exact: true }).click();
  const drawer = dialog(page, "Bản gốc");
  await expect(drawer.getByLabel("Trang 1 của bản gốc")).toBeVisible();
  await expect(drawer.locator("span[title^='Dòng 2']").first()).toBeAttached();
  await drawer
    .getByRole("button", { name: "Đóng", exact: true })
    .first()
    .click();

  await decide(
    page,
    "Không có báo giá còn hiệu lực, dòng 2",
    "Chấp nhận + lý do",
    "Khách xác nhận giá theo thư ngày 22/09",
  );
  await decide(
    page,
    "Thiếu NOC/ESF",
    "Chấp nhận + lý do",
    "Đã kiểm tra danh sách cấm, chờ ESF năm nay",
  );
  // Each decision is a new version of the case: its source is opened again.
  await expectRefused(
    page,
    "Chuẩn bị xong",
    "Chưa mở nguồn: mở bản gốc của phiên bản hồ sơ này trước khi quyết định.",
  );
  await openSource(page, "Mở nguồn");
  await page
    .getByRole("button", { name: "Chuẩn bị xong", exact: true })
    .click();
  await expectOrderStatus(an, ids.m03, "prepared");

  const upload = await renderAndDownload(page, "Tệp nhập Bravo (mẫu giả lập)");
  expect(upload).toMatch(/\.xlsx$/);

  await page
    .getByRole("button", { name: "Đã nhập Bravo", exact: true })
    .click();
  const bravo = dialog(page, "Ghi số đơn Bravo");
  await bravo.getByLabel("Số đơn bán hàng trên Bravo").fill("SO26-1001");
  await bravo
    .getByText("Tôi đã đối chiếu các dòng đơn trên Bravo với PO")
    .click();
  await bravo
    .getByRole("button", { name: "Ghi số đơn Bravo", exact: true })
    .click();
  await expect(bravo).toBeHidden();
  await expectOrderStatus(an, ids.m03, "uploaded_to_bravo");
  m03 = await order(an, ids.m03);
  expect(m03.bravo_so_no).toBe("SO26-1001");
  expect(m03.bravo_entry_compared).toBe(true);

  // Refusal: the preparer cross-checks his own order (tách nhiệm).
  await expectRefused(
    page,
    "Kiểm chéo đạt",
    "Bạn đã chuẩn bị đơn này nên không tự kiểm chéo được (tách nhiệm, WIV-03-012 bước 9).",
  );
  const page1 = m03.header_anchors.po_no.page;
  expect(
    (
      await an.get(`/orders/${ids.m03}/source/${m03.attachment_id}`, {
        page: page1,
      })
    ).status(),
  ).toBe(200);
  const own = await an.post(`/orders/${ids.m03}/cross-check`, {
    case_version: m03.case_version,
    decision: "accept",
  });
  expect(own.status()).toBe(409);
  expect((await own.json()).message).toContain("tách nhiệm");

  // Refusal: a file before its state (the confirmation needs `confirmed`).
  const early = await an.post(`/orders/${ids.m03}/artifacts`, {
    case_version: m03.case_version,
    kind: "confirmation_draft",
  });
  expect(early.status()).toBe(409);
});

test("4. Diệu opens the source, then cross-checks An's order", async ({
  page,
  request,
}) => {
  const dieu = await persona(request, DIEU);
  await signIn(page, request, DIEU);
  await page.goto(`/sales/orders/${ids.m03}`);
  // She holds no export-control permission: the NOC/ESF card says who does.
  await expect(
    finding(page, "Thiếu NOC/ESF").getByText(
      "Chỉ PIC kiểm soát xuất khẩu xác nhận cờ này.",
    ),
  ).toBeVisible();
  await expectRefused(page, "Kiểm chéo đạt", "Chưa mở nguồn");
  await openSource(page);
  await page
    .getByRole("button", { name: "Kiểm chéo đạt", exact: true })
    .click();
  const check = dialog(page, "Kiểm chéo đạt");
  await expect(check.getByText("SO26-1001")).toBeVisible();
  await check
    .getByRole("button", { name: "Ghi kiểm chéo đạt", exact: true })
    .click();
  await expect(check).toBeHidden();
  await expectOrderStatus(dieu, ids.m03, "cross_checked");
});

test("5. An confirms M03 with a confirmed date for each line", async ({
  page,
  request,
}) => {
  const an = await persona(request, AN);
  await signIn(page, request, AN);
  await page.goto(`/sales/orders/${ids.m03}`);
  await page
    .getByRole("button", { name: "Đã gửi xác nhận", exact: true })
    .click();
  const drawer = dialog(page, "Xác nhận đơn với khách");
  const m03 = await order(an, ids.m03);
  for (const line of m03.lines as { line_no: number }[]) {
    const input = drawer.getByLabel(`Ngày xác nhận dòng ${line.line_no}`);
    await input.click();
    await input.fill("27/11/2026");
    await input.press("Enter");
  }
  await drawer
    .getByRole("button", { name: "Ghi đã gửi xác nhận", exact: true })
    .click();
  await expect(drawer).toBeHidden();
  await expectOrderStatus(an, ids.m03, "confirmed");
  const confirmed = await order(an, ids.m03);
  expect(
    new Set(
      confirmed.lines.map(
        (l: { confirmed_delivery_date: string }) => l.confirmed_delivery_date,
      ),
    ),
  ).toEqual(new Set(["2026-11-27"]));
  expect(await renderAndDownload(page, "Thư xác nhận PO (nháp)")).toBeTruthy();
});

test("6. Diệu takes M10 from the YCBG to Design, prices it from the evidence and submits it; she may not approve it", async ({
  page,
  request,
}) => {
  const dieu = await persona(request, DIEU);
  ids.m10 = await caseOf(dieu, "M10");
  await signIn(page, request, DIEU);
  await page.goto(`/sales/quotes/${ids.m10}`);
  await openSource(page);
  await ycbgToDesign(page, dieu, ids.m10, "YCBG-2609-030");
  await expectQuoteStatus(dieu, ids.m10, "sent_to_design");

  await reprocess(page, "M25");
  await page.goto(`/sales/quotes/${ids.m10}`);
  await expect(
    page.getByText("YCBG YCBG-2609-030 · trả lời ngày"),
  ).toBeVisible();
  // Other customers' prices reach the quotation PIC (sales_price_evidence).
  await expect(page.getByText("Q26-0104")).toBeVisible();
  await expect(page.getByText("0,712 USD")).toBeVisible();

  await priceAndSubmit(page, "0.6890", "Q26-0301");
  const pending = await quote(dieu, ids.m10);
  expect(pending.status).toBe("pending_approval");
  expect(pending.submission.quote_no).toBe("Q26-0301");

  // Refusal: she lacks sales.quote.approve, whatever approver_boost gives her.
  await expectRefused(
    page,
    "Duyệt báo giá",
    "Bạn không có quyền duyệt báo giá",
  );
  const own = await dieu.post(`/quotes/${ids.m10}/approval`, {
    case_version: pending.case_version,
    decision: "approve",
    document_sha256: pending.submission.document_sha256,
  });
  expect(own.status()).toBe(403);
});

test("6b. An sees other customers' prices for M10 as 'Đã ẩn'", async ({
  page,
  request,
}) => {
  const an = await persona(request, AN);
  const seen = await quote(an, ids.m10);
  expect(seen.evidence[0].other_customers).toEqual({ hidden: true });
  await signIn(page, request, AN);
  await page.goto(`/sales/quotes/${ids.m10}`);
  await expect(
    page.getByRole("heading", { name: "Giá đã báo cho khách khác" }),
  ).toBeVisible();
  await expect(page.getByText("Đã ẩn").first()).toBeVisible();
  await expect(page.getByText("Q26-0104")).toHaveCount(0);
  await expect(page.getByText("0,712 USD")).toHaveCount(0);
});

test("7. Giang approves M10 with the document preview shown; the send draft is refused before, downloadable after", async ({
  page,
  request,
}) => {
  const giang = await persona(request, GIANG);
  const pending = await quote(giang, ids.m10);
  const early = await giang.post(`/quotes/${ids.m10}/artifacts`, {
    case_version: pending.case_version,
    kind: "send_draft",
  });
  expect(early.status()).toBe(409);

  await signIn(page, request, GIANG);
  await page.goto(`/sales/quotes/${ids.m10}`);
  await expect(
    page.getByText("Duyệt báo giá Q26-0301", { exact: true }),
  ).toBeVisible();
  // The preview is rendered on request, from "Tệp và thư nháp DW1 soạn". The
  // approval panel reads the file list on its own and is not told when the
  // other panel renders one, so the page is read again after rendering.
  const render = page.getByRole("button", {
    name: "Soạn Tài liệu báo giá (bản xem trước)",
    exact: true,
  });
  const preview = page.getByRole("button", { name: /Xem bản xem trước \(PDF/ });
  await expect(render.or(preview)).toBeVisible();
  if (await render.isVisible()) {
    await render.click();
    await expect(
      page
        .getByRole("button", {
          name: "Tải Tài liệu báo giá (bản xem trước)",
          exact: true,
        })
        .first(),
    ).toBeVisible();
    await page.reload();
  }
  await preview.click();
  await expect(page.getByLabel("Trang 1 của bản gốc")).toBeVisible();
  await page
    .getByRole("button", { name: "Duyệt báo giá", exact: true })
    .click();
  await expectQuoteStatus(giang, ids.m10, "approved");
  const approved = await quote(giang, ids.m10);
  expect(approved.approval.document_sha256).toBe(
    pending.submission.document_sha256,
  );

  await page.reload();
  expect(await renderAndDownload(page, "Thư gửi báo giá (nháp)")).toBeTruthy();
  expect(
    await renderAndDownload(page, "Tài liệu báo giá (bản đã duyệt)"),
  ).toBeTruthy();
});

test("8. Giang prices M14 and may not approve it; Khoa approves it", async ({
  page,
  request,
}) => {
  const giang = await persona(request, GIANG);
  ids.m14 = await caseOf(giang, "M14");
  await signIn(page, request, GIANG);
  await page.goto(`/sales/quotes/${ids.m14}`);
  await openSource(page);
  // A request forwarded internally: Sales names the customer first.
  await expectRefused(
    page,
    "Soạn YCBG",
    "Còn 1 thông tin của yêu cầu báo giá chưa đủ",
  );
  await page.getByLabel("Mã khách hàng").fill("VLX");
  await page
    .getByRole("button", { name: "Ghi câu trả lời của khách", exact: true })
    .click();
  await expect(page.getByText(/Đã bổ sung.*khách VLX/)).toBeVisible();
  await ycbgToDesign(page, giang, ids.m14, "YCBG-2609-029");

  await reprocess(page, "M29");
  await page.goto(`/sales/quotes/${ids.m14}`);
  await expect(
    page.getByText("YCBG YCBG-2609-029 · trả lời ngày"),
  ).toBeVisible();
  await priceAndSubmit(page, "0.8200", "Q26-0302");

  // Refusal: the pricer is never the approver (tách nhiệm).
  await expectRefused(
    page,
    "Duyệt báo giá",
    "Bạn đã định giá báo giá này nên không tự duyệt được (tách nhiệm, WIV-03-023 bước 9).",
  );
  const pending = await quote(giang, ids.m14);
  const own = await giang.post(`/quotes/${ids.m14}/approval`, {
    case_version: pending.case_version,
    decision: "approve",
    document_sha256: pending.submission.document_sha256,
  });
  expect(own.status()).toBe(409);

  const khoa = await persona(request, KHOA);
  await signIn(page, request, KHOA);
  await page.goto(`/sales/quotes/${ids.m14}`);
  await expect(
    page.getByText("Duyệt báo giá Q26-0302", { exact: true }),
  ).toBeVisible();
  for (const reason of await page.getByLabel("Lý do chấp nhận khi duyệt").all())
    await reason.fill("Đã xem căn cứ giá");
  await page
    .getByRole("button", { name: "Duyệt báo giá", exact: true })
    .click();
  await expectQuoteStatus(khoa, ids.m14, "approved");
  expect((await quote(khoa, ids.m14)).approval.approved_by).not.toBe(
    pending.pricing.decided_by,
  );
});

test("9. Who sees what: Hà the overview only, Bình and Tâm nothing, Bảo none of tenant Alpha", async ({
  page,
  request,
}) => {
  // The search can find a price: the quotation PIC's own view carries them.
  const dieu = await persona(request, DIEU);
  const control = await (await dieu.get(`/quotes/${ids.m10}`)).text();
  expect(leaked(control, API_PRICES).length).toBeGreaterThan(0);

  const caseUrls = [
    "/inbox",
    "/orders",
    "/quotes",
    `/orders/${ids.m03}`,
    `/quotes/${ids.m10}`,
    "/master-data/quotations",
  ];

  // Hà (Lãnh đạo): the overview, with no price in it; every other URL is 403.
  const ha = await persona(request, HA);
  const overview = await ha.get("/overview");
  expect(overview.status()).toBe(200);
  expect(leaked(await overview.text(), API_PRICES)).toEqual([]);
  for (const url of caseUrls)
    expect((await ha.get(url)).status(), url).toBe(403);
  await signIn(page, request, HA);
  await page.goto("/sales/overview");
  await expect(
    page.getByRole("heading", { name: "Tổng quan quy trình" }),
  ).toBeVisible();
  expect(leaked(await page.locator("body").innerText(), SCREEN_PRICES)).toEqual(
    [],
  );
  for (const url of [
    "/sales",
    "/sales/inbox",
    "/sales/orders",
    `/sales/quotes/${ids.m10}`,
  ]) {
    await page.goto(url);
    await expect(page.getByText("Bạn không có quyền mở mục này")).toBeVisible();
    expect(
      leaked(await page.locator("body").innerText(), SCREEN_PRICES),
    ).toEqual([]);
  }

  // Bình (purchasing) and Tâm (IT): no Sales route at all, so no price.
  for (const subject of [BINH, TAM]) {
    const outsider = await persona(request, subject);
    for (const url of ["/overview", ...caseUrls]) {
      const response = await outsider.get(url);
      expect(response.status(), `${subject} ${url}`).toBe(403);
      expect(leaked(await response.text(), API_PRICES)).toEqual([]);
    }
  }
  await signIn(page, request, TAM);
  await page.goto(`/sales/quotes/${ids.m10}`);
  await expect(page.getByText("Bạn không có quyền mở mục này")).toBeVisible();
  expect(leaked(await page.locator("body").innerText(), SCREEN_PRICES)).toEqual(
    [],
  );

  // Bảo (tenant Beta): an empty mailbox, and Alpha's ids are not found.
  const bao = await persona(request, BAO);
  expect(await (await bao.get("/inbox")).json()).toEqual([]);
  expect((await bao.get(`/orders/${ids.m03}`)).status()).toBe(404);
  expect((await bao.get(`/quotes/${ids.m10}`)).status()).toBe(404);
  await signIn(page, request, BAO);
  await page.goto("/sales/inbox");
  await expect(
    page.getByText(
      "Hộp thư giả lập không có thư nào cho không gian làm việc này.",
    ),
  ).toBeVisible();
  await page.goto(`/sales/orders/${ids.m03}`);
  await expect(page.getByText("Không tìm thấy")).toBeVisible();
});

test("10. An pauses DW1 and may not resume it; Giang resumes it with a reason", async ({
  page,
  request,
}) => {
  const an = await persona(request, AN);
  await signIn(page, request, AN);
  await page.goto("/sales/inbox");
  await page.getByRole("button", { name: "Tạm dừng DW1", exact: true }).click();
  const pause = dialog(page, "DW1 ngừng xử lý thư mới");
  await pause.getByLabel("Lý do").fill("Diễn tập: dừng DW1 trước buổi demo");
  await pause
    .getByRole("button", { name: "Tạm dừng DW1", exact: true })
    .click();
  await expect(pause).toBeHidden();
  await expect(
    page.getByText("DW1 đang tạm dừng", { exact: true }),
  ).toBeVisible();
  await expectRefused(
    page,
    "Tiếp tục DW1",
    "Chỉ Trưởng bộ phận Sales cho DW1 chạy lại.",
  );
  const resume = await an.post("/worker/resume", { reason: "An thử chạy lại" });
  expect(resume.status()).toBe(403);

  await signIn(page, request, GIANG);
  await page.goto("/sales/inbox");
  await expect(
    page.getByText("DW1 đang tạm dừng", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Tiếp tục DW1", exact: true }).click();
  const again = dialog(page, "Cho DW1 chạy lại");
  await again.getByLabel("Lý do").fill("Đã kiểm tra xong, cho DW1 chạy lại");
  await again
    .getByRole("button", { name: "Cho DW1 chạy lại", exact: true })
    .click();
  await expect(again).toBeHidden();
  await expect(page.getByText(/^DW1 đang chạy/)).toBeVisible();
  expect((await (await an.get("/overview")).json()).worker.paused).toBe(false);
});
