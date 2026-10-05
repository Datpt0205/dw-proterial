# Sales (Proterial Vietnam) — DW1 Đơn hàng & Báo giá

This repo became the Proterial product repo on 2026-10-02: `origin` is
`github.com/Datpt0205/dw-proterial` (public; Đạt keeps it public for now).
The platform seed stays in `Datpt0205/codebase`. DW01 (procurement) keeps
running in `C:\Users\phung\dw` and gets no new features; it moves here when a
Purchasing DW for Proterial is signed (estimated 30–51 person-days).

## State

- Context `dw_sales` scaffolded with `scripts/new_context.py` (14 seams).
- Feature in progress: `sales/dw1-portal-demo/` — DW1 end to end on mock data
  behind real ports. Spec: `sales/dw1-portal-demo/spec.md`. Tickets 01–12 in
  `sales/dw1-portal-demo/issues/`.
- Tickets 01 and 07 committed 2026-10-03; 01 follow-up (fixtures M13–M32,
  mock Bravo history, open YCBG list, snapshot as_of, one SourceAnchor) and
  02/03 reworked to the amended spec, adversarially reviewed and committed
  2026-10-05 (dw_sales 683 unit tests; import contracts 9 kept).
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
- 2026-10-03, spec and tickets amended per the review: the process map, the
  actor/role/scope table, maker/checker, price visibility, per-finding and
  per-message dispositions, check basis, the ADR 0009 source gate and the
  interim behaviour per open decision are in the spec. 02/03 are amendment
  tickets, 01 has a fixture follow-up, 11 seeds the personas, and 12 holds
  the production-only gaps. Context glossary and ADRs 0001–0003 are under
  `packages/python/dw_sales/`.
- 2026-10-03, a second pass checked the amendments against the survey and
  the requirements doc. It corrected three process facts: the short-LT
  rule uses the standard lead time; the PIC still compares the Bravo entry
  with the PO when recording the order number; NOC/ESF blocks confirmation,
  not preparation. The cross-checker must also differ from the Bravo
  recorder. The quotation approval matrix waits for Proterial (ticket 12).
- Next: 04 → 11 → 05 → 06 → 08 against the amended spec. Still owed before
  calling the core done: reviewing-feature-security and /code-review on
  02/03; server-side price hiding and the maker/checker DB CHECKs land in
  04/05.
- Open from the 02/03 pass: routing reasons (complaint, sample request,
  delivery change) are keyword tables, against operator guideline §6,
  accepted by the spec for the demo; ticket 03 added the ledger to the mock
  catalog; the sales policy files stayed at 1.0.0 (never released).

## Inputs owed by Proterial

The requirements doc `DW1_Don-hang-Bao-gia_Nhung-gi-can-co_30-09-2026_v1.2.docx`
(kept outside git) lists them: convert list, item master, quotation master
list and LME rule, Bravo upload template, sample POs with their Bravo orders,
mailbox access, AI/data approval, WIV-03-012/023 texts. Not sent yet
(2026-10-02).

## Slice log

| Ticket | Commit    | What                                                                                              |
| ------ | --------- | ------------------------------------------------------------------------------------------------- |
| 07     | `78af2bd` | antd v6 shell: registry on the `antd` layer, theme owns tokens, top navbar, dates/money           |
| 01     | `b5f990b` | Mock catalog and inbox behind `SalesCatalogPort`/`InboxPort`; 12 fictional emails M01–M12         |
| 02, 03 | `ad467dd` | Amended to WIV steps: maker/checker, dispositions, revised PO, quote steps 1–12; fixtures M13–M32 |

## Open

- Spec decision 5: the Sales decision is recorded by the context, not yet a
  runtime interrupt (ticket 10).
- Public repo: the repo name and these plan files name Proterial and its
  procedure codes (WIV-03-0xx), and this file carries a commercial estimate.
  Mock data, people and figures are fictional, and Proterial's documents
  stay outside git. Đạt decides whether to alias the customer and the
  procedure codes in git.
- Defaults adopted until Proterial answers, taken from the requirements
  doc's own interim answers (Đạt may overrule); the spec's "Interim
  behaviour" table names the policy key or role each answer changes:
    - the cross-check is kept;
    - the signed hard copy stays the quotation approval of record, and portal
      approval is shown as the proposal;
    - only the quotation PIC and the head see other customers' prices;
    - NOC/ESF warns, and the export-control PIC must acknowledge it;
    - quotation steps 11–12 are built on mock data.
- The proposal states two different quotation-time targets; Đạt picks the
  one the demo measures.
- UI reference (2026-10-05): Đạt's E-HSDT v3 prototype in `docs/design/`
  (untracked, another product's handoff) is the visual language for ticket
  08; the screen mapping is in ticket 08. `docs/design/` is in `.gitignore` (Đạt, 2026-10-05)
