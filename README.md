# DiGA Directory Change Monitor

A small Python CLI and Streamlit MVP for monitoring changes in the BfArM DiGA directory.

The app compares each scan with one operational JSON baseline, writes structured change events, archives selected full snapshots in Cloudflare R2, and shows a pure change feed. It does not duplicate the public DiGA directory.

Each snapshot also stores directory-level aggregate metrics, including total DiGA count and counts by listing status. These metrics act as a cross-check for lifecycle changes: if the status counters change but no matching DiGA-level lifecycle event is detected, the monitor logs a warning so status parsing problems are visible.

## Features

- Fetch DiGA entries from the public BfArM DiGA directory/FHIR data
- Keep one current operational baseline in `data/baseline/current_snapshot.json`
- Archive change pairs and weekly compressed checkpoints in Cloudflare R2
- Detect new DiGA entries
- Detect removed DiGA entries
- Detect status, text, price, and other field changes
- Detect directory-level counter changes as a lifecycle cross-check
- Detect tiny text changes inside long text fields
- Produce a readable diff report in the terminal
- Store structured change events in `outputs/changes`
- Store scan history in `outputs/scan_history.json`
- Send optional Brevo Transactional Email API notifications for real changes
- Show detected changes in a Streamlit feed

## Project Structure

```text
.
|-- app.py
|-- .env.example
|-- data/
|   |-- baseline/
|   |-- snapshots/        # legacy history; retained until a separate migration
|   `-- simulations/
|-- outputs/
|   `-- changes/
|-- src/
|   |-- change_events.py
|   |-- diff.py
|   |-- fetch_diga.py
|   |-- main.py
|   |-- render_directory.py
|   |-- snapshot.py
|   `-- snapshot_storage.py
|-- README.md
`-- requirements.txt
```

## Setup

Requires Python 3.10 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Configuration

The scraper discovers public DiGA directory URLs from `https://diga.bfarm.de/sitemap.xml` and fetches the public FHIR resources used by the BfArM directory frontend.

You can optionally provide an approved BfArM API token:

```powershell
$env:DIGA_API_TOKEN="your-token"
```

If no token is set, the scraper requests the same short-lived public token flow used by the directory frontend. It does not use mock data.

### Listing Status Source

The current DiGA listing status is derived from the structured FHIR `CatalogEntry.status` field.

Status mapping:

- `draft`, `preliminary`, `provisional` -> `provisional`
- `active`, `final`, `permanent` -> `permanent`
- `retired`, `removed`, `revoked`, `inactive` -> `removed`

The `CatalogEntry.validityPeriod.end` field is stored as source data only. It is not treated as the current listing status, because it can remain present for historical periods even after a DiGA is reactivated.

If `CatalogEntry.status` is missing or unknown, the monitor may use the structured status entries from `change_history` as a legacy fallback. It does not infer lifecycle status from free text, the BfArM assessment text, rendered `content_sections`, or arbitrary descriptive fields.

## E-Mail Notifications

E-Mail Notifications use the Brevo Transactional Email API over HTTPS and are optional. The monitor sends an email only when real DiGA changes are detected. It skips baseline imports, no-change scans, development cleanup events, and simulated events.

Copy `.env.example` to `.env` locally and fill in your own values. Do not commit `.env`.

Required local environment variables and GitHub Actions configuration:

```powershell
$env:BREVO_API_KEY="your-brevo-api-key"
$env:DIGA_MONITOR_EMAIL_FROM="updates@diga-tracker.de"
$env:DIGA_MONITOR_EMAIL_FROM_NAME="DiGA Tracker"
$env:DIGA_MONITOR_EMAIL_TO="recipient@example.com"
$env:DASHBOARD_URL="http://localhost:8501"
```

Use placeholders like these when setting up the values. Do not commit real credentials.

| Setting | Value to enter | Example |
| --- | --- | --- |
| `BREVO_API_KEY` | Brevo API v3 key for Transactional Email | `replace-with-brevo-api-key` |
| `DIGA_MONITOR_EMAIL_FROM` | Verified Brevo sender address shown in the email | `updates@diga-tracker.de` |
| `DIGA_MONITOR_EMAIL_FROM_NAME` | Sender name shown in the email | `DiGA Tracker` |
| `DIGA_MONITOR_EMAIL_TO` | Recipient address(es) for alerts, comma-separated when needed | `alerts@example.com` |
| `DASHBOARD_URL` | Public or local URL of the Streamlit dashboard | `https://your-dashboard.streamlit.app` |

In GitHub, create each value under:

