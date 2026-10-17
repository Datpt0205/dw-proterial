# Web UI shell

`apps/web` and the shared `@dw/ui` package. CLAUDE.md's "Required stack"
names **Next.js, TypeScript strict, Ant Design v6, Tailwind for layout only**
(its "Web UI" section since 2026-09-28) and "one shared UI shell". Changing
either is an architecture decision that has to be recorded
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
- 2026-10-08, platform `ab33703` merged: antd is the only component system
  (`lib/__tests__/antd-only.test.ts` and the ESLint `no-restricted-imports`
  rule; sonner, radix, lucide, cva, assistant-ui and the shadcn files in
  `@dw/ui` are gone). One implementation of each shared piece: `@dw/ui`
  `PageHeader` (platform API: `subtitle`, `actions`, `tags`; Sales' `meta`
  moved into `tags`), `RegionState`/`ERROR_STATE`/`stateForError` (the
  product's `components/region-state.tsx` is gone; Sales pages use
  `LoadError`, which also offers "Tải lại" on a conflict), drawn by this
  product's theme (`appTheme`, `UiProvider`, `THEME_ROOT_CLASS`, Be Vietnam
  Pro and JetBrains Mono, #006edc) plus the platform's antd `Tag` text
  colours. The platform's `ThemeProvider`/`buildTheme` (dark mode) were not
  taken: this product is light only. `lib/money.ts` is the product's
  currency-aware file plus the platform's `formatMoneyShort` and
  `moneyInWords`; the platform's whole-dong `parseMoney` and InputNumber
  helpers were not taken (one parser: `parseAmountInput`). One nav
  visibility module (`lib/nav/visibility.ts`: `isNavItemVisible` beside
  `visibleNav`/`barNav`); admin pages are one "Quản trị" group with the
  platform's Vietnamese labels. One role-label table (`lib/nav/roles.ts`)
  names the Sales roles; `displayRole` reads it, the catalogue only for a
  key it lacks. CSP middleware with a per-request nonce (layout awaits
  `connection()`). `/approvals` links a `sales.` approval to its case page
  (`app/sales/_meta/approvals.ts`).
- The web vitest suite runs in CI since `395dbf3` (sales ticket 18): the
  "Unit tests (vitest)" step in `frontend-quality`, green in run 38545008947.
- `next build` fails on this Windows account at the standalone symlink copy
  (EPERM), as it does at HEAD; the Linux builder stage passes.
- Still open from the 2026-09-30 ui-quality gaps:
    - (closed 2026-10-08 by the platform merge: Vietnamese platform
      screens, no sonner);
    - the API client sends no `Idempotency-Key`: partly closed 2026-10-15
      (`e44b897`): `/approvals` decide, the admin members grant/role/revoke
      and every Sales mutation send a key from `lib/idempotency.ts`. Still
      open: the `/platform` support-staff and support-requests assign
      routes do not read the header (no `RequireIdempotency`); add it with
      integration tests (Docker), then send keys from the support console.
      The customer `/support/grants*` routes have no web screen. Owed: a
      browser check that `/approvals` decides with a key;
    - no screenshot script: closed 2026-10-15 (`70696ca`):
      `make web-screens` (`e2e/screens.spec.ts`, `DW_SCREENS=1`) captures every
      nav page per persona and project into `apps/web/screens/`; owed a run
      on the stack and a look. Playwright projects since `aa5001a`:
      320/991/992/1440 px and `tz-los-angeles` (ui-quality §12's
      non-Vietnam timezone), light only;
    - no offline banner or session-expiry warning: partly closed 2026-10-15.
      Offline (`6e2bf35`): the `@dw/ui` shell detects it once (`useOnline`,
      `OFFLINE_REASON`) and draws the banner; `/approvals` and every Sales
      step (`GuardedButton`, `useAction`) disable or refuse while offline.
      Still open: admin hierarchy, separation-of-duties, settings,
      workspaces, members-manager, `/knowledge`, `/platform`, the support
      console, `/support` and the feedback dialog, each to be wired as
      `/approvals` is, with a vitest that goes red without it. Session
      expiry (`47d4590`, `3774ffa`, WCAG 2.2.1): the banner warns 5 minutes
      ahead and offers "Tiếp tục phiên", then "Đăng nhập lại" once ended;
      the page never navigates by itself (a 401 no longer redirects to
      `/`); a working token refresh clears an end a 401 raised. Owed: a
      real SSO expiry on the Keycloak stack (Playwright uses dev auth), and
      a browser check with the network off on a Sales case and `/approvals`.
- 2026-10-15, also (agent, Đạt: làm luôn): relative deadlines count against
  the server's clock (`7ed84b6`, `11d6336`): the API exposes `Date` through
  CORS, `lib/server-clock.ts` keeps the offset and `useNow` counts by it on
  every tick (ui-quality §8 holds for every `useNow` user); owed: confirm on
  the stack that `Access-Control-Expose-Headers` carries `Date` and the
  Caddy overlay keeps it. `/audit` names the actor the server names, marks
  the support team and reads one grant's trail (`de7e91f`). A refusal
  message has one owner per context (`REFUSAL_TABLES` in
  `lib/error-message.ts`; a vitest fails on a code in two tables or one
  the platform raises).
- The Sales bar overflowed "…" from 992 to beyond 1600 px with nine pages
  (measured 2026-10-15). Done 2026-10-18 in `f84643e` (sales ticket 39,
  Đạt chose a submenu). The bar is Việc cần làm, Hộp thư, then the **Hồ sơ**
  and **Quản lý** submenus. A nav group may hold groups, and `visibleNav`
  hides an empty one. The shell's drawer opens every section, so it lists
  every page. Owed: the Playwright check of the Sales bar (written, not
  run) and a visual check at 992/1280/1440/1600 px.
- `pnpm audit` (2026-10-15): 2 moderate next.js advisories, fixed in next
  15.5.27, below the high gate; bumping next is a separate item.

## Theme from the E-HSDT v3 prototype (2026-10-05, committed in `92b155a`)

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
