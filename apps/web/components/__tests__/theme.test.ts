// @vitest-environment node
import { readFileSync } from "node:fs";
import { theme } from "antd";
import postcss, { type AtRule, type Declaration } from "postcss";
import { describe, expect, it } from "vitest";
import {
  appTheme,
  FONT_VARIABLE,
  STATUS_TONES,
  THEME_ROOT_CLASS,
} from "@dw/ui";
import { compiledGlobals, GLOBALS } from "./globals-css";
import { serverStyles } from "./server-styles";

/**
 * The antd theme in @dw/ui is the one owner of colour, type, radius and
 * breakpoints (CLAUDE.md "Web UI"); `globals.css` only points Tailwind at it.
 * These tests make the two disagree loudly: a mapped name that resolves to
 * nothing, a colour defined a second time, a breakpoint 32px off, a contrast
 * pair the UI rules name (`.claude/rules/ui-quality.md` §12) that fails.
 */

const globals = postcss.parse(readFileSync(GLOBALS, "utf8"));
const token = theme.getDesignToken(appTheme);

function declarations(atRule: string, params: string): Declaration[] {
  const found: Declaration[] = [];
  globals.walkAtRules(atRule, (rule: AtRule) => {
    if (rule.params === params) rule.walkDecls((decl) => void found.push(decl));
  });
  return found;
}

/**
 * The variables the theme puts on the root class: the ones `<html>` has.
 * Rendered with no antd component at all, as the sign-in screen is, so a
 * variable only some component brings with it does not count.
 */
function rootVariables(): Set<string> {
  const css = postcss.parse(serverStyles("Nội dung"));
  const names = new Set<string>();
  css.walkRules((rule) => {
    if (rule.selector !== `.${THEME_ROOT_CLASS}`) return;
    rule.walkDecls((decl) => void names.add(decl.prop));
  });
  return names;
}

// ---------------------------------------------------------------- contrast

type Rgba = [number, number, number, number];

function parseColour(value: string): Rgba {
  const hex = value.trim().match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (hex) {
    const digits =
      hex[1]!.length === 3
        ? [...hex[1]!].map((digit) => digit + digit).join("")
        : hex[1]!;
    return [0, 2, 4]
      .map((at) => parseInt(digits.slice(at, at + 2), 16))
      .concat(1) as Rgba;
  }
  const rgb = value.trim().match(/^rgba?\(([^)]+)\)$/i);
  if (!rgb) throw new Error(`not a colour this test reads: ${value}`);
  const [r, g, b, a = 1] = rgb[1]!.split(",").map(Number);
  return [r!, g!, b!, a];
}

