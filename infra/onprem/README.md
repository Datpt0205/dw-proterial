# On premises: one host in the plant, nothing called outside it

Decided by Đạt on 2026-10-18 for Proterial, for DW1 (Đơn hàng & Báo giá) and DW2
(Yêu cầu mua & PO). Every model call (chat, embeddings, reranking) runs on the
plant's own host. The stack calls nothing on the internet while it runs. It
needs the internet only once, to fetch models and images, and even that step
can happen on another machine.

## What runs

| Service  | What                                                    | Network            |
| -------- | ------------------------------------------------------- | ------------------ |
| `model`  | Ollama 0.34.4: `qwen3.5-9b-dw` (chat), `bge-m3` (embed) | `dw-internal` only |
| `rerank` | llama.cpp b11146 (CPU): `bge-reranker-v2-m3` Q8_0       | `dw-internal` only |
| the rest | the usual stack (`docker-compose.yml`)                  | unchanged          |

- **Profile.** API and worker run on the `onprem` profile (`configs/models/onprem.yaml`).
- **No outside access.** No gateway, no API key and no Zalo.
- **Allow-list.** `model` and `rerank` are the only private hosts API and worker may call (`DW_*_OUTBOUND_ALLOWED_HOSTS`).
- **Vector collection.** Qdrant uses its own collection, `dw_knowledge_bge_m3`, because bge-m3 vectors are 1024 wide.

## Bring it up

On a host with internet (it can be the plant host before it is cut off):

```bash
make onprem-models          # reranker GGUF (checksummed) + Ollama models into the volume
make onprem-up              # uat profile, GPU, Caddy (DW_WEB_HOST/DW_API_HOST/DW_AUTH_HOST in .env)
```

**No GPU.** Run the same compose command without `docker-compose.onprem-gpu.yml`. It still works, but about ten times slower.

**Production.** Use `docker-compose.prod.yml` in place of `docker-compose.uat.yml`.

### A plant with no internet

1. On a connected machine, run `make onprem-models`.
2. On the same machine, run `bash infra/onprem/fetch-models.sh --export /media/usb`. This writes the reranker file and `ollama-models.tgz`.
3. On the same machine, export the images: `docker save` for the pinned images, plus `dw-*:local` after `--build`.
4. On the plant host, run `docker load` for the images.
5. On the plant host, run `bash infra/onprem/fetch-models.sh --import /media/usb`, then `make onprem-up`.

## Measured, and not yet

- **Measured on this exact model shape** (Ollama, `qwen3.5:9b`, num_ctx 8192, thinking off; 2026-10-13, sales tickets 28 to 33):
    - DW1's readings, for example 94.6% of RFQ values read into the right field against an 85% bar.
    - Hardware: a GTX 1080 8 GB.
    - Data: fictional mock data, not Proterial's documents.
- **Run on 2026-10-19** (a Windows 10 laptop, Docker Desktop on WSL2 with 10 GB, GTX 1080 Max-Q 8 GB; `local` profile, so without Caddy and the uat checks):
    - these compose files (base, `onprem`, `onprem-gpu`), with `make onprem-models` filling the volume;
    - **reranking**: `scripts/check_rerank.py` run inside the api container, through `build_reranker` → llama.cpp `/rerank`. The answer was ranked first (3.49 against -5.95 and -11.02), in 1.5 s on CPU;
    - **embeddings**: bge-m3 through the api's own `build_embeddings`, at 1024 dimensions, with 25/25 layers on the GPU. Six texts took 2.6 s warm. A Vietnamese query ranked its Vietnamese, English and Japanese answers first, ahead of a related and an unrelated sentence;
    - **chat**: `qwen3.5-9b-dw` in the container, with 32/33 layers on the GPU and both models resident (6.9 of 8 GB). Ollama 0.34.4 matched the 0.40.4 host build on the live evals: intent 89.8%, layout 97.7%, hand-off 98.6%.