Store the Brevo API key under `Settings > Secrets and variables > Actions > Secrets`. Store sender, recipient, and dashboard configuration under `Settings > Secrets and variables > Actions > Variables`.

Required secret names:

```text
BREVO_API_KEY
```

Required repository variable:

```text
DIGA_MONITOR_EMAIL_FROM
DIGA_MONITOR_EMAIL_FROM_NAME
DIGA_MONITOR_EMAIL_TO
DASHBOARD_URL
```

Email body creation, recipient resolution, and Brevo API delivery are separate. The current production variable contains one recipient; the resolver already accepts a comma-separated list so a future subscription source can be added without changing change detection. No public subscription or newsletter management is implemented.

Run with email notification enabled:

```powershell
py -m src.main run --notify
```

Preview the email without sending it:

```powershell
py -m src.main run --notify --dry-run
```

Send or preview a dedicated test notification without running a DiGA scan:

```powershell
py -m src.main notify-test
py -m src.main notify-test --dry-run
```

`notify-test` checks the Brevo API configuration and sends exactly one simulated price-change message with subject `[TEST / SIMULATION] DiGA Watch: 1 Änderung(en) erkannt`. The message is also marked `TEST / SIMULATION` in its body. It creates no snapshot, baseline, history, change-event, or R2 output and exits with a non-zero status if required variables are missing or API delivery fails.

In GitHub Actions, open the `DiGA Monitor` workflow manually with `Run workflow` and set `notification_test` to `true`. This sends only the test email and skips the normal DiGA scan and commit step.

GitHub Actions logs show one of these statuses during notification handling:

- `Notification configuration incomplete. Missing: ...`
- `Notification configuration complete.`
- `Notification skipped: no real changes detected.`
- `Notification sent to: ...`
- `Notification failed: ...`

Notification attempts are logged in `outputs/notification_log.json`.

## CLI Usage

Fetch the directory, compare it with the operational baseline, and replace that baseline after successful archival:

```powershell
python -m src.main run
```

When changes are found, this also writes a structured event file to `outputs/changes`.
Every run also appends scan metadata to `outputs/scan_history.json`.

Fetch entries and print them without saving:

```powershell
python -m src.main fetch
```

Compare the latest two legacy local snapshots:

```powershell
python -m src.main diff
```

List legacy local snapshots:

```powershell
python -m src.main snapshots
```

Render one official DiGA detail page as a browser archive:

```powershell
python -m playwright install chromium
python -m src.main render-entry --url https://diga.bfarm.de/de/verzeichnis/00508 --diga-id 00508 --slug somnio
```

This optional prototype opens the real BfArM detail page in Chromium, expands visible accordions where possible, and writes audit artifacts to `data/rendered_pages/<timestamp>/`:

- `<diga_id>_<slug>.pdf`
- `<diga_id>_<slug>.png`
- `<diga_id>_<slug>_structure.json`

The structure JSON contains the rendered heading outline, extracted `content_sections`, and simple stats such as opened accordions, section count, and field/value count. The section extraction is derived from the visible DOM after rendering, not from FHIR/JSON data.

Inspect a rendered structure file:

```powershell
python -m src.main inspect-structure --file .\data\rendered_pages\<timestamp>\00508_somnio_structure.json
python -m src.main inspect-structure --file .\data\rendered_pages\<timestamp>\00508_somnio_structure.json --out structure_preview.md
```

The inspection command prints summary counts, top-level sections, a readable tree of extracted paths, and field/value examples. This is a validation aid before using `content_sections` for production change detection.

Dry-run a future `content_sections` change detection without touching production snapshots or events:

```powershell
python -m src.main diff-content-sections --before .\data\rendered_pages\<old>\00508_somnio_structure.json --after .\data\rendered_pages\<new>\00508_somnio_structure.json
python -m src.main diff-content-sections --before .\data\rendered_pages\<old>\00508_somnio_structure.json --after .\data\rendered_pages\<new>\00508_somnio_structure.json --out content_section_diff.md
```

The dry-run compares `content_sections` by `stable_key`, ignores ordering changes, and reports added sections, removed sections, changed text, and changed field/value pairs.

Run the normal monitor with an optional rendered-structure parallel scan:

```powershell
python -m src.main run --with-rendered-structure --limit 2
```

You can also enable it with:

```powershell
$env:DIGA_RENDER_STRUCTURE="true"
python -m src.main run
```

