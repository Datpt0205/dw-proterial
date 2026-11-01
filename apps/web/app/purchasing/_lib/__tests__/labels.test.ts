// @vitest-environment node
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { GLOSSARY_LINES, mailReason, ROLE } from "../labels";

/**
 * DW2's glossary owns the words; `labels.ts` is the screens' copy. This reads
 * the glossary itself, so a label changed, added or dropped on either side
 * turns this red instead of drifting (failure-modes.md #2).
 */
const GLOSSARY = readFileSync(
  resolve(
    __dirname,
    "../../../../../../packages/python/dw_purchasing/CONTEXT.md",
  ),
  "utf8",
);

/** code → words from the line (or bullet) starting `lead:`, up to its end. */
function line(lead: string): Record<string, string> {
  const start = GLOSSARY.indexOf(`${lead}:`);
  expect(start, `CONTEXT.md has a "${lead}:" line`).toBeGreaterThan(-1);
  const rest = GLOSSARY.slice(start);
  const end = rest.search(/\n\n|\n- /);
  const paragraph = (end === -1 ? rest : rest.slice(0, end)).replace(
    /\n/g,
    " ",
  );
  const pairs = [...paragraph.matchAll(/`([a-z_]+)`\s*\(([^)]*)\)/g)];
  return Object.fromEntries(pairs.map(([, code, words]) => [code, words]));
}

describe("the DW2 labels", () => {
  it.each(Object.entries(GLOSSARY_LINES))(
    "match CONTEXT.md's %s, code for code",
    (lead, labels) => {
      expect(labels).toEqual(line(lead));
    },
  );

  it("name every role the glossary lists", () => {
    const roles = Object.fromEntries(
      [...GLOSSARY.matchAll(/^- `(purchasing_[a-z0-9_]+)` \(([^)]+)\)/gm)].map(
        ([, code, words]) => [code, words],
      ),
    );
    expect(ROLE).toEqual(roles);
  });

  it("word a form rule's missing field and never hide an unknown code", () => {
    expect(mailReason("missing:budget_code")).toBe(
      "thiếu budget_code mà quy tắc của công ty đòi hỏi",
    );
    expect(mailReason("brand_new")).toBe("brand_new");
    expect(mailReason(null)).toBe("không rõ lý do");
  });
});
