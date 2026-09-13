"""Tests for the ASGI app construction itself: CORS configuration.

Deliberately tests the ``_allowed_origins``/``_build_middleware`` helper
functions directly rather than re-importing ``asgi_app`` with different
environment variables -- the module-level ``app`` (and its middleware
stack) is already built once at import time, so re-testing that via
reimport would need import-system gymnastics for no real benefit; the
helpers below are what actually decides the behaviour, and are already
exercised end-to-end by every other test in this package running
against the real, already-constructed ``app``.
"""

from __future__ import annotations

import unittest
from unittest import mock

from starlette.middleware.cors import CORSMiddleware

from poc.http_signup import asgi_app


class AllowedOriginsTests(unittest.TestCase):
    def test_defaults_to_no_origins_when_env_var_unset(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop(asgi_app._ALLOWED_ORIGINS_ENV, None)
            self.assertEqual(asgi_app._allowed_origins(), [])

    def test_parses_a_comma_separated_list(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {asgi_app._ALLOWED_ORIGINS_ENV: "https://a.example, https://b.example"},
        ):
            self.assertEqual(
                asgi_app._allowed_origins(), ["https://a.example", "https://b.example"]
            )

    def test_blank_value_is_treated_as_unset(self) -> None:
        with mock.patch.dict("os.environ", {asgi_app._ALLOWED_ORIGINS_ENV: "   "}):
            self.assertEqual(asgi_app._allowed_origins(), [])


class BuildMiddlewareTests(unittest.TestCase):
    def test_no_middleware_when_no_origins_configured(self) -> None:
        with mock.patch.object(asgi_app, "_allowed_origins", return_value=[]):
            self.assertEqual(asgi_app._build_middleware(), [])

    def test_cors_middleware_added_when_origins_configured(self) -> None:
        with mock.patch.object(
            asgi_app, "_allowed_origins", return_value=["https://example.com"]
        ):
            middleware = asgi_app._build_middleware()
        self.assertEqual(len(middleware), 1)
        self.assertIs(middleware[0].cls, CORSMiddleware)


class AppRouteCompositionTests(unittest.TestCase):
    def test_poc_routes_contains_only_the_api_and_health_routes(self) -> None:
        # poc_routes is exported separately precisely so it can be handed
        # to Streamlit's st.App(routes=...) later without also pulling in
        # this module's own static test-page mount -- see README.md.
        paths = {route.path for route in asgi_app.poc_routes}
        self.assertEqual(paths, {"/api/newsletter/subscribe", "/healthz"})


if __name__ == "__main__":
    unittest.main()