When enabled, the regular FHIR/JSON scan still runs as before. The monitor additionally renders each DiGA detail page with Playwright and stores extracted `content_sections` inside each snapshot entry. These fields are ignored by the production snapshot diff, so the first rendered-structure scan does not create normal change events.

If both the previous and current snapshots contain `content_sections`, the scan writes a separate dry-run report to `outputs/content_section_dry_run/`. This report is only for validation and is not used by the dashboard or email notifications.

For local testing, use `--limit` because Playwright rendering is slower than the normal scan. PDF/PNG archives are not written unless `--archive-rendered-pages` is also passed.

Build committed visible baselines for all current DiGA entries:

```powershell
python -m src.main build-rendered-baseline
```

For a short local test:

```powershell
python -m src.main build-rendered-baseline --limit 5
```

This stores one durable `*_structure.json` baseline per DiGA under:

```text
data/rendered_structure/latest/
```

These baseline files are intended to be committed. They represent the visible BfArM directory structure extracted from the rendered page. PDF/PNG archives are not created unless `--archive-rendered-pages` is explicitly passed.

Render only DiGA entries where the normal scan detected real changes:

```powershell
python -m src.main run --render-changed-entries
```

You can also enable this mode with:

```powershell
$env:DIGA_RENDER_CHANGED_ENTRIES="true"
python -m src.main run
```

This keeps the normal scan fast because Playwright runs only after regular change detection and only for affected DiGA. In this mode, FHIR/JSON changes are used only as a trigger. The user-facing change events are generated from the visible BfArM `content_sections` diff against the stored rendered baseline.

The monitor stores durable visible baselines under:

```text
data/rendered_structure/latest/
```

When a new DiGA appears and no visible baseline exists yet, the monitor creates the baseline and keeps the user-facing event compact: "Neue DiGA im Verzeichnis". It does not list every `content_section` as a separate change.

When an existing DiGA has a FHIR/JSON-triggered change, the monitor renders the current BfArM page, compares the current `content_sections` against the committed baseline, writes visible diff events if visible changes exist, and then updates the baseline. If FHIR reports a change but the rendered visible structure is unchanged, no fachliche dashboard event is written; the scan log records that there was no visible change.

Current run structures are stored under:

```text
outputs/rendered_structure/runs/<scan_timestamp>/
```

Add `--archive-rendered-pages` if PDF and PNG archives should also be saved for manual review:

```powershell
python -m src.main run --render-changed-entries --archive-rendered-pages
```

PDF/PNG files remain a human-readable audit archive. The dashboard should not show raw FHIR fields such as `descriptive_texts.questionnaire.*`; those fields only trigger rendering and visible-structure comparison.

Use a custom snapshot directory:

```powershell
python -m src.main --snapshot-dir .\data\snapshots run
```

Create safe simulation events:

```powershell
py -m src.main simulate-orthopy-change
py -m src.main simulate all --notify --dry-run
py -m src.main simulate text-change --notify --dry-run
py -m src.main simulate price-change --notify --dry-run
py -m src.main simulate status-change --notify --dry-run
py -m src.main simulate new-diga --notify --dry-run
py -m src.main simulate removed-diga --notify --dry-run
py -m src.main simulate all-page-fields --notify --dry-run
```

Simulations write structured simulated events to `outputs/changes`, generate `outputs/simulation_report.md`, and do not modify real snapshots. In the dashboard, enable `Simulationen anzeigen` to view simulated events grouped by category.

Preview the notification email for the Orthopy simulation:

```powershell
py -m src.main simulate-orthopy-change --notify --dry-run
```

Simulation notifications are dry-run only. They print the email body but never send email.

## Claude Code review authentication

Automated Codex → Claude Code reviews use Anthropic API-key authentication only. Create one repository Actions secret named `ANTHROPIC_API_KEY`; do not store the key in repository files, variables, workflow inputs, command-line arguments, or logs. The Claude PR Review workflow validates the secret against the Anthropic API before starting the review and fails with a redacted error when the secret is missing or rejected.

Local automated reviews use the same environment variable and the repository wrapper:

```powershell
python -m scripts.claude_review --pr-number 5
```

The wrapper removes OAuth and alternate-provider overrides from Claude's child environment and uses a temporary empty Claude configuration directory. Existing personal Claude settings remain untouched but cannot be used by this automated path. Claude receives read-only inspection tools only; Codex remains responsible for triaging findings and making any accepted changes.

## Change Feed Dashboard

Start the local Streamlit app:

```powershell
python -m streamlit run app.py
```

The dashboard reads `outputs/changes/*.json` and only displays detected changes. It does not show full stored DiGA profiles.

