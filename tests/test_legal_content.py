from __future__ import annotations

import os
import unittest
from unittest import mock

from src.legal_content import (
    OPERATOR_NAME,
    REQUIRED_OPERATOR_ENV_VARS,
    is_legal_content_ready,
    load_operator_profile,
    missing_operator_fields,
)


READY_ENV = {
    "NEWSLETTER_LEGAL_READY": "true",
    "DIGA_TRACKER_OPERATOR_ADDRESS": "Musterstrasse 1, 8000 Zuerich, Schweiz",
    "DIGA_TRACKER_OPERATOR_CONTACT_EMAIL": "datenschutz@example.com",
    "DIGA_TRACKER_OPERATOR_REGISTER_INFO": "CHE-000.000.000, Handelsregister ZH",
    "DIGA_TRACKER_DATA_RETENTION_PERIOD": "Bis zum Widerruf der Einwilligung",
}


class LegalContentReadinessTests(unittest.TestCase):
    def test_defaults_to_not_ready_with_empty_environment(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(is_legal_content_ready())
            self.assertIsNone(load_operator_profile())

    def test_not_ready_when_switch_off_even_if_all_fields_set(self) -> None:
        env = dict(READY_ENV)
        env["NEWSLETTER_LEGAL_READY"] = "false"
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertFalse(is_legal_content_ready())
            self.assertIsNone(load_operator_profile())

    def test_not_ready_when_switch_on_but_a_field_missing(self) -> None:
        for missing_var in REQUIRED_OPERATOR_ENV_VARS:
            env = dict(READY_ENV)
            del env[missing_var]
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertFalse(is_legal_content_ready(), msg=f"should be blocked by missing {missing_var}")
                self.assertIsNone(load_operator_profile())
                self.assertIn(missing_var, missing_operator_fields())

    def test_ready_only_when_switch_on_and_every_field_present(self) -> None:
        with mock.patch.dict(os.environ, READY_ENV, clear=True):
            self.assertTrue(is_legal_content_ready())
            self.assertEqual(missing_operator_fields(), [])
            profile = load_operator_profile()
            self.assertIsNotNone(profile)
            self.assertEqual(profile.name, OPERATOR_NAME)
            self.assertEqual(profile.address, READY_ENV["DIGA_TRACKER_OPERATOR_ADDRESS"])
            self.assertEqual(profile.contact_email, READY_ENV["DIGA_TRACKER_OPERATOR_CONTACT_EMAIL"])
            self.assertEqual(profile.register_info, READY_ENV["DIGA_TRACKER_OPERATOR_REGISTER_INFO"])
            self.assertEqual(profile.data_retention_period, READY_ENV["DIGA_TRACKER_DATA_RETENTION_PERIOD"])

    def test_operator_name_is_leevsten_gmbh_and_not_environment_driven(self) -> None:
        # The Verantwortlicher name is a confirmed constant, not read from
        # the environment -- it cannot be silently overridden or blanked.
        self.assertEqual(OPERATOR_NAME, "Leevsten GmbH")


if __name__ == "__main__":
    unittest.main()
