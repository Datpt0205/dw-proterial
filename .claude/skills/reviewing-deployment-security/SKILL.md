---
name: reviewing-deployment-security
description: Run this before finishing any change that adds an API route, a response type, a compose service, a container image, an outbound URL/webhook, a CORS/auth setting, or a default/mock/dev-only code path — anything whose risk depends on WHICH ENVIRONMENT reaches it rather than who calls it. Complements reviewing-feature-security (business-logic trust boundaries) with OWASP-style deployment and configuration exposure: what a caller outside this system can see or reach, by profile. Use it without being asked.
---

# Reviewing deployment security before it ships

`reviewing-feature-security` asks who else can reach a piece of _logic_. This
skill asks a different question: given the right caller and the right tenant,
what does this environment expose that it shouldn't — a debug surface, a dev
default, an unscanned image, a URL this app will fetch on someone else's say-so.
The canonical failure in this class is boring and doesn't need a clever
attacker: Swagger left reachable in production, a mock provider answering
real traffic, a CORS origin that's really a wildcard, a webhook nobody scanned.

This repo already has the right mechanism for most of this —
`settings.is_deployed` / `DEPLOYED_PROFILES`, never `profile == "production"`
(`CLAUDE.md`, Environments) — so most of this skill is _using that mechanism
correctly for the new surface_, not inventing a new one.

Unlike `.claude/rules/failure-modes.md`, this skill is not yet backed by a
count of times each shape has actually shipped here — it is preventive, not a
post-mortem. Update it with a count the day one of these actually escapes.

---

## 1. A debug, mock or dev-only surface reaching a deployed profile

This repo's own precedent: `ApiSettings.validate_for_profile()` already
refuses dev auth mode, the mock model provider, the mock task connector, the
hash embedding provider and an empty CORS list the moment `is_deployed` is
true — one function, one place, fail loud at startup rather than fail open at
request time.

- Does the new setting/flag/provider have a "this isn't real" variant (mock,
  hash, in-memory, dev-*)? If so, is it in that same refusal list, or a new
  one just like it (`WorkerSettings.validate_for_profile()` for the worker)?
- Does a new route, docs page or introspection endpoint gate on `is_deployed`
  the way `hide_docs` gates `/api/docs`/`/api/redoc`/`/api/openapi.json`? A
  route that lists other routes is itself something to hide.
- Is the gate `settings.is_deployed`, never a literal `profile == "production"`
  string comparison? The latter reopens the hole for every environment that
  isn't literally spelled "production" — `uat` included, which this repo
  explicitly says must obey identical rules.

**Verify:** a test that constructs the setting in a deployed profile and
asserts refusal — same shape as `test_production_forbids_dev_auth_mode`.

## 2. What a response actually contains, in every branch

- Does the unhandled-exception path still return only taxonomy (`ErrorCode`,
  a generic message), never a stack trace, a SQL fragment, or an internal
  path? (`dw_api/exception_handlers.py`'s `handle_unexpected` is the existing
  contract — a new handler installed elsewhere must match it, not bypass it.)
- Does a new list/search endpoint leak existence through a status-code
  difference (404 vs 403) the way `reviewing-feature-security`'s tenant-
  isolation boundary already requires answering for cross-tenant reads?
  That's the same question asked from the response-shape side.
- Security headers (CSP, `X-Frame-Options`, `X-Content-Type-Options`, HSTS)
  are not set anywhere in this app today — no in-repo reverse proxy config
  exists, so that is presumably the deploying operator's job at the edge, not
  a gap this app silently has. If a change assumes the app itself sets one
  (e.g. serving HTML, embeddable content), that assumption needs to be
  checked against what actually fronts a deployed instance, not assumed.

## 3. Secrets and defaults

- Compose: is a real secret `${VAR:?}` (refuses to start without it), never
  `${VAR:-some-default}`? A default that "just works" locally is a default
  that ships to whoever forgets to override it.
- Does `.env.example` carry a placeholder (`change-me-...`, empty, or an
  obviously-fake value), never a working credential?
- Is a new secret ever interpolated into a log line, an error message, or a
  URL that could end up in access logs (a token in a query string, not a
  header)?

## 4. CORS and cross-origin exposure

- Is the allowed-origins list explicit and non-empty in every deployed
  profile (`validate_for_profile` already refuses an empty one — does a new
  surface bypass `CORSMiddleware` and set its own headers instead, where
  that refusal doesn't apply)?
- `allow_credentials: true` paired with a wildcard origin is a browser-side
  hole by itself — this repo doesn't do that today; a change introducing a
  second CORS-configured app/route must not either.
- Headers/methods lists (`_CORS_HEADERS`, `_CORS_METHODS`) are named
  explicitly, not `["*"]`. A new header a client needs to send goes on the
  list; the list doesn't get replaced with a wildcard to save the edit.

## 5. An outbound URL this app doesn't control (SSRF-shaped)

A webhook, a connector, a search provider, anything where the destination
comes from configuration or, worse, a request.

- Is the destination operator-configured (an env var set at deploy time,
  like `ALERTMANAGER_WEBHOOK_URL`) or can a caller/tenant influence it? The
  former is a normal, low-risk operational knob; the latter needs a scheme
  and host allowlist before the first fetch, not after an incident.
- Does the fetch follow redirects to wherever the far end points, including
  into `dw-internal` where Qdrant and Valkey sit unauthenticated? A URL
  fetcher reachable from outside that can also reach the internal network
  is a pivot, not just an integration.

## 6. A new image or dependency, scanned rather than trusted

`reviewing-feature-security`'s own closing section already says to run
`trivy image --severity HIGH,CRITICAL --ignore-unfixed` "on the image this
change produces" — read narrowly, that covers `dw-api`/`dw-worker`/`dw-docgen`,
the images this repo's own Dockerfiles build. It does not obviously cover an
image a change merely _references_ in `docker-compose.yml` and pulls from a
registry (an exporter, a proxy, a sidecar) — found the gap this way while
shipping Ops hardening Phase 5's Prometheus/Alertmanager services, where the
first pass scanned nothing because none of the four new images were "built."

**The rule, stated to close that gap: every image newly referenced in a
compose file — built by this repo or merely pulled — gets scanned before the
change ships**, same command, same severity floor. A HIGH/CRITICAL finding
with a fix available doesn't have to block the commit by itself (a Go-stdlib
DoS CVE in a vendored binary is a different risk than one in code this repo
wrote), but it has to be a decision written down (the area's plan file under
`.claude/plans/`, or the commit message), not silence.

A dependency version bump gets the same "run it, don't trust the changelog"
treatment `failure-modes.md` #4 already requires for libraries generally —
a new pinned image version is exactly that, just at the container layer.

---

## The verification each boundary above earns

Not every boundary here produces a pytest the way `reviewing-feature-security`'s
six do. Match the check to what's actually being claimed:

- A profile-gated setting/route → a unit test that constructs it in a
  deployed profile and asserts refusal (§1), same shape as the existing
  `test_production_forbids_*` tests.
- A response-shape claim ("errors never leak internals") → a test that
  triggers the failure path and asserts on the body, not the log line (§2).
- An image or dependency claim → the tool's actual output, pasted into the
  record, not a description of what the tool is supposed to do (§6). This is
  `failure-modes.md`'s "two things no checklist can do" — run it and look —
  applied to every new image, not only the ones this repo compiles.

If a boundary above doesn't apply to the change, say so in one line rather
than skipping it silently — that sentence is usually where the second-guess
surfaces.
