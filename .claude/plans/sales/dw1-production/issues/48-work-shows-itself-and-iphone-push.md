# 48 — Work shows itself: one place with inline decisions, pushed to the iPhone, held to an SLA

Status: in progress (slice built 2026-11-15; a real iPhone is a UAT step; what is left is under "Done")
Blocked by: none (44 later lowers how much reaches a person)
Category: enhancement

## Why

Đạt, 2026-11-17: notify the iPhone's screen for every flow that needs a
person (the plant gives the host full internet); clicking each row to open
a chat makes it hard to see that there is work; make it fast enough to meet
the SLA.

## Shape

- **One place for a person's work**: "Việc của tôi", the same page as 47's
  "Hôm nay" (the brief on top). Every item that waits on this person shows
  its decision inline, without opening anything: what DW proposes, the
  quote or figure it rests on ("Xem trong thư" on click), and the buttons
  the case already has (confirm, correct, pick, approve). A correction
  opens in place. The chat (46) is for questions, never the way to act.
- **Ordered by the SLA**: each item carries its due time from the tenant's
  configuration (the follow-up hours already on the head's screen, ticket
  35); overdue and about-to-breach first, then by tier; a countdown shows.
- **Push to the iPhone (Web Push to the installed portal)**: the portal is
  a PWA (manifest, icons, a service worker of our own, no library); a
  person turns notifications on once from their profile (iOS asks inside
  the installed app, 16.4+). The worker sends a push when an item enters
  their queue, before it breaches its SLA, and when it escalates to the
  head. Tapping opens that item, expanded, ready to decide; the app badge
  is the count. Several items within a few minutes become one push
  ("3 việc mới"), so the phone does not ring for each.
- **What a push says**: the kind of work and the case number, never a
  price, an amount or a customer's text; the tenant may turn the case
  number off for the lock screen.
- **Sending**: VAPID keys from the deployment's secrets (never in the
  repo); payloads encrypted per RFC 8291 by `pywebpush` (pinned); the push
  services' hosts in `DW_API_OUTBOUND_ALLOWED_HOSTS` (Apple's
  `web.push.apple.com`, and the others only if someone subscribes from
  them); a subscription gone (404/410) is deleted; per tenant and user,
  RLS, retention.
- **Escalation**: an item past its SLA notifies the head too (the
  escalation hours already exist); the item shows who was told when.

## Acceptance

1. A new item for a person reaches their iPhone as one push that opens the
   item ready to decide (measured on a real iPhone at UAT; the payload and
   deep link tested here).
2. No push carries a price, an amount or a customer's text (a test over
   every push kind).
3. Another tenant's or person's subscription never receives a push meant
   for someone else (negative test).
4. An item is decided from the list without opening a chat or a second
   page, for every item kind the queue holds.
5. An item past its SLA reaches the head, once.

## Risks to check

- iOS needs the portal served over HTTPS with a certificate the iPhone
  trusts and installed to the Home Screen; an internal CA means installing
  its profile on each iPhone (ask IT).
- Cato's client sits between the iPhone and the portal; the push itself
  goes from Apple to the phone, outside it.

## Done (2026-11-15, one slice with ticket 47)

- **Decided inline.** Each row of "Việc cần làm" expands (and a push's link
  `/sales?item=order:<id>` opens it expanded and scrolled to) into the case
  page's own components: `OrderActions` for an order, `QuoteActions` plus the
  send and approval panels for a quote, so no rule is decided twice. An
  order step that needs its source opened stays disabled with the reason and
  links to the case page (the server refuses it too). A mail links to its
  place in "Hộp thư". `served.ts` now owns "what of the source is unopened"
  for both the page and the row.
- **Ordered by the SLA.** `WorkItem.sla_warn_at` / `sla_due_at` come from
  `dw_sales.domain.followups.sla_of`, the same timings the lane reminds and
  escalates by: an unconfirmed order is about to be late at its reminder
  (4 h) and late at its escalation to the head (24 h); a quote request at its
  deadline warning (48 h before) and the end of its due day. Late first,
  then about to be, then by due time, with a countdown column ("Hạn xử lý").
  Sorted in the browser over the whole list (`myWork` reads every page).
- **Web Push.** The portal's manifest and icons were there; `public/sw.js`
  is our own worker (no library): shows the push, adds to the app badge,
  opens the link on tap. "Thông báo trên điện thoại" in the account menu
  turns it on per device (iOS: explains, once, to add DW to the Home Screen
  first). `platform.push_subscriptions` (RLS per tenant + workspace + user,
  one door in `platform.save_push_subscription`, a device that signs in as
  someone else moves to them, 90-day prune for one not renewed, the portal
  renews on every open). `PushSenderPort` with `PyWebPushSender`
  (`pywebpush==2.5.0`, measured against a local endpoint and kept as a test:
  aes128gcm decrypts, VAPID `sub`/`aud`, 410 is gone) and fakes in tests. A
  gone subscription (404/410) is deleted. VAPID key from
  `DW_WEB_PUSH_VAPID_PRIVATE_KEY` only; a deployed profile with
  `DW_WEB_PUSH_ENABLED=true` and no key or subject refuses to start;
  `scripts/dev.sh` writes a local key into `.env` when it has none. A
  subscription and a send are allowed only for an `https` endpoint whose
  host is in the outbound allow-list (on premises: `web.push.apple.com`).
- **What is pushed.** Every reminder the `sales_followups` lane records:
  "your turn" (a new item), the reminder before the SLA breaks, the
  escalation to the head (once: the lane's record), and the other
  follow-ups. One push per person per tick (about five minutes), so several
  items ring once ("3 việc mới"). Payload: five fields, the kind of work and
  the case number at most (a number that does not look like one is left
  out; the tenant can turn the number off: `sales_followups@1.5.0`
  `push.case_number`). Test over every push kind. Audited as the lane
  (`sales.followup.pushed`, counts only).

**Left:** "Xem trong thư" (the quote or figure an item rests on) in the row;
the item showing who was told of an escalation and when; a mail routed to
Sales is not pushed (no follow-up times it); approvals of rule versions,
layouts and master data are linked from the priority panel, not inlined;
signing out does not turn a device's pushes off (a shared phone would keep
ringing for its last person until someone else turns pushes on there); a
real iPhone at UAT (HTTPS with a certificate the iPhone trusts, installed to
the Home Screen, 16.4+).

