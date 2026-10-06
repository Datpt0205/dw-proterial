import { defineConfig, devices } from "@playwright/test";

/**
 * Browser tests for the account screen and the DW1 demo walk.
 *
 * These exist because the Python suites prove the API and prove nothing about a
 * button. A CRUD control that 500s, a tab that renders an empty state over real
 * data, a form that posts the wrong field - none of that shows up in a contract
 * test, and all of it is what a reviewer actually clicks.
 *
 * An API already answering on E2E_API_URL (8000) is reused, the worker beside
 * it; otherwise Playwright starts one in dev auth mode against the database the
 * environment names (`set -a; . ./.env; set +a`, or run through `make`). The web
 * is started the same way, because a Next dev server takes long enough that
 * reusing a running one is the difference between a usable loop and a coffee
 * break.
 */
const WEB_URL = process.env.E2E_WEB_URL ?? "http://localhost:3000";
const API_URL = process.env.E2E_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  testDir: "./e2e",
  // `next dev` on `.next-e2e` rewrites next-env.d.ts; this puts it back.
  globalTeardown: "./e2e/restore-next-env.ts",
  // One worker: the tests share one seeded account and one database, so running
  // them in parallel would make a scan started by one the reason another sees a
  // spinner it never asked for.
  workers: 1,
  fullyParallel: false,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    // localhost, not 127.0.0.1: Next 15 rejects /_next/static/* requests whose
    // Host does not match the server's notion of its own origin with a 400,
    // which strands the app on a blank "Loading…" screen.
    baseURL: WEB_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    locale: "vi-VN",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      // The repo's `.env` puts the API in oidc mode, which is right for a
      // deployment and wrong for a browser test: an OIDC login makes the suite
      // depend on a Keycloak password. `dev` mode is the same session bridge
      // with a local HS256 token, and the web below is started the same way.
      command: `uv run uvicorn dw_api.main:app --port ${new URL(API_URL).port || "8000"}`,
      cwd: "../..",
      url: `${API_URL}/api/v1/health`,
      reuseExistingServer: true,
      timeout: 120_000,
      stdout: "ignore",
      stderr: "pipe",
      env: {
        DW_API_AUTH_MODE: "dev",
        DW_API_DEV_SECRET:
          process.env.DW_E2E_DEV_SECRET ??
          "playwright-local-dev-secret-0123456789",
        // CORS: the API allows the one web origin this names.
        DW_PUBLIC_WEB_URL: WEB_URL,
      },
    },
    {
      command: `pnpm dev --port ${new URL(WEB_URL).port || "3000"}`,
      // Same URL the tests target, so a server the runner started by hand (e.g.
      // a prod build on another port) is reused instead of a second dev server
      // racing it for the same build directory.
      url: WEB_URL,
      reuseExistingServer: true,
      timeout: 180_000,
      stdout: "ignore",
      stderr: "pipe",
      env: {
        NEXT_PUBLIC_AUTH_MODE: "dev",
        NEXT_PUBLIC_API_BASE_URL: API_URL,
        // Its own build directory: a developer's `next dev` on another port
        // keeps `.next`, and two dev servers writing one directory corrupt it.
        NEXT_DIST_DIR: ".next-e2e",
      },
    },
  ],
});
