# 11 — Base price and BP code from Design's reply

Status: ready-for-agent (2026-11-16: the Excel path; B21 "Danh mục Base price" columns known, B07's BP-latest block and B16's YCBG rows carry the BP code)
Blocked by: none to build; the full Base price list (B21 holds the latest 100) is requested from Proterial Sales
Category: enhancement

## Why

Drawio 1a: Design answers a YCBG with the Base price and a BP code, which
the quotation and Bravo need later.

## Shape

- Two fields on the Design reply (form and mail readers), anchored in the
  source like every other value, and shown to price readers only.

## Acceptance

1. A reply's Base price is kept only when it is read from its source span.
2. A support viewer never sees it (ticket 22's rule).

## Comments

- 2026-11-10 (Bravo screens): "Danh mục Base price" holds every BP: the
  code (`BP` + 6 digits), date, unit, Cu weight, base price, LME of BP,
  %MR, the cost split, and the change history. DW1 reads it through the
  Bravo port, and checks a BP code named in Design's reply against it. The
  cost split is shown to price readers only. Unblocked once ticket 14 can
  read the list.

## Done in part (2026-11-16, the Excel path)

- **Bravo's "Danh mục Base price" is a master list** (`CatalogList.BASE_PRICES`,
  `domain/catalog.BasePrice`), read through the Bravo port (ticket 14):
  uploaded as Bravo exports it, previewed, approved by a second person, then
  in force. B21's own titles are its columns' aliases (`_x000d_` and
  `{BP Unit}` inside them read fine). Importing or previewing it needs
  `sales.price.read` (`_PRICED`), mutation-checked. Migration
  `acb2a1fbb213` admits the list. **Measured outside git: B21, 100 of 100
  rows** (it holds the latest 100 BPs only; the full list is asked of
  Proterial).
- **A QUOTE line's BP shown with Bravo's base price**, on the quote case
  (`QuoteCaseView.design_prices`): the base price per BP unit, the unit,
  copper and LME of BP and the list's `as_of`, for a price reader only
  (decided once, in `views.quote_case`; a reader of cases only gets none,
  mutation-checked); a BP the list read does not hold is said so ("Không có
  trong danh mục Base price đã đọc"), never a blank price. Web: a column in
  "Phản hồi của Design", `MaskedValue` for a caller without prices.

Left:

- The contract (`openapi.json`, `sales.d.ts`) regenerated with this, held
  while the parallel session's routes are uncommitted.
- A QUOTE moving the case to pricing (ticket 16's "Left"): the spec number
  and copper weight are now in hand from the BP's row, but a value taken
  from a master list needs an anchor kind of its own before `DesignReply`'s
  `Sourced` fields can hold it. Next slice.
- Base price and BP code read from a Design reply *mail* (the form and mail
  readers): unchanged.
- 2026-11-17 (dw-proterial-33), **why the QUOTE-to-pricing slice stops
  here**: `design_replied` needs a `DesignReply`, every value `Sourced` and
  read from one file (`DesignReplyDocument._one_file_and_distinct_lines`).
  The BP code is in the YCBG export, the spec number and copper weight in
  the Base price list: two files, neither a case attachment nor the mail,
  which is all a `SourceAnchor` can point at. Making it work means a new
  anchor kind for a value read from a master list (which snapshot, which
  row, its hash), served on the source pane like a page crop: a change to
  dw_sales ADR 0005's provenance rule, so it is an ADR, owed by Đạt
  (`.claude/PLAN.md` "Decisions Đạt owes"), not a judgement made mid-slice.
  Meanwhile the price evidence and Design's result are both on the case,
  and Sales records Design's reply from its mail as before.

- 2026-11-17, **the two-file premise above was wrong; no new anchor kind is
  needed** (Đạt left ticket 11's ADR to the agent's recommendation). Bravo's
  "RFQ List" export (B16, row 4 titles) carries every value a Design reply
  line holds, in one file: "Base price code", "Bản vẽ/ Specification" (the
  spec number, `SPV-…`), "CU WT: (KG/BP Unit)", "Unit BP", "Giá cơ bản",
  "LME of BP"; ticket 16's reader takes only some of them. So a QUOTE read
  from Bravo becomes a `DesignReply` anchored by cell in the export file,
  the same rule as a reply's own Excel (dw_sales ADR 0005 unchanged). What
  it needs, the next slice:
  1. Keep the export's bytes for a case it answers. Today
     `SqlBravoExports.settle` deletes them once read. Recommended: the
     worker stores them as the case's Design source in the attachment store
     the source pane already reads (`inbox.read_attachment`, keyed by
     tenant/workspace), never as a mailbox message to triage.
  2. Read the three columns with each cell's place (`TableRow` row number
     plus the column's letter) into `DesignCheckLine`.
  3. "Dùng kết quả Design trên Bravo" on the case, by a person with
     `sales.quote.prepare`, records the `DesignReply` and moves the case to
     `design_replied`; ticket 16's rule that a read moves no status stays.
  4. Copper per km from CU WT per BP unit: only when "Unit BP" is km (the
     B21 convert rate says 1 km = 1,000 m); any other unit leaves copper
     unknown rather than converted by a guess.
- 2026-11-18, **step 2 of the slice above done**: the YCBG reader takes
  "Bản vẽ/ Specification", "CU WT: (KG/BP Unit)" and "Unit BP" (optional,
  so an older export reads as before; copper a plain number with "." or
  the row is rejected naming the column), and each QUOTE line's
  `DesignCheckLine` keeps them with its export row; a DECLINE states none
  (mutation-checked). The quote page shows them beside the BP code ("Bản
  vẽ · Cu (Design)"); copper is not an amount, as on a Design reply. No
  status moves. `test_ycbg_design_values.py`, `design-check-values.test.tsx`.
  Next: steps 1 and 3 (keep the export's bytes for the case; "Dùng kết quả
  Design trên Bravo").
- 2026-11-18, **step 1 decided (the agent's call, as Đạt asked): keep a
  snapshot of the case's own rows, never the export file.** One "RFQ List"
  export holds every open YCBG, other customers' among them, so the whole
  file on a case would show a case reader rows of customers they were never
  sent (ui-quality §6's side door). What the case keeps instead: the export's
  sha256, its sheet name, the title row and the rows of that YCBG only, as
  the sandbox read them, on `DesignCheck` (case body, no migration). It
  lives as long as the case, so nothing new needs a retention rule. The
  source pane draws it as a sheet grid, the person opens it (a served
  record, as for a file) before "Dùng kết quả Design trên Bravo" records the
  reply; each value's anchor is `RFQ List!<column><row>` in that snapshot,
  bound to the export's sha256. `DesignReply` gains this third origin
  beside a file and a mail text; dw_sales ADR 0005's rule (every value opens
  where it was read) is kept, with the snapshot as the place.
