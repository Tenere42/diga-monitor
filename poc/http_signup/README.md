# PoC: HTTP Newsletter Signup

A small, isolated proof of concept validating whether a classic
`browser → HTTP endpoint → Brevo DOI` flow works reliably on Railway, as
a potential long-term, more robust alternative to the existing Streamlit
form/rerun signup in `app.py`.

**This is a technical validation only.** It does not remove, replace, or
touch the existing Streamlit newsletter flow, does not change any
Railway or Brevo configuration, and is not reachable in production —
nothing in `app.py` imports from here, and nothing here imports from
`app.py`. It lives on its own branch and is not merged.

## TL;DR architecture decision

**Root cause context:** the existing Streamlit signup form was
investigated across several sessions (see `app.py`'s
`render_newsletter_signup_section()` docstring and this repo's commit
history) after users reported the confirmation banner disappearing and,
later, submissions apparently not reaching the server at all in
production. That investigation proved the Streamlit-side code is
correct (an identical click was reproduced locally against the same
Streamlit version and worked), which pointed the remaining suspicion at
Streamlit's own rerun/WebSocket transport in this specific production
environment — motivating this PoC's question: would a plain HTTP POST
sidestep that entire class of problem?

**This PoC's answer:** yes, technically — a classic HTTP endpoint is a
strictly simpler, more standard, more observable mechanism than
Streamlit's session/rerun/WebSocket machinery, and it works reliably in
every environment tested here (see "What was tested" below). Whether it
should actually replace the Streamlit form is a separate judgment call
requiring production-environment evidence this PoC alone cannot supply
— see "Recommendation" at the end.

## The explicit technical question: can the existing Streamlit/Uvicorn setup be extended with a normal HTTP endpoint?

**Yes — Streamlit's own architecture already has a mechanism for exactly
this, in the version this project actually runs.**

