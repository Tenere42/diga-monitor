# Temporary Production-Like Deployment (Railway)

**Status: prepared, NOT deployed.** This session has no Railway CLI,
API token, or dashboard access (verified before writing this document —
no `railway` binary, no `RAILWAY_TOKEN`, no other credential available
in this environment). Everything below is a ready-to-execute runbook
for a human with Railway dashboard access to this project to actually
create the temporary service; nothing in this document has been applied
to Railway. See the end of this document for exactly what to report
back once you have.

This does **not** touch the existing "diga-monitor" service, its
`railway.json`, or any of its environment variables. It proposes a
second, temporary, independently deletable Railway service in the same
project.

## Proposed architecture

```
Railway project "diga-monitor" (existing)
├── Service: diga-monitor (existing, UNCHANGED)
│   └── streamlit run app.py --server.port=$PORT ...
│       serving www.diga-tracker.de / *.up.railway.app
│
└── Service: diga-monitor-http-signup-poc (NEW, temporary)
    └── pip install -r poc/http_signup/requirements.txt &&
        python -m uvicorn poc.http_signup.asgi_app:app --port $PORT
        serving a new, separate *.up.railway.app URL
        (no custom domain attached)
```

Both services build from the **same GitHub repo**, same branch
(`poc/http-newsletter-signup`), same **Root Directory (repo root)** —
this is the key simplification: the new service does *not* need its
Root Directory pointed at `poc/http_signup/`, because
`poc/http_signup/routes.py` imports `src.subscribers` from the repo
root. Keeping Root Directory at the repo root and only changing the
**Start Command** avoids needing any Python path/package hacks.

