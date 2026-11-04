import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, resolve, sep } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * One component system (CLAUDE.md "Web UI"): antd. shadcn/ui, its Radix
 * primitives, its variant helper and sonner were removed on 2026-10-08, and
 * this keeps them out of the web app and of `@dw/ui` alike. ESLint guards the
 * app too, but `@dw/ui` has no lint step, and a dependency can come back in a
 * manifest without any import; this reads both.
 *
 * One exception, Đạt's of 2026-10-23: React Flow (`@xyflow/react`) draws the
 * DW1 process map, and only the file that draws it may import it
 * (`CONFINED`). Any other library a page ships has to be a recorded decision
 * too: the runtime dependencies of both manifests are an allowlist
 * (`RUNTIME_DEPENDENCIES`), so a new UI library fails here before any page
 * imports it.
 *
 * A second, Đạt's of 2026-11-04: Ant Design X (`@ant-design/x`, antd's own
 * chat components) draws the one chat frame, `@dw/ui`'s `AssistantChat`,
 * and only that file imports it.
 */

const WEB = resolve(__dirname, "../..");
const UI = resolve(WEB, "../../packages/typescript/ui");

/** Module specifiers that bring the old system back, or React Flow by another door. */
const FORBIDDEN_MODULE =
  /^(sonner|radix-ui|@radix-ui\/.+|class-variance-authority|lucide-react|cmdk|vaul|tailwind-merge|clsx|@assistant-ui\/.+|reactflow|react-flow-renderer|@xyflow\/(?!react(\/|$)).+)$/;

/**
 * A package allowed only in the files named, paths from `apps/web`. React
 * Flow is the process map's (CLAUDE.md "Web UI", 2026-10-23); its CSS import
 * counts as an import of it.
 */
const CONFINED: Record<string, string[]> = {
  "@xyflow/react": ["app/sales/_components/process-flow.tsx"],
  "@ant-design/x": ["../../packages/typescript/ui/src/assistant-chat.tsx"],
};

/**
 * What the web app and `@dw/ui` ship to the browser, each one decided:
 * antd and its parts, the workspace packages, the framework, dates
 * (`lib/dates.ts`), sign-in, PDF pages, and React Flow for the process map.
 * A dependency added to either manifest fails until it is added here, with
 * its decision in CLAUDE.md. Dev dependencies are not shipped and not listed.
 */
const RUNTIME_DEPENDENCIES = new Set([
  "@ant-design/cssinjs",
  "@ant-design/icons",
  "@ant-design/nextjs-registry",
  "@ant-design/x",
  "@dw/api-client",
  "@dw/contracts",
  "@dw/ui",
  "@xyflow/react",
  "antd",
  "dayjs",
  "keycloak-js",
  "next",
  "pdfjs-dist",
  "react",
  "react-dom",
]);

/** "@xyflow/react/dist/style.css" → "@xyflow/react"; "dayjs/plugin/utc" → "dayjs". */
function packageOf(specifier: string): string {
  const parts = specifier.split("/");
  return specifier.startsWith("@") ? parts.slice(0, 2).join("/") : parts[0]!;
}

/** What `@dw/ui` exported before: none of these may be imported from it. */
const REMOVED_PRIMITIVES = new Set([
  "Alert",
  "AlertDescription",
  "AlertTitle",
  "Badge",
  "badgeVariants",
  "Button",
  "buttonVariants",
  "Card",
  "CardContent",
  "CardDescription",
  "CardFooter",
  "CardHeader",
  "CardTitle",
  "Input",
  "Label",
  "Select",
  "Separator",
  "Skeleton",
  "Switch",
  "Table",
  "TableBody",
  "TableCell",
  "TableHead",
  "TableHeader",
  "TableRow",
  "Tabs",
  "TabsContent",
  "TabsList",
  "TabsTrigger",
  "Textarea",
  "cn",
]);

function sources(root: string): string[] {
  const found: string[] = [];
  const walk = (dir: string) => {
    for (const name of readdirSync(dir)) {
      if (name === "node_modules" || name === ".next" || name.startsWith(".")) {
        continue;
      }
      const path = join(dir, name);
      if (statSync(path).isDirectory()) walk(path);
      else if (/\.(ts|tsx|mts|js|mjs|css)$/.test(name)) found.push(path);
    }
  };
  walk(root);
  return found;
}

// A side-effect import (`import "x.css"`) first: tried later, the lazy
// names of the next alternative would swallow it into the following import.
const IMPORT =
  /import\s+["']([^"']+)["']|(?:import|export)\s+(?:type\s+)?([\s\S]*?)\s+from\s+["']([^"']+)["']|import\s*\(\s*["']([^"']+)["']\s*\)|require\(\s*["']([^"']+)["']\s*\)|@import\s+["']([^"']+)["']/g;

