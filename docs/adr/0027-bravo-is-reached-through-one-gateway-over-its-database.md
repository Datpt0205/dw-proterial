---
status: Accepted
date: 2026-11-21
accepted: 2026-11-21 (Đạt: take the best option now and build on it; Proterial IT reviews the gateway's grants before production)
supersedes: 0026-bravo-is-read-through-its-vendor-api-and-written-by-a-person.md
source:
    - ../../.claude/plans/sales.md
    - ../../.claude/plans/ops-hardening.md
    - ../../.claude/plans/sales/dw1-production/issues/63-bravo-gateway.md
    - ../../.claude/plans/sales/dw1-production/issues/64-one-person-many-accounts.md
---

# Bravo is reached through one gateway over its database, writing under the PIC's own Bravo user

## Context

ADR 0026 had DW read Bravo through a vendor API and leave every write to a
person. The API never came, and on 11-19/20 Proterial IT agreed to let DW use
Bravo's SQL Server instead, on two conditions: writes are tried on UAT first,
and no business data leaves Proterial. Đạt (11-20) wants DW to perform the
writes itself, an Import included, under the approving PIC's own Bravo user,
after the PIC approves on the portal.

What the 11-19/20 survey measured (details in `docs/proterial/`, outside git):

- Bravo is two-tier. Every client connects with one shared SQL login. "The
  Bravo user" is an id the client puts in the connection's context, which
  Bravo's triggers and logs read. SQL Server itself never checks who the user
  is.
- A screen's rules are XML data in Bravo's database, executed by the client,
  not by SQL Server. A write through the database skips them unless DW runs
  them (ticket 59 runs the SO screen's offline, column for column against a
  UAT trace).
- Bravo saves with plain INSERT and UPDATE statements under an optimistic
  `timestamp` check, not through stored procedures.
- Bravo's rights are rows in its database (`B00Permission`, `B00PermissionData`,
  `B00UserRole`, the `B00UserList` group tree), resolved by Bravo's own
  functions. A Bravo user carries its employee code (`B00UserList.Ma_CbNv`),
  which joins the employee record and its e-mail. Bravo can map Windows
  accounts to its users, but Proterial uses that for few of them.

## Options considered

**Where the Bravo code runs**

| Option                                                                                                                        | Verdict                                                                                                                                                                                                                                                                                                                                             |
| ----------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A. The vendor's API (ADR 0026)                                                                                                | Rejected: none exists, and it would still not run the screen's XML rules. Kept as an adapter behind the same port if one ever ships.                                                                                                                                                                                                                |
| B. Each context connects to SQL Server itself                                                                                 | Rejected: the credential in two packages and two processes, two copies of the write rules.                                                                                                                                                                                                                                                          |
| C. Stored procedures and views in a `dw` schema inside Bravo's database, writes staged in a table and applied by an Agent job | Rejected: the procedures either copy the screen rules (a second copy that drifts, against ticket 59's purpose) or apply whatever they are given (no safety added). Our code would live in the vendor's database, deployed by IT, who do not touch Bravo, and survive or vanish with each Bravo upgrade and UAT restore. Two languages for one gate. |
| D. An MCP server whose tools write Bravo                                                                                      | Rejected for writes: a model would call the effect directly, around the executor's approval, idempotency and audit, and any MCP client that connects could write the ERP. Possible later as a read-only face of the gateway, for a consumer outside DW.                                                                                             |
| **E. One gateway service, in this monorepo, the only holder of Bravo's credentials**                                          | **Chosen.**                                                                                                                                                                                                                                                                                                                                         |

**How a document is created**

| Option                                                                            | Verdict                                                                                                                                |
| --------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| 1. The vendor's automatic Import or procedure (ticket 60)                         | Preferred when the vendor offers one; plugs into the gateway as another creation path.                                                 |
| **2. DW's runner of Bravo's own XML rules (ticket 59) computes the exact INSERT** | **The path built now.** It reproduced every saved SO UPDATE in the trace; creation waits on the shared template's layout (script 03c). |
| 3. UI automation of the Import button                                             | Last resort only: authoring as the PIC would need each PIC's Bravo password stored.                                                    |

**Whose name is on the write, and how DW knows it is that person**

| Option                                          | Verdict                                                                                                 |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| A robot Bravo user                              | Rejected: Đạt wants the PIC's own name on the document.                                                 |
| Storing PICs' Bravo passwords, or checking them | Rejected: DW would hold or verify passwords whose hashing is the vendor's.                              |
| Linking by Windows login or e-mail              | Rejected as the key: both change. Used once, to find the employee code, when the AD has no employee id. |
| An admin linking every account by hand          | Kept as the fallback for what the automatic link refuses.                                               |
| **The employee code as the anchor**             | **Chosen**: the person, not an account.                                                                 |

**Who signs in to DW**

| Option                                      | Verdict                                                                                           |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| DW-only accounts                            | Rejected: a second password per person, and leavers removed by hand.                              |
| The app reading Proterial's AD directly     | Rejected: ties the platform to one customer's directory; FPT's own staff are not in it.           |
| **Keycloak, federated with Proterial's AD** | **Chosen**: Windows sign-in, AD disable ends DW access, Keycloak stays the platform's one broker. |

## Decision

1. **One gateway.** `apps/bravo-gateway`, a container of its own on the DW
   host, beside SQL Server on Proterial's LAN, is the only process that holds
   a Bravo credential or a SQL Server driver. The architecture test refuses a
   driver anywhere else. It is Python and runs `dw_bravo` (ticket 59) on
   Bravo's live layouts. DW1 and DW2 reach it through a port each context
   already declares, with an HTTP adapter. Typed commands are versioned
   contracts, for example "set line N's confirmed date" or "create the SO for
   case C". There is no free-form SQL, and nothing else crosses.
