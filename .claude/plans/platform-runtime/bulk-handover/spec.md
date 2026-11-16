# Bulk handover: everything a leaver owns, to one successor

Status: ready-for-agent (Đạt, 2026-11-16: "làm Bàn giao toàn bộ"; who presses
it is the default below until he says otherwise)
Category: enhancement
Areas: platform (members), dw_sales (DW1), dw_purchasing (DW2)

## Why

A PIC or buyer leaves while work is open. Today the head reassigns one case at
a time (`dw_sales.application.assignment`, ticket 17), nothing moves the rest,
and a member can be removed while still owning open work, which then belongs
to nobody. Proterial will run `record_visibility = restricted` (Đạt leans that
way, to confirm with Proterial), where staff do not see each other's cases,
so a handover is the only way work moves.

How a mailbox is tied to a member (no AD): the member's sign-in email equals
their Outlook address equals their folder `DW-mail/<address>` in the Team,
shared to them alone; a lane reads only folders named by a member holding its
scope (`dw_platform.application.drop_folder.OwnedFolders`, compared
lowercase). A deactivated leaver's folder is therefore read by no one.

## Shape

- One action: pick leaver A and successor B; a **preview** lists what moves
  and every warning; one **confirm** moves it all. Each move is its own row's
  change with its own audit event ("handover A -> B by X", ids and counts,
  never amounts), the whole under one idempotency key; B is told once through
  the platform inbox with a summary.
- **Moves:**
  1. DW1 open order and quote cases assigned to A (`order_cases.assigned_to`,
     `quote_cases.assigned_to`): to B, version bumped as in ticket 17.
  2. DW1 customers whose Sales PIC is A (master data), so new POs route to B.
  3. Mail A pressed to send that has not left (`outbound_mails` with
     `requested_by` = A, no receipt yet): cancelled, its job file withdrawn
     from A's outbox, returned to B as a draft (it would leave from A's
     mailbox, which is about to close).
  4. A's reminders (`reminder_marks`).
  5. DW2 open requests and RFQs where A is the buyer; unsent RFQs back to
     drafts for B, as in 3.
- **Stays:** history and audit (who did what stays A), A's private assistant
  sessions (`assistant_sessions`, pruned by retention).
- **Warnings in the preview:** A is the only holder of a scope (e.g. the only
  quote approver): grant it to someone first; B lacks the scope the work needs
  (B cannot be chosen); B has no `DW-mail/<B's address>` folder yet; a
  reminder to IT to forward A's mailbox to B before the M365 account goes.
- **Guard:** A cannot be deactivated while owning open work (refused, naming
  what is open). Deactivate, never delete: history keeps A's name.
- **Who:** a granted scope (`platform.member.handover` or per context),
  default given to the department head for their workspace and to IT (admin)
  as fallback. Refused for support contexts. Cross-workspace or cross-tenant
  successors refused without saying whether they exist.

## Also in this slice

- **A mailbox with no folder:** a member holding a mail-reading scope whose
  address has no folder in the drop (a typo at account creation, an alias) is
  told to IT once (the drop already lists folders; compare lowercase).
- **DW2 does not apply managers:** `dw_purchasing` lists ignore
  `AccessContext.visible_owners` (DW1 applies it, `dw_sales.application.visibility`).
  Apply the same rule to DW2's requests by their buyer: own, unassigned,
  reports', and those waiting on the viewer's decision; not found, never 403.

## Acceptance

1. A preview for A lists exactly A's open cases, customers, unsent mail,
   reminders and DW2 requests, and nothing of anyone else's (a second PIC's
   work in the same workspace stays put).
2. Confirm moves them all to B; each has an audit row naming A, B and who
   pressed; a retry with the same key changes nothing.
3. An unsent mail of A's does not leave from A's mailbox after the handover;
   B sees it as a draft.
4. A cannot be deactivated while anything is open; after the handover A can.
5. B without the needed scope cannot be chosen; another workspace's or
   tenant's member cannot be chosen, and the refusal does not confirm they
   exist.
6. In a restricted tenant, a DW2 buyer sees only own, unassigned, reports' and
   to-decide requests; an open tenant sees all.
7. A member with a mail-reading scope and no matching folder is reported once.

## Owed

- Đạt: confirm who presses it (default: head per department, IT fallback).
- Proterial: `restricted` or `open` (Đạt leans restricted).
