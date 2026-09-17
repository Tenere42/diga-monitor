# Change-notification email

## Existing architecture, retained

`src/main.py::notify_and_dispatch_subscriber_alerts` still calls the existing
admin notifier and then the fault-isolated subscriber notifier. No second
notification system, subscriber database, or contact export was added.

- `src/notifications.py::notify_changes` previously built a verbose plain-text
  report in `build_email_body`, assembled it in `build_email_message`, and sent
  it through `send_email` to Brevo `POST /v3/smtp/email`. It now uses the shared
  concise renderer for both `htmlContent` and `textContent`. Explicitly configured
  admin recipients remain operational recipients, not the subscriber list.
- `src/subscriber_alerts.py` retains the existing Campaign API create/send flow,
  legal gate, confirmed `BREVO_NEWSLETTER_LIST_ID`, and failure isolation. Its
  former short HTML event list is replaced with the same presentation renderer.
- `src/notification_email.py` owns grouping, conservative German classifications,
  HTML escaping, provider-template-injection protection and text rendering.
  `templates/change-notification.html` owns the repository-controlled layout.
- Email content includes names, category labels and CTAs only, never summaries,
  before/after values, timestamps, scraper diagnostics or greetings. Counts refer
  to displayed public DiGA/day records, not repetitive raw detection events.
  Mixed categories use `Aktualisierung`; no guessed lifecycle outcome.
- Existing technical/no-op exclusions are applied using the existing semantic
  price/evidence helpers. Historical coverage checks every resulting link against
  the actual public groups without hardcoding the current group count.

## Deep links

`src/change_links.py` is shared with the app. It preserves the existing
`change-` + truncated SHA-256 of lowercase DiGA identity and Berlin calendar date.
The URL is `https://www.diga-tracker.de/?view=changes&detail=change-…`.
No session state, event-list index, current filter, or email address enters it.
Existing links remain valid. Several events on one DiGA/day produce one CTA;
different public dates can produce separate cards because their destinations
are different. Invalid/missing dates produce no card. Configured dashboard URLs
remain supported but must use HTTPS; existing query/fragment values are replaced.

The app resolves links against all public groups, independently of date/search
filters. Missing or unavailable old records show the existing German message and
an `Alle Änderungen ansehen` action. Unknown classifications use a neutral label;
an unsupported/unavailable public record uses that same graceful fallback.

## Unsubscribe and privacy

Every subscriber HTML email explicitly includes `<a href="{{ unsubscribe }}">`.
Brevo resolves that native campaign tag to the recipient's unsubscribe page and
blocklists the contact for email campaigns. Subsequent campaigns target only the
confirmed list, and Brevo suppresses blocklisted contacts even if they remain on
that list. This is account-wide email-campaign suppression, not necessarily just
one list. The application never replaces this with a homepage, personal address,
custom token endpoint, transactional delivery or a manually assembled audience.
Existing resubscription requires a new native DOI flow and is unchanged.

Mocks verify the native tag, confirmed-list audience, absence of direct recipient
addresses, absence of bypass calls, legal/configuration gates and safe failure
logging. They do not claim to prove Brevo delivery or change any real contact.
Provider errors are logged as status/class only; provider bodies are not logged.
New admin log records store recipient counts instead of addresses. Existing logs
and all historical data are preserved.

## Plain text

The transactional API accepts `textContent`, which now contains the same concise
headline, names and individual links. The Campaign API does **not** expose a
`textContent` request property. Brevo automatically generates its multipart text
alternative from the submitted HTML, including native link personalization.
`build_alert_text_body` and the preview command provide a deterministic local
text equivalent with links and native unsubscribe tag; they are not a claim that
our exact `.txt` bytes are transmitted by the Campaign API. Before rollout,
inspect the generated campaign text/MIME and confirm detail and unsubscribe URLs
in a controlled approved test. Do not add an unsupported API field or switch
subscribers to transactional mail to force the text part.

## Configuration and rollout

`DIGA_TRACKER_IMPRESSUM_URL` must be the actual published HTTPS Impressum URL.
The website currently has no Impressum route, so no fake destination or legal
content was invented. Subscriber configuration fails closed while this setting
is absent/invalid. Configure the GitHub repository variable and any scheduler
environment after the real URL is confirmed; workflow wiring is included.
Read-only production inspection on 2026-09-17 confirmed that the rendered footer
links only to `https://www.diga-tracker.de/?view=datenschutz`. That page is headed
Datenschutzerklärung, not Impressum. `app.py` implements that gated privacy route;
`docs/legal-notes.md` explicitly records that no Impressum page was implemented.
The privacy URL is therefore not silently reused under an Impressum label.
The synthetic previews use `https://example.invalid/impressum` explicitly as a
fixture, never as a production fallback. The existing Datenschutz route and
legal gate are retained. Admin-only messages use the Impressum URL when supplied.

