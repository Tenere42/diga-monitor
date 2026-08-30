from __future__ import annotations

import os
import unittest
from unittest import mock

from src.legal_content import (
    INTERNATIONAL_TRANSFER_STATEMENT,
    OPERATOR_NAME,
    REQUIRED_OPERATOR_ENV_VARS,
    is_legal_content_ready,
    load_operator_profile,
    missing_operator_fields,
)


READY_ENV = {
    "NEWSLETTER_LEGAL_READY": "true",
    "DIGA_TRACKER_OPERATOR_CONTACT_EMAIL": "datenschutz@example.com",
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
            self.assertEqual(profile.contact_email, READY_ENV["DIGA_TRACKER_OPERATOR_CONTACT_EMAIL"])
            self.assertEqual(
                profile.data_retention_period, READY_ENV["DIGA_TRACKER_DATA_RETENTION_PERIOD"]
            )
            self.assertEqual(profile.international_transfer_statement, INTERNATIONAL_TRANSFER_STATEMENT)

    def test_operator_name_is_leevsten_gmbh_and_not_environment_driven(self) -> None:
        # The Verantwortlicher name is a confirmed constant, not read from
        # the environment -- it cannot be silently overridden or blanked.
        self.assertEqual(OPERATOR_NAME, "Leevsten GmbH")

    def test_zero_width_space_only_value_is_treated_as_missing(self) -> None:
        # Regression for a real gap found in adversarial review:
        # str.strip() does not remove U+200B ZERO WIDTH SPACE, so a
        # required field set to only invisible characters must not pass
        # the readiness check -- it would render as a blank fact on the
        # public Datenschutzerklärung page otherwise.
        env = dict(READY_ENV)
        env["DIGA_TRACKER_OPERATOR_CONTACT_EMAIL"] = "​" * 3  # ZERO WIDTH SPACE only, no visible content
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertFalse(is_legal_content_ready())
            self.assertIn("DIGA_TRACKER_OPERATOR_CONTACT_EMAIL", missing_operator_fields())
            self.assertIsNone(load_operator_profile())

    def test_zero_width_space_mixed_with_real_content_still_counts_as_present(self) -> None:
        # A field containing invisible characters *alongside* real
        # content is a harmless cosmetic issue, not a blank field -- it
        # must not be blocked (that would make the gate too strict to
        # ever pass with ordinary copy-pasted text).
        env = dict(READY_ENV)
        env["DIGA_TRACKER_OPERATOR_CONTACT_EMAIL"] = "datenschutz​@example.com"
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertTrue(is_legal_content_ready())


class MinimalDisclosureTests(unittest.TestCase):
    """Regression for the minimal-disclosure correction: an address and
    commercial register entry are intentionally NOT required, NOT
    collected, and NOT rendered -- only what has an identified legal
    basis (contact data, retention period) gates the feature.
    """

    def test_address_and_register_info_are_not_required_env_vars(self) -> None:
        self.assertNotIn("DIGA_TRACKER_OPERATOR_ADDRESS", REQUIRED_OPERATOR_ENV_VARS)
        self.assertNotIn("DIGA_TRACKER_OPERATOR_REGISTER_INFO", REQUIRED_OPERATOR_ENV_VARS)

    def test_gate_only_requires_contact_email_and_retention(self) -> None:
        self.assertEqual(
            set(REQUIRED_OPERATOR_ENV_VARS),
            {"DIGA_TRACKER_OPERATOR_CONTACT_EMAIL", "DIGA_TRACKER_DATA_RETENTION_PERIOD"},
        )

    def test_ready_with_only_the_two_required_fields_even_if_address_env_vars_are_unset(self) -> None:
        # A leftover/legacy DIGA_TRACKER_OPERATOR_ADDRESS in someone's
        # local environment must not be required and must not be read.
        with mock.patch.dict(os.environ, READY_ENV, clear=True):
            self.assertNotIn("DIGA_TRACKER_OPERATOR_ADDRESS", os.environ)
            self.assertTrue(is_legal_content_ready())

    def test_operator_profile_has_no_address_or_register_attribute(self) -> None:
        with mock.patch.dict(os.environ, READY_ENV, clear=True):
            profile = load_operator_profile()
        self.assertFalse(hasattr(profile, "address"))
        self.assertFalse(hasattr(profile, "register_info"))

    def test_international_transfer_statement_is_not_a_deferred_stub(self) -> None:
        # Regression: an earlier version of this page deferred with
        # "Details ... werden hier ergänzt, sobald sie abschliessend
        # geprüft sind" -- a placeholder for legally required content.
        # The statement must be real, sourced content naming the actual
        # vendors and countries, not a promise to fill it in later.
        lowered = INTERNATIONAL_TRANSFER_STATEMENT.lower()
        for stub_phrase in ("werden hier ergänzt", "wird hier ergänzt", "details to follow", "input erforderlich"):
            self.assertNotIn(stub_phrase.lower(), lowered)
        for expected in ("brevo", "railway", "usa", "standardvertragsklauseln"):
            self.assertIn(expected, lowered)

    def test_international_transfer_statement_is_not_env_driven(self) -> None:
        # It must be a fixed, code-reviewed statement, not free-form
        # human input via an environment variable (the earlier version
        # of this gate did that and was corrected after review).
        self.assertNotIn("DIGA_TRACKER_INTERNATIONAL_TRANSFER_BASIS", REQUIRED_OPERATOR_ENV_VARS)
        with mock.patch.dict(
            os.environ,
            dict(READY_ENV, DIGA_TRACKER_INTERNATIONAL_TRANSFER_BASIS="something a human typed"),
            clear=True,
        ):
            profile = load_operator_profile()
        self.assertEqual(profile.international_transfer_statement, INTERNATIONAL_TRANSFER_STATEMENT)


if __name__ == "__main__":
    unittest.main()
