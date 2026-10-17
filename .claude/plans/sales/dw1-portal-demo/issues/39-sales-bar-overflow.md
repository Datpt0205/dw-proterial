# 39 — The Sales bar overflows "…" on every desktop width

Status: done (2026-10-18, `f84643e`; Đạt chose (b), a submenu. The visual check at 992/1280/1440/1600 px is still owed)
Blocked by: —
Category: enhancement

## What

The Sales-only top bar (restyle `92b155a`) was recorded as overflowing into
antd's "…" between 992 and ~1250 px (`sales.md` Open). Re-measured
2026-10-15 in Chromium with Be Vietnam Pro, it is worse: with nine Sales
pages (the rules page, ticket 38's follow-up `bd666a7`, is the ninth) "…"
appears from 992 px to beyond 1600 px: 6 items hidden at 992, 1-2 still
hidden at 1472-1600. The menu alone needs 1004 px; the whole bar (brand,
workspace block, menu, bell, account) about 1580 px, about 1730 at 2xl
(where the account shows name and role). No Tailwind or antd layout tweak
fits it into one 56 px row at `lg`.

## Question for Đạt (why needs-info)

Which layout:

- (a) a two-row header on desktop (brand and account above, pages below);
- (b) a Sales submenu for the setup pages (rules, layouts and the like), so
  the bar holds the daily pages only;
- (c) the drawer below `xl`/`2xl` instead of below `lg`, which changes
  `CLAUDE.md` "Web UI" (the shell's drawer breakpoint) and must be recorded
  there.

## Acceptance (once chosen)

1. No "…" in the Sales bar at 1280, 1440 and 1600 px; at 992 px either none
   or the chosen fallback.
2. A visual check at 992/1280/1440/1600 px (`make web-screens`, `aa5001a`'s
   projects).
3. The nav visibility rules (`lib/nav/visibility.ts`) stay the one owner of
   which page a person sees.

## Comments

- 2026-10-18 (agent; Đạt chose option (b)). As built in `f84643e`: the bar
  keeps the two daily pages that carry counts, Việc cần làm and Hộp thư. A
  count never goes inside a closed submenu. The other seven sit in two
  submenus, grouped by the work: **Hồ sơ** (Đơn hàng, Báo giá, Kiểm chéo &
  duyệt) and **Quản lý** (Mẫu PO, Quy tắc, Dữ liệu giả lập, Tổng quan quy
  trình). That is four entries instead of nine. A `NavGroup` may now hold
  groups. `visibleNav` (still the one owner of who sees what) drops a
  submenu whose pages are all hidden. It draws a nested submenu left with
  one page as that page, so `sales_viewer` still gets "Tổng quan quy trình"
  alone on the bar. The drawer opens every section, so it lists every page.
  This also applies to the admins' drawer, where only the current page's
  section used to open.
  Checked: vitest. `lib/__tests__/nav.test.ts` covers the model: an empty
  submenu hidden, a visible child keeps its submenu, a single child
  flattened. `components/__tests__/app-shell-submenu.test.tsx` covers the
  shell: the active route marks its submenu, the submenu title is a
  keyboard `menuitem`, the drawer lists every page. Mutation: keeping an
  empty nested submenu turns 4 tests red, and closing the drawer's sections
  turns the drawer test red. tsc and lint are clean.
  Owed: `e2e/platform-pages.spec.ts` "the Sales bar fits one row" (as
  `giang.do`, in the 991/992/1440/LA projects) was written but not run.
  The fit at 992 px is an estimate, about 380 of about 416 px, not a
  measurement. Acceptance 2 (`make web-screens` at 992/1280/1440/1600) needs
  the stack.
