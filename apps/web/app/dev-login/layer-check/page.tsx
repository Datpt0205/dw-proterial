import { notFound } from "next/navigation";
import { AUTH_MODE } from "../../../lib/auth/config";
import { LayerCheckFixture } from "./fixture";

/**
 * Fixture for e2e/antd-shell.spec.ts: the shell, and an antd Button carrying a
 * Tailwind utility, on a page that needs no sign-in or API. It exists only in
 * dev-auth builds, the mode the e2e suite runs in. A server component on
 * purpose: `notFound()` runs on the server, so any other build sends the
 * not-found fallback and never the fixture. (The status is still 200 there:
 * the auth gate's loading screen is what the server renders for every page.)
 * The gate lets the page through only in dev mode (components/app-frame).
 */
export default function LayerCheckPage() {
  if (AUTH_MODE !== "dev") notFound();
  return <LayerCheckFixture />;
}
