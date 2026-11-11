# Chat channels (Zalo first)

A two-way chat channel for staff: link a chat, receive notifications in it,
send a few commands, decide an approval after viewing it on the portal. Built
in the first product (Elmich supply chain, `feat/elmich-a-d-s1`) and
upstreamed here without its product commands, on 2026-10-07. The slice ids
are the product's, so its commit messages and this file name the same work.

Decisions: `docs/adr/0005-zalo-bot-is-the-first-chat-channel.md` (the
channel, the link, inbound commands), and the ADRs each slice below names.
Two files share each of the numbers 0005, 0006, 0007, 0009, 0010 and 0011
in `docs/adr`, so an ADR is
cited by file name (`CLAUDE.md` Domain docs, 2026-10-15): 0006 is
`0006-provider-neutral-channel-delivery-outbox.md`, 0007
`0007-chat-decisions-after-a-portal-view.md`, 0008
`0008-chat-updates-poll-locally-webhook-when-hosted.md`, 0009
`0009-hosting-on-three-hostnames-behind-caddy.md`.

| Slice | What it is                                                                                                                                                                                                                                                                               | Platform commit |
| ----- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------- |
| Z1    | Link with a single-use `/start` token (`channel_link_nonces`), `/zalo/status`, `/connect`, `/disconnect`, the `zalo_link_poll` lane, link changes audited and announced in the app                                                                                                       | `dfa0f39`       |
| Z4a   | Inbound foundation: `InboundRouter`, `ChannelCommandRegistry` (empty), message-id dedupe and its retention lane, `find_linked_access` (no role, ceiling), `/zalo/workspace`                                                                                                              | `dfa0f39`       |
| Z2    | Notifications out through a linked chat: `channel_deliveries` queued by `deliver_notification`, the `channel_delivery` lane (SKIP LOCKED, link and membership re-checked, 1/2/4/8 min backoff, fail at 5), prune lane; ADR 0006                                                          | `8f1928f`       |
| Z5    | Decide in a chat after a portal view: view receipts, single-use 6-digit HMAC codes (10 min, lock at 5), `decide(channel=, admission=)`, the `DUYỆT`/`KHÔNG` command builder for a context's runner, `/approvals/[id]` with "Lấy mã"; ADR 0007                                            | `3da0138`       |
| Z3    | Webhook for hosted deployments: `POST /zalo/webhook` under `ZALO_UPDATES_MODE=webhook` (header secret, 64 KB, schema), `channel_inbound_updates` queue, `zalo_webhook_drain` lane, mode guard, https and 32-character secret required when deployed, `scripts/zalo_webhook.py`; ADR 0008 | `0231c1a`       |
| —     | Channel delivery expiry: a delivery pending past `retention@1.7.0.yaml` `channel_deliveries.pending_expiry_days` (7) fails as `channel_unconfigured`, audited (`platform-runtime/channel-delivery-expiry/01`, ADR 0006 amendment)                                                        | `7a3e438`       |

Upstreamed in the same pass, outside this area: the shared model-stack
builder and `DailyAllowance` (`dc40a33`, ADR 0005 amendment), the Caddy host
overlay and https-when-deployed (`f1a260c`, ADR 0009), the eval grader seam
(`5643634`), the RLS catalog-query fence (`ca369f2`). Migrations
`02930a73bbdf`, `9f2becb1bf80`, `5a25154e0296`, `e399be8c0a2d` and
`395acbcad324` are idempotent twins of the product's `cf66605631d7`,
`988592a8100f`, `4a865a1c97aa`, `dbb8c3359981` and `8728e2fac660`: run on a
scratch database after the product's DDL they apply cleanly and leave the
schema, policies and grants identical to the platform chain alone.

## Not here, and why

- **The settings page** ("Kết nối Zalo", the workspace select): the platform
  web has no `/settings` page, so the link and the workspace choice are API
  only (`/api/v1/zalo/*`, typed in `@dw/api-client`). A product with a
  settings page renders them; the first product's page is its own design.
  The bot still answers a person with several workspaces and no choice with
  `<DW_PUBLIC_WEB_URL>/settings`, a page this web does not have: a product
  provides it, or that sentence changes when the platform gets one.
- **The decide command in this worker:** the platform worker hosts no graph,
  so it has no runner to resume a decided run on. A context that hosts its
  graph in the worker builds the command with `build_channel_decision_command`
  over its runner and passes it to `build_channel_commands`.
- **The first product's runbook** (`docs/deploy/host.md`): it names that
  product's overrides; ADR 0009 carries the platform's short version.
- **Chat commands** (a proposal, read-only questions): product commands,
  registered at the product's composition root.

## Owed

