# Web UI shell

`apps/web` and the shared `@dw/ui` package. CLAUDE.md's "Required stack"
names **Next.js, TypeScript strict, Tailwind, shadcn/ui** and "one shared UI
shell". Changing either is an architecture decision that has to be recorded
there, not a refactor.

## What the shell is (measured 2026-09-28)

- **Framework:** Next 15.5.25 (App Router), React 19.2.8, TypeScript 5.9.3.
- **Styling:** Tailwind 4.3.3; colour tokens in `app/globals.css`. There is
  no dark mode and no i18n library; the Vietnamese copy is hard-coded, and
  `lib/dates.ts` formats dates by hand.
- **Components:**
    - `@dw/ui`: 12 shadcn-style modules. Select and Switch are native elements,
      not Radix.
    - `components/ui`: 7 shadcn files, used by the assistant-ui pieces.
    - Also in use: radix-ui, lucide-react, sonner.
- **Usage:**
    - 42 of 70 non-test `.tsx` files import `@dw/ui`.
    - 927 `className=` uses in 59 files.
    - Most-used components: Button 54, TableCell 44, Card 31.
- **Missing kinds of widget:** no date inputs and no form library.
  `@tanstack/react-table` is declared, but its only user,
  `components/data-table.tsx`, is imported by nothing.

## Ant Design assessment (Đạt asked, 2026-09-28)

Measured in a scratch app with the repo's exact Next and React versions. The
repo was not touched.

- **antd v6.6.5 works:** peer `react >=18`, no React-19 patch needed, and
  `next build` produced zero warnings. `vi_VN` locale, `message` and
  `Modal.confirm` all ran clean in Playwright.
- **Cost:**
    - +250 kB first-load JS on a page using ConfigProvider, Table, Form,
      Select and DatePicker (104 → 354 kB);
    - about 420 KB of CSS inlined into that page's HTML;
    - a dev compile of 3 518 modules against 545.
- **Tailwind conflict:** Tailwind classes on antd components are silently
  ignored unless both `AntdRegistry layer` and
  `@layer theme, base, antd, components, utilities;` come before
  `@import "tailwindcss"`. That setup fails silently when it is wrong.

**Recommendation: option C.** Keep the stack, and add a focused library when a
screen first needs one:

- TanStack Table through the existing `DataTable`;
- react-hook-form with zod for complex forms;
- react-day-picker for the first date field.

Why not A or B: option A (full switch, about 60 files) and option B (antd for
tables, forms and dates only, about 10–12 files) both pay a fixed cost up
front: bundle size, two styling systems, and a CSS layer order that breaks
silently. That buys widgets the app does not use yet. A also still leaves the
927 Tailwind layout classes and the assistant-ui pieces on Tailwind.

**If Đạt still wants antd, the decision recorded in CLAUDE.md must settle:**

1. Replace shadcn/ui or coexist with it, and which component comes from
   which system.
2. v6 only.
3. The CSS layer order, with a test that fails without it.
4. One owner of the colour tokens, feeding both Tailwind and the antd theme.
5. The accepted bundle increase.
6. Who owns date formatting: `lib/dates.ts`, or antd/dayjs.
7. Whether `@dw/ui` becomes antd wrappers, so "one shared UI shell" stays
   true.

## Decision (Đạt, 2026-09-28): switch to antd v6

Đạt chose antd over option C after seeing a working antd v6 prototype with
a top navbar. CLAUDE.md "Web UI" records the seven
points above. Its settled answers are: replace shadcn/ui, page by page; the
antd theme owns the tokens; dayjs behind `lib/dates.ts`; and `@dw/ui` holds
the theme, the shell and the shared composites, not primitive wrappers.

## Open