The owner subsequently authorized merging PR #15 and exactly one production-list
notification, conditional on a real Impressum. PR #15 is merged; PR #16 must
remain unmerged until the owner inspects the received email. Production Railway
variable names and the public site were inspected: no Impressum URL or company
address/representative/register data is configured. Existing legal documentation
explicitly did not collect these facts. Missing publishable facts are the full
company address (including country), authorized representative(s), and commercial
register/UID details; tax/VAT identification applicability also needs confirmation.
These are missing facts for the requested company-identification page, not a new
legal determination about which jurisdiction's duties apply. No URL or legal
content was invented and no partial legal page was published.

**Live test stopped before any campaign creation or send.** Zero notifications
were triggered; there is no production simulated change, campaign ID, acceptance,
delivery or generated unsubscribe result. The stated one-subscriber audience was
not independently counted. No production history, R2 snapshots, baseline or events
were changed. After the missing facts are supplied, publish and verify the real
page, configure the variable in the actual scheduler environment, and run the
single authorized subscriber-path test without automatic retry. Inspect delivered
HTML/plain text, native unsubscribe and mobile rendering before merge approval.

## Local QA and review

Run `python -m scripts.preview_notification_email` to create four local HTML/text
fixtures under ignored `work/email-previews`: one new DiGA, two different DiGA,
several events for one DiGA, and an unclassified update. This command has no
network or send path. Preview footer links are placeholders for local inspection.

The actual generated HTML and screenshots were inspected in headless Edge at
1000px, 390px and 320px. All four fixtures have correct card counts, black CTAs
over 48px high, readable wrapping (including a long name), footer/unsubscribe
and no horizontal overflow. Tables, inline CSS, system fonts and MSO width/padding
fallbacks are used. Browser QA is not Gmail/Apple Mail/Outlook delivery proof.

Claude authentication preflight failed because `ANTHROPIC_API_KEY` is unavailable.
No OAuth fallback was attempted. Codex self-review covered transport separation,
group/link consistency, escaping, template injection, unsubscribe, fail-closed
configuration and PII-safe errors. It found and fixed technical-only cards and
unsafe provider-error logging. No substantive code findings remain; the rollout
configuration/client/provider checks above remain open.

Integration verification after merging main `89fc043614b1fbb471e4835653d54fb7c95d8b38`:
237 tests, 234 passed. The same three accepted historical-count failures remain:
392 versus 369 events in two tests and 27 versus 23 public groups. Main's imported
monitoring data explains the updated actual counts; no expectations were changed.
Compileall over app/src/scripts/tests and staged/unstaged whitespace checks pass.
The sole merge conflict was PROJECT_STATE documentation. Operational data files
are identical to main; PR #16's diff contains no history or baseline changes.
Claude preflight still fails for a missing API key; repeated self-review covered
the integrated routing, lifecycle labels, filtering, HTML escaping, list-only
Campaign payload, failure isolation, configuration gates and safe error logging.
No new substantive findings remain.

Repeated browser QA on integrated previews at 1000, 390 and 320px found no
horizontal overflow across all four fixtures. Long-name two-card screenshots were
visually checked at all three widths. The deployed homepage, real ACTICORE1 detail
and Datenschutz destinations resolve. Synthetic fixture detail IDs intentionally
do not identify production records. The Impressum fixture is deliberately invalid
and the unsubscribe token can only resolve through Brevo; neither is represented
as a verified live link. Historical link equivalence tests pass for all real groups.

## Provider references (checked 2026-09-17)

- [Campaign API request schema](https://developers.brevo.com/reference/create-email-campaign)
- [Native unsubscribe links](https://help.brevo.com/hc/en-us/articles/209553645-Insert-a-custom-unsubscribe-link-in-your-emails)
- [Campaign blocklist behavior](https://help.brevo.com/hc/en-us/articles/209458705-What-is-a-blacklisted-contact-)
- [Automatic plain-text generation](https://help.brevo.com/hc/en-us/articles/360000486460-How-do-I-create-edit-the-plain-text-version-of-HTML-emails)
