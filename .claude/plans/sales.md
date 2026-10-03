# Sales (Proterial Vietnam) — DW1 Đơn hàng & Báo giá

This repo became the Proterial product repo on 2026-10-02: `origin` is
`github.com/Datpt0205/dw-proterial` (public; Đạt keeps it public for now).
The platform seed stays in `Datpt0205/codebase`. DW01 (procurement) keeps
running in `C:\Users\phung\dw` and gets no new features; it moves here when a
Purchasing DW for Proterial is signed (estimated 30–51 person-days).

## State

- Context `dw_sales` scaffolded with `scripts/new_context.py` (14 seams).
- Feature in progress: `sales/dw1-portal-demo/` — DW1 end to end on mock data
  behind real ports. Spec: `sales/dw1-portal-demo/spec.md`. Tickets 01–10 in
  `sales/dw1-portal-demo/issues/`.
- 2026-10-03: tickets 01 (mock data and ports) and 07 (antd v6 shell) are
  reviewed and committed. Tickets 02 (order intake core) and 03 (quotation
  core) are implemented but not yet reviewed (the review hit the session
  limit); they stay uncommitted until the amendment pass below reviews them.
- 2026-10-03, conformance review done. The review itself stays outside git
  because it quotes Proterial's survey. The plan gets the mechanics right
  (reading, mapping, checks) but not the process:
    - WIV-03-012 steps 9–10 are missing: no cross-check by a second Sales
      member, no joint confirmation. One PIC can approve and confirm alone.
    - The revised-PO loop dead-ends: a correction request plus Rev.1 never
      yields an upload file.
    - The confirmation carries no delivery date, and the short-LT rule counts
      from the PO date, not the date the PO was received.
    - Quotation steps 2, 5, 6, 8, 9, 11 and 12 have no state or artifact.
    - Roles are three generic scopes, so the walk-through only works as
      platform_admin.
    - ADR 0008, 0009 and 0010 decisions are not followed, nor recorded as
      exceptions.
- Next: when 02/03 finish, amend the spec and tickets (see Open), run one
  amendment pass on 02/03, then build 04/05/06/08 against the amended spec.
  Production-only gaps become their own tickets.

## Inputs owed by Proterial

The requirements doc `DW1_Don-hang-Bao-gia_Nhung-gi-can-co_30-09-2026_v1.2.docx`
(kept outside git) lists them: convert list, item master, quotation master
list and LME rule, Bravo upload template, sample POs with their Bravo orders,
mailbox access, AI/data approval, WIV-03-012/023 texts. Not sent yet
(2026-10-02).

## Slice log

| Ticket | Commit    | What                                                                                      |
| ------ | --------- | ----------------------------------------------------------------------------------------- |
| 07     | `78af2bd` | antd v6 shell: registry on the `antd` layer, theme owns tokens, top navbar, dates/money   |
| 01     | this one  | Mock catalog and inbox behind `SalesCatalogPort`/`InboxPort`; 12 fictional emails M01–M12 |

## Open

- Spec decision 5: the Sales decision is recorded by the context, not yet a
  runtime interrupt (ticket 10).
- Public repo: the repo name and these plan files name Proterial and its
  procedure codes (WIV-03-0xx), and this file carries a commercial estimate.
  Mock data, people and figures are fictional, and Proterial's documents
  stay outside git. Đạt decides whether to alias the customer and the
  procedure codes in git.
- Amendments the review requires, to land in the spec before 04/05/08:
    - order flow per WIV-03-012: a decision on every finding, then the upload
      file, the Bravo order number, a cross-check by someone other than the
      preparer (refused server-side), and a confirmation with the date per
      line;
    - revised PO supersedes its predecessor in the same case;
    - quotation steps 1–12 with the quotation document;
    - a role and scope matrix with price visibility, covering the audit log;
    - every message ends in a disposition;
    - a line-completeness check;
    - each check's basis stamped on the case;
    - KPIs measured on the mock set.
- Defaults adopted until Proterial answers, taken from the requirements
  doc's own interim answers (Đạt may overrule):
    - the cross-check is kept;
    - the signed hard copy stays the quotation approval of record, and portal
      approval is shown as the proposal;
    - only the quotation PIC and the head see other customers' prices;
    - NOC/ESF warns, and the export-control PIC must acknowledge it;
    - quotation steps 11–12 are built on mock data.
- The proposal states two different quotation-time targets; Đạt picks the
  one the demo measures.
