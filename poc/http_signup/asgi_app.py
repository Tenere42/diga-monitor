"""Standalone ASGI app for the HTTP newsletter signup PoC.

Run locally (from the repo root, so ``src`` and ``poc`` are importable):

    pip install starlette uvicorn httpx   # already transitive deps of
                                           # streamlit; httpx is dev-only,
                                           # for the integration test
    uvicorn poc.http_signup.asgi_app:app --port 8600 --reload

Then open http://localhost:8600/ for the minimal test form, or POST
directly:

    curl -X POST http://localhost:8600/api/newsletter/subscribe \\
      -H "Content-Type: application/json" \\
      -d '{"email": "you@example.com", "consent": true}'

This module is never imported by ``app.py`` or started by
``railway.json``'s ``startCommand`` -- it is not reachable in production
and does not change how the existing Streamlit app runs. See
``README.md`` in this directory for the architecture question this PoC
answers (how this *could* run inside the existing Railway service
without a separate deployment, if ever adopted for real) and for the
CORS/rate-limiting/abuse-risk analysis.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .routes import subscribe

STATIC_DIR: Final = Path(__file__).parent / "static"

# CORS is closed by default (empty allowlist -> CORSMiddleware simply
# isn't added). This endpoint is only ever same-origin with its own
# bundled test page in this PoC. A real deployment serving this from a
# different origin than the caller (e.g. the endpoint on the app's
# Railway domain, called from a separately hosted page) would need to
# set this explicitly -- see README.md's CORS section for why "*" is
# deliberately not the default.
_ALLOWED_ORIGINS_ENV: Final = "POC_HTTP_SIGNUP_ALLOWED_ORIGINS"


def _allowed_origins() -> list[str]:
    raw = os.environ.get(_ALLOWED_ORIGINS_ENV, "").strip()
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


async def healthz(request):  # noqa: ANN001, ARG001 - Starlette handler signature
    return JSONResponse({"status": "ok"})


def _build_middleware() -> list[Middleware]:
    origins = _allowed_origins()
    if not origins:
        return []
    return [
        Middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["POST"],
            allow_headers=["content-type"],
        )
    ]


# Exposed separately from `app` so a real integration (see README.md)
# could pass just this list into `st.App(..., routes=poc_routes)`
# without pulling in this module's own StaticFiles test-page mount.
poc_routes: Final = [
    Route("/api/newsletter/subscribe", subscribe, methods=["POST"]),
    Route("/healthz", healthz, methods=["GET"]),
]

app = Starlette(
    routes=[
        *poc_routes,
        Mount("/", app=StaticFiles(directory=STATIC_DIR, html=True), name="poc-static"),
    ],
    middleware=_build_middleware(),
)
