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
