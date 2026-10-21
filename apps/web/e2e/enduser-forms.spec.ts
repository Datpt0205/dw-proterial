import { execSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
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
 * Forms and dialogs, pressed the way an end user presses them: empty and
 * invalid input, double clicks, "Hủy", and the close / decline / return /
 * reassign steps. Black box through the UI; the API is read only to check
 * that the state changed exactly once (or not at all).
 *
 * One ordered story on one database, like `sales-demo.spec.ts`: the demo
 * tenants are reset first (`dw_sales.testing.demo_reset`), then each test
 * builds on the one before. Messages used:
 *   M01 (VLX, An)  processed by a double click, prepared by a double click,
 *                  then the Bravo dialog is fed empty and invalid numbers;
 *   M08 (VLX, An)  M01's PO sent again: cancelled close, then closed as "PO trùng";
 *   M09 (QRL, Diệu) cancelled decline, then declined with a reason;
 *   M10 (KMH, Diệu) priced, "Trình duyệt" fed an empty number, submitted,
 *                  returned by Giang, priced again by Diệu;
 *   M21 (VLX, An)  reassigned to Diệu by Giang.
 * Needs the worker beside the API (inbox lane off), as the demo walk does.
 */

const expect = baseExpect.configure({ timeout: 60_000 });

const API_URL = process.env.E2E_API_URL ?? "http://127.0.0.1:8000";
const SALES = `${API_URL}/api/v1/sales`;
const REPO_ROOT = path.resolve(__dirname, "../../..");

const AN = "dev|an.nguyen";
const DIEU = "dev|dieu.hoang";
const GIANG = "dev|giang.do";

// ------------------------------------------------------------- helpers --

interface Persona {
  get: (p: string) => Promise<APIResponse>;
  post: (p: string, data?: unknown) => Promise<APIResponse>;
}

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

interface Disposition {
  kind: string;
  case_id: string | null;
}

async function dispositionOf(as: Persona, id: string): Promise<Disposition> {
  const inbox: { message_id: string; disposition: Disposition }[] = await (
    await as.get("/inbox")
  ).json();
  const m = inbox.find((x) => x.message_id === id);
  expect(m, `${id} is in the mailbox`).toBeTruthy();
  return m!.disposition;
}

/** Setup only: queue a message as `as` and wait for the worker to finish it. */
async function processViaApi(as: Persona, id: string): Promise<string> {
  const queued = await as.post(`/inbox/${id}/process`);
  expect(queued.status(), await queued.text()).toBeLessThan(300);
  await expect
    .poll(async () => (await dispositionOf(as, id)).kind, { timeout: 240_000 })
    .not.toBe("not_yet_processed");
  const d = await dispositionOf(as, id);
  expect(d.case_id, `${id} opened or joined a case`).toBeTruthy();
  return d.case_id!;
}

async function getCase(as: Persona, kind: "orders" | "quotes", id: string) {
  const r = await as.get(`/${kind}/${id}`);
  expect(r.status()).toBe(200);
  return r.json();
}

async function history(
  as: Persona,
  kind: "orders" | "quotes",
  id: string,
): Promise<{ action: string }[]> {
  const r = await as.get(`/${kind}/${id}/history`);
  expect(r.status()).toBe(200);
  return r.json();
}

function dialog(page: Page, title: string): Locator {
  return page.getByRole("dialog").filter({ hasText: title });
}

/** Open the source (header "Mở bản gốc", or "Mở nguồn" for a new
 * version) and close the drawer again. */
async function openSource(page: Page, name = "Mở bản gốc"): Promise<void> {
  await page.getByRole("button", { name, exact: true }).first().click();
  const drawer = dialog(page, "Bản gốc");
  await expect(drawer.getByText("Đã mở lúc")).toBeVisible();
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

/**
 * Every antd message toast the page shows, in order, each counted once,
 * however long it stays on screen.
 */
async function recordToasts(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const w = window as unknown as { __toasts: string[] };
    w.__toasts = [];
    const seen = new WeakSet<Element>();
    new MutationObserver(() => {
      document.querySelectorAll(".ant-message-notice").forEach((n) => {
        if (seen.has(n)) return;
        seen.add(n);
        w.__toasts.push(n.textContent ?? "");
      });
    }).observe(document, { childList: true, subtree: true });
  });
}

