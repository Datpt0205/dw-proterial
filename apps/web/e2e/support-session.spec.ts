import { execFileSync } from "node:child_process";
import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

/**
 * Support-access ticket 03, in a browser against the local stack: a support
 * staff member signed in with two factors sees the grant a customer gave at
 * /support, presses "Mở", lands on the context's page (Sales' orders list),
 * and the next request carries the grant; the same person without a second
 * factor is stopped with the reason.
 *
 * Needs the stack the config starts (API in dev auth mode on 8000, the web on
 * 3000) over the database `.env` names, migrated and seeded (`make
 * demo-reset`). The setup turns `support_access` on for tenant-alpha, makes a
 * staff member, has Giang (Sales head) grant Sales' support set and Chi (a
 * platform operator) assign it, all through the API; it turns the feature
 * off again after.
 */

const API_URL = process.env.E2E_API_URL ?? "http://127.0.0.1:8000";
const SECRET =
  process.env.DW_E2E_DEV_SECRET ?? "playwright-local-dev-secret-0123456789";
const CONTAINER = `${process.env.COMPOSE_PROJECT_NAME ?? "dw_proterial"}-postgres-1`;
const TAG = Date.now().toString(36);
const STAFF = {
  subject: `dev|support.e2e.${TAG}`,
  email: `support.e2e.${TAG}@support.example`,
};

function sql(statement: string): string {
  return execFileSync(
    "docker",
    [
      "exec",
      CONTAINER,
      "psql",
      "-U",
      process.env.POSTGRES_USER ?? "dw_admin",
      "-d",
      "dw",
      "-tAc",
      statement,
    ],
    { encoding: "utf-8" },
  ).trim();
}

/** A dev token the API verifies, with or without a second factor. */
function token(subject: string, amr: string[] | null): string {
  const args = amr ? `, amr=${JSON.stringify(amr)}` : "";
  return execFileSync(
    "uv",
    [
      "run",
      "python",
      "-c",
      `from dw_platform.adapters.identity.dev_token import DevTokenVerifier;` +
        `print(DevTokenVerifier(${JSON.stringify(SECRET)}).issue(${JSON.stringify(subject)}${args}))`,
    ],
    { encoding: "utf-8", cwd: "../.." },
  ).trim();
}

async function call(
  request: APIRequestContext,
  method: "GET" | "POST",
  path: string,
  bearer: string,
  {
    body,
    scope,
  }: { body?: unknown; scope?: { tenant: string; workspace: string } } = {},
) {
  const headers: Record<string, string> = {
    Authorization: `Bearer ${bearer}`,
    "Idempotency-Key": crypto.randomUUID(),
  };
  if (scope) {
    headers["X-Tenant-Id"] = scope.tenant;
    headers["X-Workspace-Id"] = scope.workspace;
  }
  const response = await request.fetch(`${API_URL}/api/v1${path}`, {
    method,
    headers,
    data: body,
  });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(
    true,
  );
  return response.json();
}

let tenantId = "";

test.beforeAll(async ({ request }) => {
  const head = token("dev|giang.do", null);
  const operator = token("dev|chi.le", null);
  const bootstrap = await call(request, "GET", "/auth/bootstrap", head);
  const alpha = bootstrap.memberships.find(
    (m: { tenant_slug: string }) => m.tenant_slug === "tenant-alpha",
  );
  tenantId = alpha.tenant_id;
  const scope = { tenant: alpha.tenant_id, workspace: alpha.workspace_id };
  sql(
    `UPDATE platform.entitlements SET feature_overrides = feature_overrides || '["support_access"]'::jsonb` +
      ` WHERE tenant_id = '${tenantId}' AND NOT feature_overrides ? 'support_access'`,
  );
  const staffId = sql(
    `INSERT INTO platform.users (id, subject, email, display_name) VALUES` +
      ` (gen_random_uuid(), '${STAFF.subject}', '${STAFF.email}', 'Nhân viên hỗ trợ (e2e)') RETURNING id`,
  ).split("\n")[0]!;
  await call(request, "POST", "/platform/support-staff", operator, {
    body: { email: STAFF.email },
  });
  const grant = await call(request, "POST", "/support/grants", head, {
    scope,
    body: {
      scope_set_key: "sales.case_support",
      resource_type: "workspace",
      reason: "Kiểm thử phiên quyền hỗ trợ (e2e)",
      duration_hours: 24,
    },
  });
  await call(
    request,
    "POST",
    `/platform/support-requests/${grant.id}/assign`,
    operator,
    {
      body: { staff_user_id: staffId },
    },
  );
});

test.afterAll(() => {
  sql(
    `UPDATE platform.entitlements SET feature_overrides = feature_overrides - 'support_access'` +
      ` WHERE tenant_id = '${tenantId}'`,
  );
});

async function signIn(page: Page, bearer: string): Promise<void> {
  await page.goto("/dev-login");
  await page.evaluate((value) => {
    window.localStorage.setItem("dw.dev.token", value);
    window.sessionStorage.clear();
  }, bearer);
  await page.goto("/support");
}

test("a staff member with two factors opens a grant and works under it", async ({
  page,
}) => {
  await signIn(page, token(STAFF.subject, ["pwd", "otp"]));
  await expect(
    page.getByRole("heading", { level: 1, name: "Quyền hỗ trợ của tôi" }),
  ).toBeVisible();
  await expect(page.getByText("giờ Việt Nam").first()).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow, "the page scrolls sideways").toBeLessThanOrEqual(0);

  const underGrant = page.waitForRequest(
    (req) =>
      req.url().includes("/api/v1/sales/") &&
      !!req.headers()["x-dw-support-grant"],
  );
  await page
    .getByRole("button", { name: /^Mở quyền SG-/ })
    .first()
    .click();
  await page.waitForURL("**/sales/orders");
  const sent = await underGrant;
  expect(sent.headers()["x-tenant-id"]).toBe(tenantId);
  await expect(
    page.getByRole("status").filter({ hasText: "quyền hỗ trợ" }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Thoát quyền hỗ trợ" }).click();
  await page.waitForURL("**/support");
});

test("without a second factor the grant is refused with the reason", async ({
  page,
}) => {
  await signIn(page, token(STAFF.subject, ["pwd"]));
  await page
    .getByRole("button", { name: /^Mở quyền SG-/ })
    .first()
    .click();
  await expect(
    page.getByText("Cần xác thực hai lớp để dùng quyền hỗ trợ"),
  ).toBeVisible();
});
