# 63 — The Bravo gateway: the one process that reads and writes Bravo

Status: in-progress — built and tested offline and on a throwaway SQL Server 2017 (2026-11-21); acceptance 4 pending: IT's two logins on UAT (grant script `docs/proterial/sql/08`), script 07 (triggers under column grants, the cross-database log), the command right and the context's event word for an existing SO's save (ticket 52)
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
- **Fingerprint.** The gateway computes it, for the watch lane (ticket 65),
  and compares it before each write. What a change does (goes on with a
  notice, or pauses only the dependent write kinds) is ticket 65's table.
  Each write kind declares what it depends on.
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
   `timestamp`, a repeated approval id, a write kind paused by the watch.
3. Replaying the 11-20 UAT trace through the gateway produces the client's
   statements for every saved SO UPDATE.
4. On UAT (after ticket 52), each write kind:
   - equals a PIC's own save in every column but ids and times;
   - has Bravo's log naming the PIC.

## Done (2026-11-21, offline and on a throwaway SQL Server)

- **Architecture test first** (`f4c57516`): a driver import, declaration or
  URL outside `apps/bravo-gateway`, or a `uv.lock` driver any other package
  depends on (a library pulling one in counts), fails
  `bravo_database_violations` (ADR 0027). A probe import in `dw_sales` turned
  the script red. Import-linter: nothing imports `dw_bravo_gateway`.
- **Contract** (`ad44cd12`): `dw_bravo.contract`, typed and versioned, five
  write kinds and six reads, each kind declaring its screen and tables;
  `content_hash` over one canonical text; `contracts/jsonschema/bravo_gateway.json`
  generated from it (CI's `--check`). Measured, so the contract changed:
  - the trace holds **no real cancel** (its one cancel save sets `IsCancel`,
    `CancelPrice`, `CancelQuantity` and `CancelAmount` to NULL), so
    `so.line.cancel` is `pending` like split and create (script 03c);
  - the header's rowversion is not in an approval: Bravo rewrites the header
    on every line's save, so the gateway holds the header's condition from
    its own read.
- **Approval token** (`1eda477a`): Ed25519, one fixed format (no header, no
  algorithm to choose), at most 2 h; the approval path holds the private key,
  the gateway public keys by key id. `ApproveAndResumeService.decision_stamps`
  (by approval-type prefix) signs inside the decision's transaction; a stamp
  that cannot be made records nothing. The Sales stamp for an actual Bravo
  write approval type is ticket 53's (the type does not exist yet).
- **The six checks in order** (`8a043345`): token (then the kind's
  `pending`, the tenant's switch, the ledger), identity, Bravo's command
  right and `usp_sys_GetControlPermission` on each typed column, the rules on
  the document as Bravo holds it now, `ufn_Prevent_Edit`, then the ledger's
  claim, the client's statements in one transaction, and the read-back.
  `preview()` runs checks 1-5 and renders the statements without sending.
- **Trace replay (acceptance 3):** of the six saved SO UPDATEs, three are a
  gateway command (a quantity, two confirmed dates); for each the gateway
  renders the client's context line and UPDATE (table, assignments, the
  rowversion WHERE, the read-back) with the client's values. The other three:
  a header's PO number (not a command), `Divide` (a split's first half), the
  cancel cleared. The client's SET column order is its own (not the table's,
  the view's or the rules' order, each tried); an UPDATE's meaning does not
  depend on it, so assignments compare as a set. On the real layout the
  gateway **holds all three back**: ten blocking validators stay undecided
  offline (`NotNull` and others wait on the template, script 03c; `DocNo`'s
  key lookup and `CheckC2`/ECP need Bravo's routines live, ticket 50).
- **Switches (g)**: rule key `sales_bravo_writes`, every kind off in the
  platform's file; a kind is switched on only in a tenant version (proposed
  and approved by two people, as every Sales rule) naming its UAT proof
  (`uat_proof`, required when on). The gateway reads the tenant's approved
  version before each write (`SqlSwitches`), anything malformed reads as off.