function luminance([r, g, b]: Rgba): number {
  const channel = (value: number) => {
    const c = value / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

/** WCAG contrast of `fore` drawn on `back`; a translucent `fore` is composited first. */
function contrast(fore: string, back: string): number {
  const b = parseColour(back);
  const [r, g, bl, alpha] = parseColour(fore);
  const f: Rgba = [
    r * alpha + b[0] * (1 - alpha),
    g * alpha + b[1] * (1 - alpha),
    bl * alpha + b[2] * (1 - alpha),
    1,
  ];
  const [light, dark] = [luminance(f), luminance(b)].sort((x, y) => y - x);
  return (light! + 0.05) / (dark! + 0.05);
}

type ColourToken = {
  [K in keyof typeof token]: (typeof token)[K] extends string ? K : never;
}[keyof typeof token];

const SURFACES: ColourToken[] = ["colorBgContainer", "colorBgLayout"];

/** `colour` drawn over `back`, as one opaque hex: a translucent tint as rendered. */
function over(colour: string, back: string): string {
  const b = parseColour(back);
  const [r, g, bl, alpha] = parseColour(colour);
  const hex = [r, g, bl]
    .map((c, i) => Math.round(c * alpha + b[i]! * (1 - alpha)))
    .map((c) => c.toString(16).padStart(2, "0"))
    .join("");
  return `#${hex}`;
}

describe("theme contrast (ui-quality §12)", () => {
  const text: ColourToken[] = [
    "colorText",
    "colorTextSecondary",
    "colorTextDescription",
    "colorPrimary",
    "colorLink",
    "colorError",
    "colorErrorText",
    "colorSuccessText",
    "colorWarningText",
    "colorInfoText",
  ];
  it.each(text.flatMap((fore) => SURFACES.map((back) => [fore, back])))(
    "%s on %s is text: 4.5:1",
    (fore, back) => {
      expect(contrast(token[fore], token[back])).toBeGreaterThanOrEqual(4.5);
    },
  );

  const onFills: Array<[ColourToken, ColourToken]> = [
    ["colorTextLightSolid", "colorPrimary"],
    ["colorTextLightSolid", "colorPrimaryHover"],
    ["colorTextLightSolid", "colorPrimaryActive"],
    ["colorTextLightSolid", "colorError"],
    ["colorPrimary", "colorPrimaryBg"],
    ["colorText", "colorPrimaryBg"],
  ];
  it.each(onFills)("%s on %s is text: 4.5:1", (fore, back) => {
    expect(contrast(token[fore], token[back])).toBeGreaterThanOrEqual(4.5);
  });

  // The focus ring, a field's border, and the status colours drawn as icons.
  const nonText: ColourToken[] = [
    "colorPrimaryBorder",
    "colorBorder",
    "colorError",
    "colorWarning",
    "colorSuccess",
    "colorInfo",
  ];
  it.each(nonText.flatMap((fore) => SURFACES.map((back) => [fore, back])))(
    "%s on %s is a non-text boundary or icon: 3:1",
    (fore, back) => {
      expect(contrast(token[fore], token[back])).toBeGreaterThanOrEqual(3);
    },
  );
});

describe("status tags and the navbar, as rendered (ui-quality §12)", () => {
  // A tag's text on its own tint is the trap §12 names: measured on both
  // surfaces, a translucent tint composited onto each first.
  const tones = Object.entries(STATUS_TONES).flatMap(([tone, { bg, fg }]) =>
    SURFACES.map((surface) => [tone, surface, bg, fg] as const),
  );
  it.each(tones)("the %s tag's text on %s is text: 4.5:1", (_, surface, bg) => {
    const back =
      bg === "transparent" ? token[surface] : over(bg, token[surface]);
    const fg = STATUS_TONES[_ as keyof typeof STATUS_TONES].fg;
    expect(contrast(fg, back)).toBeGreaterThanOrEqual(4.5);
  });

  it("the unknown tone keeps a border of its own colour, dashed in the tag", () => {
    expect(STATUS_TONES.unk.border).toBe(STATUS_TONES.unk.fg);
    expect(
      contrast(STATUS_TONES.unk.border!, token.colorBgContainer),
    ).toBeGreaterThanOrEqual(3);
  });

  // The bar is translucent white over the page: its links are measured on
  // the colour that results, the page showing through.
  const header = over(
    String(appTheme.components?.Layout?.headerBg),
    token.colorBgLayout,
  );
  it.each([
    ["the menu's text", String(appTheme.components?.Menu?.itemColor)],
    ["the selected item", token.colorPrimary],
    ["the page's own text", token.colorText],
  ])("%s on the navbar is text: 4.5:1", (_, fore) => {
    expect(contrast(fore, header)).toBeGreaterThanOrEqual(4.5);
  });
});

describe("the theme's type is the type the root layout loads", () => {
  const layout = readFileSync(
    new URL("../../app/layout.tsx", import.meta.url),
    "utf8",
  );

  it.each(Object.entries(FONT_VARIABLE))(
    "%s: next/font declares %s and the theme reads it",
    (kind, name) => {
      expect(layout).toContain(`variable: "${name}"`);
      const family = kind === "sans" ? token.fontFamily : token.fontFamilyCode;
      expect(family.startsWith(`var(${name})`)).toBe(true);
    },
  );
});

describe("globals.css takes its visual facts from the theme", () => {
  const themeInline = declarations("theme", "inline").filter((decl) =>
    /^--(color|radius|font)-/.test(decl.prop),
  );

  it("maps Tailwind's colours, radii and fonts", () => {
    expect(themeInline.map((decl) => decl.prop)).toEqual(
      expect.arrayContaining([
        "--color-primary",
        "--color-background",
        "--color-foreground",
        "--color-border",
        "--radius-lg",
        "--font-sans",
      ]),
    );
  });

  it("points every one of them at a variable the theme puts on <html>", () => {
    const emitted = rootVariables();
    const dangling = themeInline.flatMap((decl) => {
      const used = [...decl.value.matchAll(/var\((--[a-z0-9-]+)\)/g)].map(
        (match) => match[1]!,
      );
      if (used.length === 0) return [`${decl.prop}: ${decl.value}`];
      return used
        .filter((name) => !name.startsWith("--ant-") || !emitted.has(name))
        .map((name) => `${decl.prop} -> ${name}`);
    });
    expect(dangling).toEqual([]);
  });

  it("reads no variable that nothing defines, anywhere in the file", async () => {
    // A `var()` with no fallback must resolve: to the theme's variables on
    // <html>, or to a variable the compiled file declares (the names its
    // @theme blocks map). A typo is no error in CSS, only an unset colour, and
    // a rule in @layer base is as exposed to one as the mapping above.
    const defined = rootVariables();
    (await compiledGlobals()).walkDecls((decl) => {
      if (decl.prop.startsWith("--")) defined.add(decl.prop);
    });
    const dangling: string[] = [];
    globals.walkDecls((decl) => {
      for (const [, name] of decl.value.matchAll(/var\(\s*(--[\w-]+)\s*\)/g)) {
        if (!defined.has(name!)) dangling.push(`${decl.prop} -> ${name}`);
      }
    });
    expect(dangling).toEqual([]);
  });

  it("defines no colour of its own", () => {
    const literal =
      /#[0-9a-f]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab|lab|lch|hwb)\(|(?:^|[\s,(])(?:white|black)(?:$|[\s,)])/i;
    const colours: string[] = [];
    globals.walkDecls((decl) => {
      if (literal.test(decl.value)) colours.push(`${decl.prop}: ${decl.value}`);
    });
    expect(colours).toEqual([]);
  });

  it("switches at antd's screen widths", () => {
    const breakpoints = Object.fromEntries(
      declarations("theme", "")
        .filter((decl) => decl.prop.startsWith("--breakpoint-"))
        .map((decl) => [decl.prop, decl.value]),
    );
    expect(breakpoints).toEqual({
      "--breakpoint-sm": `${token.screenSM}px`,
      "--breakpoint-md": `${token.screenMD}px`,
      "--breakpoint-lg": `${token.screenLG}px`,
      "--breakpoint-xl": `${token.screenXL}px`,
      "--breakpoint-2xl": `${token.screenXXL}px`,
    });
  });

  it("pads the page's scroll by the sticky navbar's height", () => {
    const padding = declarations("layer", "base").find(
      (decl) =>
        decl.prop === "scroll-padding-top" &&
        (decl.parent as { selector?: string }).selector === "html",
    );
    expect(padding?.value).toBe(
      `${appTheme.components?.Layout?.headerHeight}px`,
    );
  });
});
