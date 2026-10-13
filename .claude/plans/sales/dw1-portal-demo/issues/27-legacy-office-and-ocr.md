# 27 — Legacy `.xls`/`.doc` are converted and image PDFs are OCRed (G17, part 2)

Status: needs-info (2026-10-13, agent, Đạt away): waits on ticket 25's sandbox
question, and on WSL being restarted on the dev machine (Comments)
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

- 2026-10-13, needs-info (agent, Đạt away). Not started in code, for two
  reasons, each with its question:
    1. **Blocked by ticket 25's acceptance 5**, now needs-info: acceptance 1
       here runs the conversion "in the worker sandbox from ticket 25", and
       the OCR of a page belongs in the same place (ADR 0010 decisions 2 and
       6). Which sandbox that is, docgen or a reader container of its own, is
       ticket 25's question to Đạt, and it decides where LibreOffice and the
       OCR engine are installed and measured. Building the conversion or the
       OCR in the API or worker process now would put a parser of scans and
       of legacy Office files, the riskiest inputs ADR 0010 names, outside
       the containment, so it was not done.
    2. **The machine.** Docker Desktop's WSL VM died at 22:01 on 2026-10-13
       (its log: "connection multiplexer has shutdown"; its own restart then
       failed in `wsl-bootstrap`), and `WslService` has been stuck in
       StopPending since. Restarting it needs administrator rights this
       session does not have: Đạt, please restart WSL (`wsl --shutdown` from
       an elevated prompt, or restart Windows), then Docker Desktop. Ollama
       runs on Windows itself and was not touched. Measuring an engine "on the
       dev machine" (acceptance 3) needs the container, so it waits too.
       Nothing domain-side was added ahead of the engine: a `value_uncertain`
       flag for OCR'd values, or a conversion finding, that nothing raises would
       be a declared field nobody reads (failure-modes #1).
- Plan, for when both are answered (agent's recommendation, unmeasured):
    - **Conversion.** LibreOffice headless, the toolchain docgen already
      carries; docgen has only `libreoffice-writer-nogui` (`.doc`), so a
      `.xls` needs `libreoffice-calc-nogui` added to whichever image runs it,
      with macros off (`--norestore`, no `--infilter` macro security
      override) and one throwaway profile directory per file. The derived
      file's sha256 and `soffice --version` go on the document; an anchor
      carries both hashes (ADR 0009).
    - **OCR.** Measure first, lightest first, CPU only: the GTX 1080 belongs
      to Ollama (691 MiB of 8 GiB in use when checked; it was not stopped).
      Candidates in that order: Tesseract 5 with `vie` (`tesseract-ocr-vie`
      from apt, tens of MB, word boxes from its TSV output); then RapidOCR
      (PaddleOCR's models on onnxruntime, a latin recognition model) if
      Tesseract misreads stacked diacritics on the fixture scans; EasyOCR or
      VietOCR only if both fail, since each brings torch. The record per
      engine: resident memory, seconds per A4 page at 300 dpi, and values
      right on the fixtures, every OCR value flagged `value_uncertain`
      whatever its confidence.
    - **Fixtures.** One fictional `.xls` PO and one scanned PO rendered from
      fictional data (the generator already draws `M16`'s scan as bars; a
      text scan needs glyphs, rasterised by the sandbox's own toolchain so
      the bytes do not depend on a host's fonts).
