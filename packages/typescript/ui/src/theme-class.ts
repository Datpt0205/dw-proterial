/**
 * The class that carries the theme's CSS variables.
 *
 * antd emits every token as an `--ant-*` custom property on the elements that
 * carry `cssVar.key` as a class. Its own components carry it; the root layout
 * also puts it on `<html>`, so the page itself, Tailwind's colour utilities
 * (mapped in `apps/web/app/globals.css`) and whatever a non-antd library
 * portals to `<body>` read the same values instead of a second copy.
 *
 * A module of its own, exported as `@dw/ui/theme-class`, for the root layout.
 * A server component importing the package's index pulls every client module
 * the index re-exports into the page's JavaScript, and in the root layout that
 * is every page (measured 2026-10-03: about 4 kB on each route) for one
 * string.
 */
export const THEME_ROOT_CLASS = "dw-theme";

/**
 * The CSS variables the root layout's `next/font` loaders put on `<html>`,
 * which the theme's `fontFamily` and `fontFamilyCode` read. `next/font` takes
 * only literals, so `apps/web/app/layout.tsx` writes these names out again;
 * `theme.test.ts` fails the day the two differ.
 */
export const FONT_VARIABLE = {
  /** Be Vietnam Pro, Vietnamese subset: every UI text. */
  sans: "--font-dw-sans",
  /** JetBrains Mono: codes and identifiers. */
  mono: "--font-dw-mono",
} as const;

/**
 * The two seeds a server route needs without the theme: the installed app's
 * manifest (`apps/web/app/manifest.ts`) colours its title bar and splash with
 * them. `theme.ts` seeds antd from these same constants, so each value has one
 * owner; it is a client module, and a server route cannot read its values.
 */
export const PRIMARY_COLOR = "#006edc";
export const PAGE_BACKGROUND = "#f5f5f7";
