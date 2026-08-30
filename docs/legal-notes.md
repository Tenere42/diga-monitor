# Legal Notes — DiGA Tracker Newsletter (DiGA Tracker Alerts)

This document tracks legal assumptions and open questions for the public
newsletter feature. It is engineering documentation, not legal advice or a
legal certification, and none of the assumptions below should be relied on
without confirmation from qualified legal counsel before or at the point
they become materially relevant (see each section's trigger condition).

Verantwortlicher (data controller) for the newsletter feature is confirmed
by the project owner as **Leevsten GmbH**. No other operator fact (address,
contact, register entry, retention period, international-transfer basis) is
assumed, invented, or hardcoded anywhere in this codebase — see
`src/legal_content.py`, whose readiness gate keeps the entire feature
invisible on the public site until those facts are supplied and confirmed.

## Assumption: no Impressum in the current scope

**Assumption.** No German-style Impressum (§5 TMG/DDG-style operator
identification page) is implemented in this iteration.

**Basis given by the project owner:** the site is currently a free,
non-commercial Swiss information service — no sale of goods, no service
fee, no contract conclusion with visitors.

**Trigger to re-examine:** before any monetization, paid tier, sponsorship
with contractual obligations, or other commercial use of the site is
introduced. This assumption must be re-checked with legal counsel at that
point, not carried forward by default.

**Status:** documented assumption, not a legal conclusion. Not gated behind
a human sign-off for the *current* scope, because the project owner
supplied both the assumption and its stated basis directly. It *is*
listed here so it is not silently forgotten at the next scope change.

## Open legal check: GDPR applicability and Art. 27 EU representative

**Question.** Does the EU GDPR apply to this Swiss-operated site because of
its `.de` domain, German-language content, and clear focus on the German
DiGA framework (Art. 3(2) GDPR territorial-scope reasoning: offering
services to, or monitoring, individuals in the EU)? If GDPR applies, is an
EU representative required under Art. 27 GDPR?

**Status: OPEN. Not decided by this codebase, this implementation pass, or
any automated agent.** No conclusion — neither "GDPR applies" nor "GDPR
does not apply", and neither "an Art. 27 representative is required" nor
"none is required" — is asserted anywhere in the code, the
Datenschutzerklärung, or this document. The Datenschutzerklärung explicitly
names this as an open point (see `app.py`, `render_datenschutz_page`).

**Who resolves this:** the project owner, with qualified legal counsel.

**What would change if resolved "GDPR applies, representative required":**
the Datenschutzerklärung would need an EU representative's contact details
added, which is itself operator data that must come from the project owner
(same non-invention rule as every other operator fact) — this would extend
the `REQUIRED_OPERATOR_ENV_VARS` gate in `src/legal_content.py`, not bypass
it.

**This is a hard stop, not a loop-managed task:** no amount of iteration
against acceptance criteria may resolve this question by inference,
default, or "reasonable assumption." It stays open until a human closes it.

## Cookie/tracking technical analysis

**Finding: no consent-requiring cookie or tracking technology was
introduced by this change; no cookie banner was built.**

Evidence:

- `grep -rniE "google-analytics|gtag|analytics\.js|matomo|hotjar|segment\.com|mixpanel|facebook\.net/.*fbevents|cookieconsent|iframe"` across `app.py`, `src/subscribers.py`, `src/subscriber_alerts.py`, and `src/legal_content.py` returns no matches.
- The Brevo double opt-in call in `src/subscribers.request_double_optin` is made **server-side** from Python (`urllib.request.urlopen`), triggered by a Streamlit form submit handled entirely on the server. No Brevo JavaScript widget, tracking pixel, or `<iframe>` is loaded in the visitor's browser at any point in the signup, confirmation, or unsubscribe flow — Brevo's own DOI confirmation page and campaign unsubscribe page are external pages the visitor is redirected/linked to, not embedded on this site.
- `requirements.txt` gains no new dependency for this feature beyond the Python standard library already used by `src/notifications.py` for the same pattern.

Because no consent-requiring cookie/tracker is introduced, no cookie banner
was built, per the instruction that a banner is built only if the technical
analysis finds one is actually needed. If a future change adds a
client-side Brevo embed (e.g. a hosted signup widget) instead of the
server-side API call used here, this finding no longer holds and the
cookie-banner question must be re-escalated before shipping that change.
