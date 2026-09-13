"""HTTP newsletter signup PoC.

A small, standalone Starlette/ASGI service that exposes
``POST /api/newsletter/subscribe`` as a classic HTTP alternative to the
existing Streamlit form/rerun signup in ``app.py``. It reuses
``src.subscribers.request_double_optin`` for the actual Brevo call --
no Brevo logic is duplicated here.

This package is completely isolated from the production app: nothing in
``app.py`` imports from here, and nothing here imports from ``app.py``.
It is not started by ``railway.json``'s ``startCommand`` and is not
reachable in production. See ``README.md`` in this directory for how to
run it locally and for the architecture analysis this PoC exists to
answer.
"""
