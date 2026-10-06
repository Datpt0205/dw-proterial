import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

/**
 * The e2e web builds into `.next-e2e` (playwright.config.ts), and `next dev`
 * rewrites the tracked `next-env.d.ts` to reference that directory's route
 * types. Pointed back at `.next` when the run ends, so a test run leaves no
 * change in the working tree.
 */
export default function restoreNextEnv(): void {
  const path = join(__dirname, "..", "next-env.d.ts");
  const text = readFileSync(path, "utf8");
  const restored = text.replaceAll("./.next-e2e/", "./.next/");
  if (restored !== text) writeFileSync(path, restored);
}
