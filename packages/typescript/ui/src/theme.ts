import { theme, type MappingAlgorithm, type ThemeConfig } from "antd";

/**
 * The one owner of colour, type, radius and the header's size (CLAUDE.md
 * "Web UI"). Tailwind reads these through the CSS variables antd emits;
 * nothing restates a value.
 *
 * Palette A of design v3, as the S0 spec's token table gives it (values from
 * the v3 shell CSS where the catalogue differs). The catalogue's light error
 * #e0352b is 4.46:1 on white and its dark #ff453a is 3.41:1 under white text;
 * the shell CSS's #c4271e and #d63a30 are the ones taken here, with the dark
 * error text split out as #ff6b61.
 */

/**
 * The class antd declares its CSS variables on (`.css-var-dw { --ant-… }`).
 * antd puts it on each of its own components; the root layout also puts it on
 * `<html>`, so plain elements and portals that are not antd's (a Radix dialog,
 * a toast) read the same tokens.
 */
export const THEME_CSS_VAR_CLASS = "css-var-dw";

/** Height of the top navbar. The header's 1px bottom rule sits inside it. */
const HEADER_HEIGHT = 56;

const light = {
  colorPrimary: "#0071e3",
  colorLink: "#0060c0",
  colorSuccess: "#1f9d4c",
  colorSuccessText: "#146c33",
  colorWarning: "#c26a00",
  colorWarningText: "#9a5200",
  colorError: "#c4271e",
  colorErrorText: "#c4271e",
  colorText: "#1d1d1f",
  colorTextSecondary: "#515154",
  colorTextTertiary: "#6e6e73",
  colorBgLayout: "#f5f5f7",
  colorBgContainer: "#ffffff",
  colorBorderSecondary: "#e3e3e8",
};

const dark: typeof light = {
  colorPrimary: "#0071e3",
  colorLink: "#4da3ff",
  colorSuccess: "#30d158",
  colorSuccessText: "#30d158",
  colorWarning: "#ff9f0a",
  colorWarningText: "#ff9f0a",
  colorError: "#d63a30",
  colorErrorText: "#ff6b61",
  colorText: "#f5f5f7",
  colorTextSecondary: "#c7c7cc",
  colorTextTertiary: "#8e8e93",
  colorBgLayout: "#000000",
  colorBgContainer: "#1c1c1e",
  colorBorderSecondary: "#3a3a3c",
};

/** The dark danger button's hover: lighter than its #ff6b61 label, as antd
 * lightens a hover in dark mode. */
const DARK_ERROR_TEXT_HOVER = "#ff8a82";

/**
 * These five are antd *seed* tokens. antd drops a seed key from the token
 * override and keeps what the algorithm derived from it, which in light is
 * the seed itself and in dark is not: the dark algorithm turns #0071e3 into
 * #0363c4 (antd 6.6.5, theme/util/alias.js). Running after the base
 * algorithm, this puts the seeds back, so both modes render what the palette
 * says. The colours derived around them (hover, border, background) stay
 * antd's.
 */
const keepSeedColors: MappingAlgorithm = (seed, map) => ({
  ...map!,
  colorPrimary: seed.colorPrimary,
  colorLink: seed.colorLink,
  colorSuccess: seed.colorSuccess,
  colorWarning: seed.colorWarning,
  colorError: seed.colorError,
});

export type ColorMode = "light" | "dark";

/**
 * @param fontFamily the family the app loaded (next/font renames it, so the
 *   app passes what it got); antd's own system stack follows it.
 */
export function buildTheme(mode: ColorMode, fontFamily: string): ThemeConfig {
  const palette = mode === "dark" ? dark : light;
  return {
    algorithm: [
      mode === "dark" ? theme.darkAlgorithm : theme.defaultAlgorithm,
      keepSeedColors,
    ],
    cssVar: { key: THEME_CSS_VAR_CLASS },
    token: {
      ...palette,
      borderRadius: 8,
      borderRadiusLG: 12,
      controlHeight: 32,
      fontSize: 14,
      fontFamily: `${fontFamily}, ${theme.defaultSeed.fontFamily}`,
    },
    components: {
      Layout: {
        headerHeight: HEADER_HEIGHT,
        headerBg: palette.colorBgContainer,
      },
      Menu: {
        // The selected item's bar lands on the header's bottom rule.
        horizontalLineHeight: `${HEADER_HEIGHT - 1}px`,
        // No rule down the side of the menu in the navigation drawer.
        activeBarBorderWidth: 0,
        // antd colours the current item with colorPrimary. In the drawer and
        // the "…" popup it sits on colorPrimaryBg, where light #0071e3 is
        // 4.27:1 and the link colour 5.57:1, so it takes the link colour in
        // both modes.
        itemSelectedColor: palette.colorLink,
        // On the dark header colorPrimary, current or hovered, is 3.62:1 and
        // the link colour 6.48:1. On the light header it is 4.70:1 and stays.
        ...(mode === "dark" && {
          horizontalItemSelectedColor: palette.colorLink,
          horizontalItemHoverColor: palette.colorLink,
        }),
      },
      // A status tag writes its text in the status colour on that colour's
      // own tint. The status colour is for icons, borders and fills: light
      // success on its tint is 2.96:1 and warning 3.27:1, dark error 3.4:1.
      // The status text colours are the ones made for text.
      Tag: {
        colorSuccess: palette.colorSuccessText,
        colorWarning: palette.colorWarningText,
        colorError: palette.colorErrorText,
      },
      // A danger button that is not filled writes its label in colorError:
      // dark #d63a30 on the card is 3.65:1. In dark mode it takes the error
      // text colour, and a filled one, now that light, takes the card colour
      // for its label instead of white (white on #ff6b61 is 2.6:1).
      ...(mode === "dark" && {
        Button: {
          colorError: palette.colorErrorText,
          colorErrorHover: DARK_ERROR_TEXT_HOVER,
          colorErrorActive: palette.colorError,
          dangerColor: palette.colorBgContainer,
        },
      }),
    },
  };
}