async function toasts(page: Page, text: string): Promise<number> {
  const all: string[] = await page.evaluate(
    () => (window as unknown as { __toasts: string[] }).__toasts ?? [],
  );
  return all.filter((t) => t.includes(text)).length;
}

/** Count the POSTs the page sends whose URL contains `fragment`. */
function countPosts(page: Page, fragment: string): () => number {
  let n = 0;
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().includes(fragment)) n += 1;
  });
  return () => n;
}

function button(scope: Page | Locator, name: string): Locator {
  return scope.getByRole("button", { name, exact: true });
}

// --------------------------------------------------------------- the walk --

// Not serial: one failing scenario must not skip the rest. With one worker
// the tests still run in file order; after a failure Playwright starts a new
// worker and runs beforeAll again, so the reset happens once per run (a
// marker keyed by the runner's pid) and the case ids are read back from the
// mailbox.
test.describe.configure({ timeout: 600_000 });

const ids = {} as {
  m01: string;
  m03: string;
  m08: string;
  m09: string;
  m10: string;
  m21: string;
};

const RESET_MARKER = path.join(
  os.tmpdir(),
  `dw-enduser-forms-reset-${process.ppid}`,
);

test.beforeAll(async ({ playwright }) => {
  const request = await playwright.request.newContext();
  const an = await persona(request, AN);
  const dieu = await persona(request, DIEU);
  const fresh =
    fs.existsSync(RESET_MARKER) &&
    Date.now() - fs.statSync(RESET_MARKER).mtimeMs < 3_600_000;
  if (!fresh) {
    execSync("uv run python -m dw_sales.testing.demo_reset", {
      cwd: REPO_ROOT,
      stdio: "inherit",
      env: process.env,
    });
    fs.writeFileSync(RESET_MARKER, "reset");
    // Cases the later scenarios start from; M01/M08 are processed in the
    // walk. M03 is a PDF PO.
    await processViaApi(an, "M03");
    await processViaApi(dieu, "M09");
    await processViaApi(dieu, "M10");
    await processViaApi(an, "M21");
  }
  for (const id of ["M01", "M03", "M08", "M09", "M10", "M21"] as const) {
    const caseId = (await dispositionOf(an, id)).case_id;
    if (caseId) ids[id.toLowerCase() as keyof typeof ids] = caseId;
  }
  await request.dispose();
});

test("2a. Double-click 'DW xử lý thư M01': one case, one toast", async ({
  page,
  request,
}) => {
  const an = await persona(request, AN);
  await recordToasts(page);
  const posts = countPosts(page, "/inbox/M01/process");
  await signIn(page, request, AN);
  await page.goto("/sales/inbox");
  const row = page.getByRole("row").filter({ hasText: "M01" });
  await row
    .getByRole("button", { name: "DW xử lý thư M01", exact: true })
    .dblclick();
  await expect(row.getByText("Đã tạo hồ sơ")).toBeVisible({
    timeout: 240_000,
  });
  const d = await dispositionOf(an, "M01");
  ids.m01 = d.case_id!;
  // Exactly one case for M01's PO, checked once.
  const m01 = await getCase(an, "orders", ids.m01);
  const orders: { po_no: string }[] = await (await an.get("/orders")).json();
  expect(orders.filter((o) => o.po_no === m01.po_no)).toHaveLength(1);
  expect(
    (await history(an, "orders", ids.m01)).filter(
      (e) => e.action === "order.checked",
    ),
  ).toHaveLength(1);
  expect(await toasts(page, "Đã xếp thư M01 cho DW1 xử lý")).toBe(1);
  // Informational: how many POSTs the double click sent.
  test.info().annotations.push({
    type: "process POSTs sent",
    description: String(posts()),
  });
  await expect(row.getByText("DW1 chưa xử lý được")).toHaveCount(0);
  await expect(
    page.getByText(/^(Chưa làm được bước này|Máy chủ từ chối)$/),
  ).toHaveCount(0);
});

