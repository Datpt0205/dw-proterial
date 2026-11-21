import { expect as baseExpect, test, type Page } from "@playwright/test";
import { signIn } from "./dev-login";

/**
 * Ticket 62: "Vì sao dòng này đi như vậy" on an order's line, at desktop and
 * at a 320 px phone. Needs the dev stack with a worker (the mailbox lane off,
 * `DW_WORKER_SALES_INBOX_LANE=false`) and the demo reset; M03 is processed
 * here if it is not on a case yet. Local only, like the other Sales specs.
 */

const expect = baseExpect.configure({ timeout: 60_000 });
const API_URL = process.env.E2E_API_URL ?? "http://127.0.0.1:8000";
// The head: the head sees every PIC's cases in the demo tenant.
const HEAD = "dev|giang.do";

async function headers(page: Page): Promise<Record<string, string>> {
  const session = await (
    await page.request.post(`${API_URL}/api/v1/dev/session`, {
      data: { subject: HEAD },
    })
  ).json();
  return {
    Authorization: `Bearer ${session.token}`,
    "X-Tenant-Id": session.tenant_id,
    "X-Workspace-Id": session.workspace_id,
  };
}

async function m03Case(page: Page): Promise<string | null> {
  const response = await page.request.get(`${API_URL}/api/v1/sales/inbox`, {
    headers: await headers(page),
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  const rows: {
    message_id: string;
    disposition: { case_id: string | null };
  }[] = await response.json();
  return rows.find((m) => m.message_id === "M03")?.disposition.case_id ?? null;
}

/** M03's order: DW1 processes it first if it is not on a case yet (the
 * worker's processing lane runs the job). */
async function orderOfM03(page: Page): Promise<string> {
  await signIn(page, HEAD);
  if (!(await m03Case(page))) {
    const queued = await page.request.post(
      `${API_URL}/api/v1/sales/inbox/M03/process`,
      { headers: await headers(page) },
    );
    expect(queued.ok(), await queued.text()).toBeTruthy();
    await expect.poll(() => m03Case(page), { timeout: 240_000 }).not.toBeNull();
  }
  return (await m03Case(page)) as string;
}

async function openTrailOfLine1(page: Page, caseId: string) {
  // `next dev` compiles a route on its first request and aborts that
  // navigation; a second try lands on the compiled page.
  await expect(async () => {
    await page.goto(`/sales/orders/${caseId}`);
  }).toPass({ timeout: 180_000 });
  const row = page.getByRole("row").filter({
    has: page.getByRole("cell", { name: "1", exact: true }),
  });
  await row.getByRole("button", { name: "Mở rộng dòng" }).first().click();
  await page.getByRole("button", { name: "Vì sao dòng 1 đi như vậy" }).click();
  const drawer = page
    .getByRole("dialog")
    .filter({ hasText: "Dòng 1: các bước đã đi" });
  await expect(drawer.getByRole("status")).toContainText(
    /\d+ bước: \d+ do luật/,
  );
  return drawer;
}

test("an order line's trail: every step with its code and who decided", async ({
  page,
}) => {
  test.setTimeout(360_000);
  const caseId = await orderOfM03(page);
  const drawer = await openTrailOfLine1(page, caseId);
  await expect(drawer.getByText("Đọc dòng từ PO")).toBeVisible();
  await expect(drawer.getByText("Các bước kiểm")).toBeVisible();
  await expect(drawer.getByText("Mã PRV của dòng")).toBeVisible();
  await expect(drawer.getByText("checks", { exact: true })).toBeVisible();
  await expect(drawer.getByText("Luật").first()).toBeVisible();
  await page.screenshot({
    path: "../../.playwright-mcp/t62-line-trail-desktop.png",
  });
  // Esc closes it and the page is back.
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
});

test("the trail at a 320 px phone: no sideways scroll, the steps readable", async ({
  page,
}) => {
  test.setTimeout(360_000);
  await page.setViewportSize({ width: 320, height: 640 });
  const caseId = await orderOfM03(page);
  const drawer = await openTrailOfLine1(page, caseId);
  await expect(drawer.getByText("Đọc dòng từ PO")).toBeVisible();
  const box = await drawer.boundingBox();
  expect(box?.width ?? 0).toBeLessThanOrEqual(320);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
  await page.screenshot({
    path: "../../.playwright-mcp/t62-line-trail-320.png",
  });
});
