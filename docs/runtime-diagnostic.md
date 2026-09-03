# Temporary newsletter runtime diagnostic

This branch adds a temporary, production-safe diagnostic log line for the newsletter legal readiness gate.

The log emits booleans only:

- whether `NEWSLETTER_LEGAL_READY` resolves to `true`
- whether the operator contact variable has visible content
- whether the retention variable has visible content
- the resulting gate decision

No environment variable values, email addresses, subscriber data, or secrets are logged.

Remove this diagnostic after the Railway runtime issue is identified.
