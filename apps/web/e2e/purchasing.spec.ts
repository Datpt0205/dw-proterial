import { expect as baseExpect, test, type Page } from "@playwright/test";
import { signIn } from "./dev-login";

/**
 * DW2 (Mua hàng) in a browser, each person in turn, on the demo tenant after
 * `uv run python -m dw_purchasing.testing.seed_personas` (local only):
 *
 * 1. An (người yêu cầu) writes "Tôi cần mua…"; with no model on the machine
 *    DW2 says it could not read and the form opens to fill by hand. An sees
 *    where the request stands, never a step that is someone else's.
 * 2. DW2 sends it to its approver on its own (the default switch), or Khoa
 *    (nhân viên mua hàng) does; Khoa cannot decide it.
 * 3. Giang (Tổng giám đốc, the last tier alone) reads the request on
 *    "Việc của tôi" and decides it with one press after the reason.
 * 4. Tâm (người cấu hình) reads the switches and the rules in words, no code.
 * 5. The case page holds at phone width.
 *
 * The approval moves the case once the worker settles it; this walk stops at
 * the decision, so it needs the API and the web, not the worker.
 */
const expect = baseExpect.configure({ timeout: 60_000 });

const AN = "dev|an.nguyen";
const KHOA = "dev|khoa.lam";
const GIANG = "dev|giang.do";
const TAM = "dev|tam.ngo";

test.describe.configure({ mode: "serial" });

let caseUrl = "";
let prNo = "";

async function caseNumber(page: Page): Promise<string> {
  const title = await page
    .getByText(/^Yêu cầu DW2-\S+$/)
    .first()
    .innerText();
  return title.replace("Yêu cầu ", "").trim();
}

test("1. a requester writes their own request and sees only where it stands", async ({
  page,
}) => {
  await signIn(page, AN);
  await page.goto("/purchasing/new");
  await page
    .getByRole("textbox", { name: "Bạn cần mua gì" })
    .fill("Cần 20 hộp găng tay nitrile cỡ M cho xưởng 2, mã ngân sách SX-2026");
  await page.getByRole("button", { name: "DW2 soạn yêu cầu" }).click();
  await expect(page.getByText("Yêu cầu sẽ gửi")).toBeVisible();

  // Whatever DW2 read (or nothing, with no model), the person's own values.
  const description = page.locator("#lines_0_description");
  if (!(await description.count()))
    await page.getByRole("button", { name: "Thêm dòng" }).click();
  await page.locator("#lines_0_description").fill("Găng tay nitrile cỡ M");
  await page.locator("#lines_0_quantity").fill("20");
  await page.locator("#lines_0_unit").fill("hộp");
  await page.locator("#lines_0_estimated_unit_price").fill("150.000");
  await page.locator("#currency").fill("VND");
  await page.locator("#budget_code").fill("SX-2026");
  await page.getByRole("button", { name: "Gửi", exact: true }).click();

  await page.waitForURL(/\/purchasing\/requests\/[0-9a-f-]+$/);
  caseUrl = new URL(page.url()).pathname;
  await expect(page.getByText("Yêu cầu của bạn đang ở đâu")).toBeVisible();
  await expect(page.getByRole("button", { name: "Gửi duyệt" })).toHaveCount(0);
  prNo = await caseNumber(page);
  expect(prNo).toMatch(/^DW2-/);
});

test("2. the request goes to its approver, by DW2 or by a buyer", async ({
  page,
}) => {
  await signIn(page, KHOA);
  await page.goto(caseUrl);
  // "Gửi người duyệt" is AI tự làm by default: the automation lane may have
  // sent it already; else the buyer does.
  const waiting = page.getByText(/^Chờ .* duyệt\./);
  const send = page.getByRole("button", { name: "Gửi duyệt" });
  await expect(waiting.or(send)).toBeVisible();
  if (await send.isVisible()) await send.click();
  await expect(waiting).toBeVisible();
  await expect(page.getByText(/^Gửi duyệt: /)).toBeVisible();
  // Khoa holds approvals.decide for Sales; this request's tier is not his.
  const approve = page.getByRole("button", { name: `Duyệt yêu cầu ${prNo}` });
  if (await approve.count()) await expect(approve).toBeDisabled();
});

test("3. the director decides it on 'Việc của tôi' after a reason", async ({
  page,
}) => {
  await signIn(page, GIANG);
  await page.goto("/purchasing");
  const card = page.locator(".ant-card-type-inner", { hasText: prNo });
  await expect(card).toBeVisible();
  // What is decided is on screen: the number, the amount, the tier.
  await expect(card.getByText(/Bậc duyệt: /)).toBeVisible();
  const approve = card.getByRole("button", { name: `Duyệt yêu cầu ${prNo}` });
  await expect(approve).toBeDisabled();
  await card
    .getByRole("textbox", { name: `Lý do quyết định yêu cầu ${prNo}` })
    .fill("Đồng ý, tạo mã hàng sau");
  await approve.click();
  await expect(
    page.locator(".ant-card-type-inner", { hasText: prNo }),
  ).toHaveCount(0);
});

test("4. the settings read in words, never in codes", async ({ page }) => {
  await signIn(page, TAM);
  await page.goto("/purchasing/settings");
  await expect(page.getByText("Công tắc tự động").first()).toBeVisible();
  await expect(
    page.getByRole("radiogroup", { name: "Mức cho bước Soạn thư hỏi giá" }),
  ).toBeVisible();
  const text = await page.locator("main").innerText();
  for (const code of [
    "ai_auto",
    "ai_review",
    "purchasing_",
    "policy_version",
    "{",
  ])
    expect(text, code).not.toContain(code);
});

test("5. the case page holds at phone width", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 740 });
  await signIn(page, KHOA);
  await page.goto(caseUrl);
  await expect(page.getByText("Dòng hàng")).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});
