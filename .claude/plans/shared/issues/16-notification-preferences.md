# 16 — Each person chooses which notices push, and quiet hours

Status: ready-for-agent
Blocked by: none
Category: notifications / platform

## What

§4: "Tùy chọn từng người: loại nào báo, giờ im lặng, bật/tắt push từng loại".
Checked 2026-11-27: not built. Push is on or off per device
(`dw_platform/application/web_push.py`), and since `04769aab` every notice
`platform.deliver_notification` inserts is pushed to every subscribed device
of its recipient (`p_push`, lane `web_push_delivery`). There is no per-kind
choice and no quiet time; `platform.channel_preferences` is the Zalo
workspace choice, not this.

## Design

- **Kinds have one owner:** a notice's kind is its `source_key` up to the
  first `:` (e.g. `sales.case.assigned`); each context declares the kinds it
  sends and their Vietnamese labels in one table (web labels keyed by code).
- `platform.notification_preferences` (tenant, workspace, user, kind, push
  on/off) and `platform.notification_quiet_hours` (user, from, to, in the
  tenant's zone); RLS narrowed by recipient like the inbox; migration with
  grants. A person reads and writes their own only.
- **The inbox always keeps the notice.** Preferences only decide the push:
  `deliver_notification` queues no `web_push` for a kind turned off; one in
  quiet hours is queued with `not_before` at the end of the quiet time and
  collapses under the existing tag.
- **Not mutable away:** a kind marked required by its context (an approval
  the person must decide, a Bravo write in doubt) cannot be turned off;
  the page shows it locked with the reason.
- Web: a "Thông báo" section on the profile next to the push switch.

## Acceptance

- PostgreSQL: a kind turned off queues no push but inserts the notice; quiet
  hours delay; a required kind still pushes; another user's preferences
  unreadable and unwritable (RLS).
- Unit: the lane sends nothing before `not_before`.
- Mutation: the off check, the required exception: red.

## Owed

- none. (The shared-device consent gap is Sales ticket 78's follow-up.)
