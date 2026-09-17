/**
 * Generate TypeScript API types from the OpenAPI snapshot, split per bounded
 * context so two people never regenerate the same file.
 *
 * Input:  contracts/openapi/openapi.json (written by scripts/generate_contracts.py)
 *         contexts.json (path-prefix claims; unclaimed paths -> platform)
 * Output: src/generated/<context>.d.ts (one file per context + platform)
 *
 * Run via `make generate-contracts` (or `pnpm run generate:api-types`).
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import openapiTS, { astToString } from "openapi-typescript";

const pkgDir = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const repoRoot = path.resolve(pkgDir, "..", "..", "..");
const specPath = path.join(repoRoot, "contracts", "openapi", "openapi.json");
const outDir = path.join(pkgDir, "src", "generated");

const spec = JSON.parse(fs.readFileSync(specPath, "utf8"));
const { contexts } = JSON.parse(
  fs.readFileSync(path.join(pkgDir, "contexts.json"), "utf8"),
);

const claimsPath = (prefixes, p) =>
  prefixes.some((pre) => p === pre || p.startsWith(`${pre}/`));

// Each split keeps only the components its paths transitively $ref — otherwise
// every context file embeds the full shared components object and one context
// adding a schema would rewrite all generated files (the conflict this
// generator exists to prevent). securitySchemes are referenced by name in
// `security`, not by $ref, so that section is always kept whole.
const collectRefs = (node, out) => {
  if (Array.isArray(node)) for (const item of node) collectRefs(item, out);
  else if (node && typeof node === "object") {
    for (const [key, value] of Object.entries(node)) {
      if (
        key === "$ref" &&
        typeof value === "string" &&
        value.startsWith("#/components/")
      )
        out.add(value);
      else collectRefs(value, out);
    }
  }
};

const pruneComponents = (fullSpec, paths) => {
  const seen = new Set();
  const queue = [];
  const enqueue = (refs) => {
    for (const ref of refs)
      if (!seen.has(ref)) (seen.add(ref), queue.push(ref));
  };
  const initial = new Set();
  collectRefs(paths, initial);
  enqueue(initial);
  while (queue.length) {
    const [, , section, name] = queue.pop().split("/");
    const target = fullSpec.components?.[section]?.[name];
    if (target === undefined) continue;
    const nested = new Set();
    collectRefs(target, nested);
    enqueue(nested);
  }
  const components = {};
  for (const ref of [...seen].sort()) {
    const [, , section, name] = ref.split("/");
    const value = fullSpec.components?.[section]?.[name];
    if (value !== undefined) (components[section] ??= {})[name] = value;
  }
  if (fullSpec.components?.securitySchemes)
    components.securitySchemes = fullSpec.components.securitySchemes;
  return components;
};

const claimed = new Set();
const splits = contexts.map((ctx) => {
  const paths = Object.fromEntries(
    Object.entries(spec.paths ?? {}).filter(([p]) => {
      const hit = claimsPath(ctx.pathPrefixes, p);
      if (hit) claimed.add(p);
      return hit;
    }),
  );
  return { name: ctx.name, paths };
});
splits.unshift({
  name: "platform",
  paths: Object.fromEntries(
    Object.entries(spec.paths ?? {}).filter(([p]) => !claimed.has(p)),
  ),
});

fs.mkdirSync(outDir, { recursive: true });
const expected = new Set();
for (const { name, paths } of splits) {
  const ast = await openapiTS({
    ...spec,
    paths,
    components: pruneComponents(spec, paths),
  });
  const banner = `/**\n * Auto-generated types for context "${name}" — do not edit.\n * Regenerate with \`make generate-contracts\`.\n */\n`;
  fs.writeFileSync(
    path.join(outDir, `${name}.d.ts`),
    banner + astToString(ast),
  );
  expected.add(`${name}.d.ts`);
  console.log(
    `wrote src/generated/${name}.d.ts (${Object.keys(paths).length} paths)`,
  );
}

for (const file of fs.readdirSync(outDir)) {
  if (file.endsWith(".d.ts") && !expected.has(file)) {
    fs.rmSync(path.join(outDir, file));
    console.log(`removed stale src/generated/${file}`);
  }
}
