# 27 — Legacy `.xls`/`.doc` are converted and image PDFs are OCRed (G17, part 2)

Status: ready-for-agent
Blocked by: 25
Category: enhancement

Split from ticket 12 on 2026-10-12.

## What

ADR 0010 decision 2 (Proposed): legacy Office files are converted to the
current format or PDF in a one-use sandbox per file (CPU, memory, time limits;
no network; no macros), and the derived file carries its own hash and the
converter's version. Image-only PDFs are OCRed per ADR 0009/0010 so a scanned
PO yields values with page coordinates.

## Acceptance

1. `.xls` → `.xlsx` and `.doc` → `.docx` (or PDF) conversion runs in the
   worker sandbox from ticket 25, macros disabled, no network. The derived
   file's hash and converter version are stored; the anchor carries both
   hashes.
2. An image-only PDF page is OCRed; each value read from it keeps a page and
   bounding box, and every OCR value raises `value_uncertain` until Sales
   confirms it (OCR is never taken on trust).
3. The OCR engine and converter are pinned images or packages; the choice
   is recorded in Comments with measured memory and time per page on the dev
   machine.
4. Fictional fixtures: one `.xls` PO, one scanned PDF PO, with eval cases.
5. A converter or OCR failure is a finding, not a failed run.

## Out of scope

- Converting TCVN3/VNI text (ticket 20 detects; conversion is later).

## Sources (as of 2026-10-12)

- `docs/adr/0009-parser-page-output-with-coordinates.md`,
  `docs/adr/0010-document-intake-at-real-size-and-format.md` (both Proposed).

## Comments