test("2x. 'Mở bản gốc' on Excel PO M01 opens the sheet", async ({
  page,
  request,
}) => {
  await signIn(page, request, AN);
  await page.goto(`/sales/orders/${ids.m01}`);
  await page.getByRole("button", { name: "Mở bản gốc", exact: true }).click();
  const drawer = dialog(page, "Bản gốc");
  await expect(drawer.getByText("Đã mở lúc")).toBeVisible({ timeout: 20_000 });
});

test("2b. Double-click 'Ghi quyết định' and 'Chuẩn bị xong' on M03: one change each, one toast each", async ({
  page,
  request,
}) => {
  const an = await persona(request, AN);
  await recordToasts(page);
  const decisions = countPosts(page, `/orders/${ids.m03}/findings/`);
  const prepares = countPosts(page, `/orders/${ids.m03}/prepare`);
  await signIn(page, request, AN);
  await page.goto(`/sales/orders/${ids.m03}`);
  const refusal = page.getByText(/^(Chưa làm được bước này|Máy chủ từ chối)$/);

  // A finding's decision, double-clicked.
  const card = finding(page, "Không có báo giá còn hiệu lực, dòng 2");
  await card.locator("label").filter({ hasText: "Chấp nhận + lý do" }).click();
  await card
    .getByLabel("Lý do chấp nhận")
    .fill("Khách xác nhận giá theo thư ngày 22/09");
  await button(card, "Ghi quyết định").dblclick();
  await expect(card.getByText("Bỏ quyết định")).toBeVisible();
  await page.waitForTimeout(2_000);
  expect(
    (await history(an, "orders", ids.m03)).filter(
      (e) => e.action === "order.finding_disposed",
    ),
  ).toHaveLength(1);
  expect(await toasts(page, "Đã ghi: Chấp nhận (có lý do)")).toBe(1);
  await expect(refusal).toHaveCount(0);

  // The NOC/ESF finding, one press (An holds export control).
  const noc = finding(page, "Thiếu NOC/ESF");
  await noc.locator("label").filter({ hasText: "Chấp nhận + lý do" }).click();
  await noc
    .getByLabel("Lý do chấp nhận")
    .fill("Đã kiểm tra danh sách cấm, chờ ESF năm nay");
  await button(noc, "Ghi quyết định").click();
  await expect(noc.getByText("Bỏ quyết định")).toBeVisible();

  // Each decision is a new version: open its source, then prepare.
  await openSource(page, "Mở nguồn");
  const prepare = button(page, "Chuẩn bị xong");
  await expect(prepare).toBeEnabled();
  await prepare.dblclick();
  await expect
    .poll(async () => (await getCase(an, "orders", ids.m03)).status)
    .toBe("prepared");
  await expect(page.getByText("PIC đã tự kiểm").first()).toBeVisible();
  await page.waitForTimeout(2_000);
  expect(
    (await history(an, "orders", ids.m03)).filter(
      (e) => e.action === "order.prepared",
    ),
  ).toHaveLength(1);
  expect(await toasts(page, "Đã chuẩn bị xong")).toBe(1);
  await expect(refusal).toHaveCount(0);
  test.info().annotations.push({
    type: "POSTs sent by the double clicks",
    description: `decision ${decisions()}, prepare ${prepares()}`,
  });
});

