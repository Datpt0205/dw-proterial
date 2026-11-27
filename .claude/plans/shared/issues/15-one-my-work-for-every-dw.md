# 15 — One "Việc của tôi" across every DW

Status: ready-for-agent
Blocked by: none
Category: approvals / platform

## What

§2: "Một 'Việc của tôi' chung cho mọi DW (hiện DW1, DW2 mỗi bên một trang)".
Checked 2026-11-27: not built. DW1's is `apps/web/app/sales/page.tsx`
(`sales/my-work`), DW2's is `apps/web/app/purchasing/page.tsx`; a person who
works in both, or who decides platform approvals, has three places to look.

## Design

- **The platform composes, each context answers:** the platform declares
  `WorkItemsPort` (`items(context) -> list[WorkItem]`: context, kind, id,
  title without any amount, due and late from that context's SLA, link to the
  item in its own page with `?item=`), and the composition root registers
  one per context (Sales from `my-work`, Purchasing from its list) and one for
  pending platform approvals the caller may decide. `GET /api/v1/my-work`
  merges them, late first.
- **Decisions stay where they are:** a row links into its DW's own row,
  which carries the case page's buttons; this page decides nothing (one door
  per decision).
- A context the caller has no scope in contributes nothing; a context that
  fails to answer is named in the response ("DW2 chưa trả lời") and the
  rest still shows.
- Web: the portal home (`apps/web/app/page.tsx`) shows the merged list with
  the DW as a tag; each DW's page stays.

## Acceptance

- Unit: merge and order; a failing source named, not hidden.
- API: an item of a context the caller cannot read never appears; another
  tenant's never (PostgreSQL); no amount in the payload (assert on the JSON).
- Web: every region state; a row's link carries `?item=`.

## Owed

- none.
