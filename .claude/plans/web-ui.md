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

- **2026-10-27, a sweep of every page** (Đạt: "chạy test và kiểm tra lại, UX UI khó dùng thì sửa"): a scripted walk of 31 routes as an.nguyen, giang.do, ha.vu and tam.ngo at 1440 and 390 px on the Docker stack (218 page views; no horizontal overflow, no page over 8 s, no script error). **Fixed:** `/audit` names a background lane by what it does (its `system:<lane>` actor) instead of a short id, labels the Sales actions (35 of them read "Hoạt động hệ thống"), shortens a stored mail's 68-character id (copyable, whole in the title) and writes details as "key: value" without empty values (the literal "null" a head saw); `code` with `text-xs` printed 10.2 px there and on `/admin/separation-of-duties`; `/sales/layouts/new` opened without a message asked the API with empty ids (422). **Fixed in batch A** (a900d92): refusals in Vietnamese with a way out, no link to a page the viewer is refused, Duyệt on the head's bar. **Fixed in batch B:** a routed mail on Việc cần làm names its owner as the inbox does (`WorkItem.owner`; every mail read "Chưa giao"); the overview names no mock set (it was hard-coded "giả lập"), splits the three PRV counts into tiles, says "Thư" and reads a holder or a target no case has been through as "Chưa có hồ sơ", not "Không rõ"; a case's steps are titled by the states they hold, the WIV code beside, and a case that is not the viewer's says whom it waits on ("Đến lượt …", Design, the cross-checker, the customer, the approver) instead of only "Không có việc của bạn"; Việc cần làm's "Đã chờ" is "Từ khi nhận" (it counts from the mail). The "thư chuyển Sales" counts that disagreed (inbox 15, overview 22) were 7 `eml-` dispositions left from ticket 43's stored-mailbox run in a stack now on `mock`: residue, not a defect; `make demo-reset` clears it. **Owed (Đạt):** a routed mail has no done state, so it stays on Việc cần làm for good. **Fixed in batch C:** below `md` a Sales list (Việc cần làm, Hộp thư, Đơn hàng, Báo giá, Quy tắc) draws its first column with a phone line under the title (state, deadline or flags; the inbox an unverified sender and the age) and keeps only the column holding the row's action (the inbox's DW1); nothing is pinned on a phone. One hook owns it, `usePhoneColumns`/`useIsPhone` in `list-parts.tsx`, and "phone" is measured (`xs` or `sm` matching), so jsdom's all-false `matchMedia` stays a desk. The board skips statuses no case is in on a phone and says how many; `/audit` writes "Lúc (giờ Việt Nam)" once in the header. **Fixed in batch D:** a permission shows by name, not code (`lib/nav/scopes.ts`, the one scope label table; its test reads the `0001` seed and `SalesScopes` and fails on an unlabelled one) on the admin page, the role catalog, separation of duties and an approval's refusal; master data labels a customer's status, language, channel and PIC and an item's family; screening drops "giả lập", names the customer and says Sales decides outside DW1; the approvals page speaks of rules, quotes and DW1, not "worker"; "Cần xử lý" says which example it names ("Chờ lâu nhất", "Trễ nhất") and that a tag is a total; the layouts' empty states open the inbox; Kiểm chéo & duyệt shows a quote's deadline; Việc cần làm names the approvals waiting on the viewer (rules, PO layouts, master data), which my-work does not carry; a separation-of-duties rule's sentence wraps. **Owed (Đạt):** the tenant's "Múi giờ" and "Ngôn ngữ" are stored and read by nothing (every time shows in giờ Việt Nam): wire them or take the fields off (`failure-modes.md` #1). **Open:** batch E (admin and safety); `members-manager.test.tsx` also times out under load; 25 other `text-xs`/`text-sm` utilities on platform pages (12 px, a style breach of `ui-quality.md` §1, not under 12 px); antd's `code` at 85% of 13 px reads 11.05 px on item codes and rule keys (§8 says nothing under 12 px; the theme has no token for it); `rule-drafts.test.tsx` and `rules-process.test.tsx` time out whenever the machine is loaded.

- **2026-10-26, found while taking the user guide's screenshots; 2026-10-27 resolved:**
    - ~~The order list's row link has no accessible name~~: wrong. The link names the customer and line count; the PO number sits outside it, which is why a search for "PO …" found nothing. Checked on the rendered page 2026-10-27: 23 of 23 links named.
    - Admin → Thành viên: **fixed.** Each row is a multi-select of every role the admin may grant; a save sends the selected roles plus every role the select does not show, so nothing is dropped; an administrator's row is locked for a non-platform-admin with the reason; **Lưu** stays off until a role changes (`members-manager.test.tsx`, 6 tests; a mutation dropping the kept roles goes red; seen on the rendered page).
    - `/approvals` subtitle: **fixed** ("Các việc trên trang này đều chưa được thực hiện.").
    - **Owed to Đạt:** the role list offers "DW1 (tài khoản dịch vụ)" (`sales_dw1`, the service account's role), so IT could give a person the service account's role. Hide service roles from the members screen, or keep it visible?

- **2026-10-26, a long list scrolls inside its region, not the page** (Đạt). `lib/use-fill-height.ts` sizes a region (antd `Table` through `ref={tableRef}` and `scroll.y`) from its top to the window's bottom, from `md` (the theme's `screenMD`) up; below it the page scrolls as before. The hook's `tableRef` must stay stable (`useCallback`): a new ref per render re-attached the table on every render, which an inbox test caught. List pages that adopt it: `sales.md` State 2026-10-26.

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
- 2026-10-23, React Flow for the DW1 process map (Đạt's decision, the first
  exception to antd-only; CLAUDE.md "Web UI"). `@xyflow/react` **12.12.0**,
  MIT: the latest stable on 2026-10-23, published 2026-09-24 (29 days;
  13.0.0 is only `next.0`); its transitive packages are all older than two
  weeks (newest `@types/d3-zoom` 3.0.9, 2026-09-29). Lockfile committed with
  it.
    - **Confined:** only `app/sales/_components/process-flow.tsx` imports it
      (and its stylesheet). `antd-only.test.ts` fails any other file, any
      import of `@xyflow/system`, `reactflow` or `react-flow-renderer`, and
      any runtime dependency of `apps/web` or `@dw/ui` not on its allowlist;
      ESLint says the same (an override for that one file). Mutated: an
      import in the process page turned both red.
    - **CSP, unchanged:** React Flow writes `style` attributes and ships a
      stylesheet; `lib/csp.ts` already allows inline styles
      (`'unsafe-inline'` in `style-src`, which antd needs too) and the CSS
      is bundled from `'self'`. It runs no eval, injects no script, loads no image or font
      and makes no request, so `script-src` (nonce + `strict-dynamic`),
      `connect-src` and `img-src` hold. Its stylesheet is unlayered but every
      selector is `.react-flow*`; colours are mapped to antd tokens through
      its `--xy-*` variables, not its defaults. Owed: e2e
      `enduser-nav.spec.ts` 10 checks the page under the real header with no
      violation (written, not run).
    - **Bundle (measured, `next build` into a scratch dist dir; the route
      table is not printed on this Windows account because the standalone
      copy fails with EPERM, so gzip sizes are summed from
      `app-build-manifest.json`):** React Flow is two chunks, 21.9 + 31.7 kB
      gz (`d3-zoom`/`d3-drag` included), loaded by `/sales/rules/process`
      only; its CSS 2.6 kB gz. That page: 200.7 kB gz of JS beyond the root
      layout's 402.6 kB (about 147 kB without React Flow). Not lazy-loaded:
      a phone below `lg` downloads it without drawing it; `next/dynamic` is
      the fix if that matters.
    - **Accessibility:** cards are the focus stops (real links, Enter opens
      the drawer, Tab in column order); nodes and edges are not focusable or
      selectable; each edge has a Vietnamese `aria-label`; the controls'
      names are Vietnamese. React Flow fixes `role="application"` on its
      wrapper and keeps its "React Flow" attribution link (its authors ask
      Pro subscribers only to hide it).
- 2026-10-23, Sales slices 2–3 web half checked: `tsc --noEmit`, `next lint`
  (whole app), prettier on every changed file, the full web vitest suite
  (74 files, 550 tests, rule-drafts and quote-preview included), api-client
  `tsc`. Mutations, each red then restored: an `@xyflow/react` import outside
  the allowed file (test and ESLint); a dropped `EDGE_ACTION` key and a
  dropped reason label; a count link without `tab=all`; the order list
  ignoring the URL's filter; the AI section drawn for an empty `models`; the
  arch direction swapped.
- 2026-10-24, shell and Sales web half of defects C–E, audit gaps 1–5 and the
  browser look (`sales.md` State 2026-10-24). Uncommitted.
    - **Shell, feedback button:** below `md` it is an icon button among the
      top bar's actions (`FeedbackLauncher placement="bar"`), because a fixed
      button covers whatever scrolls under it, padding or not; from `md` up it
      floats bottom-left as spec 003 US5 says, and `AppFrame` keeps
      `md:pb-20` under the page so its end scrolls clear. While antd's
      breakpoint is unknown it floats, as before. `feedback.spec.ts` (desktop)
      still holds.
    - **React Flow is lazy-loaded** (`next/dynamic`, `ssr: false`, a Skeleton
      while it loads): a phone below `lg` draws the list and never downloads
      the ~56 kB gz. `antd-only.test.ts` unchanged and green (the page imports
      `process-flow.tsx`, not `@xyflow/react`).
    - **Checked:** `tsc --noEmit`, `next lint` (whole app), prettier on every
      changed file, the full web vitest suite: 77 files, 584 tests, all
      passed with `--maxWorkers=3`. At default parallelism two runs failed
      6–7 rules-editor tests (`rule-drafts`, once `rules` and one editor test
      in `rules-process`) on `findBy` timeouts, the flake noted 2026-10-21;
      those three files pass together (45/45) and alone. Owed: make the
      editor tests' waits load-proof, or cap workers in `vitest.config.mts`.
      Mutations, each red then restored: the press not reloading the bar
      (D); the "còn N thư" branch removed (C); the conflict not reading the
      quote again, and re-submitting on the old version (E); the `not_opened`
      look removed; the `source_not_served` reason dropped; no reload on
      closing a source; the unopened list never drawn; the quote coverage
      title replaced; the history moved back above the flags; the drawer
      always on the right; the timing said on every entry; the feedback
      button always floating; React Flow imported statically; and four in
      the geometry (one lane for all, neighbour words over the card, back
      moves under the band, neighbour words not stacked).

- 2026-10-24, the DW1 process map in n8n's look (Đạt approved; `sales.md`
  "Quy trình DW1"). Uncommitted.
    - **Canvas** (`process-flow.tsx`, still the one `@xyflow/react` file):
      React Flow's `Background` (dots), `MiniMap` (pannable, not zoomable,
      so the wheel still scrolls the page) and horizontal `Controls`, both in
      a strip the frame adds under the lane, so neither covers a tile; the
      attribution sits bottom-centre. Every colour is an antd token through
      `--xy-*` or a prop; no CSP change (React Flow still only writes styles).
    - **Tiles:** an antd `Card` in the real `Link` (Tab, Enter, new tab as
      before): turn icon (aria-hidden, its meaning in a legend line of words
      above the canvas), name first in the DOM so the link's name starts with
      it, step codes as tags, `AiStateTag short`. Details are an antd
      `Popover` (`trigger` hover + focus, controlled, closed on click so it
      never floats over the drawer; antd sets `aria-describedby` while open;
      Esc closes). Handles render only on sides a drawn line meets, above the
      tile (`zIndex`), not connectable.
    - **Geometry:** `CARD_W` 168, `CARD_MIN_H` 88 (below the shortest
      measured tile, so lines meet handles), `GAP` 148; label size estimated
      inside the pill (`PILL_PAD`, owned by the geometry and read by the
      canvas); `roundedPath` rounds each bend on the same route.
    - **Checked:** `tsc --noEmit`, `next lint`, prettier on changed files;
      web vitest 77 files / 592 tests with `--maxWorkers=3` (one earlier run
      had the known rules-editor `findBy` timeout while a Docker build ran;
      the file alone and the full rerun passed). e2e `enduser-nav` 13/13 on
      a rebuilt `dw-web:e2e`; test 10 now also checks no tile or label sits
      under the controls or minimap, and the details open on keyboard focus
      and close on Esc. Mutations, each red then restored: neighbour words
      over the source card; all channel lanes on one line; details on hover
      only; handles on every side; whole AI words on the tile; bends not
      rounded. Seen at 1440 (order, quote, focused tile, drawer) and 390
      (list): the first build hid the handles under the tile (4 px, painted
      over) and the minimap tiles were too faint; both fixed and re-shot.
      A full-page screenshot blurs the focused tile (its viewport resize),
      so that shot uses a viewport as tall as the page.
    - **Calm re-cut (same day, Đạt: too busy):** the bands, channel lanes
      and guard tags are gone. `process-geometry.ts` places the main path
      (`layoutLane().main`) in one row and every other status on a row
      below on the same columns, so the gaps stay free in both rows; every
      line is a chain of cubic Béziers (`Curve`, `pathOf`, sampled by
      `pointsOf` in the test). Neighbours: straight; skips and ways back on
      the row: arches over it, stacked shorter-under-longer, the outer foot
      outside, words slid along the arch off any other arch; between the
      rows: upright curves (never into a tile), words on corridor tracks
      (a track is added until every pill has a spot no other line crosses;
      wide pills, else gap-width, slid sideways while still on the line);
      exits: down the gap after their tile onto a rail, one bus per final
      status. `GAP` 160, `CHAR_W` 7 (measured ~5.5 px). Pills: action only,
      `text-wrap: balance`, one lock `Button` + `Tooltip` for guards.
      Handles: both always present (React Flow draws no edge without
      them), visible only where a side line meets (`data-shown`). Switch
      "Hiện đường quay lại" is an antd `Switch` in a `label`, its state
      `?back=1` via the page's `useOpenItem`. Opens at zoom 0.85 from the
      row's start (pans; minimap shows all); "Xem cả quy trình" fits the
      whole lane, centred above the controls' strip. Phone list, lazy
      load, popover, drawer, `?node=`, Back and focus return unchanged; no
      CSP change.
    - **Checked (re-cut):** `tsc --noEmit`, `next lint`, prettier on the
      changed files; vitest geometry (both lanes × default/ways back × three
      tile heights: no label over a tile or a label, no line through a tile
      or another move's words), graph (main path, detour, tie), page (row
      and forward moves only, switch toggles and URL, `?back=1` link, lock
      tooltip on focus and hover, a served extra status below the row with
      its way back only when asked). Full web vitest 77 files / 602 tests
      with `--maxWorkers=3`: two runs each had one `findBy` timeout in an
      untouched test under load (rule-drafts, then the proposal test); both
      files pass alone. Mutations, each red then restored: a detour may end
      the row; a tie to the last status; arch feet in the corridor order;
      corridor words never slide or change track; gap words wider than the
      gap; arch words always at the top. e2e `enduser-nav`: 13/13 on the final `dw-web:e2e`;
      test 10 now fits the lane with "Xem cả quy trình" before checking
      tiles and labels inside the frame, and toggles the switch (URL, a
      way back drawn, then gone). Shots at 1440 in the session scratchpad
      (`n8n-look2/`).

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