test("1a. 'Ghi số đơn Bravo' with an empty and an invalid number: field errors, nothing sent", async ({
  page,
  request,
}) => {
  const an = await persona(request, AN);
  const before = await getCase(an, "orders", ids.m03);
  expect(before.status).toBe("prepared");
  const posts = countPosts(page, "/bravo-entry");
  await signIn(page, request, AN);
  await page.goto(`/sales/orders/${ids.m03}`);
  await button(page, "Đã nhập Bravo").click();
  const bravo = dialog(page, "Ghi số đơn Bravo");
  await expect(bravo).toBeVisible();

  // Empty: both rules speak, the dialog stays.
  await button(bravo, "Ghi số đơn Bravo").click();
  await expect(bravo.getByText("Số đơn là bắt buộc")).toBeVisible();
  await expect(
    bravo.getByText("Cần xác nhận đã đối chiếu với PO"),
  ).toBeVisible();

  // Invalid (space and '#', DOCUMENT_NO): the format rule speaks.
  const help = bravo.getByText(
    "Số phiếu gồm chữ in hoa, số, '-' hoặc '/' (2–32 ký tự).",
  );
  await bravo.getByLabel("Số đơn bán hàng trên Bravo").fill("SO 26#1");
  await bravo
    .getByText("Tôi đã đối chiếu các dòng đơn trên Bravo với PO")
    .click();
  await button(bravo, "Ghi số đơn Bravo").click();
  await expect(help).toBeVisible();
  // One character is too short as well.
  await bravo.getByLabel("Số đơn bán hàng trên Bravo").fill("S");
  await button(bravo, "Ghi số đơn Bravo").click();
  await expect(help).toBeVisible();
  await expect(bravo).toBeVisible();
  await button(bravo, "Hủy").click();
  await expect(bravo).toBeHidden();

  expect(posts()).toBe(0);
  await page.reload();
  await expect(page.getByText("PIC đã tự kiểm").first()).toBeVisible();
  const after = await getCase(an, "orders", ids.m03);
  expect(after.status).toBe("prepared");
  expect(after.case_version).toBe(before.case_version);
  expect(after.bravo_so_no ?? null).toBeNull();
});

test("3a. 'Đóng hồ sơ' → 'Hủy' on M08 changes nothing", async ({
  page,
  request,
}) => {
  const an = await persona(request, AN);
  // M01's PO sent again: processed after M01, so it is a duplicate.
  // Its own case with duplicate_po is the domain's rule (order_checks.check_history), not a defect.
  ids.m08 = await processViaApi(an, "M08");
  const before = await getCase(an, "orders", ids.m08);
  expect(before.findings.map((f: { code: string }) => f.code)).toContain(
    "duplicate_po",
  );
  const posts = countPosts(page, `/orders/${ids.m08}/close`);
  await signIn(page, request, AN);
  await page.goto(`/sales/orders/${ids.m08}`);
  await button(page, "Đóng hồ sơ").click();
  const close = dialog(page, `Đóng hồ sơ PO ${before.po_no}`);
  await expect(close).toBeVisible();
  await button(close, "Hủy").click();
  await expect(close).toBeHidden();
  expect(posts()).toBe(0);
  await page.reload();
  await expect(button(page, "Đóng hồ sơ")).toBeVisible();
  const after = await getCase(an, "orders", ids.m08);
  expect(after.status).toBe(before.status);
  expect(after.case_version).toBe(before.case_version);
});