2. **Nothing of DW's inside Bravo's database.** IT creates two logins once, and
   no view, procedure, table or job:
    - **read**: SELECT on the tables and columns DW reads, under SNAPSHOT;
    - **write**: INSERT/UPDATE on exactly the tables and columns the planned
      writes touch (column-level grants).

    Neither login is sysadmin, a member of `db_owner`, or able to read
    passwords. The grant script is FPT's, reviewed by IT, kept outside git.

3. **A write is the PIC's, proven three times.**
    - **Signed approval.** The PIC approves the exact content on the portal.
      The approval path signs a token carrying: the approval id, the content's
      hash, the resolved Bravo user, and an expiry.
      The approval is decided by **one person**, the one whose Bravo user the
      write goes under (`bravo_write.<document>`, not under a context's strict
      maker-checker prefix; sales ticket 53, 2026-11-21): their own Bravo
      rights, read at the write, decide what they may change.
    - **The gateway checks before it writes.** It verifies the token, then:
        - the Bravo user is still active and still that person's (identity 5);
        - the user's right on that screen, from Bravo's own permission rows and
          functions, read live, never copied;
        - the screen's rules (`dw_bravo`), with blocks refusing;
        - the document's lock and approval state.
    - **Bravo's own way of writing.** The write carries the PIC's user in the
      client's context format, holds the `timestamp` condition, uses the
      approval id as its idempotency key, and is read back and reconciled.
    - **Never.** The trigger-bypass context is never used.
4. **Watch for change; do not ask for a promise** (Đạt, 11-21; ticket 65).
    - **What is watched.** On a schedule, DW fingerprints what its writes
      depend on: layouts, templates, columns, triggers, the routines it calls,
      and the client version. It notices a change and tells a person.
    - **A change the runner follows goes on.** A layout whose rules all still
      parse, and whose nightly replay agrees, keeps the writes running, with a
      notice. This is why the rules are read, not copied.
    - **A change it cannot follow pauses only the writes that depend on it.**
      That covers an unknown rule, and a changed column, trigger, routine or
      context format. Reads go on. The writes resume when a person accepts the
      new baseline after the UAT replay. Nothing resumes by itself.
    - **Early warning.** A difference between UAT and production is reported
      as a warning ahead of the upgrade.
5. **Identity is anchored on the employee code.**
    - **DW side.** Keycloak federated with the AD keys a person on the AD's
      immutable object id, so a renamed account stays the same person. DW
      stores person ↔ employee code.
    - **Bravo side.** The Bravo user is looked up live by employee code at each
      write.
    - **Links happen automatically when unambiguous.** An exact, unique match
      links itself, and every link is audited and announced. Anything
      ambiguous waits for an admin: two live accounts for one code, two Bravo
      users for one code, or no match.
    - **Leavers and changes stop the write.** A leaver is stopped by the AD and
      by Bravo's `IsActive`. A Bravo user that changed between approval and
      write refuses the write, and the PIC approves again.
6. **Three layers, each the owner of one answer.**
    - **Who someone is:** the AD, through Keycloak.
    - **What they may do in DW:** DW's permission sets.
    - **What they may do in Bravo:** Bravo, at the moment of the write.
7. **UAT first, always.** A write kind is enabled in production only after it
   has reproduced a PIC's own save column for column on UAT.

## Consequences

- ADR 0026 is superseded. Its "no answer from Bravo means no answer" holds
  unchanged. The paste sheet stays as the manual fallback while a write kind
  is not yet enabled.
- Tickets:
    - 49: this ADR.
    - 50: reads through the gateway, no views.
    - 51: creation through the gateway.
    - 52: what must be measured on UAT first.
    - 53: adjustments through the gateway, no staging table or job.
    - 63: the gateway.
    - 64: identity.
    - 65: the change watch.
- What this rests on that is not yet measured goes to ticket 52:
    - Bravo's triggers run under a login with column grants;
    - the driver in a Linux container;
    - Keycloak's AD federation keeps a renamed account as the same person;
    - employee codes are filled and unique for live users.

    Đạt decided to build on the assumption that they hold. A failed
    measurement changes only the gateway's adapter or grants, never a context.

## Addendum 2026-11-25: DW enters everything Sales entered (Đạt)

Đạt, 2026-11-25: "giờ scope không còn là sale tự nhập nữa mà là DW nhập cho
họ, chỉ duyệt trước khi nhập thôi". DW1 performs every Bravo entry Sales
made by hand, each after the PIC approves it on the portal, under the PIC's
Bravo user, through the gateway as decided above. The paste sheet and the
YCBG draft stay only as the fallback while a write kind is off.

The write kinds, per screen Sales entered (`docs/proterial/bravo`):

- **YCBG** (`EDIT_BizDocRQ`, `B30BizDoc` + `B30BizDocDetailRQ`): create, and
  edit a line before Design answers.
- **Quotation** (`EDIT_BizDocSQ`, `B30BizDocDetailSQ`): create after Design's
  QUOTE, and edit; the price stays Bravo's, computed by the screen's own
  rules the runner executes (ticket 59, dw_sales ADR 0008), never DW's.
- **SO** (`EDIT_BizDocSO`, `B30BizDocDetailSO`): create (typed or by Import),
  a line's confirmed date and quantity, a split, a cancel (the 5 kinds
  already defined).

Each kind stays off until a UAT save of it was traced (the columns it
writes, the context's event word, the rights it checks, what the client
sets that no layout holds), the gateway's write login is granted exactly
those columns (`docs/proterial/sql/08`), and its UAT acceptance passed
(decision 7). No approval workflow exists in Bravo for SO or quotations
(script 05, 2026-11-25): the approval is DW's, before the entry.
