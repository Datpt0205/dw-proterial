import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, resolve, sep } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * One tone-mark style, the old one, everywhere a person reads (Đạt,
 * 2026-11-27): "hủy", "xóa", "khóa", "hòa", "thủy", never "huỷ", "xoá",
 * "khoá", "hoà", "thuỷ". In "oa", "oe" and "uy" with nothing after them
 * the mark sits on the first vowel; with a final letter ("hoàn", "khoảng",
 * "quyền") both styles agree, and "quý" is "qu" + "ý", so neither is
 * flagged. `.claude/rules/ui-quality.md` §8 states the rule.
 *
 * Read from every source of the web app and `@dw/ui`. Tests are left out:
 * a fixture may hold a tenant's own words as they were stored.
 */

const WEB = resolve(__dirname, "../..");
const UI = resolve(WEB, "../../packages/typescript/ui/src");
const ROOTS = ["app", "components", "lib"].map((dir) => join(WEB, dir));

const NEW_STYLE =
  /(?<![qQ])[uU][ỳýỷỹỵỲÝỶỸỴ](?!\p{L})|[oO][àáảãạèéẻẽẹÀÁẢÃẠÈÉẺẼẸ](?!\p{L})/gu;

/** Every new-style word in a text, as written. */
export function newStyleMarks(text: string): string[] {
  const words = text.normalize("NFC").match(/\p{L}+/gu) ?? [];
  return words.filter((word) => {
    NEW_STYLE.lastIndex = 0;
    return NEW_STYLE.test(word);
  });
}

function sources(root: string): string[] {
  const found: string[] = [];
  const walk = (dir: string) => {
    for (const name of readdirSync(dir)) {
      if (
        name === "node_modules" ||
        name === "__tests__" ||
        name.startsWith(".")
      ) {
        continue;
      }
      const path = join(dir, name);
      if (statSync(path).isDirectory()) walk(path);
      else if (/\.(ts|tsx)$/.test(name) && !/\.test\.tsx?$/.test(name))
        found.push(path);
    }
  };
  walk(root);
  return found;
}

describe("one tone-mark style", () => {
  it("flags the new style and nothing else", () => {
    expect(
      newStyleMarks("Huỷ, xoá, Khoá, hoà, thuỷ, khoẻ, tuỳ ý, KHOÁ"),
    ).toEqual(["Huỷ", "xoá", "Khoá", "hoà", "thuỷ", "khoẻ", "tuỳ", "KHOÁ"]);
    expect(
      newStyleMarks(
        "Hủy, xóa, khóa, hòa, thủy, khỏe, tùy ý, hoàn tất, khoảng, quyền, quý khách, Quý, thuyết, xoáy",
      ),
    ).toEqual([]);
    // Decomposed text is read as it renders.
    expect(newStyleMarks("Huỷ".normalize("NFD"))).toEqual(["Huỷ"]);
  });

  it("no source in the web app or @dw/ui writes the new style", () => {
    const offenders = [...ROOTS, UI]
      .flatMap(sources)
      .flatMap((path) =>
        newStyleMarks(readFileSync(path, "utf8")).map(
          (word) => `${relative(WEB, path).split(sep).join("/")}: ${word}`,
        ),
      );
    expect(offenders).toEqual([]);
  });
});
