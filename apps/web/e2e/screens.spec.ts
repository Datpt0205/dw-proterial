import path from "node:path";
import { test } from "@playwright/test";
import { NAV_ITEMS } from "../lib/nav/registry";
import { signIn } from "./dev-login";

/**
 * Screenshots of every page for a person to review (ui-quality.md, "A clean
 * review of the code is not a reviewed screen"). It asserts nothing: it is
 * the rendered page, captured as each persona sees it, at every viewport and
 * time zone `playwright.config.ts` owns.
 *
 * Off unless `DW_SCREENS=1` (`make web-screens`), so `make test-web` does not
 * spend minutes on pictures. Needs the stack and the seed, like the other
 * specs. The pages are the nav registry's, so a page added to the menu is
 * captured without touching this file; a page the persona may not open is
 * captured too, because its forbidden state is a screen as well.
 *
 * Writes `<DW_SCREENS_DIR or ./screens>/<project>/<persona>/<page>.png`,
 * outside `test-results/`, which the next Playwright run empties.
 */

const ENABLED = process.env.DW_SCREENS === "1";
// Who to look through: the tenant's platform admin and operator, and the Sales
// head. Another persona is one entry in DW_SCREENS_AS (comma-separated).
const PERSONAS = (process.env.DW_SCREENS_AS ?? "dev|chi.le,dev|giang.do")
  .split(",")
  .map((subject) => subject.trim())
  .filter(Boolean);
const OUT_DIR = process.env.DW_SCREENS_DIR ?? "screens";

function slug(href: string): string {
  return href === "/" ? "home" : href.replace(/^\//, "").replace(/\//g, "_");
}

for (const subject of PERSONAS) {
  test(`screens as ${subject}`, async ({ page }, testInfo) => {
    test.skip(!ENABLED, "DW_SCREENS=1 turns the screenshot run on");
    test.setTimeout(60_000 + NAV_ITEMS.length * 20_000);
    await signIn(page, subject);
    const persona = subject.replace(/^dev\|/, "").replace(/[^\w.-]/g, "_");
    for (const item of NAV_ITEMS) {
      await test.step(item.href, async () => {
        await page.goto(item.href);
        // A region still loading is not what a reviewer should see.
        await page
          .waitForLoadState("networkidle", { timeout: 15_000 })
          .catch(() => undefined);
        await page.screenshot({
          path: path.join(
            OUT_DIR,
            testInfo.project.name,
            persona,
            `${slug(item.href)}.png`,
          ),
          fullPage: true,
        });
      });
    }
  });
}
