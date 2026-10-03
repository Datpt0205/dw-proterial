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
    - the header's workspace switcher, bell and session chip are still
      hand-built Tailwind dropdowns; no offline banner or session-expiry
      warning.
