# 36 — Bravo's own convert list and item master, imported as exported; a run on the real files measured

Status: ready-for-agent
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
