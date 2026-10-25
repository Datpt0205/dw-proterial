import { expect, test, type Page } from "@playwright/test";

/**
 * The whole life of an account IT creates, through Keycloak's real pages
 * (`playwright.oidc.config.ts` says what must be running):
 *
 * 1. Tenant IT (seeded `tam.ngo`, org_admin) adds a person on Admin →
 *    Thành viên and reads the temporary password from its one-time dialog.
 * 2. The person signs in with it, is made to set a password of their own, in
 *    Vietnamese, and lands in DW.
 * 3. The person changes it again from "Đổi mật khẩu" in the account menu.
 * 4. Only the latest password signs in.
 * 5. IT removes the person again; the Keycloak account is deleted after.
 */

const ADMIN_EMAIL = "tam.ngo@alpha.local";
const ADMIN_PASSWORD = process.env.DW_DEV_USER_PASSWORD ?? "";
const KEYCLOAK_URL =
  process.env.NEXT_PUBLIC_KEYCLOAK_URL ?? "http://localhost:8686";
const REALM = process.env.NEXT_PUBLIC_KEYCLOAK_REALM ?? "dw";

const STAMP = Date.now().toString(36);
const PERSON = {
  name: `Người Thử ${STAMP}`,
  email: `e2e-${STAMP}@alpha.local`,
  first: `Rieng-Dau-${STAMP}9`,
  second: `Rieng-Sau-${STAMP}7`,
};

async function signInAtKeycloak(page: Page, email: string, password: string) {
  await expect(
    page.getByRole("heading", { name: "Đăng nhập vào tài khoản của bạn" }),
  ).toBeVisible();
  await page.getByLabel("Tên người dùng hoặc email").fill(email);
  await page.getByLabel("Mật khẩu", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Đăng nhập" }).click();
}

async function signIn(page: Page, email: string, password: string) {
  await page.goto("/");
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await signInAtKeycloak(page, email, password);
}

async function setPasswordAtKeycloak(page: Page, password: string) {
  await expect(
    page.getByRole("heading", { name: "Cập nhật mật khẩu" }),
  ).toBeVisible();
  await page.getByLabel("Mật khẩu mới").fill(password);
  await page.getByLabel("Xác nhận mật khẩu").fill(password);
  await page.getByRole("button", { name: "Gửi" }).click();
}

async function accountMenu(page: Page, name: string) {
  await page
    .getByRole("button", { name: new RegExp(`^Tài khoản: ${name}`) })
    .click();
}

async function signOut(page: Page, name: string) {
  await accountMenu(page, name);
  await page.getByRole("menuitem", { name: "Đăng xuất" }).click();
  await expect(page.getByRole("button", { name: "Đăng nhập" })).toBeVisible();
}

test.beforeAll(() => {
  if (!ADMIN_PASSWORD)
    throw new Error("DW_DEV_USER_PASSWORD is not set (load .env)");
});

test.afterAll(async ({ request }) => {
  // The Keycloak account, which no DW screen deletes.
  const token = await request.post(
    `${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token`,
    {
      form: {
        grant_type: "password",
        client_id: "admin-cli",
        username: process.env.KEYCLOAK_ADMIN ?? "",
        password: process.env.KEYCLOAK_ADMIN_PASSWORD ?? "",
      },
    },
  );
  if (!token.ok()) return;
  const headers = {
    Authorization: `Bearer ${(await token.json()).access_token}`,
  };
  const users = await request.get(
    `${KEYCLOAK_URL}/admin/realms/${REALM}/users?email=${encodeURIComponent(PERSON.email)}&exact=true`,
    { headers },
  );
  for (const user of (await users.json()) as { id: string }[]) {
    await request.delete(
      `${KEYCLOAK_URL}/admin/realms/${REALM}/users/${user.id}`,
      {
        headers,
      },
    );
  }
});

test("IT adds a person; they set their own password, change it again, and only the latest works", async ({
  page,
}) => {
  // 1. IT adds the person.
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto("/admin");
  const add = page.getByRole("button", { name: "Thêm người" });
  await expect(add).toBeEnabled();
  await add.click();
  const form = page.getByRole("dialog", {
    name: "Thêm người và tạo tài khoản đăng nhập",
  });
  await form.getByLabel("Họ và tên").fill(PERSON.name);
  await form.getByLabel("Email công ty").fill(PERSON.email);
  await form.getByRole("button", { name: "Tạo tài khoản" }).click();
  const shown = page.getByRole("dialog", {
    name: `Mật khẩu tạm của ${PERSON.name}`,
  });
  const temporary = (await shown.locator("code").innerText()).trim();
  expect(temporary).toMatch(/^[A-Za-z2-9]{4}-[A-Za-z2-9]{4}-[A-Za-z2-9]{4}$/);
  await shown.getByRole("button", { name: "Đã ghi lại" }).click();
  // The member list's row, not the dialog closing over it.
  await expect(
    page.locator("li").filter({ hasText: PERSON.email }),
  ).toBeVisible();
  await signOut(page, "Ngô Minh Tâm");

  // 2. First sign-in: the temporary password only opens the page that replaces it.
  await signIn(page, PERSON.email, temporary);
  await expect(
    page.getByText("Bạn cần thay đổi mật khẩu để kích hoạt tài khoản."),
  ).toBeVisible();
  await setPasswordAtKeycloak(page, PERSON.first);
  await expect(
    page.getByRole("button", {
      name: new RegExp(`^Tài khoản: ${PERSON.name}`),
    }),
  ).toBeVisible();

  // 3. "Đổi mật khẩu" from the account menu, and back to DW.
  await accountMenu(page, PERSON.name);
  await page.getByRole("menuitem", { name: "Đổi mật khẩu" }).click();
  await setPasswordAtKeycloak(page, PERSON.second);
  await expect(
    page.getByRole("button", {
      name: new RegExp(`^Tài khoản: ${PERSON.name}`),
    }),
  ).toBeVisible();
  await signOut(page, PERSON.name);

  // 4. The first password no longer signs in; the second does.
  await signIn(page, PERSON.email, PERSON.first);
  await expect(
    page.getByText("Tên người dùng hoặc mật khẩu không hợp lệ."),
  ).toBeVisible();
  // Past the realm's quick-login check (two failures inside a second).
  await page.waitForTimeout(1500);
  await page.getByLabel("Mật khẩu", { exact: true }).fill(PERSON.second);
  await page.getByRole("button", { name: "Đăng nhập" }).click();
  await expect(
    page.getByRole("button", {
      name: new RegExp(`^Tài khoản: ${PERSON.name}`),
    }),
  ).toBeVisible();
  await signOut(page, PERSON.name);

  // 5. IT removes the person from the workspace again.
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto("/admin");
  await page.getByRole("button", { name: `Gỡ ${PERSON.name}` }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Gỡ" }).click();
  await expect(
    page.locator("li").filter({ hasText: PERSON.email }),
  ).toHaveCount(0);
});
