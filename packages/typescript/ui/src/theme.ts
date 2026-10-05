"use client";

// A client module although it holds no component: building the theme calls
// into antd, which is client code. Without the line above, a server component
// importing anything from the @dw/ui index (a Card, say) would evaluate it on
// the server, and `next build` fails that page ("getDesignToken is not a
// function").
import { theme, type ThemeConfig } from "antd";
import { FONT_VARIABLE, THEME_ROOT_CLASS } from "./theme-class";

/**
 * The seeds: the E-HSDT v3 prototype's light palette (its `[data-ap="light"]`
 * variables and the token table on its `#catalog` screen), primary #0071e3 as
 * decided by Đạt on 2026-10-05. Where a prototype value fails
 * `.claude/rules/ui-quality.md` §12 as rendered here, the nearest value that
 * passes is used instead, and the line says so; `theme.test.ts` measures every
 * pair.
 */
const seed: ThemeConfig["token"] = {
  // #0071e3 is 4.31:1 as text on the page background (#f5f5f7), so the
  // nearest blue that reaches 4.5:1 there. White on it is 4.9:1.
  colorPrimary: "#006edc",
  // Hover and press go darker, never lighter: white text stays above 4.5:1.
  colorPrimaryHover: "#0064c8",
  colorPrimaryActive: "#0058b0",
  // The prototype's selection tint (--sel, #ebf4fd) carries primary text at
  // 4.4:1; the nearest lighter tint passes.
  colorPrimaryBg: "#f0f7ff",
  colorPrimaryBgHover: "#e6f1fc",
  // The focus ring is drawn in this colour: 3:1 against the surfaces.
  colorPrimaryBorder: "#2f86e4",
  colorPrimaryBorderHover: "#006edc",
  colorPrimaryText: "#0060c0",
  colorPrimaryTextHover: "#0058b0",
  colorPrimaryTextActive: "#004f9e",
  colorLink: "#0060c0",
  colorLinkHover: "#0058b0",
  colorLinkActive: "#004f9e",
  colorInfo: "#006edc",
  colorInfoText: "#0060c0",
  colorInfoBg: "#e6f1fc",
  colorInfoBorder: "#b9d7f6",
  colorSuccess: "#1f9d4c",
  colorSuccessText: "#146c33",
  colorSuccessBg: "#e3f7e8",
  colorSuccessBorder: "#a9dfbb",
  // The seed draws icons and tints (3:1); its text step needs 4.5:1.
  colorWarning: "#c26a00",
  colorWarningText: "#9a5200",
  colorWarningBg: "#fff0d8",
  colorWarningBorder: "#f5cf94",
  // The catalog's #e0352b is 4.46:1 on white; the prototype's own --err passes.
  colorError: "#c4271e",
  colorErrorText: "#c4271e",
  colorErrorBg: "#ffebea",
  colorErrorBorder: "#f5b5b0",
  colorTextBase: "#1d1d1f",
  colorText: "#1d1d1f",
  colorTextSecondary: "#515154",
  colorTextTertiary: "#6e6e73",
  colorTextQuaternary: "#86868b",
  colorBgLayout: "#f5f5f7",
  colorBgContainer: "#ffffff",
  // A field's border is what shows where to type: the prototype's #8e8e93 is
  // 2.99:1 on the page background, so the nearest grey that reaches 3:1.
  colorBorder: "#8c8c91",
  colorBorderSecondary: "#e3e3e8",
  colorSplit: "rgba(60, 60, 67, 0.12)",
  colorFill: "rgba(120, 120, 128, 0.16)",
  colorFillSecondary: "rgba(120, 120, 128, 0.08)",
  colorFillTertiary: "rgba(120, 120, 128, 0.05)",
  colorFillQuaternary: "rgba(120, 120, 128, 0.03)",
  // Self-hosted by next/font in the root layout (no request to Google at run
  // time); the names after the variable are the fallback before it loads.
  fontFamily: `var(${FONT_VARIABLE.sans}), "Be Vietnam Pro", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif`,
  fontFamilyCode: `var(${FONT_VARIABLE.mono}), "JetBrains Mono", ui-monospace, SFMono-Regular, Consolas, monospace`,
  fontSize: 14,
  // The catalog: controls 8, cards 12, dialogs 16; buttons are pills below.
  borderRadius: 8,
  borderRadiusLG: 12,
  borderRadiusSM: 6,
  controlHeight: 32,
  boxShadowTertiary:
    "0 1px 1px rgba(0, 0, 0, 0.03), 0 8px 24px rgba(0, 0, 0, 0.05)",
};