- 2026-10-03: the first slice landed (Sales ticket 07): antd 6.6.5, icons,
  nextjs-registry and dayjs pinned; `AntdRegistry` on the `antd` layer with a
  layer-order test that goes red without either half; the antd theme owns
  the tokens and Tailwind maps to its variables; a top navbar with a drawer
  below 992 px; `lib/dates.ts` (Asia/Ho_Chi_Minh, time first, "Không rõ")
  and `lib/money.ts`; `lang="vi"`; `globals.css` rules all in `@layer base`;
  Tailwind breakpoints equal antd's; muted text at 4.5:1 or above. Shell
  cost: about 130 kB first-load JS per route.
- The web vitest suite is not run by CI (one step in `frontend-quality`).
- `next build` fails on this Windows account at the standalone symlink copy
  (EPERM), as it does at HEAD; the Linux builder stage passes.
- Still open from the 2026-09-30 ui-quality gaps:
    - many platform screens and labels are English under `lang="vi"`;
    - sonner's `<Toaster>` and `useCachedResource`'s raw `failure.message`
      toast; feedback moves to `App.useApp()` page by page;
    - the API client sends no `Idempotency-Key`;
    - `playwright.config.ts` has one Desktop Chrome project: no viewport
      projects, no non-Vietnam `timezoneId`, no screenshot script;
    - no offline banner or session-expiry warning (the header's workspace
      switcher, bell and account menu are antd since 2026-10-05).

## Theme from the E-HSDT v3 prototype (2026-10-05, uncommitted)

Đạt: "chỉnh giao diện cho giống bản design". The prototype's light palette
and its `#catalog` token table are the source; `@dw/ui/src/theme.ts` is the
one place they land, and `theme.test.ts` measures every pair. Mapping kept
here once (ui-quality: "the product records that mapping once"):

- **Primary:** decided `#0071e3` (Đạt, 2026-10-05). It is 4.31:1 as text on
  the page background `#f5f5f7`, so the theme uses the nearest passing blue,
  `#006edc` (4.52:1; white on it 4.9:1). Hover/press go darker (`#0064c8`,
  `#0058b0`). The selection tint `--sel` (#ebf4fd) carries primary text at
  4.4:1, so `colorPrimaryBg` is `#f0f7ff`. Links `#0060c0` (`--link`).
- **Other nearest-passing values:** field border `#8c8c91` (prototype
  `#8e8e93` is 2.99:1 on the page); error `#c4271e` (the prototype's `--err`;
  the catalog's `#e0352b` is 4.46:1 on white). Everything else is the
  prototype's value: text `#1d1d1f`/`#515154`/`#6e6e73`, page `#f5f5f7`,
  separators `#e3e3e8`, status text-on-tint pairs (`okTx`, `warnTx`, …).
- **Type:** Be Vietnam Pro (Vietnamese subset) and JetBrains Mono for codes,
  self-hosted by `next/font` in `app/layout.tsx` (fetched at build, no call
  to Google at run time); the variable names live in `FONT_VARIABLE` and a
  test compares them with the layout's literals.
- **Shape:** radius 8 controls / 12 cards / 16 dialogs, buttons as pills;
  56px frosted navbar (`scroll-padding-top` follows).
- **Status tags:** `@dw/ui` `StatusTag` with the prototype's label-table
  tones (`STATUS_TONES`): tint + its text colour, pill, icon; `unk` dashed
  purple only. antd's own status tags draw `colorSuccess` etc. as text on
  their tint (fails 4.5:1), which is why the tag reads the theme's pairs.
- **Shell:** the bar is words only (icons stay in the drawer); brand, then
  the workspace block, the pages with count pills, bell, account (initials;
  name and role from 1600px, always in its menu). `barNav`: someone who
  reaches exactly one bounded context (`NavGroup.context`) and administers
  nothing gets that context's pages as the bar; administrators keep every
  menu. Role names come from `/auth/bootstrap` `role_names`
  (`platform.roles.name`); the English `ROLE_LABELS` remain for platform
  roles only.
- **Not taken from the prototype:** list rows sit on white tables, not on the
  page grey (a translucent table breaks sticky headers and fixed columns);
  no dark mode, no command palette, no motion beyond antd's; selected menu
  items are primary-coloured, not bold black.
