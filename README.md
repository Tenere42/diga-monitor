# DiGA Directory Change Monitor

A small Python CLI and Streamlit MVP for monitoring changes in the BfArM DiGA directory.

The app stores local JSON snapshots, compares each new snapshot with the previous one, writes structured change events, and shows a pure change feed. It does not duplicate the public DiGA directory.

## Features

- Fetch DiGA entries from the public BfArM DiGA directory/FHIR data
- Store timestamped snapshots locally as JSON
- Detect new DiGA entries
- Detect removed DiGA entries
- Detect status, text, price, and other field changes
- Detect tiny text changes inside long text fields
- Produce a readable diff report in the terminal
- Store structured change events in `outputs/changes`
- Store scan history in `outputs/scan_history.json`
- Send optional SMTP email notifications for real changes
- Show detected changes in a Streamlit feed

## Project Structure

```text
.
|-- app.py
|-- .env.example
|-- data/
|   |-- snapshots/
|   `-- simulations/
|-- outputs/
|   `-- changes/
|-- src/
|   |-- change_events.py
|   |-- diff.py
|   |-- fetch_diga.py
|   |-- main.py
|   `-- snapshot.py
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

## E-Mail Notifications

E-Mail Notifications use SMTP and are optional. The monitor sends an email only when real DiGA changes are detected. It skips baseline imports, no-change scans, development cleanup events, and simulated events.

Copy `.env.example` to `.env` locally and fill in your own values. Do not commit `.env`.

Required local environment variables and GitHub Actions Secrets:

```powershell
$env:SMTP_HOST="smtp.example.com"
$env:SMTP_PORT="587"
$env:SMTP_USERNAME="your-smtp-username"
$env:SMTP_PASSWORD="your-smtp-password"
$env:EMAIL_FROM="diga-watch@example.com"
$env:EMAIL_TO="recipient@example.com"
$env:DASHBOARD_URL="http://localhost:8501"
```

In GitHub, set the same names under `Settings > Secrets and variables > Actions > Repository secrets`:

```text
SMTP_HOST
SMTP_PORT
SMTP_USERNAME
SMTP_PASSWORD
EMAIL_FROM
EMAIL_TO
DASHBOARD_URL
```

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

GitHub Actions logs show one of these statuses during notification handling:

- `Notification skipped because secrets missing: ...`
- `Notification sent: ...`
- `Notification failed: ...`

Notification attempts are logged in `outputs/notification_log.json`.

## CLI Usage

Create a new snapshot and compare it with the previous one:

```powershell
python -m src.main run
```

When changes are found, this also writes a structured event file to `outputs/changes`.
Every run also appends scan metadata to `outputs/scan_history.json`.

Fetch entries and print them without saving:

```powershell
python -m src.main fetch
```

Compare the latest two saved snapshots:

```powershell
python -m src.main diff
```

List saved snapshots:

```powershell
python -m src.main snapshots
```

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

Simulation notifications are dry-run only. They print the email body but never send SMTP email.

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

For regular checks, run the CLI with Windows Task Scheduler, cron, GitHub Actions, or another scheduler:

```powershell
python -m src.main run
```

The command exits successfully even when no changes are found, making it suitable for scheduled automation. Notification channels can later be attached to the structured files in `outputs/changes`.

## Recommended Production Schedule

Run the monitor every 3 hours:

```text
00:00
03:00
06:00
09:00
12:00
15:00
18:00
21:00
```

OS-specific scheduling is not implemented in the project yet. The CLI is prepared for scheduled execution by external tools.

Future deployment with GitHub Actions cron:

```yaml
0 */3 * * *
```

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