const derived = theme.getDesignToken({ token: seed });

/**
 * The status tag tones, from the prototype's label table (`V3Tag`'s TONES):
 * a tint, the text drawn on it, and a border only where the tone has one.
 * `unk` (the unknown state) is dashed purple and means nothing else.
 * `theme.test.ts` measures every text-on-tint pair, composited on both
 * surfaces where the tint is translucent.
 */
export const STATUS_TONES = {
  ok: { bg: seed.colorSuccessBg!, fg: seed.colorSuccessText!, border: null },
  err: { bg: seed.colorErrorBg!, fg: seed.colorErrorText!, border: null },
  warn: { bg: seed.colorWarningBg!, fg: seed.colorWarningText!, border: null },
  gold: { bg: "#fff5cc", fg: "#855c00", border: null },
  pri: { bg: seed.colorInfoBg!, fg: seed.colorInfoText!, border: null },
  geek: { bg: "#eaeefd", fg: "#1d39c4", border: null },
  unk: { bg: "#f7eefc", fg: "#7b36b3", border: "#7b36b3" },
  gray: { bg: seed.colorFill!, fg: seed.colorTextSecondary!, border: null },
  grayStrong: { bg: seed.colorFill!, fg: seed.colorText!, border: null },
  outline: {
    bg: "transparent",
    fg: seed.colorTextSecondary!,
    border: seed.colorBorder!,
  },
} as const;

export type StatusTone = keyof typeof STATUS_TONES;

/** The tag's shape: a pill for a status, a soft square for a code. */
export const STATUS_TAG_SHAPE = {
  radius: 999,
  codeRadius: 6,
  weight: 600,
  codeWeight: 500,
  paddingInline: 8,
} as const;

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
    // texts) reads the tertiary step, which the prototype sets at 4.66:1.
    colorTextDescription: seed.colorTextTertiary,
  },
  components: {
    // The navbar is sticky: `globals.css` pads the page's scroll by this
    // height so it never covers the focused element (WCAG 2.4.11). The
    // prototype's bar is 56px of frosted white.
    Layout: {
      headerBg: "rgba(255, 255, 255, 0.82)",
      headerHeight: 56,
      headerPadding: "0 20px",
      bodyBg: derived.colorBgLayout,
    },
    Menu: {
      itemBg: "transparent",
      horizontalItemSelectedBg: "transparent",
      horizontalLineHeight: "54px",
      itemColor: seed.colorTextSecondary,
      itemHoverColor: seed.colorText,
      itemPaddingInline: 12,
      activeBarHeight: 2,
    },
    // Buttons are pills in the prototype (`--btnR: 999px`).
    Button: {
      borderRadius: 999,
      borderRadiusLG: 999,
      borderRadiusSM: 999,
      fontWeight: 500,
      primaryShadow: "none",
      defaultShadow: "none",
      dangerShadow: "none",
    },
    Card: {
      headerFontSize: 14,
      headerFontSizeSM: 14,
      headerHeightSM: 42,
    },
    Table: {
      headerBg: derived.colorBgContainer,
      headerColor: seed.colorTextSecondary,
      headerSplitColor: "transparent",
      cellPaddingBlock: 10,
      cellPaddingInline: 12,
      cellPaddingBlockSM: 8,
      cellPaddingInlineSM: 10,
      rowHoverBg: "rgba(120, 120, 128, 0.05)",
      footerBg: derived.colorBgContainer,
      footerColor: seed.colorTextTertiary,
    },
    Segmented: {
      trackBg: "rgba(120, 120, 128, 0.12)",
      itemSelectedBg: derived.colorBgContainer,
      itemColor: seed.colorText,
      itemHoverColor: seed.colorText,
      trackPadding: 2,
    },
    Tabs: {
      itemColor: seed.colorTextSecondary,
      itemSelectedColor: seed.colorText,
      itemHoverColor: seed.colorText,
      inkBarColor: seed.colorText,
    },
    Modal: { borderRadiusLG: 16 },
    Alert: { borderRadiusLG: 12 },
    Breadcrumb: {
      itemColor: seed.colorTextTertiary,
      linkColor: seed.colorTextTertiary,
      lastItemColor: seed.colorTextTertiary,
      separatorColor: seed.colorTextTertiary,
    },
  },
};