Each event includes:

- detection time
- DiGA name and manufacturer
- official BfArM directory link
- change type
- changed field
- before and after values
- previous and current snapshot timestamps
- word-level highlighting for text changes

Available filters:

- change type
- DiGA name search
- date range

If no change events exist, the app shows `Keine Änderungen erkannt.`

Simulated events are hidden by default. Enable `Simulationen anzeigen` to test the feed with generated events such as the Orthopy BfArM assessment text removal.

## Scheduling

GitHub Actions is the regular production scheduler. For local diagnostics, the CLI can still be run manually:

```powershell
python -m src.main run
```

The command exits successfully even when no changes are found, making it suitable for scheduled automation. Notification channels can later be attached to the structured files in `outputs/changes`.

## Recommended Production Schedule

GitHub Actions runs the monitor five times per day at these local times in Zurich:

```text
06:00, 09:00, 12:00, 15:00, 18:00 Europe/Zurich
```

The `Europe/Zurich` timezone automatically follows CET/CEST changes. Actual execution can be delayed by GitHub depending on runner availability and platform load.

GitHub Actions schedule:

```yaml
schedule:
  - cron: "0 6,9,12,15,18 * * *"
    timezone: "Europe/Zurich"
```

Rendered page archives are not enabled in the scheduled workflow by default. If browser rendering is later activated in GitHub Actions, the workflow must install Chromium with:

```powershell
python -m playwright install chromium
```

PDF and PNG archives can become large, so enable this only deliberately and consider whether rendered artifacts should be committed or stored externally.

## Optional External Fallback

GitHub Actions is the only regular automatic scheduler. cron-job.org is not used for regular scans. The `repository_dispatch` trigger with event type `scheduled-scan` remains available as an optional external or manual fallback.

An external service can send this request when the fallback is deliberately needed:

```text
POST https://api.github.com/repos/Tenere42/diga-monitor/dispatches
```

Body:

```json
{
  "event_type": "scheduled-scan"
}
```

Headers:

```text
Authorization: Bearer <GitHub Personal Access Token>
Accept: application/vnd.github+json
```

Do not store the token in this repository. Configure it only in the external scheduler's protected secret or header settings.

## Snapshot Storage and R2

Every successful scan atomically replaces `data/baseline/current_snapshot.json`. An unchanged scan creates no historical full snapshot. When the existing change detection reports a change, the previous and current full snapshots are uploaded as gzip-compressed JSON to `full-snapshots/changes/` in R2. The first successful scan in each ISO week also uploads one compressed checkpoint to `full-snapshots/checkpoints/`.

GitHub Actions reads the R2 endpoint and bucket from repository variables `R2_ENDPOINT` and `R2_BUCKET_NAME`, and credentials from secrets `R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY`. No credentials are stored in the repository. A production run fails before replacing the baseline if required R2 archival fails.

An R2 token with **Object Read & Write** access scoped to the `diga-monitor` bucket is sufficient. It must permit listing objects, reading object metadata, uploading objects, and deleting the temporary object used by the optional connectivity check. With the same R2 environment variables set, run `python -m scripts.r2_connectivity_check` to verify `ListBucket`, `HeadObject`, `PutObject`, and `DeleteObject` access. The command uses a unique key below `diagnostics/`, removes it afterward, and never prints configuration values.

The existing `data/snapshots` history remains untouched pending the final cleanup decision. All historical change events now embed the compact context needed by the dashboard, and production baseline/scan-status paths no longer fall back to the legacy directory. The verified minimal retention set and restore evidence are recorded in `data/audit/legacy_history_manifest.json`.

## Notes About BfArM Integration

The official BfArM DiGA API is documented as a FHIR-based REST API. The BfArM documentation lists the current DiGA FHIR base URL as `https://diga.bfarm.de/api/fhir/v3.0/` and notes that API users receive a confidential bearer token after approval.

The current `src/fetch_diga.py` module:

- discovers DiGA detail URLs from the public sitemap
- fetches BfArM FHIR resources with bearer token authentication
- normalizes one local JSON record per public DiGA

If BfArM changes the public frontend API, update `FHIR_PROFILES` or the normalization helpers in `src/fetch_diga.py`.

Useful official references:

- BfArM DiGA API overview: https://fhir.bfarm.de/guide/diga-overview-en.html
- BfArM FHIR fundamentals: https://fhir.bfarm.de/guide/fhir-fundamentals-en.html
- BfArM DiGA use cases: https://fhir.bfarm.de/guide/diga-use-cases-de.html
