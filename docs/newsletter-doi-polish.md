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

## Active DOI template — updated 24 September 2026

The app selects its existing Brevo template through BREVO_DOI_TEMPLATE_ID.
The active Brevo template #1 (Neues Template) was inspected and updated in place
using its existing visual editor/YAML layout. Its native confirmation expression
was verified as {{ params.DOIurl }} and retained unchanged. Sender, subject,
preheader, template ID/status, list/DOI configuration and tracking settings were
not changed. The repository HTML is a portable design reference, not an automated
upload source; Brevo's existing editor remains the live template source.

The active design uses white background, near-black text, Arial sans-serif,
24px bold heading and full-width black/white CTA, with the requested German copy
and understated homepage/Datenschutz footer. Brevo desktop/mobile preview passed.
The saved settings page showed the updated content and Active status. No test
email or campaign was sent; token completion/delivery was not retested live.

## UI hotfix — 24 September 2026
Newsletter hover previously fell through to Streamlit's generated hover rule;
the widget paragraph also did not inherit the primary CTA's font weight.
Scoped normal/hover/active, paragraph weight and focus rules now preserve the
dark CTA and white 600-weight text without global overrides or !important.
Disabled opacity and all native signup behavior remain.

Recent entries use 20px top / 24px bottom padding around the existing divider,
8px heading-to-badges and 16px timestamp-to-action margin. Browser QA caught the
framework list-padding override; the final selector is scoped with enough
specificity to apply these values. No content/typography/card redesign.

Validation: 56 focused tests passed once. Local desktop/390/320 measurements show
no overflow; normal and actual hover colors, 600 weight, keyboard focus, checkbox
default and existing consent/DOI tests passed. The CSS-only specificity correction
was checked in the browser. No Claude or broad review loop.

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
