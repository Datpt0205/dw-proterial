# 17 — A PO file with a password, opened with its own mail's password

Status: ready-for-agent
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