- **Proterial over Zalo (asked by Đạt 11-10, not decided).** Proterial staff
  would ask questions and give commands in Zalo instead of the portal.
  - **Feasible on what exists:** Z1–Z5, plus the status assistant as a
    product command. Polling needs only outbound HTTPS from the host to
    Zalo's API, with no port open inward.
  - **Blocked on Proterial, not on code:**
    - the plant host's outbound internet (still owed);
    - IT and security accepting that questions and answers pass through
      VNG's servers;
    - staff's personal Zalo accounts on personal phones.
  - **Unchanged:**
    - decisions still need a portal view and a code (ADR 0007), so they
      only work inside the plant network;
    - no prices in chat;
    - free-text commands become a typed intent that code authorizes and
      a person confirms.
  - **Not yet measured:**
    - Qwen3.8 with several users chatting at once on the one GPU;
    - tool calling;
    - the live bot run owed above.
  - **Which Zalo (11-10, from web sources, not Zalo's own price page):**
    - zBusiness Pro (about 5,500 VND/day) is a feature pack for one personal
      account: auto-reply, catalog, bulk send. It has no official API; the
      unofficial libraries that drive a personal account break Zalo's terms.
      Never.
    - The Official Account (OA, a verified business, server-to-server API;
      ZNS for templated customer notices, with quotas) belongs to the
      company, not to a person. It is a new adapter behind the same
      channel port.
    - The Bot Platform is what Z1–Z5 speak (Telegram-style API, 2,000
      characters per message, no groups for creator bots). Proposed for an
      internal pilot, created under a company-held Zalo account. Move to
      the OA only when Proterial needs company ownership and admins, or
      messages to customers.
    - Neither changes where the data goes: through VNG.
  - **For Proterial IT (11-10):**
    - one outbound rule: DW host → `bot-api.zaloplatforms.com:443` (the
      only base URL in `dw_connectors/adapters/zalo_bot.py`);
    - nothing inbound. `getUpdates` long-polls for 25 s, so a message
      arrives about as fast as with a webhook;
    - the bot token rides in the URL path (Telegram dialect), so a proxy
      that inspects TLS or logs full URLs must exempt that host, or its
      logs hold a secret;
    - webhook mode (ADR 0008) is for hosted deployments only, never the
      plant.
    - measured 11-10 from the dev machine: the host answers, and a fake
      token gets `{"ok":false,"error_code":401}`. A browser showing 404 is
      not a fault: it is an API, not a page;
    - ~~Cato may sit on the host's path~~. Corrected 11-11
      (`ops-hardening.md`, "How Proterial's network works"): the host goes
      out from the office VLAN directly. Cato is a client on PCs and phones,
      so the token never passes it. An office proxy on the host's path would
      still need this host exempted.
    - Zalo is off at the plant on purpose: `docker-compose.onprem.yml` pins
      `ZALO_BOT_TOKEN: ""` (lines 155, 176). Turning it on means reading the
      token from the environment there, never writing it into the file,
      then the first live bot run. The token is issued when the bot is
      created under the company-held Zalo account, and reissued if it leaks.
  - **Without Zalo (Đạt, 11-10, on the belief that Cato sat on the host's
    path; that reason fell on 11-11, so whether to use Zalo or the portal is
    open again and is Đạt's call):** no new chat UI and no open-source one. The portal
    already is the phone app:
    - a manifest (`apps/web/app/manifest.ts`, standalone) for "Add to Home
      Screen";
    - lists that fold to one column below `md`;
    - the assistant at `/sales/assistant` and `/purchasing/assistant`
      (`@dw/ui` `AssistantChat`, Ant Design X), streamed with
      `X-Accel-Buffering: no`.
  - Open WebUI, LibreChat and the like talk to the model directly. That
    skips the sign-in, the tenant, the check on the model's words, approvals
    and audit, and adds a second login and a second app to run.
  - Owed:
    - the chat page in Safari at 390 px (keyboard, streaming) has never been
      looked at;
    - SSE through Cato measured on a real iPhone;
    - an iOS-trusted certificate on the portal's LAN name;
    - the DW host inside what Cato routes for phones, as Bravo's already
      is. It is a new Ubuntu server, so it is not covered by default.
  - The home-screen icon needs no App Store: Safari's "Add to Home Screen"
    reads `app/apple-icon.png` and the manifest.
  - Not covered: notifications. Web push needs iOS 16.4+, a home-screen
    install, and the server going out to Apple's push service. Until then a
    person opens the app, or mail notifies them.
  - Web push, if built (Đạt asked, 11-10). The path:
    - the phone hands the portal its Apple endpoint over the LAN;
    - the DW host POSTs to `web.push.apple.com:443`, outbound only;
    - Apple reaches the phone over the phone's own connection.

    The payload is encrypted for the phone (RFC 8291), and a send is signed
    with DW's VAPID key. So unlike Zalo, the URL carries no secret, and a
    proxy inspecting TLS sees only ciphertext. Needs the plant host to have
    internet at all (owed: `ops-hardening.md`). The natural seam is a
    `webpush` channel in `platform.channel_deliveries` (ADR 0006), with a
    subscription per device rather than one link per person.
    - On the office VLAN (83.x, internet) the call likely goes out as is.
      Ask IT:
      - whether servers there are held tighter than PCs;
      - whether a TLS-inspecting office proxy sits on the path. Cato does
        not: it is on the phones and PCs. If one does, the sender fails on
        certificates unless the host is exempted or the proxy's root is
        trusted;
      - whether the proxy needs credentials.

      Not built yet (11-11).

- A live run against a real bot: the message id field, the webhook's secret
  header and the 400/403/404 "unreachable" classification are read as Zalo
  documents them (Telegram's dialect) and have not been measured.
- A hosted run of the Caddy overlay on this repo's stack (verified here with
  `docker compose config` and `caddy validate` only).
