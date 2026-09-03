# Legal Notes — DiGA Tracker Newsletter (DiGA Tracker Alerts)

This document tracks legal assumptions and open questions for the public
newsletter feature. It is engineering documentation, not legal advice or a
legal certification, and none of the assumptions below should be relied on
without confirmation from qualified legal counsel before or at the point
they become materially relevant (see each section's trigger condition).

Verantwortlicher (data controller) for the newsletter feature is confirmed
by the project owner as **Leevsten GmbH**. Only facts with an identified
legal basis are collected from the project owner (see "Minimal disclosure"
below); nothing is invented anywhere in this codebase — see
`src/legal_content.py`, whose readiness gate keeps the entire feature
invisible on the public site until those facts are supplied and confirmed.

## Minimal disclosure: address and register info are not collected

**Correction (this section supersedes an earlier version of the gate).** An
earlier implementation pass required a postal address, a commercial
register entry, and a free-form "international transfer basis" sentence
from the project owner before the feature could go live. On review, this
was flagged as inconsistent with the project's minimal-disclosure
principle and the project owner's private residential address doubling as
the Leevsten GmbH address. It has been corrected as follows.

**Address.** Not collected, not required, not rendered. Under the Swiss
revDSG baseline this project uses, Art. 19 DSG requires "Identität und
Kontaktdaten des Verantwortlichen" (identity and contact details of the
controller) in a privacy notice — this is satisfied by the confirmed name
("Leevsten GmbH") plus a reachable contact **email** address; DSG's Art. 19
minimum-content list does not itself require a postal address. A postal
address is more characteristic of German Impressum duties (§5 TMG/DDG),
which this project has separately decided are out of scope (see below) as
a non-commercial Swiss information offering. This is a documented legal
assumption, not a certified legal conclusion — re-examine with counsel if
challenged, and always before the Impressum-scope trigger below is hit
(since an Impressum, if ever required, would typically require an
address).

**Commercial register entry (Handelsregister-Nr./UID).** Not collected,
not required, not rendered, for the same reason: it is an Impressum-style
identification duty, not part of DSG Art. 19's privacy-notice minimum
content.

**International transfer.** Not collected as free-form human input.
Requiring the project owner to invent or informally state "the basis" for
international transfer risked producing an unverified, possibly inaccurate
legal claim. Instead, `src/legal_content.py::INTERNATIONAL_TRANSFER_STATEMENT`
is a fixed statement, sourced from Brevo's and Railway's own published Data
Processing Agreements (checked 2026-08-30):

- Railway Data Processing Addendum, https://railway.com/legal/dpa (fetched
  directly; verbatim): Section 9.1 — "Company's primary processing
  operations take place in the United States"; the DPA also permits hosting
  in the Netherlands or Singapore depending on configuration (per
  https://station.railway.com/questions/eu-safe-6c98d8a5 and Railway's own
  compliance docs, https://docs.railway.com/enterprise/compliance). Section
  9.2 — EU transfers use the EU Standard Contractual Clauses (or the EU-US
  Data Privacy Framework); Section 9.4 — UK SCCs for UK transfers; Section
  9.5 — the Switzerland-adapted SCCs for Swiss transfers. Railway's
  subprocessor list is published at https://trust.railway.com/item/subprocessors.
- Brevo Data Processing Agreement (Annex 2),
  https://corp-backend.brevo.com/wp-content/uploads/2024/08/BREVO-Annex-2-DPA-150524.pdf,
  and Brevo's GDPR help article,
  https://help.brevo.com/hc/en-us/articles/360001258744-How-does-Brevo-comply-with-the-GDPR
  — indexed/summarized content (the primary PDF could not be extracted as
  plain text with the tools available for this pass, so this reflects a
  search-engine-indexed summary of the document's own stated content, not a
  directly fetched verbatim quote): personal data may be transferred to the
  United States and India, countries without a European Commission adequacy
  decision; Brevo states it applies the Standard Contractual Clauses and
  additional measures for such transfers.

**Verification caveat, explicitly stated in the public statement itself:**
this reflects the vendors' publicly documented *standard* terms, not a
review of Leevsten GmbH's actual signed contracts with them (which this
codebase has no access to). If Leevsten GmbH ever negotiates non-standard
terms with either vendor, or either vendor's public documentation changes,
this statement must be re-verified and updated in code — not silently
re-confirmed by a human typing a new sentence into an environment variable,
which is exactly the pattern this correction removes.

**What remains required from the project owner:** only
`DIGA_TRACKER_OPERATOR_CONTACT_EMAIL` (a reachable contact for
privacy/data-subject-rights requests) and `DIGA_TRACKER_DATA_RETENTION_PERIOD`
(an operational fact only Leevsten GmbH can state — e.g. "until consent is
withdrawn"). Both still fail-closed: `NEWSLETTER_LEGAL_READY` cannot become
effectively "true" while either is unset or visually blank (see
`_has_visible_content()` in `src/legal_content.py`).

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
