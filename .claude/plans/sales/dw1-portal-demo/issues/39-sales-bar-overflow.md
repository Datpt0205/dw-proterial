# 39 — The Sales bar overflows "…" on every desktop width

Status: needs-info (2026-10-15; measured by the agent, the layout is Đạt's call)
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