test("4. An closes duplicate M08 as 'PO trùng': Đã đóng, no further step, closed column", async ({
  page,
  request,
}) => {
  const an = await persona(request, AN);
  // M08 on its own case, closed as duplicate: the domain's rule (order_checks.check_history), not a defect.
  const m08 = await getCase(an, "orders", ids.m08);
  await signIn(page, request, AN);
  await page.goto(`/sales/orders/${ids.m08}`);
  await button(page, "Đóng hồ sơ").click();
  const close = dialog(page, `Đóng hồ sơ PO ${m08.po_no}`);
  // A duplicate offers one reason, already chosen.
  await expect(close.getByText("Lý do: PO trùng")).toBeVisible();
  await button(close, "Đóng hồ sơ").click();
  await expect(close).toBeHidden();
  await expect
    .poll(async () => (await getCase(an, "orders", ids.m08)).status)
    .toBe("closed");
  await page.reload();
  await expect(
    page.getByText("Đã đóng", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("Không có bước nào của Sales ở trạng thái này."),
  ).toBeVisible();
  for (const name of [
    "Đóng hồ sơ",
    "Chuẩn bị xong",
    "Đã nhập Bravo",
    "Gửi yêu cầu khách sửa",
  ])
    await expect(button(page, name)).toHaveCount(0);
  expect((await getCase(an, "orders", ids.m08)).close_reason).toBe("duplicate");

  await page.goto("/sales/pipeline");
  const closed = page
    .getByRole("region", { name: "Đơn hàng" })
    .getByRole("group", { name: /^Đã đóng: \d+ hồ sơ$/ });
  await expect(closed).toBeVisible();
  await expect(
    closed.locator(`a[href="/sales/orders/${ids.m08}"]`),
  ).toBeVisible();
});

test("3b. 'Từ chối báo giá' → 'Hủy' on M09 changes nothing", async ({
  page,
  request,
}) => {
  const dieu = await persona(request, DIEU);
  const before = await getCase(dieu, "quotes", ids.m09);
  const posts = countPosts(page, `/quotes/${ids.m09}/decline`);
  await signIn(page, request, DIEU);
  await page.goto(`/sales/quotes/${ids.m09}`);
  await button(page, "Từ chối báo giá").click();
  const decline = page
    .getByRole("dialog")
    .filter({ hasText: "Hồ sơ dừng ở trạng thái từ chối" });
  await expect(decline).toBeVisible();
  await button(decline, "Hủy").click();
  await expect(decline).toBeHidden();
  expect(posts()).toBe(0);
  await page.reload();
  await expect(button(page, "Từ chối báo giá")).toBeVisible();
  const after = await getCase(dieu, "quotes", ids.m09);
  expect(after.status).toBe(before.status);
  expect(after.case_version).toBe(before.case_version);
});

test("5. Diệu declines M09 with a reason: 'Từ chối báo giá' and the reason shown", async ({
  page,
  request,
}) => {
  const dieu = await persona(request, DIEU);
  await signIn(page, request, DIEU);
  await page.goto(`/sales/quotes/${ids.m09}`);
  await button(page, "Từ chối báo giá").click();
  const decline = page
    .getByRole("dialog")
    .filter({ hasText: "Hồ sơ dừng ở trạng thái từ chối" });
  // No reason: refused in the field, nothing sent.
  await button(decline, "Từ chối báo giá").click();
  await expect(decline.getByText("Lý do là bắt buộc")).toBeVisible();
  await decline.getByLabel("Lý do").click();
  await page
    .locator(".ant-select-item-option")
    .filter({ hasText: "Lý do thương mại" })
    .click();
  await decline
    .getByLabel("Ghi chú")
    .fill("Khách cần hàng trong 3 ngày, không kịp sản xuất");
  await button(decline, "Từ chối báo giá").click();
  await expect(decline).toBeHidden();
  await expect
    .poll(async () => (await getCase(dieu, "quotes", ids.m09)).status)
    .toBe("declined");
  await page.reload();
  await expect(
    page.getByText("Từ chối báo giá: Lý do thương mại"),
  ).toBeVisible();
  await expect(
    page.getByText(/Khách cần hàng trong 3 ngày, không kịp sản xuất/),
  ).toBeVisible();
  await expect(page.getByText("Báo giá đã bị từ chối.").first()).toBeVisible();
  await expect(button(page, "Từ chối báo giá")).toHaveCount(0);
});

test("3c. 'Tạm dừng DW1' → 'Hủy' changes nothing", async ({
  page,
  request,
}) => {
  const an = await persona(request, AN);
  const posts = countPosts(page, "/worker/pause");
  await signIn(page, request, AN);
  await page.goto("/sales/inbox");
  await button(page, "Tạm dừng DW1").click();
  const pause = dialog(page, "DW1 ngừng xử lý thư mới");
  await expect(pause).toBeVisible();
  await pause.getByLabel("Lý do").fill("Thử rồi hủy");
  await button(pause, "Hủy").click();
  await expect(pause).toBeHidden();
  expect(posts()).toBe(0);
  await page.reload();
  await expect(button(page, "Tạm dừng DW1")).toBeVisible();
  await expect(
    page.getByText("DW1 đang tạm dừng", { exact: true }),
  ).toHaveCount(0);
  expect((await (await an.get("/overview")).json()).worker.paused).toBe(false);
});

/** Diệu's pricing of M10's one line (the demo's numbers). */
async function price(page: Page, unitPrice: string): Promise<void> {
  await page.getByLabel("Đơn giá dòng 1").fill(unitPrice);
  await page.getByLabel("MOQ dòng 1").fill("3000");
  await page.getByLabel("Lead time dòng 1").fill("45");
  await page.getByLabel("Căn cứ đồng dòng 1").getByText("Theo dải LME").click();
  await page.getByLabel("LME từ (USD/tấn) dòng 1").fill("10500");
  await page.getByLabel("LME đến (USD/tấn) dòng 1").fill("11000");
}

test("1b. 'Trình duyệt' with no 'Số báo giá' (and an invalid one): field error, nothing sent", async ({
  page,
  request,
}) => {
  const dieu = await persona(request, DIEU);
  await signIn(page, request, DIEU);
  await page.goto(`/sales/quotes/${ids.m10}`);
  // M10's source is not opened: no quote step below requires it.
  // YCBG to Design, then Design's reply (M25) joins the case.
  await button(page, "Soạn YCBG").click();
  await expect
    .poll(async () => (await getCase(dieu, "quotes", ids.m10)).status)
    .toBe("ycbg_drafted");
  await expect(
    page.getByText("Đã soạn YCBG", { exact: true }).first(),
  ).toBeVisible();
  await button(page, "Đã lập YCBG").click();
  const record = dialog(page, "Ghi số YCBG Bravo đã cấp");
  await record.getByLabel("Số YCBG trên Bravo").fill("YCBG-2609-030");
  await button(record, "Ghi số YCBG").click();
  await expect(record).toBeHidden();
  await expect(
    page.getByText("YCBG YCBG-2609-030", { exact: true }),
  ).toBeVisible();
  await button(page, "Gửi Design").click();
  await expect
    .poll(async () => (await getCase(dieu, "quotes", ids.m10)).status)
    .toBe("sent_to_design");
  await processViaApi(dieu, "M25");
  await expect
    .poll(async () => (await getCase(dieu, "quotes", ids.m10)).status)
    .toBe("design_replied");

  await page.reload();
  await price(page, "0.6890");
  await button(page, "Ghi giá").click();
  await expect(
    page.getByText("Đã định giá", { exact: true }).first(),
  ).toBeVisible();
  const priced = await getCase(dieu, "quotes", ids.m10);
  expect(priced.status).toBe("priced");

  const posts = countPosts(page, `/quotes/${ids.m10}/submit`);
  await button(page, "Trình duyệt").click();
  const submit = dialog(page, "Trình duyệt báo giá");
  await button(submit, "Trình duyệt").click();
  await expect(submit.getByText("Số báo giá là bắt buộc")).toBeVisible();
  await submit.getByLabel("Số báo giá").fill("Q 26#1");
  await button(submit, "Trình duyệt").click();
  await expect(
    submit.getByText("Số phiếu gồm chữ in hoa, số, '-' hoặc '/' (2–32 ký tự)."),
  ).toBeVisible();
  await button(submit, "Hủy").click();
  await expect(submit).toBeHidden();
  expect(posts()).toBe(0);
  await page.reload();
  await expect(
    page.getByText("Đã định giá", { exact: true }).first(),
  ).toBeVisible();
  const after = await getCase(dieu, "quotes", ids.m10);
  expect(after.status).toBe("priced");
  expect(after.case_version).toBe(priced.case_version);
});

test("6. Giang returns M10 with a reason: 'Bị trả lại định giá'; Diệu prices it again", async ({
  page,
  request,
}) => {
  const dieu = await persona(request, DIEU);
  const giang = await persona(request, GIANG);
  await signIn(page, request, DIEU);
  await page.goto(`/sales/quotes/${ids.m10}`);
  await button(page, "Trình duyệt").click();
  const submit = dialog(page, "Trình duyệt báo giá");
  await submit.getByLabel("Số báo giá").fill("Q26-0301");
  await button(submit, "Trình duyệt").click();
  await expect(submit).toBeHidden();
  await expect
    .poll(async () => (await getCase(dieu, "quotes", ids.m10)).status)
    .toBe("pending_approval");
  // The approval request the run paused on is there before Giang decides.
  await expect
    .poll(async () =>
      Boolean((await getCase(giang, "quotes", ids.m10)).decision),
    )
    .toBe(true);

  await signIn(page, request, GIANG);
  await page.goto(`/sales/quotes/${ids.m10}`);
  await expect(page.getByText("Duyệt báo giá Q26-0301")).toBeVisible();
  await button(page, "Trả lại định giá").click();
  const back = dialog(page, "Lý do trả lại");
  // Empty reason: refused in the field.
  await button(back, "Trả lại").click();
  await expect(back.getByText("Lý do là bắt buộc")).toBeVisible();
  const why = "Giá dưới mức khách cũ, xem lại dải LME";
  await back.getByLabel("Lý do trả lại").fill(why);
  await button(back, "Trả lại").click();
  await expect(back).toBeHidden();
  await expect
    .poll(async () => (await getCase(giang, "quotes", ids.m10)).status)
    .toBe("returned");
  await page.reload();
  await expect(
    page.getByText("Bị trả lại định giá", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByText(new RegExp(why))).toBeVisible();

  await signIn(page, request, DIEU);
  await page.goto(`/sales/quotes/${ids.m10}`);
  await expect(
    page.getByText("Bị trả lại định giá", { exact: true }).first(),
  ).toBeVisible();
  const again = button(page, "Ghi giá mới");
  await expect(again).toBeEnabled();
  await page.getByLabel("Đơn giá dòng 1").fill("0.6950");
  await again.click();
  await expect
    .poll(async () => (await getCase(dieu, "quotes", ids.m10)).status)
    .toBe("priced");
  await expect(
    page.getByText("Đã định giá", { exact: true }).first(),
  ).toBeVisible();
  await expect(button(page, "Trình duyệt")).toBeEnabled();
});

test("7. Giang reassigns M21 to Diệu: the case shows Diệu; it leaves An's work", async ({
  page,
  request,
}) => {
  const an = await persona(request, AN);
  const mine = async () =>
    (
      (await (await an.get("/my-work?limit=200")).json()).items as {
        id: string;
      }[]
    ).some((w) => w.id === ids.m21);
  expect(await mine()).toBe(true);

  await signIn(page, request, GIANG);
  await page.goto(`/sales/orders/${ids.m21}`);
  await expect(page.getByText("Nguyễn Văn An").first()).toBeVisible();
  await button(page, "Phân công lại").click();
  const assign = dialog(page, "Phân công lại hồ sơ");
  await assign.getByLabel("Giao cho").click();
  await page
    .locator(".ant-select-item-option")
    .filter({ hasText: "Hoàng Thị Diệu" })
    .click();
  await button(assign, "Phân công").click();
  await expect(assign).toBeHidden();
  await page.reload();
  await expect(page.getByText("Hoàng Thị Diệu").first()).toBeVisible();

  expect(await mine()).toBe(false);
  await signIn(page, request, AN);
  await page.goto("/sales");
  await expect(
    page.getByRole("heading", { name: "Việc cần làm" }),
  ).toBeVisible();
  await expect(page.getByText(/việc đang chờ bạn/)).toBeVisible();
  await expect(page.locator(`a[href="/sales/orders/${ids.m21}"]`)).toHaveCount(
    0,
  );
  await page.goto("/sales/pipeline");
  await page.getByText(/^Việc của tôi \(\d+\)$/).click();
  await expect(page.locator(`a[href="/sales/orders/${ids.m21}"]`)).toHaveCount(
    0,
  );
});
