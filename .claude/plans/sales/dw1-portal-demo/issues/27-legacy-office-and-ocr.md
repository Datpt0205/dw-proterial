# 27 — Legacy `.xls`/`.doc` are converted and image PDFs are OCRed (G17, part 2)

Status: built-pending-measurement (2026-10-14, agent): conversion and OCR
built in ticket 25's reader container, tested at their seams and in the
evals (`sales_legacy@1.0.0`); what the real LibreOffice and Tesseract make of
the fixtures, and their time and memory, are measured on the image after the
WSL reboot ("Post-reboot checks" below)
Blocked by: — (25 built)
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

## As built (2026-10-14, agent)

1. **Conversion, in the reader sandbox** (`readers/legacy.py`,
   `LibreOfficeConverter`): an `.xls` to `.xlsx` and a `.doc` to PDF by
   LibreOffice headless, started by the one-use reading process (ticket 25),
   so under its `ulimit`s, its process group and its wall clock, with no
   network. A throwaway profile per conversion (`-env:UserInstallation` in the
   request's own directory), written before LibreOffice starts with
   `DisableMacrosExecution` true and macro security "very high";
   `--norestore --nologo --nodefault --nolockcheck`, no filter option; its own
   90 s clock. The copy is read as any `.xlsx`/PDF (the same layouts), and
   the PO says how (`PoDocument.derivation`: `converted`, the tool's own
   `soffice --version`, the copy's sha256); **every anchor carries both
   hashes** (`attachment_sha256` the customer's file, `derived_sha256` the
   copy), and the PO refuses an anchor naming another copy. A source view of
   a legacy file shows its copy (converted again). The type is told by the
   bytes: `formats.sniff` reads a compound file's directory (`Workbook`/`Book`
   → `xls`, `WordDocument` → `doc`, a name taken only at a directory entry),
   and `READ_AS` maps each to what it is read as (layouts, pairing, the
   platform's layouts).
2. **OCR** (`readers/ocr.py`, `TesseractOcr`; `readers/pdf.py`): a PDF page
   with no text layer is rasterised (`pdftoppm -r 300`, one page) and read by
   `tesseract -l vie+eng --psm 6 tsv`; its words, by line, become the page's
   lines and rows (a gap wider than 1.2 word heights ends a cell), so the
   customer's PDF layout reads it unchanged and each value keeps its page and
   a box. **Every value of a PO a page of which was OCRed is flagged `ocr`**
   (`RegionFlag.OCR`, so `value_uncertain` until Sales confirms it, whatever
   the confidence; a word under 30 is dropped as noise), and the PO names the
   engine (`derivation`: `ocr`, `tesseract --version` and the languages).
3. **Pinned**: the base image by tag and digest; LibreOffice
   (`libreoffice-calc-nogui`, `libreoffice-writer-nogui`), Tesseract
   (`tesseract-ocr`, `tesseract-ocr-vie`) and poppler from Debian bookworm,
   each reading stamped with the tool's own version. Memory and time per page:
   owed (below).
4. **Fixtures** (fictional, from the fictional mocks):
   `adapters/mock/legacy/scan_BRN-PO-2610-027.pdf` (M03 drawn as a bilevel
   300 dpi scan, no text layer) and its `.tsv` (what a perfect OCR reads),
   made by `python -m dw_sales.adapters.mock.generate_scan`, deterministic.
   **No `.xls` is committed**: the public-repo guard cannot read a binary
   Office file and counts one a finding; the unit suite and the evals hand
   the reader a compound file naming a workbook stream with the converter
   scripted, and the image suite makes real `.xls`/`.doc` files in the image
   with LibreOffice. Evals `sales_legacy@1.0.0` (6/6, full security coverage):
   converted (both hashes, the converter), OCR (every value `ocr`,
   `value_uncertain`), a failed conversion routed with the reason, an
   instruction printed on a scan kept as a flagged value that moves nothing,
   another tenant reaching nothing (and nothing converted), a scan OCR reads
   nothing on yielding no value.
5. **A converter or OCR failure is a finding on the message, not a failed
   run**: the PO is `Unreadable` ("the xls file could not be converted:
   LibreOffice exited 81"; "the PDF has no text layer, and OCR read no text
   on it"), the message routed `attachment_unreadable` with that reason. A
   tool that is not installed (in process, on a developer's machine) reads
   as before: unreadable, with the reason.

## Comments

- 2026-10-14, agent: built inside ticket 25's reader container (Đạt decided
  "DW xử lý" asynchronous; the container was the ticket's recommendation,
  taken by the agent while Đạt was away).
- Decided by the agent: Tesseract 5 with `vie` first (the plan below); page
  segmentation mode 6 and 300 dpi are starting values the measurement
  confirms or changes. The fixture's type is small (the long description
  column puts about 190 characters on a landscape line, about 6 pt): if
  Tesseract misreads it at 300 dpi, try 400 dpi before another engine.
- Decided by the agent: each read of a legacy file converts it again (the
  sandbox keeps nothing between requests, and intake reads a PO twice);
  caching the copy is a follow-up if the measurement says it is slow.
- Not done: a fixture with a macro that would act if run, to show that it
  does not (LibreOffice writes such a file only with its own macro editor);
  the disabled profile is tested as written, not as obeyed. Owed with the
  reboot: make one in the image and convert it.
- **Post-reboot checks** (after ticket 25's, which build the image):
    1. `DW_TEST_READER=http://127.0.0.1:8120 uv run pytest -m integration apps/reader/tests/integration -k "libreoffice or tesseract or legacy or bars"`:
       the `.xls` made from M01 converted and read with both hashes; the scan
       read by Tesseract to the same quantities and prices as M03 (prints
       what it read); M16 (bars) still unreadable; a `.doc` shown as its PDF.
    2. `uv run python scripts/measure_reader.py --runs 3`: seconds and peak
       memory per reading process for the `.xls` (LibreOffice) and the 2-page
       scan (Tesseract); record them here (acceptance 3).
    3. If Tesseract misreads the scan: rerun with `DPI = 400` in
       `readers/ocr.py`, then `--psm 4`, and record each; RapidOCR only if
       both fail (the plan below).
    4. A macro fixture: in the reader container, write a `.xls` with an
       `Auto_Open` that writes a file, convert it through the reader, and
       check no file was written.

- 2026-10-14, CI run 38513561151, the first run of the image suite (agent):
    - **The `.xls` test read a file that does not exist**
      (`legacy/legacy_VLX-PO-2610-0021.xls`): none is committed, as this
      ticket says, so the test and `scripts/measure_reader.py` now make it
      in the running image (`reading_tools.xls_made_in_reader`: M01 as
      `VLX-PO-2610-0021`, written by the image's LibreOffice as
      `xls:MS Excel 97`). What LibreOffice's round trip does to M01's cells
      is unmeasured until CI runs it.
    - **The scan was refused "no line holds the currency"**. Measured
      locally (Docker down): Tesseract 5.3.4 from conda-forge with
      tessdata_fast 4.1.0 `vie`+`eng`, on this repository's own `ocr.py`.
      Not the image's build (Debian bookworm's 5.3.0), but it reproduced
      CI's refusal exactly. Page 1 reads clean except where a mixed-case
      label carries a stacked or barred letter: `Đơn vị tiền tệ` came back
      as `Don vị tiền tệ`, and the column titles `ĐVT`, `Đơn giá`,
      `Thành tiền`, `Ngày giao` as `DVT`, `Don gia`, `Thanh tién`,
      `Ngay giao`. The labels and titles are matched exactly, so nothing
      matched. Every number read right (`6.100`, `1.150`, `7.015.000`,
      dates). Settings tried, before the fix:
      300 dpi `--psm 6` (the shipped one), `--psm 4` and `--psm 3`: no
      currency; 400 dpi `--psm 6` and `--psm 4`: no table; 600 dpi: no PO
      number (`S6 don hang`); `vie` alone at 300 dpi: titles right but `ĐVT`
      dropped, no table; `vie` alone at 400 dpi: read, but 1 line of 3
      (`6100`, `2_`). Tuning settings for this one fixture was not a fix.
    - **Fix** (`readers/pdf.py`, `pdf_po_reader@1.6.0`): on a page read by
      OCR, a label and the column titles are matched without diacritics
      (`đ` as `d`). A text-layer page is matched exactly, as before. The
      values are unchanged and every one of them is still flagged `ocr`, so
      nothing is trusted that was not before. After it, at 300 dpi
      `--psm 6` `vie+eng`, the scan reads `BRN-PO-2610-027`, VND,
      23/09/2026, and 3 lines whose quantities and prices equal M03's, all
      flagged `ocr`, in about 4.6 s for both pages in process on this
      machine (not the sandbox; acceptance 3's numbers still come from
      `measure_reader.py` on the image). 400 dpi also reads 3/3, and
      `--psm 4` 1 of 3, so 300 dpi and `--psm 6` stay. Unit test
      `test_a_scan_whose_labels_lost_their_diacritics_is_read_by_its_layout`
      feeds the measured misreads through `TruthOcr`, and it fails without
      the fix.
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