Confidence note on how this was established: the following is based on
reading the *installed* `streamlit` package's own source and docstrings
(`streamlit.web.server.starlette.starlette_app`, plus
`streamlit.web.server.app_discovery`), not a linked public docs page --
this session did not have web access to cross-check it against
Streamlit's official online documentation. The API itself is public
(importable as `st.App`, with runnable `>>>` docstring examples in the
package, the same convention the rest of Streamlit's public API uses),
so treat this as "confirmed present and working against this exact
installed version," not as "verified against Streamlit's published
docs."

**This also does not hold for every environment automatically:** the
main `requirements.txt` pins only `streamlit>=1.35.0`, no upper bound,
no lockfile. `st.App` is confirmed present in `streamlit==1.63.0`
(locally and in production, per the `NEWSLETTER_FORM_RENDER
streamlit_version=...` log line added in an earlier round) — a fresh
environment resolving an older `>=1.35.0` release is not guaranteed to
have it, and would need to be checked before relying on this.

The Streamlit version this project runs on is built on **Starlette +
Uvicorn**, not the older Tornado-based server older Streamlit releases
used. Its `streamlit.web.server.starlette.starlette_app` module exposes
a public `st.App` class (`import streamlit as st; st.App(...)`) that
accepts a `routes` parameter:

```python
import streamlit as st
from starlette.routing import Route
from starlette.responses import JSONResponse

async def health(request):
    return JSONResponse({"status": "ok"})

app = st.App("main.py", routes=[Route("/health", health)])
```

`streamlit run` **statically scans the target script's AST** for a
module-level `app = st.App(...)` (or `streamlit_app = st.App(...)`)
assignment (see the installed package's
`streamlit/web/server/app_discovery.py`) and, if found, serves that
`App` — Streamlit's own routes plus the extra ones passed in —
**via the exact same `streamlit run app.py` command already in
`railway.json`**. No new process, no new port, no Railway config change
needed for that part.

### How minimal, concretely — and why this PoC does *not* do it

The catch: `st.App(script_path, routes=[...])` must be constructed
**once, at process startup**, in the file `streamlit run` is actually
pointed at. `railway.json`'s `startCommand` is `streamlit run app.py`,
so that file is `app.py` itself — today, the entire ~2000-line dashboard
script.

Two ways to wire this up:

1. **Add `app = st.App(__file__, routes=[...])` directly inside the
   current `app.py`**, near the top. The problem: `app.py`'s top-level
   code re-runs on *every single Streamlit script rerun* (Streamlit
   re-executes the whole file per interaction) — so this line would
   reconstruct a new `App` instance on every dashboard filter change,
   every newsletter form rerun, etc. `App.__init__` is mostly idempotent
   (guarded against re-setting global config), but this is clearly not
   the intended usage pattern and adds needless per-rerun overhead and a
   class of “first App instance in the process wins” footguns the
   docstring explicitly warns about.
2. **Split today's `app.py` into a tiny launcher (`app.py`) plus the
   actual dashboard script under a new name**, e.g.:
   ```python
   # app.py (new, ~5 lines)
   import streamlit as st
   from starlette.routing import Route
   from poc.http_signup.asgi_app import poc_routes  # or wherever it lives for real

   app = st.App("dashboard.py", routes=poc_routes)
   ```
   with the current `app.py` content moved to `dashboard.py` unchanged.
   This is the pattern Streamlit's own docs actually demonstrate. It
   requires **zero changes to any dashboard/newsletter rendering code**
   and **zero Railway config changes** (still `streamlit run app.py`) —
   but it does rename/restructure the main entry point.

Given the task's explicit constraint — **"Bestehende Streamlit UI nicht
umbauen"** and, separately, **"falls dafür zusätzliche
Server-Infrastruktur nötig wäre, bitte zuerst erklären und nicht
einfach umbauen"** — this PoC deliberately does **neither** of the
above. It ships as a fully standalone Starlette app
(`poc/http_signup/asgi_app.py`) that can be run completely independently
(`uvicorn poc.http_signup.asgi_app:app`), proving the HTTP-endpoint
concept in isolation without touching `app.py` at all. `poc_routes` in
that module is exported separately from the app's own test-page mount
specifically so that, **if this is adopted for real later**, that exact
route list could be passed into option 2 above with no further
rewriting.

### If no Streamlit/Uvicorn extension existed (the "if no" branch of the question)

Had `st.App(routes=...)` not existed (e.g. on an older Streamlit
version), the smallest alternative structure would have been a genuine
second process: a separate lightweight ASGI service (exactly what this
PoC already is) started as its own Railway service, needing its own
`railway.json`/start command, its own domain or path-based routing at
Railway's edge, and its own copy of (or access to) the `BREVO_*` env
vars. That is real additional infrastructure — another service to
deploy, monitor, and keep in sync — which is precisely why this PoC
treats that as a bigger decision to explain, not to just build, and
avoids needing it given `st.App` is actually available here.

## What was built

```
poc/
  http_signup/
    __init__.py
    asgi_app.py           # standalone Starlette ASGI app (the "server")
    routes.py              # POST /api/newsletter/subscribe handler
    validation.py           # pure request validation + outcome→response mapping
    rate_limit.py           # minimal in-memory per-IP rate limiter
    requirements.txt        # starlette/uvicorn (transitive already), httpx (dev/test only)
    static/index.html       # minimal standalone test client (NOT the real newsletter box)
    tests/
      test_validation.py
      test_rate_limit.py
      test_routes_integration.py
    README.md               # this file
```

### Endpoint

`POST /api/newsletter/subscribe`

Requires `Content-Type: application/json` exactly (charset parameter
aside) — anything else, including the three CORS-"safelisted" content
types, is rejected with `validation_error` before the body is even
parsed. See the CORS bullet in the Security section for why this is a
deliberate security control, not just strictness.

Request body (JSON):
```json
{"email": "visitor@example.com", "consent": true}
```
`consent` must be the JSON boolean `true` — `"true"` (string), `1`, or a
missing field are all rejected as a validation error. This mirrors the
existing Streamlit flow's own rule (`app.py`: `if not consent: ...`)
applied to a JSON field instead of a checkbox widget.

Response (JSON), always with a `status` field distinguishing every
outcome the task asked for, plus a matching HTTP status code:

| `status`            | HTTP code | Meaning                                                              |
|----------------------|-----------|-----------------------------------------------------------------------|
| `success`            | 201       | DOI confirmation email triggered (`SignupOutcome.CONFIRMATION_SENT`)  |
| `already_subscribed` | 200       | Address already pending/confirmed with Brevo                          |
| `validation_error`   | 400       | Bad request shape, or Brevo rejected the email format                 |
| `config_error`       | 503       | `BREVO_*` env vars missing/invalid on this process                    |
| `api_error`          | 502       | Brevo API call failed, or an unexpected exception was caught          |
| `rate_limited`       | 429       | This PoC's own per-IP rate limit was hit                              |

### No Brevo logic duplicated

`routes.py` imports and calls `src.subscribers.request_double_optin()`
directly — the exact same, already-reviewed function the Streamlit flow
uses (email format validation, the Brevo DOI API call, the
resubscribe-after-unsubscribe handling, and the outcome classification
all live in exactly one place). This PoC only adds:
- HTTP-request-shape validation (`validation.py`) — things
  `request_double_optin()` has no way to know about, since it takes a
  bare email string, not a request.
- Mapping `SignupOutcome` → this endpoint's own `status` field.

If `src/subscribers.py` changes (a new outcome, different Brevo
behaviour), this PoC picks that up automatically for anything reused;
only the `_OUTCOME_TO_STATUS` mapping in `validation.py` needs
maintenance if a genuinely new outcome is added — the
`test_unrecognized_outcome_falls_back_to_api_error` test exists so that
forgetting to update the mapping fails safe (an `api_error`, never a
crash or an unmapped/missing `status`).

## Security / privacy

- **No email addresses or secrets are logged.** `routes.py` logs only
  fixed marker strings and, on completion, the Brevo *outcome code*
  (mapped through a closed allowlist, same pattern as `app.py`'s
  `_safe_outcome_for_log` — see `_safe_outcome_for_log` in
  `routes.py`). On an unexpected exception, only the exception *type*
  and a sanitized traceback (`traceback.format_tb`, never
  `str(exc)`/`exc.args`) are logged — the same defensive pattern
  established for the Streamlit flow, for the same reason (an
  exception's own message is outside this function's control and could
  in principle echo request data).
- **No open-proxy / open-redirect surface.** The Brevo redirect URL
  (`BREVO_DOI_REDIRECT_URL`) is server-side configuration inside
  `src/subscribers.py`, never derived from the request — this endpoint
  cannot be used to make Brevo redirect anywhere the caller chooses.
  Nothing in this PoC fetches or proxies an arbitrary caller-supplied
  URL.
- **CORS is closed by default — and, importantly, is only meaningful at
  all because of the content-type check next to it.** `asgi_app.py`
  only adds `CORSMiddleware` if `POC_HTTP_SIGNUP_ALLOWED_ORIGINS` is
  explicitly set (comma-separated origin list); with no origins
  configured, no CORS headers are ever sent. `allow_origins=["*"]` is
  deliberately never the default.

  **A first version of this analysis stated that this alone stops other
  websites from triggering the endpoint — that was wrong, and worth
  spelling out why**, since it's a common CORS misunderstanding: CORS is
  a *response-reading* control enforced by the browser, not a
  *request-sending* control. A `fetch()`/form POST whose `Content-Type`
  is one of the three "CORS-safelisted" values
  (`application/x-www-form-urlencoded`, `multipart/form-data`,
  `text/plain`) is sent as a plain cross-origin request with **no
  preflight at all** — the browser still sends it, still lets the
  server process it (still triggers a real DOI email), and CORS only
  determines whether the *calling page's JavaScript* is allowed to read
  the *response*. An attacker's page never needed to read the response
  anyway — the side effect (the email) already happened.

  This is why `routes.py` **requires `Content-Type: application/json`
  exactly** (`validation.is_acceptable_content_type`), rejecting
  anything else before it ever reaches `request_double_optin()`. Only
  once that's enforced does CORS configuration start to matter for a
  browser-based caller: `application/json` is *not* one of the
  safelisted content types, so a cross-origin `fetch()` that sets it
  forces the browser to run a CORS preflight (`OPTIONS`) first — and
  with no matching `Access-Control-Allow-Origin`, the browser refuses to
  ever send the real request. Content-type enforcement is the actual
  request-blocking control; CORS configuration is what determines *who*
  it blocks a browser from bypassing that way.

  **None of this affects a non-browser caller** (`curl`, a script, a
  server-to-server call) — CORS and content-type "safelisting" are both
  purely browser conventions; nothing stops a direct HTTP client from
  sending `Content-Type: application/json` from anywhere. That residual
  risk is exactly abuse vector 2 below, which the rate limiter (not
  CORS or content-type checking) is meant to address.
- **Rate limiting / abuse risk — analysis:**
  - **Abuse vector 1: spamming a fixed address.** Already substantially
    mitigated by Brevo's own DOI dedup, reused via
    `request_double_optin()` — repeated requests for the same address
    return `already_subscribed`, not a fresh email each time.
  - **Abuse vector 2: mail-bombing arbitrary third-party addresses.**
    This is the real risk of *any* public "trigger an email to X"
    endpoint, regardless of transport (Streamlit form or HTTP POST):
    someone scripts requests against harvested addresses, and each
    *first-time* address gets one unsolicited "please confirm your
    DiGA Tracker subscription" DOI email. Not a full subscription (DOI
    requires the recipient's own click), but still an unwanted email
    sent in the operator's name — a real spam/reputation/nuisance risk.
  - **Abuse vector 3: endpoint/credential scanning, generic API abuse**
    (bulk requests, resource exhaustion). Generic HTTP-endpoint risk,
    same as any public POST endpoint.
  - **What this PoC does about it:** `rate_limit.py` implements a
    simple in-memory, per-IP, sliding-window limiter
    (`InMemoryRateLimiter`, 5 requests / 10 minutes by default, see
    `routes.py`), demonstrated by `RateLimitingTests` in
    `test_routes_integration.py`. **This is PoC-grade, not
    production-grade**: it is per-process and in-memory, so (a) it does
    not coordinate across multiple Railway replicas — each would have
    its own independent counters — and (b) it resets on every
    restart/deploy. It also keys on the immediate TCP peer address
    (`request.client.host`), which behind Railway's own edge proxy may
    already be the proxy's address rather than the original visitor's;
    this PoC deliberately does **not** trust a client-suppliable
    `X-Forwarded-For`-style header for this purpose, since a caller
    could trivially spoof a fresh value on every request to evade the
    limit otherwise. A real deployment would need either a
    proxy-verified real-IP source, or (more robustly) a shared store
    (Redis, or Railway's own rate-limiting/WAF features if available)
    instead of in-process memory.

## What was tested

- **Unit tests** (`test_validation.py`, `test_rate_limit.py`): pure
  validation logic, outcome→response→HTTP-status mapping, and the rate
  limiter's sliding-window behaviour — no ASGI app, no I/O.
- **Integration tests** (`test_routes_integration.py`): the real
  Starlette app via `starlette.testclient.TestClient`, covering every
  `status` value in the table above, the rate-limit 429 path, and that
  an unexpected exception still returns a real (never-crashing, never
  email-leaking) response. `request_double_optin()` is mocked
  throughout — **no test in this PoC ever makes a real network call or
  could create a real Brevo contact.**
- **Manual local smoke test** (this session): ran
  `uvicorn poc.http_signup.asgi_app:app --port 8600` locally with no
  `BREVO_*` env vars set (so even a "successful" request could only ever
  reach the safe `config_error` path, never a real Brevo call) and
  confirmed via `curl`: empty email → `validation_error`; a well-formed
  request → `config_error` (proving the endpoint end-to-end up to, but
  deliberately stopping short of, the real Brevo call); `/healthz` and
  the test page both served correctly.
- **Not tested here:** an actual live Brevo DOI call end-to-end (would
  create a real, unwanted test signup — explicitly out of scope per the
  task). `src/subscribers.py`'s own existing test suite
  (`tests/test_subscribers.py`) already covers `request_double_optin()`
  itself against a mocked Brevo API in detail; this PoC only needed to
  prove it reuses that function correctly, which the mocked integration
  tests above do.

## Running it locally

```bash
# From the repo root. starlette/uvicorn are already installed
# transitively via streamlit; httpx is dev-only, for the integration test.
pip install httpx

python -m unittest discover -s poc/http_signup/tests -v

uvicorn poc.http_signup.asgi_app:app --port 8600 --reload
# then open http://localhost:8600/ for the test form, or:
curl -X POST http://localhost:8600/api/newsletter/subscribe \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "consent": true}'
```

## Temporary production-like validation on Railway

See **[DEPLOYMENT.md](DEPLOYMENT.md)** for a ready-to-execute runbook:
deploying this exact code as a second, temporary Railway service
alongside the existing app (no changes to it), which Railway variables
are needed and how to reuse the existing Brevo secrets without copying
them, and how to run `scripts/smoke_test_production.py` against the
deployed instance to confirm a real double-opt-in email is triggered.
That script is deliberately separate from the automated test suite
above -- it makes real HTTP requests and, when explicitly told to,
sends a real email.

With no `BREVO_*` env vars set, any well-formed request safely resolves
to `config_error` — no real subscriber or email is ever created without
deliberately exporting real Brevo credentials first.

## Recommendation: HTTP endpoint vs. the existing Streamlit signup?

**Lean yes for the signup form specifically, but not a slam dunk, and
not urgent enough to justify the restructuring cost right now.**

**In favour of the HTTP approach:**
- Categorically simpler transport: one stateless request/response, no
  session, no WebSocket, no multi-step rerun state machine to reason
  about. The entire class of problem this project spent multiple
  sessions investigating (a rerun/WebSocket message apparently not
  reaching the Streamlit script in production, cause still unconfirmed)
  cannot happen the same way here — a dropped HTTP request fails loudly
  (a network error in the browser, or a non-2xx response), rather than
  silently.
- Trivially more observable and debuggable: standard HTTP status codes
  and a structured JSON body a `curl`/browser devtools/any monitoring
  tool understands immediately, vs. needing custom Streamlit-side
  logging (as this project had to add) to see anything at all.
- Decouples the signup form's reliability from the dashboard's — today,
  the newsletter form is rendered by the exact same Streamlit process
  and script execution as the whole (fairly heavy) DiGA dashboard;
  an HTTP endpoint would keep working even if the dashboard rendering
  itself were slow, erroring, or had unrelated issues.

**Against / open questions before actually adopting it:**
- **The production root cause is still unconfirmed.** This PoC
  strongly suggests an HTTP endpoint *would* sidestep the specific
  failure class investigated so far, but that hasn't been proven
  against the *actual* production Railway environment — only argued
  from first principles (simpler transport = fewer ways to silently
  fail) and tested locally/in isolation. If the real cause turns out to
  be something like a Railway edge/proxy issue affecting large
  WebSocket frames specifically, that's evidence for this
  recommendation; if it turns out to be something else entirely
  (unlikely given what's already been ruled out, but not disproven),
  this recommendation should be revisited.
- **Adopting it for real is not actually a drop-in swap.** It means
  either (a) the `app.py` restructuring into a launcher + dashboard
  script described above, or (b) a second deployed service — both real
  decisions with real tradeoffs, not covered by this PoC's scope.
- **The rate limiting and CORS posture here are PoC-grade**, not
  production-grade — see the security section above for exactly what's
  missing (shared-store rate limiting, a verified real-client-IP
  source).
- The existing Streamlit flow, once the production issue is actually
  found and fixed, may well be perfectly reliable going forward — this
  PoC is evidence for a *more robust by construction* alternative, not
  evidence that the current approach is unfixable.

**Bottom line:** worth keeping this PoC around as a validated fallback
option and revisiting once the production root-cause investigation
concludes — either as the actual fix (if the cause is
transport/infrastructure-specific to Streamlit's rerun mechanism) or as
a deliberate, planned migration once someone weighs the
launcher-restructuring cost against the reliability/observability gain.
Not something to rush into merging today.
