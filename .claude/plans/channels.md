# Chat channels (Zalo first)

A two-way chat channel for staff: link a chat, receive notifications in it,
send a few commands, decide an approval after viewing it on the portal. Built
in the first product (Elmich supply chain, `feat/elmich-a-d-s1`) and
upstreamed here without its product commands, on 2026-10-07. The slice ids
are the product's, so its commit messages and this file name the same work.

Decisions: ADR 0005 (the channel, the link, inbound commands), and the ADRs
each slice below names.

| Slice | What it is                                                                                                                                                                         | Platform commit |
| ----- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------- |
| Z1    | Link with a single-use `/start` token (`channel_link_nonces`), `/zalo/status`, `/connect`, `/disconnect`, the `zalo_link_poll` lane, link changes audited and announced in the app | item 1          |
| Z4a   | Inbound foundation: `InboundRouter`, `ChannelCommandRegistry` (empty), message-id dedupe and its retention lane, `find_linked_access` (no role, ceiling), `/zalo/workspace`        | item 1          |

## Not here, and why

- **The settings page** ("Kết nối Zalo", the workspace select): the platform
  web has no `/settings` page, so the link and the workspace choice are API
  only (`/api/v1/zalo/*`, typed in `@dw/api-client`). A product with a
  settings page renders them; the first product's page is its own design.
- **Chat commands** (a proposal, read-only questions): product commands,
  registered at the product's composition root.

## Owed

- A live run against a real bot (the message id field is read as Zalo
  documents it and has not been measured here).
