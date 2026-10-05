// @vitest-environment node
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { GLOSSARY_LISTS, GLOSSARY_TABLES } from "../labels";

/**
 * The glossary owns the words; `labels.ts` is the screen's copy. This reads
 * the glossary itself, so a label changed, added or dropped on either side
 * turns this red instead of drifting (failure-modes.md #2).
 */
const GLOSSARY = readFileSync(
  resolve(__dirname, "../../../../../../packages/python/dw_sales/CONTEXT.md"),
  "utf8",
);

/** The section under `## heading`, up to the next heading of that level. */
function section(heading: string): string {
  const start = GLOSSARY.indexOf(`## ${heading}\n`);
  expect(start, `CONTEXT.md has a "## ${heading}" section`).toBeGreaterThan(-1);
  const rest = GLOSSARY.slice(start + heading.length + 4);
  const end = rest.search(/\n## /);
  return end === -1 ? rest : rest.slice(0, end);
}

/** code → label from the section's first table, reading the label column by
 * its header ("Label", or "Vietnamese name" for the roles). */
function table(heading: string): Record<string, string> {
  const rows = section(heading)
    .split("\n")
    .filter((line) => line.startsWith("|"))
    .map((line) =>
      line
        .slice(1, -1)
        .split("|")
        .map((cell) => cell.trim()),
    );
  const header = rows[0]!;
  const column = header.findIndex((name) =>
    ["Label", "Vietnamese name"].includes(name),
  );
  expect(column, `"${heading}" names a label column`).toBeGreaterThan(0);
  return Object.fromEntries(
    rows
      .slice(2)
      .map((cells) => [cells[0]!.replace(/`/g, ""), cells[column]!] as const),
  );
}

/** code → label from a prose line: "Close reasons: `duplicate` (PO trùng), …". */
function list(lead: string): Record<string, string> {
  const start = GLOSSARY.indexOf(`${lead}:`);
  expect(start, `CONTEXT.md has a "${lead}:" line`).toBeGreaterThan(-1);
  const paragraph = GLOSSARY.slice(start).split("\n\n")[0]!.replace(/\n/g, " ");
  const pairs = [...paragraph.matchAll(/`([a-z_]+)`\s*\(([^)]*)\)/g)];
  return Object.fromEntries(pairs.map(([, code, words]) => [code, words]));
}

describe("the Sales labels", () => {
  it.each(Object.entries(GLOSSARY_TABLES))(
    "match CONTEXT.md's %s table, row for row",
    (heading, labels) => {
      expect(labels).toEqual(table(heading));
    },
  );

  it.each(Object.entries(GLOSSARY_LISTS))(
    "match CONTEXT.md's %s, code for code",
    (lead, labels) => {
      expect(labels).toEqual(list(lead));
    },
  );
});
