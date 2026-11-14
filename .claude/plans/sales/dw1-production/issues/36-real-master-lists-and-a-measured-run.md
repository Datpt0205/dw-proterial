# 36 — Bravo's own convert list and item master, imported as exported; a run on the real files measured

Status: done (2026-11-14)
Blocked by: none (the files are in the Box download, outside git)
Category: enhancement

## Why

Đạt, 11-13: "các excel mỗi khách mỗi khác, cần đưa về 1 file chuẩn … cần 1
cái masterlist để convert các mã code, description về chuẩn của PRV".
The master lists exist: Box B04 (Bravo's convert list, 11,523 rows, 55
customers) and B06 (Bravo's item master, 12,271 codes). What does not fit
them is DW1:

- the convert list import is DW's own three-column template (customer code,
  customer item code, PRV code); B04 has its header on row 2 under a merged
  title, a group label row ("3. Đã duyệt") before the data, twelve columns,
  and its key is the customer's **converting description** per direct
  customer, with 66 descriptions mapping to different PRV codes at different
  customers;
- the item master's attributes (family, colour, packaging, …) were built for
  the mock data; B06 has 28 columns, units as text with conversion factors
  as text ("km,m" in one cell), and real item names such as
  `UL2464 3x17AWG(50/0.18TA) LF`.

## Shape

- Import B04 and B06 exactly as Bravo exports them (the column mapping step
  that exists for unknown headers, a person confirms the mapping once; the
  title and group-label rows skipped by structure, not by their words).
  Bravo's own export stays the owner; DW keeps no second copy beyond the
  approved snapshot (ticket 14 replaces the file with the read API later).
- The convert entry keys on (direct customer, converting description) as
  B04 does; a PO line matches by the customer's code or description as its
  layout names it.
- Item attributes for description matching re-derived from B06's real
  fields and names (code parses the spec string; a model reads a customer's
  description into the same attributes, ADR 0005).
- **A measured run, outside git:** the four customers' real POs (Box B01,
  B03, B11) through layout mapping, conversion and the paste sheet on this
  machine; the result written as counts only (lines read, codes exact /
  candidate / missing, values flagged) into this ticket. No customer data
  enters the repository.

## Acceptance

1. B04 and B06 import unedited; the import says how many rows and which
   were refused, with why.
2. A line of one customer never takes another customer's mapping for the
   same description (66 such descriptions exist).
3. The measured run's counts are written here.

## Measured (2026-11-14, on this machine, counts only)

The three Box-1114 files, unedited, through the import as the worker runs it
(in-process reader, `parse_rows`, the reference checks, approval) into a
throwaway in-memory tenant; then the PO lines of the four customers through
DW1's convert lookup (`order_intake._convert_entry`) and description match.
Script and output stay in the session scratchpad, outside git.

Imports:

| List | Rows read | Kept | Refused, by reason |
| --- | --- | --- | --- |
| B05 customers | 467 | 251 | 207 no contact address; 4 a contact neither "Tên <email>" nor an address; 3 an address that is not one; 2 a language DW1 does not write in. 6 domains claimed by several customers taken off them (noted on row 0) |
| B06 items | 12,271 | 12,266 | 5 code outside the PRV code alphabet |
| B04 convert list | 11,523 | 6,798 | 3,513 PRV code not in B06; 1,112 customer not among B05's kept customers; 92 no converting description; 8 no customer code |

14 customers' language cells name several languages (TAISEI, PCS and FBHP
among them); drafts are written in the first named. Refusing them, as first
built, cost 3 of the 4 measured customers.

Spec grammar on B06's 12,266 names: any attribute 74.5%, standard 54.9%,
cores 58.2%, gauge 60.9% (90.5% of the 8,251 names printing AWG or SQ),
strands 65.4%, colour 43.7%. Unit Packing known on 10,255 items; unit "m" on
9,091.

PO lines (reading by each file's own headers in the scratchpad, since no
tenant PO layout exists yet):

| Customer | Lines read | Exact (convert list) | Candidate | Missing | Values flagged | Not read |
| --- | --- | --- | --- | --- | --- | --- |
| TAISEI (B01 x2, B11) | 293 | 293 | 0 | 0 | 0 | 4 PDFs with no layout (B03 revisions, signed copies) |
| PCS (B01 PO_REMAIN) | 225 | 225 | 0 | 0 | 0 | 1 workbook locked with a password |
| FBHP (B01 CSV, firm rows) | 50 | 50 | 0 | 0 | 50 unit "PC" DW1 has no word for | 441 forecast rows (not orders) |
| PCA (B01 PDF) | 0 | 0 | 0 | 0 | 0 | 1 image-only PDF (OCR and a layout) |

No measured line's code is listed by another customer. PCA is not in the
customer list (B05 gives it no contact) and has no convert row.

## Done

- Bravo exports import as exported: header by shape under title rows
  (`master_data.header_row`), a group's label row left out by shape in the
  reader (`tables._group_labels`), Bravo's labels as column aliases, a
  repeated contacts column read together, defaults that fail closed for
  columns Bravo lacks (NOC not confirmed, channel email), `MAX_ROWS` 20,000,
  and a list's cell cap sized to it (the zip-bomb bound stays the PO's).
- Customers: domain "@x" read, a domain several customers claim is shared
  and taken off each, contacts on any domain, Bravo's group ("Nhóm mẹ") kept
  and the status read from it, several languages read as the first.
- Items: name, unit as Bravo writes it (DW1's `uom` read from it), unit
  conversions paired unit by factor (a pair that does not hold is refused
  with why), packaging style, category, BP code, specification; Unit Packing
  0 is unknown; MOQ, pack and lead time may be unknown and are then not
  checked (`checks_run` says so). Attributes read from the name's spec string
  (`domain/item_names.py`); `standard` added to what DW1's vocabulary reads.
- Convert list: keyed (direct customer, code or converting description);
  `ConvertEntry.customer_item_code` is `PrintedText`; a PO line is looked up
  under its customer by its code, else its description; an indirect
  customer's row is refused. Migration `d7c11e671769` widens the recorded
  converts' CHECK to the same text.
- The reference check reads each list once (B04 names 8,000+ codes).
- Owed, not done here: currency and payment term (B05 has no currency; no
  reader for a payment term yet); a lead time for real items (B06 has none,
  B13's groups do not match B06's categories); the model reading's closed set
  does not include `standard` yet.
