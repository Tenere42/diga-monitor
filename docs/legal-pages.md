# Public legal pages — 24 September 2026

## Owner-confirmed final correction
datenschutz@diga-tracker.de is verified and working (owner tested forwarding).
Only that public address is published; no private forwarding destination is stored
here. Opening and click tracking are intentionally retained. The mandatory,
initially unchecked consent now links directly to /datenschutz and explicitly
includes the evaluation described there. DOI/validation and Brevo settings remain
unchanged. This wording does not retroactively obtain consent from existing contacts.

## Scope and evidence
Public /datenschutz, /lizenz and /impressum use the existing Streamlit layout.
Legacy /?view=datenschutz email links still work. Newsletter signup/dispatch
readiness is unchanged. Company facts reuse the owner-approved Impressum.

Inspected app.py, src/subscribers.py, src/notifications.py, src/legal_content.py,
src/snapshot_storage.py, UI styles and deployment/configuration files:
- Railway hosts Streamlit; IP/connection data and operational logs are processed.
  Newsletter status logs omit entered email addresses.
- Brevo handles DOI, contacts, campaigns, delivery and suppression. The form keeps
  the address in server session state; there is no local subscriber database.
- Personalized Brevo links were observed in the previously approved live email.
  Provider defaults include open/click tracking. No new campaign or contact change
  was made for this task.
- R2 archives source snapshots server-side; source material can contain published
  contact details. It is not a browser embed or subscriber store.
- No app-authored analytics, advertising, embeds, external webfonts or browser
  storage tracking code found. Scraper cookie-banner handling is not website UI.
- Streamlit's optional usage statistics default to enabled; this PR explicitly
  disables them in .streamlit/config.toml. Technical sessions/XSRF protection
  remain. Production overrides and provider-side settings were not changed or
  independently audited.

## Cookies and unresolved owner/legal facts
No generic cookie banner or dead Cookie Settings link was added. No remaining
consent-requiring website tracker was established in the application code after
disabling optional telemetry. This is not a certification of production cookie
behavior. Email measurement is disclosed and included in the signup consent; a generic
website cookie banner is not introduced for email measurement.

Before treating the notice as legally complete, confirm:
1. Actual infrastructure log scope and retention.
2. Actual provider retention for measurement, consent evidence and suppression
   records; confirm the consent basis for existing contacts before relying on the
   new wording for those contacts. Owner confirmed that tracking remains enabled.
3. Contracted processors/subprocessors, processing countries and transfer
   safeguards, including R2 and production configuration overrides.
4. Applicable GDPR grounds for technical operations and email measurement, GDPR
   territorial scope and any EU representative obligation.
The public notice uses purpose-based retention and general transfer wording.
These operational/legal checks remain internal; no locations or specific
contractual safeguards have been invented.
Existing configured newsletter retention does not establish these separate periods.
No claim of an open BfArM data licence or exclusive ownership of facts is made.

## Sources and presentation
Limbi was used only as structural inspiration; no legal text was copied.
- https://limbi.net/
- https://docs.streamlit.io/develop/api-reference/configuration/config.toml
- https://railway.com/legal/dpa
- https://docs.railway.com/enterprise/compliance
- https://help.brevo.com/hc/en-us/articles/11643306229906-Can-I-anonymize-the-tracking-of-opens-and-clicks-for-my-emails
- https://help.brevo.com/hc/en-us/articles/37114679474706-About-email-tracking-pixels-and-the-CNIL-recommendation-in-Brevo
- https://www.edoeb.admin.ch/de/kontakt
- https://diga.bfarm.de/de/verzeichnis

## Validation
37 relevant tests passed once: app newsletter gate, UI foundation/refinements and
legal content. Includes real Streamlit AppTest rendering of all legal pages and
mocked newsletter submission (no email). Browser checks of all three pages at
320, 390 and 1280 CSS px found no horizontal overflow. Footer navigation to the
copyright page worked; link targets and company/source attribution were reviewed.
One self-review completed. The unrelated three accepted historical-count failures
were not rerun. No Claude review, production deployment, configuration change,
contact update, email send or monitoring-data change.

## Final correction validation
50 focused tests passed (public routes/footer, UI integration, signup state machine
and subscriber DOI requests). Browser QA found Streamlit markdown-label links open
a new tab, so the final layout uses a native checkbox with its full accessible label
and adjacent HTML text with an explicit /datenschutz target=_self link outside the
label. The 32 affected UI/signup tests passed after that correction; unchanged
subscriber tests were not repeated. At 320/390 CSS px there is no horizontal
overflow, consent starts unchecked, and clicking the link navigates in the same tab.
Only local preview with the email backend blocked was used. No production mutations.
