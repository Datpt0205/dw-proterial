# 64 — One person, many accounts: identity anchored on the employee code

Status: ready-for-agent (build on the ADR's assumptions; script 06 and IT's AD answers confirm them)
Blocked by: none to build; the AD federation on site waits on IT (LDAPS or their federation service)
Category: enhancement (ADR 0027, decisions 5 and 6)

## Why

A write must be the PIC's own, under their Bravo user. Accounts change:
- a Windows login is renamed;
- an e-mail changes;
- an AD account is re-created;
- a Bravo user is re-created.

Đạt (11-21): linking by hand is tiring, and linking by an account name breaks
when it changes. The person is the anchor, and every account only points to
the person.

## Shape

- **Sign-in.** Keycloak is federated with Proterial's AD. It keys a user on
  the AD's immutable object id, not the login name. Measure that a rename
  keeps the same Keycloak user before relying on it. Local Keycloak accounts
  remain for FPT staff.
- **Anchor.** DW stores person ↔ employee code: the tenant, the Keycloak
  subject, the employee code, how it was linked, and when.
  - The AD's employee id gives the code when IT fills it.
  - Otherwise the AD e-mail is matched once against Bravo's employee record,
    which yields the code; after that the e-mail is not used again.
- **Bravo user.** It is looked up live at each write, by employee code:
  exactly one active Bravo user, or the write is refused.
- **Automatic, never a guess.**
  - **Links itself:** a unique exact match. The link is audited and announced
    to the person and the admin.
  - **Goes to the admin queue:**
    - two live accounts for one code;
    - two active Bravo users for one code;
    - no match;
    - a re-link while the old account is still live.
- **Changes.**
  - **Leavers:** an AD disable ends sign-in; Bravo's `IsActive = 0` refuses
    the write.
  - **A re-created account** with the same code re-links automatically once
    the old account is disabled.
  - **Approval stamp:** the approval records the Bravo user it resolved. A
    different user at write time refuses, and the PIC approves again.
- **Who may manage links** is a permission (`sales.identity.link` or a
  platform one, whichever already owns it), checked where the link is
  written.

## Acceptance

Each of these is a test:
- a rename keeps the link;
- a re-created AD account re-links only after the old one is disabled;
- two Bravo users for one code queue for the admin;
- an inactive Bravo user refuses the write;
- a user changed since the approval refuses the write;
- a cross-tenant link is impossible.

## Comments
