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
    - **The first request loads the model.** Loading took 582 s for qwen and 68 s for bge-m3 from the Docker Desktop volume on this laptop. DW1's 120 s route timeout fails such a first call, which then degrades to a person. Send one warm-up call after `up`. `OLLAMA_KEEP_ALIVE=-1` keeps the model loaded from then on.
    - **qwen35 serves one request at a time.** Ollama logs that this architecture "does not currently support parallel requests", so `OLLAMA_NUM_PARALLEL=4` does not apply to it. Requests queue instead.
    - **api and worker can still reach the internet.** They sit on `dw-edge`, so "nothing is called outside" holds only through configuration (the provider settings and `DW_*_OUTBOUND_ALLOWED_HOSTS`), not through the network. Whether the on-premises overlay should drop `dw-edge` is Đạt's decision.

    Still not run: the `uat` profile behind Caddy (`make onprem-up`), and anything on the plant's own host.

- **trivy 0.74.0, HIGH/CRITICAL, 2026-10-19.** Both images carry fixable findings:
    - `llama.cpp:server-b11146`: 2 HIGH, both openssl (CVE-2026-84782, fixed in `3.0.13-0ubuntu3.16`).
    - `ollama/ollama:0.34.4`: the same 2 in openssl, plus 48 HIGH in the `ollama` Go binary (the Go stdlib, `x/crypto`, `x/net`, `x/text`, `x/image`, `x/mod`, `jsonparser`).
    - No CRITICAL in either.

    Both serve on `dw-internal` only, with no route off the host, but the pins should move. Before bumping Ollama, scan the newer image (the host's 0.40.4 matched 0.34.4 on the evals) and rerun this section's checks. That is Đạt's call. Scanning the Ollama image needs `--timeout 30m`: its 3.4 GB layer outlasts the default 5 minutes.

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
- **Language:** the sign-in and password pages are in Vietnamese (`defaultLocale: vi`; Keycloak ships the translation).

**The realm file is read only when Keycloak's database is empty.** An existing installation does not pick these settings up by itself. Apply them in the admin console (Realm settings: Sessions, Tokens, Security defenses; Authentication: Policies), or re-import on a fresh volume.

**Two-factor sign-in:** OTP (an authenticator app, which works offline) is required today for the `dw-support` group (support access). Turning it on for everyone is one required action in the realm.

## How people are reached without Zalo

Zalo (and Microsoft Teams) bots work only through the provider's servers, which an on-premises stack does not call.

**What people use instead:**

- **The portal on the LAN** (`https://<DW_WEB_HOST>`, behind Caddy). This is the product: every list, case, approval and decision is there already.
- **The in-app inbox** (the bell): every approval, hand-off and reminder lands there. It needs nothing outside the host.
- **Email through Proterial's own mail relay**, as a link only (`/approvals/<id>`, never a price or a PO line). This is the one channel that is not built yet.

**Recommendation on a desktop app:** do not build one. A browser app installs on Windows as an app (Edge or Chrome: "Install this site as an app") once the site has a web manifest and HTTPS. It gets a window and a taskbar icon, and it updates when the server updates. A desktop build (Electron or Tauri) adds:

- code signing;
- an update channel;
- a second client to test;

and for that it gives nothing a Sales or Purchasing user needs.

**What this requires:**

- **HTTPS on the LAN.** Caddy with `DW_CADDY_LOCAL_CERTS=1` issues certificates from its own CA. Proterial's IT pushes that root certificate to the PCs once, through Group Policy. Without that, browsers warn and refuse to install the app.
- **Hostnames in the plant's DNS** for `DW_WEB_HOST`, `DW_API_HOST` and `DW_AUTH_HOST`.
- **A web manifest.** It is in place (`apps/web/app/manifest.ts` and the icons in `public/icons`), and its colours come from the theme. Nobody has installed the app on a real PC yet.

## What still wants the outside world

- **Antivirus signatures.** The ClamAV image carries its signatures as of its build (sales ticket 25: the weekly bump workflow). Without internet they age, so rebuild or reload the image on each scheduled update.
- **Building images.** `pnpm`, `uv`, base images and fonts are fetched at build time. Build on a connected machine and ship the images.
- **Support access** (ADR 0024). Open item 3, how FPT staff reach a stack inside the plant, is unchanged. Use the plant's VPN with the customer-granted support grant; never a port opened to the internet.
- **Mail.** DW1 reads mail through its mailbox port, and it needs a mail server it can reach. For on-premises Exchange that is inside the plant; Exchange Online is not.