- **Ledger**: `bravo.write_ledger` (migration `2c32bc10b019`), keyed by
  approval id, tenant and workspace under RLS forced, DELETE revoked;
  claimed before sending, settled once (`written`, `refused`, `in_doubt`,
  `reconcile_failed`). Integration: cross-tenant read, write and settle
  refused; unscoped reads nothing; a spent approval cannot be deleted.
- **One tenant per gateway**: a token another DW tenant's approval signed is
  refused (`another_tenants_approval`), found by `reviewing-feature-security`.
- **Container**: `infra/docker/bravo-gateway.Dockerfile`, compose service
  `bravo-gateway` (profile `bravo`), no port, on `dw-bravo` (internal: api,
  worker, postgres) and `dw-bravo-egress` (it alone: the route to Bravo's
  LAN, to be narrowed to Bravo's address by the host's firewall, DOCKER-USER).
  Read-only root, no capabilities, uid 1001, 512 MB, `init`. Refuses to start
  half-configured, and deployed without the approval keys or with
  encryption off. CI builds it, checks the driver loads and the refusal, and
  scans it. trivy 0.74.0 on the image: 0 HIGH/CRITICAL with a fix.
- **Tests**: unit 63 (each check refuses in its own test; service; switches),
  trace replay 1, PostgreSQL 5, SQL Server 11. Mutation: 18 pipeline guards,
  6 adapter guards, the tenant pin and the lock map, each broken, each red.

## Comments

**Driver, measured 2026-11-21** in `python:3.12-slim-bookworm` (the apps'
base) against SQL Server 2017 CU31 (Bravo runs 2017) with a schema written
for the measurement: column grants, a same-database AFTER UPDATE trigger
reading the user from CONTEXT_INFO, the rowversion WHERE, SNAPSHOT reads, TLS.

| Driver | Result | Licence | Verdict |
|---|---|---|---|
| python-tds 1.17.1 | rowversion read as text (UnicodeDecodeError), sent as nvarchar; TLS needs pyOpenSSL | MIT | rejected |
| pymssql 2.4.6 (wheel) | every check passes; 54 MB | LGPL-2.1, bundles FreeTDS | rejected: the wheel bundles **OpenSSL 1.1.1k** (end of life 2023); a source build on Debian's FreeTDS 1.3.17 fails (`DBSETLENCRYPTION`), 2.3.x does not build (setuptools_scm) |
| **mssql-python 1.18.0** | every check passes; 79 MB; loads Debian's OpenSSL 3 | MIT, plus `mssql-python-odbc` 18.6.2.2 under **Microsoft's ODBC Driver licence** (proprietary); pulls azure-identity and msal | **chosen**; needs libltdl7, libkrb5-3, libgssapi-krb5-2 |

Measured on the way, for ticket 52 and the grant script:
- a login with column grants only updates its columns, and the
  same-database trigger runs and logs the PIC from the context;
- **a trigger writing to another database fails under it** (error 916): if
  Bravo's `DML_*_ChangeLog` triggers write to `<db>_Log`, the write login
  needs a user there; script 07 answers it;
- CONTEXT_INFO stays on a connection after commit: the adapter clears it in
  `finally` and never reuses a connection;
- SQL Server refuses SNAPSHOT inside a transaction the driver already
  opened: reads connect in autocommit and begin it themselves.

Decisions taken alone, for Đạt to review: the driver (proprietary ODBC
component vs an EOL OpenSSL); the live `command_right` answers "unknown"
(every live write refused) until the client's use of
`ufn_B00Permission_Getdata` is measured; the context's event word for an
existing SO's save is refused until traced; `Expire` (tinyint) read as
inactive when set, `LockDate` not read as an account lock; with several
active layouts for a screen the gateway refuses rather than pick one.
