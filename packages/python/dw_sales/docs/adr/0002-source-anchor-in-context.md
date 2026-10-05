---
status: Proposed
date: 2026-10-03
---

# One `SourceAnchor`, inside dw_sales, until a second consumer exists

## Context

Every value DW1 reads from a PO or an RFQ must show where it came from, so
that the person checking it sees the original (ui-quality.md, ADR 0009). The
working tree has two anchor shapes:

- `orders.SourceAnchor`: sheet and cell, or page and text-line;
- `quotes.CellAnchor`: message, attachment, sheet and cell.

Neither carries a hash of the file it points into. The PDF variant points at
a line of extracted text, which ADR 0009 rejects. Platform ADR 0004 proposes
a shared `dw_evidence` package with its own `SourceAnchor`. Its option (c)
keeps the type in the context until the repo has a real second consumer.
This repo has none.

## Decision

- One type, `dw_sales.domain.anchors.SourceAnchor`, used by orders and
  quotes alike. Both existing shapes are deleted.
- Fields: `attachment_id`, `attachment_sha256`, and at least one of:
    - `cell_ref` (`Sheet!B10`);
    - `page` plus `boxes`: `PageBox(x, y, w, h)` as fractions 0–1 of the
      page, taken from the PDF's text-run positions;
    - `quote`.

    The validator refuses an anchor with none of them.

- The field names follow ADR 0009 decision 2. A later move to `dw_evidence`
  is then an import change, not a data migration.
- This is ADR 0004 option (c). The trigger to move the type to
  `dw_evidence` is a second consumer of it in this repo.

## Consequences

- The review screen draws boxes on the rendered page or marks cells on the
  sheet grid, never on extracted text. The source route records which pages
  or sheets it served to whom (spec decision 12).
- `start_offset`/`end_offset` are not carried. They come with
  `locate_quote` if the type moves.
- A changed file or parser version invalidates the anchors that point into
  it, because the hash no longer matches.
