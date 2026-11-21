# 64 — One person, many accounts: identity anchored on the employee code

Status: in-progress — measured on Keycloak 26.7.2 with LDAP; the link rules, store and admin path built (2026-11-21). pending: Proterial's AD (`objectGUID` as Keycloak's UUID attribute, whether `employeeID` is filled, LDAPS or a federation service: ticket 52 item 8); the people source (Keycloak's user attributes) and Bravo's people reads through the gateway (ticket 50) before the sweep runs; the admin page
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

## Done (2026-11-21)

- **Measured** (throwaway OpenLDAP 1.5.0 and Keycloak 26.7.2, the pinned
  version; LDAP federation, `uuidLDAPAttribute: entryUUID`, READ_ONLY):
  - a login renamed in the directory (modrdn `uid=nva` → `uid=nva.renamed`)
    is the **same Keycloak user** after sync (id unchanged, username follows);
  - an account deleted and created again with the old login is a **new
    Keycloak user** (new id, new `LDAP_ID`), and full sync removes the old.
  So the link keys on the subject, and a re-created account needs linking
  again. On Proterial's AD the attribute is `objectGUID`: only measurable
  there (pending).
- **Rules** (`dw_sales.application.identity_links.decide`): linked already
  or disabled → nothing; the AD's employee id, else one e-mail match in
  Bravo's employee record; exactly one active Bravo user for the code, else
  the queue (`no_match`, `several_matches`, `two_bravo_users`); a code held
  by a live account → `relink_while_old_live`; held by a disabled one → the
  link moves and the old one is retired. Bravo not answering links nothing.
- **Store** (migration `adad4d524377`, `bravo.person_links`,
  `bravo.link_queue`, tenant only, RLS forced, DELETE revoked): one live link
  per person and per code held by partial unique indexes; a retired link
  frees its code; one open queue item per person.
- **By hand**: `IdentityLinks.link_by_hand` checks `sales.identity.link`
  where the link is written and needs exactly one active Bravo user; audited.
- **At the write** (ticket 63): the gateway looks the Bravo user up by code
  live, refuses an inactive one, two active ones, or one changed since the
  approval (tests in `test_gateway_checks.py`).
- Tests: rules and service 13 (each acceptance item), PostgreSQL 2 (DB holds
  the invariant, cross-tenant); 7 mutations red.

## Comments
