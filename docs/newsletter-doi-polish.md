# Newsletter DOI and mobile polish

## Redirect and confirmation ownership

The existing `POST /v3/contacts/doubleOptinConfirmation` request remains the only
signup path. Brevo sends the email, validates its token, and controls membership
in `includeListIds`. Its `redirectionUrl` is the post-confirmation destination,
not the confirmation link itself.

`BREVO_DOI_REDIRECT_URL=https://www.diga-tracker.de` is the production setting.
The code also normalizes the known old production value ending in
`/?view=confirmed` to that homepage, so existing environment configuration does
not keep sending newly requested confirmations to a standalone page. Custom
preview/local destinations remain unchanged. Previously issued URLs with
`?view=confirmed` render the normal homepage as a compatibility route.

No success banner is inferred from a public URL parameter: it cannot prove
confirmation. Brevo remains the source of truth; no contact state is changed on
the return page and there is no redirect script or loop.

## Reviewable email asset (not published)

`templates/brevo-doi-confirmation.html` is an inline-styled, fluid 560px email
template with a full-width black CTA and the requested German copy. It uses the
native DOI API template placeholder `{{ params.DOIurl }}` unchanged. Do not
replace it with the homepage URL or generate a token in this application.

The application still selects the existing `BREVO_DOI_TEMPLATE_ID`; it does not
upload templates automatically. The live template and its current markup could
not be inspected because no Brevo key/template ID is available in this session.
Before an authorized email rollout, inspect and preserve the active template's
DOI link expression (including any Brevo editor-specific metadata), sender,
subject, DOI designation and account-required footer. If the existing native
link differs, preserve that exact expression rather than blindly substituting.
Review the HTML in Gmail mobile and Outlook, then validate a genuine DOI request
with a controlled test address, list exclusion before confirmation, list inclusion
after confirmation and final homepage destination. Plain template test sends
alone cannot establish that a real DOI token works. No live template was edited,
test email sent, or production configuration changed by this task.

## Mobile form

`st.form(..., enter_to_submit=False)` removes the source of Streamlit's Enter
hint for this form only. The installed frontend passes that setting into
`InputInstructions`; no CSS hides instructions, validation, counters or labels.
The explicit submit button remains keyboard accessible. Streamlit >=1.39 is
required for this parameter.

The keyed newsletter container stays in normal flow with content-sized height,
16px email input text (avoiding iOS input-focus zoom), a 48px input and button,
safe-area-aware page spacing and scroll padding. Mobile app height uses `100dvh`
where supported; no fixed/sticky newsletter positioning or scripted auto-scroll
is introduced. Dynamic viewport units alone cannot emulate a real iOS keyboard.

Visual/device QA is still required at 390px (normal and reduced viewport, focus,
validation, result) and desktop. The saved browser permission denial must be
respected; automated widget checks are not proof of iPhone keyboard behavior.

## References

- [Brevo native DOI API](https://developers.brevo.com/reference/create-doi-contact)
- [Streamlit form API](https://docs.streamlit.io/develop/api-reference/execution-flow/st.form)
