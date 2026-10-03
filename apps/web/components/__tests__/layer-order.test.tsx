// @vitest-environment node
import { Button } from "antd";
import postcss, { type AtRule, type Root, type Rule } from "postcss";
import { describe, expect, it } from "vitest";
import { compiledGlobals } from "./globals-css";
import { serverStyles } from "./server-styles";

/**
 * The cascade order antd and Tailwind share (CLAUDE.md "Web UI").
 *
 * Both halves fail without an error. If `antd` is missing from the order in
 * `globals.css`, or declared after Tailwind's own statement, antd's layer
 * lands after `utilities` and every Tailwind class on an antd component is
 * ignored. If AntdRegistry loses `layer`, antd's rules are unlayered and beat
 * every utility. So this compiles `globals.css` the way the build does and
 * renders the root the way Next's server does, and reads what comes out.
 */

const ORDER = ["theme", "base", "antd", "components", "utilities"];

/** Layer names in the order they first appear, which is the order the cascade uses. */
function layerOrder(root: Root): string[] {
  const names: string[] = [];
  root.walkAtRules("layer", (rule) => {
    for (const name of rule.params.split(",").map((part) => part.trim())) {
      if (name && !names.includes(name)) names.push(name);
    }
  });
  return names;
}

function enclosing(rule: Rule, name: string): AtRule | undefined {
  for (let node = rule.parent; node && node.type !== "root";) {
    if (node.type === "atrule" && (node as AtRule).name.endsWith(name)) {
      return node as AtRule;
    }
    node = node.parent;
  }
  return undefined;
}

/** Style rules outside every layer; keyframe steps are not style rules. */
function unlayered(root: Root): Rule[] {
  const rules: Rule[] = [];
  root.walkRules((rule) => {
    if (!enclosing(rule, "layer") && !enclosing(rule, "keyframes")) {
      rules.push(rule);
    }
  });
  return rules;
}

describe("cascade layers: Tailwind utilities over antd, antd over Tailwind's base", () => {
  it("globals.css, compiled, puts antd after base and before components and utilities", async () => {
    const order = layerOrder(await compiledGlobals()).filter((name) =>
      ORDER.includes(name),
    );
    expect(order).toEqual(ORDER);
  });

  it("globals.css, compiled, has no style rule outside a layer", async () => {
    const rules = unlayered(await compiledGlobals());
    expect(rules.map((rule) => rule.selector)).toEqual([]);
  });

  it("every antd rule the root sends to the page is in the antd layer", () => {
    const css = postcss.parse(serverStyles(<Button>Gửi</Button>));

    const layers = new Set<string>();
    let buttonRules = 0;
    css.walkRules((rule) => {
      const layer = enclosing(rule, "layer");
      if (!layer) return;
      layers.add(layer.params);
      if (rule.selector.includes(".ant-btn")) buttonRules += 1;
    });
    expect([...layers]).toEqual(["antd"]);
    expect(buttonRules).toBeGreaterThan(0);

    // Outside the layer only custom properties may be declared (the theme's
    // variables, which nothing else declares, so no layer outranks them),
    // plus cssinjs's cache marker on a class no element carries.
    const declaredOutside = unlayered(css)
      .filter((rule) => rule.selector !== ".data-ant-cssinjs-cache-path")
      .flatMap((rule) =>
        rule.nodes.flatMap((node) =>
          node.type === "decl" && !node.prop.startsWith("--")
            ? [`${rule.selector} { ${node.prop} }`]
            : [],
        ),
      );
    expect(declaredOutside).toEqual([]);
  });
});
