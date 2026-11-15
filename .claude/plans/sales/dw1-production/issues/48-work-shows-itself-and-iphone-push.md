# 48 — Work shows itself: one place with inline decisions, pushed to the iPhone, held to an SLA

Status: ready-for-agent (built with 47's feed; after 43 part 1)
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
