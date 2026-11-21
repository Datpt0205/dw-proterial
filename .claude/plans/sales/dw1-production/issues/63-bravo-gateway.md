# 63 — The Bravo gateway: the one process that reads and writes Bravo

Status: ready-for-agent (build against recorded traces; live Bravo waits on IT's two logins on UAT)
Blocked by: none offline; IT's logins (grant script from this ticket) for UAT
Category: enhancement (ADR 0027)

## Why

ADR 0027 puts every Bravo read and write in one service. Only that service
holds a Bravo credential, runs the screen rules (`dw_bravo`, ticket 59), and
can be fixed alone when Bravo changes. It serves DW1 and DW2.

## Shape

- **App.** `apps/bravo-gateway`: a container on the DW host, Python, built
  on `dw_bravo`, the only place a SQL Server driver is declared. Pick the
  driver by measuring it in the Linux image, not by reading about it
  (failure-modes #4).
- **Architecture test first.** `scripts/verify_architecture.py`
  `bravo_database_violations` allows a driver in `apps/bravo-gateway` only:
  import, declaration and URL. The `uv.lock` entry is allowed only while the
  gateway is its sole declarer. A probe import in `dw_sales` turns it red. It
  cites ADR 0027.
- **Contract.** Versioned, typed commands and queries, JSON schemas under
  `contracts/`:
  - reads:
    - customer;
    - item and convert list;
    - quotation lookup on a date;
    - SO and YCBG state;
    - black list, LME and export control;
  - writes, each with a version:
    - `so.create`;
    - `so.line.set_confirmed_date`;
    - `so.line.split`;
    - `so.line.set_quantity`;
    - `so.line.cancel`.

  A context reaches them through its own port, with an HTTP adapter in its
  `adapters` package. No context imports the gateway.
- **A write's checks, in order.** The first one that fails refuses the write:
  1. The approval token: signed at the approval decision, with the approval
     id, the content hash, the Bravo user and the expiry. The gateway trusts
     nothing else in the request.
  2. Identity is live (ticket 64): the Bravo user is active, still that
     employee's, and the same one the approval stamped.
  3. Bravo's right. It is read from Bravo's own permission functions (the
     user and group tree, roles, the `No*` flags on that command), never
     copied into DW.
  4. The screen rules (`dw_bravo` on the live layout): blocks refuse; warnings
     go back to the PIC with the result.
  5. The document is not locked and not in Bravo's approval flow.
  6. The write itself: the PIC's user in the client's context format, the
     `timestamp` condition, and the approval id as the idempotency key
     (ledger in DW's PostgreSQL). It is read back and reconciled column by
     column.
- **Fingerprint.** The hashes of the layouts, Import templates and table
  columns the gateway depends on. A hash different from the one proven on
  UAT stops writes (reads go on) and opens a notice to a person.
- **Load.** One write at a time per document. Writes are throttled during
  8–18h (Vietnam time). A Bravo that does not answer is a "could not
  check", never a pass (ADR 0026's rule 5, kept).
- **Grant script** for IT (kept in `docs/proterial/sql/`, outside git), one
  script with two sections:
  - the read login: SELECT on the tables and columns the reads use;
  - the write login: INSERT/UPDATE on exactly the columns the five writes
    touch, derived from the trace.

  Neither login gets a role.
- **Offline first.** The adapter can answer from a recorded trace (ticket
  59's `recorded`), so the whole path is tested with no Bravo.

## Acceptance

1. Outside `apps/bravo-gateway`, a driver import, declaration or URL fails the
   architecture test (red, then green).
2. Each check above refuses in a test of its own: a bad signature, a changed
   content hash, an expired token, a user changed since approval, a user
   without the right, a blocking validator, a locked document, a stale
   `timestamp`, a repeated approval id, a changed fingerprint.
3. Replaying the 11-20 UAT trace through the gateway produces the client's
   statements for every saved SO UPDATE.
4. On UAT (after ticket 52), each write kind:
   - equals a PIC's own save in every column but ids and times;
   - has Bravo's log naming the PIC.

## Comments
