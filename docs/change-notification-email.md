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

The owner supplied and approved the company details on 2026-09-18. The public
Impressum is implemented using native Streamlit routing at
https://www.diga-tracker.de/impressum, with a footer link beside Datenschutz.
Only the supplied company facts are published; no VAT number is asserted.
The page was verified in the existing Railway ui-preview environment first,
then deployed to production directly from this PR branch without merging PR #16.
Latest main monitoring data was integrated before deployment to avoid regressing
the website snapshot. Production and preview currently track this branch;
restore production's source to main after eventual merge approval.

`DIGA_TRACKER_IMPRESSUM_URL=https://www.diga-tracker.de/impressum` was saved in
GitHub Actions repository variables and Railway production service variables.
Production page content and layout passed desktop/390px/320px checks without
horizontal overflow. Datenschutz remains at `/?view=datenschutz`.

## Controlled live test — 2026-09-18

The owner confirmed all four eligible addresses belong to them and authorized one
campaign to all four. Read-only preflight found five contacts in production list
#3: four email-eligible and one blocklisted. No contacts or list settings changed.

The initial console command did not reach the send gate (no attempt marker or
send log; Brevo still had only the September 3 campaign). Its formatting was
corrected and syntax validated before running the one-shot script. The script
then called `dispatch_subscriber_alerts(..., include_simulated=True)` exactly once,
using the production runtime configuration and actual subscriber Campaign path.
It used an in-memory replay of ACTICORE1 (ID 02940), `new_diga`, from
2026-09-16T14:30:11.482070+00:00: previously absent, now provisionally listed.
The stable detail URL is `/?view=changes&detail=change-e3d1a4b6ae3d3cb1`.
No new event was persisted or made visible on the tracker.

Brevo campaign **3** was accepted on 2026-09-18 at 13:48:37 UTC; provider status
became `sent`, with sentDate 15:49:19 +02:00. Subject: "Es gibt Updates im DiGA
Verzeichnis"; sender: "DiGA Tracker" <updates@diga-tracker.de>. Four eligible
recipients were authorized; the blocklisted contact was excluded by Brevo's
native campaign suppression. No transactional admin email or second campaign
was triggered. There was no retry of a campaign send.

Receipt was independently verified in Gmail. Rendered HTML contains the expected
German ACTICORE1 card and all footer links. Original MIME includes multipart/
alternative, text/plain and text/html; the plain-text part contains ACTICORE1,
Neue DiGA, Impressum, Datenschutz, Abmelden and HTTPS links, with no unresolved
unsubscribe token. Brevo generated a personalized HTTPS link on
r.mail.diga-tracker.de and List-Unsubscribe headers. The unsubscribe link was
not followed and the subscriber was not unsubscribed. Actual phone/Outlook/Apple
Mail inspection remains for the owner; responsive browser previews passed earlier.
At the initial report check Brevo's aggregate sent/delivered counters were still
zero despite status sent and verified Gmail receipt; full four-address delivery
was not yet independently established.

Before/after hashes of all runtime data/outputs files matched. Contact membership
and blocklist-status hashes matched. The test made zero R2 calls and invoked no
scanner, baseline writer or history writer. Only the attempt marker and test log
were written under /tmp. Exactly one campaign send was triggered.

PR #16 remains unmerged pending the owner's inspection and explicit approval.

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
238 tests, 235 passed. The same three accepted historical-count failures remain:
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