- **Measured on 2026-10-19 and not handled yet:**
    - **The first GPU discovery can time out.** Ollama gives up after 30 s and serves on CPU, while the `ollama list` healthcheck still reports healthy. A restart found the GPU. Check `docker logs <model>` for `inference compute ... library=CUDA` after every start.
    - **The first request loads the model.** Loading took 582 s for qwen and 68 s for bge-m3 from the Docker Desktop volume on this laptop. DW1's 120 s route timeout fails such a first call, which then degrades to a person. Handled since 2026-11-06: `make onprem-up` returns only once `scripts/warm_model.py` has loaded every model the profile names, and says if one landed on the CPU. The `model-warm` service repeats it every five minutes, so a reboot or a crash of the model server is warm again with nobody asking. `make onprem-warm` runs it by hand. `OLLAMA_KEEP_ALIVE=-1` keeps a model loaded between those calls. Not run yet on the plant's host or inside compose: the script ran against the home lab's LM Studio.
    - **qwen35 serves one request at a time.** Ollama logs that this architecture "does not currently support parallel requests", so `OLLAMA_NUM_PARALLEL=4` does not apply to it. Requests queue instead.
    - **api and worker can still reach the internet.** They sit on `dw-edge`, so "nothing is called outside" holds only through configuration (the provider settings and `DW_*_OUTBOUND_ALLOWED_HOSTS`), not through the network. Whether the on-premises overlay should drop `dw-edge` is Đạt's decision.

    Still not run: the `uat` profile behind Caddy (`make onprem-up`), and anything on the plant's own host.

