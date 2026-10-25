import { defineConfig, devices } from "@playwright/test";

/**
 * Browser tests that sign in through Keycloak rather than the dev session.
 *
 * `playwright.config.ts` runs the API and the web in dev auth mode on purpose,
 * so that suite does not depend on a Keycloak password. What a person meets
 * the first time they sign in with a temporary password, and "Đổi mật khẩu",
 * exist only behind Keycloak, so they are tested here, through the real login
 * pages.
 *
 * Needs, from the repository root with `.env` loaded (`set -a; . ./.env; set +a`):
 * - postgres, valkey and keycloak up (`--profile infra`), the dev database
 *   migrated and seeded;
 * - the realm's `dw-accounts` client: `uv run python scripts/keycloak_accounts_client.py`;
 * - the seeded admin's login: `uv run python scripts/keycloak_dev_users.py`
 *   (`DW_DEV_USER_PASSWORD`).
 *
 * The web runs on DW_PUBLIC_WEB_URL, the origin the realm's `dw-web` client
 * redirects back to; the API beside it on its own port, in oidc mode.
 *
 *   pnpm exec playwright test -c playwright.oidc.config.ts
 */
const WEB_URL = process.env.DW_PUBLIC_WEB_URL ?? "http://localhost:3300";
const API_URL = process.env.E2E_OIDC_API_URL ?? "http://127.0.0.1:8010";
const KEYCLOAK_URL =
  process.env.NEXT_PUBLIC_KEYCLOAK_URL ?? "http://localhost:8686";

export default defineConfig({
  testDir: "./e2e",
  testMatch: /sign-in-accounts\.oidc\.spec\.ts/,
  globalTeardown: "./e2e/restore-next-env.ts",
  workers: 1,
  fullyParallel: false,
  timeout: 180_000,
  expect: { timeout: 20_000 },
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: WEB_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    locale: "vi-VN",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], timezoneId: "Asia/Ho_Chi_Minh" },
    },
  ],
  webServer: [
    {
      command: `uv run uvicorn dw_api.main:app --port ${new URL(API_URL).port}`,
      cwd: "../..",
      url: `${API_URL}/api/v1/health`,
      reuseExistingServer: true,
      timeout: 120_000,
      stdout: "ignore",
      stderr: "pipe",
      env: {
        DW_API_AUTH_MODE: "oidc",
        // Keycloak as this machine reaches it (compose sets the internal URL).
        DW_API_ACCOUNTS_ADMIN_URL: KEYCLOAK_URL,
        DW_PUBLIC_WEB_URL: WEB_URL,
      },
    },
    {
      command: `pnpm dev --port ${new URL(WEB_URL).port}`,
      url: WEB_URL,
      reuseExistingServer: true,
      timeout: 180_000,
      stdout: "ignore",
      stderr: "pipe",
      env: {
        NEXT_PUBLIC_AUTH_MODE: "oidc",
        NEXT_PUBLIC_API_BASE_URL: API_URL,
        NEXT_DIST_DIR: ".next-e2e-oidc",
      },
    },
  ],
});
