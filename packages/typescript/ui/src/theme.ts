"use client";

// A client module although it holds no component: building the theme calls
// into antd, which is client code. Without the line above, a server component
// importing anything from the @dw/ui index (a Card, say) would evaluate it on
// the server, and `next build` fails that page ("getDesignToken is not a
// function").
import { theme, type ThemeConfig } from "antd";
import { THEME_ROOT_CLASS } from "./theme-class";

/**
 * The seeds: the navy palette the app shipped with, and where a derived value
 * fails `.claude/rules/ui-quality.md` §12, the value that passes.
 */
const seed: ThemeConfig["token"] = {
  colorPrimary: "#0b3155",
  // antd derives the hover, active and tint steps from the seed's generated
  // palette, and for a seed this dark the tints come out grey (#8a9194 as the
  // selected-item background). The steps are written out instead.
  colorPrimaryHover: "#123f67",
  colorPrimaryActive: "#071f38",
  colorPrimaryBg: "#e4edf5",
  colorPrimaryBgHover: "#c8dfef",
  // The focus ring is drawn in this colour: 3:1 against the surfaces.
  colorPrimaryBorder: "#5b85ab",
  colorPrimaryBorderHover: "#4a7299",
  colorPrimaryText: "#0b3155",
  colorPrimaryTextHover: "#123f67",
  colorPrimaryTextActive: "#071f38",
  colorInfo: "#2673a6",
  colorSuccess: "#007a3d",
  // The seed draws icons and tints (3:1); its text step needs 4.5:1.
  colorWarning: "#b87400",
  colorWarningText: "#8f5b00",
  colorError: "#c10007",
  colorTextBase: "#10243e",
  colorBgLayout: "#f4f7fb",
  // A field's border is what shows where to type: 3:1 against white.
  colorBorder: "#7d8ea3",
  colorBorderSecondary: "#dce4ec",
  borderRadius: 10,
};

const derived = theme.getDesignToken({ token: seed });

/**
 * The one owner of colour, type, radius and motion (CLAUDE.md "Web UI").
 *
 * Nothing else defines a colour: Tailwind's colours are these variables, and a
 * screen reads `theme.useToken()` or `--ant-*`.
 * `apps/web/components/__tests__/theme.test.ts` measures every contrast pair
 * the UI rules name, and checks that every variable `globals.css` maps exists.
 */
export const appTheme: ThemeConfig = {
  cssVar: { key: THEME_ROOT_CLASS },
  token: {
    ...seed,
    // antd's description text (`Typography type="secondary"`, help and empty
    // texts) is the tertiary step, 2.8:1. Lifted to the secondary step so a
    // reason or a hint written in it can be read (ui-quality §12).
    colorTextDescription: derived.colorTextSecondary,
  },
  components: {
    // The navbar is sticky: `globals.css` pads the page's scroll by this
    // height so it never covers the focused element (WCAG 2.4.11).
    Layout: { headerBg: derived.colorBgContainer, headerHeight: 64 },
  },
};