- **trivy 0.74.0, HIGH/CRITICAL, 2026-10-19.** Both images carry fixable findings:
    - `llama.cpp:server-b11146`: 2 HIGH, both openssl (CVE-2026-84782, fixed in `3.0.13-0ubuntu3.16`).
    - `ollama/ollama:0.34.4`: the same 2 in openssl, plus 48 HIGH in the `ollama` Go binary (the Go stdlib, `x/crypto`, `x/net`, `x/text`, `x/image`, `x/mod`, `jsonparser`).
    - No CRITICAL in either.

    Both serve on `dw-internal` only, with no route off the host, but the pins should move. Before bumping Ollama, scan the newer image (the host's 0.40.4 matched 0.34.4 on the evals) and rerun this section's checks. That is Đạt's call. Scanning the Ollama image needs `--timeout 30m`: its 3.4 GB layer outlasts the default 5 minutes.

## Watching it run (Grafana, Loki, Tempo)

`make onprem-up` starts the `observability` profile beside `full` (2026-11-05). Everything stays on this host: no cloud, no SaaS, and each tool's usage reporting is off.

| Tool | Holds | Kept (default) | Set in `.env` |
| --- | --- | --- | --- |
| Prometheus | Numbers: up/down, queues, model calls per step, tokens | 30 days | `DW_PROMETHEUS_RETENTION` |
| Loki, fed by Alloy | Every container's stdout/stderr | 30 days | `DW_LOKI_RETENTION` |
| Tempo | Spans: which step, which model, how long, which error. No document text | 7 days | `DW_TEMPO_RETENTION` |
| Alertmanager | Firing alerts, to `ALERTMANAGER_WEBHOOK_URL` | n/a | |
| Grafana | The screen over the three stores, with four dashboards in the "Digital Worker" folder | n/a | `GRAFANA_ADMIN_PASSWORD` (required, random) |

How long each store keeps data is Proterial's call (question 40 in `docs/proterial/Cau-hoi-Proterial-DW1-DW2.xlsx`). The numbers above are defaults until they decide.

- **Reaching Grafana.** It listens on `127.0.0.1:3030` only. From IT's PC, use `ssh -L 3030:127.0.0.1:3030 <host>` and open `http://localhost:3030`. Putting it behind Caddy with Keycloak sign-in is not done yet.
- **First start.** Grafana builds its own database the first time, which took 4.5 minutes on Docker Desktop. Later starts skip this step.
- **Logs.** Alloy reads `/var/lib/docker/containers` read-only. It does not use the Docker socket. Each service logs through json-file, rotated at 5 × 10 MB, with its compose service name in the line. Lines from containers outside this project are dropped. Logs carry ids, codes and counts, not mail text or prices:
    - the API runs without uvicorn's access log;
    - database errors hide their parameters;
    - a refused payload or reader answer is described by field, not value.

    What is still open is in `.claude/plans/ops-hardening.md` (2026-11-05).
- **Langfuse** is a separate profile, `langfuse`. Use it for UAT or a short debugging window only, and only with Proterial's consent. It is useful only when traces carry prompts and answers, which would be a second copy of customers' documents.
- **Offline images.** Add `grafana/grafana:13.2.5`, `grafana/loki:3.7.9`, `grafana/tempo:2.10.10` and `grafana/alloy:v1.21.3` to the `docker save` list in step 3 above.
- **Licences.** Grafana, Loki and Tempo are AGPL-3.0, and Alloy is Apache-2.0. `make third-party-notices` lists them. FPT legal should confirm the AGPL terms for an unmodified on-premises install.

## Signing in and out

The portal signs people in through **Keycloak, on the same host**. On premises it stays that way; the only question is where the accounts come from.

**Where accounts come from:**

- **Recommended: Proterial's Active Directory, through Keycloak's LDAP user federation.** People sign in with their Windows account. Disabling someone in AD stops their next sign-in. No password is stored in this stack, and no internet is needed.
- **Microsoft Entra ID (OIDC brokering) also works,** but every sign-in then goes through Microsoft's cloud. This fits only if the plant keeps internet access for M365 anyway.
- **No directory at all: IT creates the accounts in the portal.** Admin → Thành viên → "Thêm người" makes the person, their role and a Keycloak account with a temporary password shown once, which the person changes at first sign-in. The same screen resets a password or locks a sign-in. The person changes their own password later from "Đổi mật khẩu" in the account menu; a forgotten one is reset by IT, because the realm has no mail server. The cost of having no directory: when someone leaves, IT must lock them here, because nothing else does.
    - It needs the realm's `dw-accounts` client and `DW_API_ACCOUNTS_CLIENT_SECRET` (32+ random characters) in `.env`. Compose refuses to start Keycloak or the API without it.
    - A realm created before this client existed gets it from `uv run python scripts/keycloak_accounts_client.py` (reads `.env`; idempotent).
- **With LDAP federation, turn on "Trust Email".** The API links a first sign-in to a person by email only when Keycloak says the address is verified. Without it, a person IT added beforehand does not land on their own account (the safe failure, but a confusing one).
- **Before customer SSO is brokered,** close ADR 0024's open item 2 (email-based account linking).

**What the realm does** (`infra/keycloak/dw-realm.json`, tested in `apps/api/tests/unit/test_keycloak_realm.py`):

- **Sign-in length:** a sign-in lasts a shift (idle 8 h, at most 10 h).
- **Expiry warning:** the portal warns 5 minutes before the end and offers "Tiếp tục phiên"; it never navigates away on its own.
- **Access tokens** last 5 minutes and are refreshed in the background. A person who signs out, or is disabled, can no longer act after about 5 minutes. The API only verifies the token's signature, so this lifetime is the bound.
- **Lockout:** after 10 wrong passwords the account is locked for a growing wait, up to 15 minutes, and then unlocks on its own.
- **Passwords:** at least 10 characters, not the username or the email. This also applies to the demo accounts: `DW_DEV_USER_PASSWORD` must be 10 characters or more.
- **Sign out:** "Đăng xuất" ends the Keycloak session (`keycloak.logout`), not just the tab.
- **Language:** the sign-in and password pages are in Vietnamese only (`supportedLocales: [vi]`, so no language switch; Keycloak ships the translation).

**The realm file is read only when Keycloak's database is empty.** An existing installation does not pick these settings up by itself. Apply them in the admin console (Realm settings: Sessions, Tokens, Security defenses; Authentication: Policies), or re-import on a fresh volume.

**Two-factor sign-in:** OTP (an authenticator app, which works offline) is required today for the `dw-support` group (support access). Turning it on for everyone is one required action in the realm.

## How people are reached without Zalo

Zalo (and Microsoft Teams) bots work only through the provider's servers, which an on-premises stack does not call.

**What people use instead:**

- **The portal on the LAN** (`https://<DW_WEB_HOST>`, behind Caddy). This is the product: every list, case, approval and decision is there already. Its chat streams over Server-Sent Events on the API host, which Caddy passes on frame by frame (measured 2026-11-06, the repository's Caddyfile on `caddy:2.11.7-alpine`). A proxy Proterial puts in front must not buffer `text/event-stream`.
- **The in-app inbox** (the bell): every approval, hand-off and reminder lands there. It needs nothing outside the host.
- **Email through Proterial's own mail relay**, as a link only (`/approvals/<id>`, never a price or a PO line). This is the one channel that is not built yet.

**Recommendation on a desktop app:** do not build one. A browser app installs on Windows as an app (Edge or Chrome: "Install this site as an app") once the site has a web manifest and HTTPS. It gets a window and a taskbar icon, and it updates when the server updates. A desktop build (Electron or Tauri) adds:

- code signing;
- an update channel;
- a second client to test;

and for that it gives nothing a Sales or Purchasing user needs.

**What this requires:**

- **HTTPS on the LAN.** Caddy with `DW_CADDY_LOCAL_CERTS=local_certs` issues certificates from its own CA. Proterial's IT pushes that root certificate to the PCs once, through Group Policy. Without that, browsers warn and refuse to install the app.
- **Hostnames in the plant's DNS** for `DW_WEB_HOST`, `DW_API_HOST` and `DW_AUTH_HOST`.
- **A web manifest.** It is in place (`apps/web/app/manifest.ts` and the icons in `public/icons`), and its colours come from the theme. Nobody has installed the app on a real PC yet.

## What still wants the outside world

- **Antivirus signatures.** The ClamAV image carries its signatures as of its build (sales ticket 25: the weekly bump workflow). Without internet they age, so rebuild or reload the image on each scheduled update.
- **Building images.** `pnpm`, `uv`, base images and fonts are fetched at build time. Build on a connected machine and ship the images.
- **Support access** (ADR 0024). Open item 3, how FPT staff reach a stack inside the plant, is unchanged. Use the plant's VPN with the customer-granted support grant; never a port opened to the internet.
- **Mail.** DW1 reads no mail server at all. Proterial's mail is Exchange Online and DW1 holds no access to it; the mail reaches the host as files (next section).

## Mail without access to Microsoft 365

Decided 2026-10-27 (Sales ticket 43): Proterial gives DW1 no Microsoft 365 access and its administrators are abroad, so nothing here needs one.

- **One flow for every DW, into a Team's library** (Đạt, 2026-11-02). A private Microsoft Teams team ("DW - chuyen thu", two owners, no staff as members) holds `DW-mail/<address>` at the root of its SharePoint library, one subfolder per person who works with DW1 or DW2, named by the address that person signs in to DW with, and shared (edit) with that person alone. The files belong to the team, not to a person, and an ordinary user can usually create the team: no Microsoft 365 administrator and no new licence. Fallback where Proterial forbids it: a DW account's OneDrive, the same steps with its own Site Address and Folder Path. An owner builds one flow (standard connectors) that exports every mail reaching the Inbox as an `.eml` file into a person's folder (SharePoint *Create file*, Site Address `https://<org>.sharepoint.com/sites/DW-chuyenthu`, Folder Path `/Shared Documents/DW-mail/<address>`; the Message Id field holds the token alone, a stray character fails as "Id is malformed"). Its trigger folder is the literal `Inbox`: picked from the list, the flow keeps the owner's folder id and a copy never fires in another mailbox (measured 2026-10-27).
- **Each person** (a Sales PIC, a buyer, or both) receives a copy of that flow ("Send a copy", which needs one successful run after the last edit), points it at their own folder, signs its Outlook and SharePoint connections in as themselves and turns it on. Nobody's flow differs by DW.
- **Which DW reads whose mail is the members page, not the flow**: DW1 reads the folders of the members holding `sales.inbox.process`, DW2 those holding `purchasing.request.intake`, a person holding both is read by both, asked each minute (`dw_platform.application.drop_folder.OwnedFolders`). Granting or withdrawing the scope starts or stops it. A folder named by an address no holder signs in with, and a file in the root, are read by no one. Each DW's model then sorts every mail it reads, internal included: neither the flows nor DW leave a sender out (DW1's `ignored_sender_domains` left in `sales_order_rules@1.9.0`; DW2 decides which senders may be a request by `internal_domains` and SPF/DKIM/DMARC).
- **A Windows PC in the plant** (a Windows Server with Desktop Experience works too) signs in to OneDrive as one of the team's owners, adds `DW-mail` with "Add shortcut to OneDrive → My files" (it appears as `DW - chuyen thu - DW-mail`), keeps it on disk ("Always keep on this device") and shares it over SMB, read-only, to one local user, firewalled to this host. OneDrive runs only in a live Windows session: Remote Desktop is left by Disconnect, never Sign out, the disconnected-session time limit is Never, and Autologon brings the session back after a restart.
- **This host** mounts the share at `/srv/dw/mail-drop` (`cifs`, `ro`, `_netdev`; Docker ordered after `remote-fs.target`); the onprem overlay mounts it read-only into the worker alone as `DW_MAIL_DROP_DIR`. With `DW_SALES_MAILBOX=stored` the `sales_mail_drop` lane stores DW1's mail, with `DW_PURCHASING_MAILBOX=stored` the `purchasing_mail_drop` lane DW2's, each in its own tables (ADR 0014), every minute. The APIs read the stored mailboxes, never the folder.

The step-by-step guides (each person's, and the PC's and this host's) are Word documents kept outside the repository. Measured on Đạt's machine on 2026-10-27, his FPT account as the DW1 account and his PC as the plant PC, the Docker stack reading the synced folder: a Gmail message to his own mailbox reached the stored mailbox 1 min 20 s after it arrived (flow 17 s, OneDrive sync 12 s, the lane's settle and tick 51 s), its sender, arrival and SPF/DKIM/DMARC read correctly from the Exchange export. A colleague ran the copied flow: a mail to their mailbox was stored after 11 min 29 s, 10 min 17 s of it OneDrive bringing a file another user's flow wrote down to the PC (one measurement; a file the DW1 account writes itself took 12 s). Measured again on 2026-11-02 with the folder in a Team on FPT's tenant, a colleague who was not a member writing to their own folder and Đạt's PC syncing it: the local worker stored Đạt's two mails in DW1 (he held `sales.inbox.process`) and not the colleague's, and all three in DW2 (both held `purchasing.request.intake`). Not yet run on a plant host.

## Sending mail from each PIC's own mailbox (prepared, not yet set up)

Decided 2026-10-29: "Gửi cho khách" sends a case's send draft from the mailbox of the person who pressed it, never from a shared mailbox on a server and with no Graph API: the receiving path above, run the other way. Until Proterial signs, nobody has a sending flow and the button says so; nothing below is set up yet.

- **Storage in Proterial's tenant, never a personal account.** The same team's library holds `DW-outbox/<sign-in address>/` per person, shared (edit) with that person alone. A personal Microsoft account would put customers' mail outside Proterial's control, and the connector it needs is usually blocked by Power Platform DLP.
- **Each PIC's flow**, a second one beside the receiving flow, signed in as themselves (standard connectors):
  1. *When a file is created in a folder* (OneDrive for Business or SharePoint): `DW-outbox/<their address>/outbox`.
  2. *Get file content*, *Parse JSON* of the job: `job`, `from`, `to`, `cc` (`;`-separated), `subject`, `body_html`, `attachments` (file names).
  3. For each attachment name: *Get file content* of `outbox/files/<job file stem>/<name>` (retry a few times: OneDrive may bring the job before its files).
  4. *Send an email (V2)* from their Outlook: To, CC, Subject, Body (HTML), Attachments. It lands in their Sent Items; replies come back to them and the receiving flow brings those to DW1.
  5. *Create file* `receipts/<job file stem>.json` with `{"status": "sent"}`; on any failure (a *Configure run after: has failed* branch) `{"status": "failed"}`; then delete the job file.
- **The plant PC** syncs `DW-outbox` like `DW-mail`, but shares it **read-write** to the same local user, firewalled to this host. The host mounts it at `/srv/dw/outbox` (`cifs`, `rw`).
- **This host**: an override mounts `/srv/dw/outbox:/outbox` into the worker alone with `DW_OUTBOX_DIR=/outbox` (`DW_SALES_OUTBOX_DIR` still read), and sets `DW_OUTBOX_ENABLED=true` for the API, which never touches the share. The worker's `sales_outbound` lane writes each pressed mail as `outbox/<tenant>.<workspace>.<mail>.json` (its files under `outbox/files/<same>/`) every 30 s, reads `receipts/`, marks a quotation "Đã gửi KH" as the person who pressed, and tells them when their folder is missing, their flow failed, or no receipt came within 30 minutes.
- **What a receipt cannot do**: it settles only a job DW1 wrote into that same person's folder; anything but `"sent"` counts as failed. Who receives the mail was checked by the API against the customer's contacts before the job existed.
- **DW2's RFQs go the same way** (2026-11-03): a buyer presses "Gửi từ hộp thư của tôi" on a supplier's RFQ; the worker's `purchasing_outbound` lane writes the job (`dw2.<tenant>.<workspace>.<mail>.json`) into the same person's folder, the same flow sends it, and each lane settles only the receipts of its own jobs. No second flow per person.
- Locally, `DW_SALES_OUTBOX_FAKE_FLOW=1` (refused where deployed) answers every job as a flow would, so the demo can press the button; nothing leaves the machine.
