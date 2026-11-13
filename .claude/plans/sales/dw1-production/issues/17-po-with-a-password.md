# 17 — A PO file with a password, opened with its own mail's password

Status: done (2026-11-13)
Blocked by: none
Category: enhancement

## Why

Customer 1 sends its POs as `.xlsx` files with a password and writes the
password in the same mail's body (one mail: nine POs, 225 lines). Today an
encrypted file is refused as unreadable (`readers/pdf.py`, `text_parts.py`),
so DW1 does nothing for its largest customer. Decided 11-13 (Đạt): DW opens
it with the password its mail carries; the same for a PDF.

## Shape

- The intake finds password candidates in the mail's own body (the line
  that names a password); never from another mail, never from a model's
  guess.
- The `reader` sandbox gets the file and the candidates in one request,
  decrypts in memory (Excel: an OOXML decrypter; PDF: the PDF library's own
  decrypt), reads as today, and returns the reading only. Nothing writes the
  password: not the database, not a log, not the audit, not an error.
- The audit records only that the file was opened with a password from its
  own mail.
- No candidate, or none opens it: the file is "có mật khẩu, DW không mở
  được" and goes to a person, as an unreadable file does.

## Acceptance

1. A fixture `.xlsx` and a PDF, each encrypted, whose mail carries the
   password, are read; every value stays flagged for a person.
2. The same file with a wrong password, and with none, goes to a person
   with that reason.
3. A test searches every row and log line the reading produced for the
   password and finds nothing (mutation: log it, the test goes red).
4. The password never leaves the reader request: the API and worker do not
   hold it past the call.

## Done

- **Candidates** (`dw_sales/domain/file_passwords.py`): from the one mail's
  body only, by structure, no keyword table and no model: every line's text
  after its last `:` or `：` first, then every word of 4–64 characters with
  trailing punctuation stripped; unique, at most 24 (one agile-encryption
  try measured 0.32 s, msoffcrypto-tool 6.0.0: about 8 s worst case per
  opening).
- **Door** (`application/scanned_inbox.py`): an encrypted file is no longer
  refused; it is marked "encrypted: contents not scannable by ClamAV" and
  handed over as a `LockedContent` carrying its own mail's text
  (`repr=False`, `exclude=True`). `FormatCheckPort.encrypted`
  (`dw_platform/application/malware.py`), `formats.encrypted`; an encrypted
  Office package sniffs `encrypted`, read as a workbook (`READ_AS`).
- **Wire and sandbox**: `ReaderArgs.passwords` (`repr=False`, bounded,
  `hide_input_in_errors`), sent by the client only for a `LockedContent`,
  derived per request. `adapters/readers/locked.py` opens in memory
  (msoffcrypto with key verification and integrity check; pypdf's own
  decrypt), `operations.py` reads the opened bytes as any file, anchors name
  the customer's file, every PO value flagged `opened_with_password`; source
  views (page, sheet) open it again from the same mail.
- **None opens it, or no candidate**: `Unreadable.locked`, the message routed
  `attachment_locked` ("Tệp có mật khẩu, DW không mở được"), migration
  `2afa1aca0d9d` for the CHECK, web labels and advice, CONTEXT.md.
- **Audit**: `sales.message.processed` carries `encrypted_file`: the
  attachment id and code's sentence, never a password.
- Tests: `tests/unit/test_locked_files.py` (fixtures encrypted at test time
  with a synthetic password), including acceptance 3's search of every
  in-memory row, log record, audit event and span, with mutations shown red.
