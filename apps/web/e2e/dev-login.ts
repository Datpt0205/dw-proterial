import { expect, type Page } from "@playwright/test";

const API_URL = process.env.E2E_API_URL ?? "http://127.0.0.1:8000";

/** Sign in on /dev-login (dev auth mode) by pressing that persona's
 * "Đăng nhập": the buttons follow the order of `/dev/demo-users`. */
export async function signIn(page: Page, subject: string): Promise<void> {
  const users = await (
    await page.request.get(`${API_URL}/api/v1/dev/demo-users`)
  ).json();
  const index = users.findIndex(
    (user: { subject: string }) => user.subject === subject,
  );
  expect(index, `${subject} is on the demo roster`).toBeGreaterThanOrEqual(0);
  await page.goto("/dev-login");
  const buttons = page.getByRole("button", { name: "Đăng nhập" });
  await buttons.first().waitFor({ state: "visible" });
  await buttons.nth(index).click();
  await page.waitForURL("**/");
}