On dependencies: the root `requirements.txt` already pulls in
`starlette` and `uvicorn` *transitively* via `streamlit` in the exact
version this project currently runs (confirmed present, see
`poc/http_signup/README.md`'s architecture section). That is **not**
guaranteed for whatever version a fresh build might resolve, though —
the root `requirements.txt` only pins `streamlit>=1.35.0`, no upper
bound, no lockfile, and Streamlit's Starlette/Uvicorn-based server is a
comparatively recent change in Streamlit's own history. Rather than
depend on that transitive assumption holding, the start command below
explicitly installs `poc/http_signup/requirements.txt` first — cheap,
and removes the risk entirely regardless of which Streamlit version the
build actually resolves.

Why a new service, not a new Railway *project*: services in the same
project can reference each other's environment variables directly
(`${{diga-monitor.BREVO_API_KEY}}`, see below) without copying secret
*values* anywhere. A separate project would need the Brevo secrets
re-entered by hand, which is both more manual and creates a second
place those secrets live. Either is fully reversible (delete the
service, or delete the whole project); the same-project approach is
recommended as the smaller, easier-to-clean-up footprint.

## Step-by-step (Railway dashboard)

1. Open the existing "diga-monitor" Railway project.
2. **New Service → GitHub Repo** → select this same repository.
3. In the new service's **Settings → Source**:
   - Branch: `poc/http-newsletter-signup`
   - Root Directory: leave as default (repo root) — do **not** point
     it at `poc/http_signup/`.
   - **Primary, recommended path — Custom Start Command**
     (**Settings → Deploy → Custom Start Command**), paste this
     directly rather than relying on any config-file auto-detection
     (Railway's rules for which services can pick up a `railway.json`
     via a custom path, and whether that path must be repo-root-absolute
     like `/poc/http_signup/railway.json`, were not verifiable from this
     session without Railway dashboard access and may not apply the same
     way to a brand-new service — the dashboard field is the reliable
     option):
     ```
     pip install -r poc/http_signup/requirements.txt --quiet && python -m uvicorn poc.http_signup.asgi_app:app --host 0.0.0.0 --port $PORT
     ```
   - `poc/http_signup/railway.json` in this repo records the identical
     start command as a **secondary, optional** path, in case your
     Railway plan/UI does support pointing a service's Config File Path
     at a non-root file. Verify it actually took effect (check the
     deploy logs show `uvicorn` starting, and that
     `poc/http_signup/requirements.txt` was installed) before relying on
     it; use the Custom Start Command above if in doubt.
4. **Settings → Networking**: enable **Public Networking** for this
   service (generates a `*.up.railway.app` URL; do not attach the
   production custom domain to it).
5. **Variables**: add the entries in the table below. Use Railway's
   variable-reference syntax to reuse the existing service's secrets
   without copying values — see the table for the exact syntax and
   substitute your existing service's actual name if it isn't literally
   `diga-monitor`.
6. **Deploy.** Once live, copy the generated URL (Settings → Networking
   → Public Networking; format is normally
   `https://<service-name>-production.up.railway.app`, but the exact
   name is only known once Railway generates it).
7. Run the smoke test (see below) against that URL.
8. **When done validating: delete this service** (Service Settings →
   Danger Zone → Delete Service). This does not affect the existing
   "diga-monitor" service or any of its variables — a referenced
   variable (`${{diga-monitor.BREVO_API_KEY}}`) only reads from the
   source service, it never copies or modifies it.

## Railway variables required

| Variable                     | Value to set                              | Why |
|-------------------------------|--------------------------------------------|-----|
| `BREVO_API_KEY`                | `${{diga-monitor.BREVO_API_KEY}}`           | Reused via reference — reads the existing service's secret without duplicating it |
| `BREVO_NEWSLETTER_LIST_ID`     | `${{diga-monitor.BREVO_NEWSLETTER_LIST_ID}}`| Same list as production — a real signup here becomes a real confirmed subscriber to the real list once the recipient clicks confirm |
| `BREVO_DOI_TEMPLATE_ID`        | `${{diga-monitor.BREVO_DOI_TEMPLATE_ID}}`   | Same DOI email template as production |
| `BREVO_DOI_REDIRECT_URL`       | `${{diga-monitor.BREVO_DOI_REDIRECT_URL}}`  | Reuse the existing confirmation landing page (`.../?view=confirmed` on the main app) — see note below |
| `PORT`                         | *(set automatically by Railway)*            | No action needed |

**Note on `BREVO_DOI_REDIRECT_URL` and the shared list:** this PoC does
**not** have its own "confirmed" landing page, and reusing the same
`BREVO_NEWSLETTER_LIST_ID` means a real signup through this temporary
service adds a **real, permanent, confirmed subscriber to the actual
production newsletter list** once the recipient clicks the confirmation
link — this is not a sandboxed/throwaway list. That is by design (the
task asks this smoke test to confirm the real DOI flow works, including
against the real list), but it means: **only ever use an address you
control and are fine seeing on the real subscriber list** (your own
email, not a disposable/third-party one), and remember this creates
real state in Brevo that isn't automatically cleaned up when you delete
the Railway service — see "Remaining risks" in the final report for
how to undo it if needed.

Variables intentionally **not** set: the PoC currently has no
legal-readiness gate equivalent to the Streamlit app's
`NEWSLETTER_LEGAL_READY`/`DIGA_TRACKER_OPERATOR_CONTACT_EMAIL`/
`DIGA_TRACKER_DATA_RETENTION_PERIOD` — see "Remaining risks" for why
this means the temporary URL should be treated as
unlisted-but-not-secret, not shared publicly, and torn down promptly
after validation.

## Exposing the endpoint

Railway's automatic HTTPS `*.up.railway.app` domain (from "Public
Networking" above) *is* the temporary HTTPS endpoint — no separate load
balancer, reverse proxy, or custom domain needed. Once deployed, the
target for the task's example endpoint is:

```
POST https://<whatever-railway-generated>.up.railway.app/api/newsletter/subscribe
```

This document cannot state the exact hostname in advance — Railway
generates it from the service name at creation time, which only exists
once the service is actually created. Report it back (or run the smoke
test yourself) once you have it.

## Running the smoke test

`poc/http_signup/scripts/smoke_test_production.py` — a standalone
script, deliberately **not** part of any automated test suite (it makes
real HTTP requests and, when told to, triggers a real email). See its
own module docstring for full details; summary:

```bash
# Safe: connectivity only, no email involved.
python poc/http_signup/scripts/smoke_test_production.py \
  --url https://<temp-service>.up.railway.app --healthcheck-only

# Triggers a REAL Brevo double-opt-in email to the address you pass.
# Use your own address; never a third party's.
python poc/http_signup/scripts/smoke_test_production.py \
  --url https://<temp-service>.up.railway.app \
  --email you@example.com \
  --send
```

The script cannot check any inbox itself. It distinguishes two
different "accepted" outcomes rather than treating them the same:
a fresh `201`/`success` response prints a reminder to check the inbox
(and optionally the Brevo dashboard) for a *new* confirmation email;
a `200`/`already_subscribed` response means Brevo already had that
address as pending/confirmed, so a new email may **not** have been sent
this time — the script says so explicitly and suggests using a
never-before-signed-up address instead if you need to actually confirm
a fresh DOI send.

## Tearing down

1. Delete the temporary Railway service (see step 8 above).
2. If a real signup was completed (the confirmation link was actually
   clicked) and you don't want that address to remain a real subscriber,
   unsubscribe it the same way a real subscriber would (the DOI email's
   own unsubscribe link), or remove it directly from the Brevo contacts
   list for `BREVO_NEWSLETTER_LIST_ID`. Deleting the Railway service
   does **not** do this automatically — Brevo is external state, see
   "Remaining risks" in the task's final report.