/**
 * Every forbidden import in one source text, as "specifier", "specifier
 * outside <allowed files>" or "name from @dw/ui". `file` is the source's path
 * from `apps/web`, which a confined package is checked against.
 */
export function forbiddenImports(text: string, file = ""): string[] {
  const hits: string[] = [];
  for (const match of text.matchAll(IMPORT)) {
    const names = match[2] ?? "";
    const specifier =
      match[1] ?? match[3] ?? match[4] ?? match[5] ?? match[6] ?? "";
    if (FORBIDDEN_MODULE.test(specifier)) hits.push(specifier);
    const allowed = CONFINED[packageOf(specifier)];
    if (allowed && !allowed.includes(file))
      hits.push(`${specifier} outside ${allowed.join(", ")}`);
    if (specifier === "@dw/ui") {
      for (const raw of names.replace(/[{}]/g, "").split(",")) {
        const name = raw
          .trim()
          .replace(/^type\s+/, "")
          .split(/\s+as\s+/)[0];
        if (name && REMOVED_PRIMITIVES.has(name))
          hits.push(`${name} from @dw/ui`);
      }
    }
  }
  return hits;
}

describe("antd is the only component system", () => {
  it("catches each way the old system could come back", () => {
    expect(forbiddenImports('import { toast } from "sonner";')).toEqual([
      "sonner",
    ]);
    expect(
      forbiddenImports('import { Slot } from "@radix-ui/react-slot";'),
    ).toEqual(["@radix-ui/react-slot"]);
    expect(forbiddenImports('import { Dialog } from "radix-ui";')).toEqual([
      "radix-ui",
    ]);
    expect(
      forbiddenImports(
        'import {\n  PageHeader,\n  Button as B,\n} from "@dw/ui";',
      ),
    ).toEqual(["Button from @dw/ui"]);
    expect(forbiddenImports('import { PageHeader } from "@dw/ui";')).toEqual(
      [],
    );
    expect(forbiddenImports('import { Button } from "antd";')).toEqual([]);
  });

  it("keeps React Flow to the file that draws the process map", () => {
    const flow = "app/sales/_components/process-flow.tsx";
    const use =
      'import "@xyflow/react/dist/style.css";\nimport { ReactFlow } from "@xyflow/react";';
    expect(forbiddenImports(use, flow)).toEqual([]);
    expect(forbiddenImports(use, "app/sales/rules/process/page.tsx")).toEqual([
      `@xyflow/react/dist/style.css outside ${flow}`,
      `@xyflow/react outside ${flow}`,
    ]);
    expect(
      forbiddenImports('const m = await import("@xyflow/react");', "x.tsx"),
    ).toEqual([`@xyflow/react outside ${flow}`]);
    // Not through its engine or its older names, anywhere.
    for (const other of ["@xyflow/system", "reactflow", "react-flow-renderer"])
      expect(forbiddenImports(`import x from "${other}";`, flow)).toEqual([
        other,
      ]);
  });

  it("no source in the web app or @dw/ui imports it", () => {
    const offenders = [...sources(WEB), ...sources(UI)]
      .filter((path) => !path.endsWith("antd-only.test.ts"))
      .flatMap((path) => {
        const file = relative(WEB, path).split(sep).join("/");
        return forbiddenImports(readFileSync(path, "utf8"), file).map(
          (hit) => `${file}: ${hit}`,
        );
      });
    expect(offenders).toEqual([]);
  });

  it("ships no runtime dependency nobody decided on", () => {
    const undecided = [WEB, UI].flatMap((dir) => {
      const manifest = JSON.parse(
        readFileSync(join(dir, "package.json"), "utf8"),
      ) as Record<string, Record<string, string> | undefined>;
      return ["dependencies", "peerDependencies"].flatMap((field) =>
        Object.keys(manifest[field] ?? {})
          .filter((name) => !RUNTIME_DEPENDENCIES.has(name))
          .map((name) => `${relative(WEB, dir) || "apps/web"}: ${name}`),
      );
    });
    expect(undecided).toEqual([]);
  });

  it("no manifest depends on it", () => {
    const offenders = [WEB, UI].flatMap((dir) => {
      const manifest = JSON.parse(
        readFileSync(join(dir, "package.json"), "utf8"),
      ) as Record<string, Record<string, string> | undefined>;
      return ["dependencies", "devDependencies", "peerDependencies"].flatMap(
        (field) =>
          Object.keys(manifest[field] ?? {})
            .filter((name) => FORBIDDEN_MODULE.test(name))
            .map((name) => `${relative(WEB, dir) || "apps/web"}: ${name}`),
      );
    });
    expect(offenders).toEqual([]);
  });

  it("no shadcn primitive file is left in @dw/ui", () => {
    const left = readdirSync(join(UI, "src")).filter((name) =>
      /^(alert|badge|button|card|input|label|separator|skeleton|switch|table|tabs|cn)\.tsx?$/.test(
        name,
      ),
    );
    expect(left).toEqual([]);
  });
});
