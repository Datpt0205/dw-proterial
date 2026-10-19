import { existsSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { appTheme } from "@dw/ui";
import manifest from "../manifest";

// The installed app (infra/onprem/README.md): a browser installs it only with
// a 192 and a 512 icon that load, and its colours are the theme's own.
describe("the web app manifest", () => {
  const m = manifest();

  it("names icons that exist, 192 and 512 among them, one maskable", () => {
    for (const icon of m.icons ?? []) {
      expect(existsSync(join(__dirname, "..", "..", "public", icon.src))).toBe(
        true,
      );
    }
    const sizes = (m.icons ?? []).map((i) => i.sizes);
    expect(sizes).toEqual(expect.arrayContaining(["192x192", "512x512"]));
    expect((m.icons ?? []).some((i) => i.purpose === "maskable")).toBe(true);
  });

  it("opens in its own window, in Vietnamese", () => {
    expect(m.display).toBe("standalone");
    expect(m.lang).toBe("vi");
  });

  it("takes its colours from the theme, not a second copy", () => {
    expect(m.theme_color).toBe(appTheme.token?.colorPrimary);
    expect(m.background_color).toBe(appTheme.token?.colorBgLayout);
  });
});
