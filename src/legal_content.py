"""Readiness gate for newsletter signup and dispatch only.

Public legal pages remain available independently. Operator publication was
approved for the Impressum; this gate still requires configured newsletter facts.
Legacy transfer text is retained for existing profile consumers, not rendered by
the public privacy page. See content/legal/datenschutz.md and docs/legal-pages.md.
"""

from __future__ import annotations

import logging
import os
import unicodedata
from dataclasses import dataclass


logger = logging.getLogger(__name__)

OPERATOR_NAME = "Leevsten GmbH"

# Sourced from Brevo's and Railway's own published Data Processing
# Agreements/documentation, not invented and not collected as free-form
# human input. See docs/legal-notes.md for exact source URLs and the
# date this was last checked -- re-verify there before trusting this is
# still current if it has been a while.
INTERNATIONAL_TRANSFER_STATEMENT = (
    "Für den Versand der DiGA Tracker Alerts setzen wir Brevo SA (Frankreich) "
    "als Auftragsverarbeiter ein. Nach den öffentlich zugänglichen "
    "Vertragsunterlagen von Brevo (Data Processing Agreement) kann dabei eine "
    "Übermittlung personenbezogener Daten in Länder ohne "
    "Angemessenheitsbeschluss der EU-Kommission stattfinden, namentlich in "
    "die USA und nach Indien; Brevo erklärt, hierfür Standardvertragsklauseln "
    "(Standard Contractual Clauses) und zusätzliche Massnahmen anzuwenden.\n\n"
    "Für das Hosting dieser Website setzen wir Railway ein. Railway "
    "verarbeitet Daten nach eigener Angabe primär in den USA, kann je nach "
    "gewählter Konfiguration aber auch in den Niederlanden oder Singapur "
    "hosten. Railway ist über sein Data Processing Addendum vertraglich "
    "verpflichtet, für Übermittlungen aus der EU die EU-Standardvertragsklauseln "
    "(bzw. für Übertragungen aus dem Vereinigten Königreich oder der Schweiz "
    "die entsprechend angepassten Klauseln) anzuwenden.\n\n"
    "Diese Angaben beruhen auf den zum Zeitpunkt der letzten Prüfung "
    "öffentlich zugänglichen Vertragsunterlagen von Brevo und Railway "
    "(Quellen und Prüfdatum: siehe docs/legal-notes.md) und wurden nicht "
    "anhand eines individuell verhandelten Vertrags der Leevsten GmbH "
    "verifiziert."
)

# The master switch. Defaults to OFF (unset/anything other than "true").
# A human sets this explicitly, and only after every field below is set
# to real, confirmed values -- never as a way to "unblock" development.
LEGAL_READY_ENV_VAR = "NEWSLETTER_LEGAL_READY"

# Every one of these must be a non-empty (see _has_visible_content)
# environment variable before the feature is considered ready, regardless
# of the switch above. This is a second, independent safety net: even an
# accidental early flip of the switch cannot expose the feature with
# missing facts. Deliberately short (see module docstring / minimal
# disclosure): only genuinely required facts belong here. Address,
# register info, and the international-transfer statement are NOT here
# -- see module docstring for why.
REQUIRED_OPERATOR_ENV_VARS = [
    "DIGA_TRACKER_OPERATOR_CONTACT_EMAIL",
    "DIGA_TRACKER_DATA_RETENTION_PERIOD",
]


@dataclass(frozen=True)
class OperatorProfile:
    name: str
    contact_email: str
    data_retention_period: str
    international_transfer_statement: str


def is_legal_content_ready() -> bool:
    """True only when a human has explicitly flipped the switch AND every
    required fact is present. Never true by omission or default.

    During the temporary production diagnostic, emit only boolean presence
    information. No environment variable values or subscriber data are logged.
    """
    switch_true = os.getenv(LEGAL_READY_ENV_VAR, "").strip().lower() == "true"
    missing = missing_operator_fields()
    ready = switch_true and not missing
    logger.warning(
        "NEWSLETTER_RUNTIME_GATE switch_true=%s contact_present=%s retention_present=%s ready=%s",
        switch_true,
        "DIGA_TRACKER_OPERATOR_CONTACT_EMAIL" not in missing,
        "DIGA_TRACKER_DATA_RETENTION_PERIOD" not in missing,
        ready,
    )
    return ready


def missing_operator_fields() -> list[str]:
    """Names of required operator env vars that are not yet set.

    Used only for internal readiness checks and operator-facing tooling
    (e.g. a CLI diagnostic) -- never rendered to a public visitor.
    """
    return [
        name for name in REQUIRED_OPERATOR_ENV_VARS if not _has_visible_content(os.getenv(name, ""))
    ]


def _has_visible_content(value: str) -> bool:
    """True if ``value`` contains at least one visually meaningful
    character.

    ``str.strip()`` alone only removes characters with the Unicode
    White_Space property. It does NOT catch invisible format characters
    such as U+200B ZERO WIDTH SPACE, U+200C/200D (ZWNJ/ZWJ), or U+FEFF
    (BOM) -- a required env var set to only such characters would pass a
    naive ``.strip()`` truthiness check while rendering as visually
    blank on the public Datenschutzerklärung page. Excluding Unicode
    category groups "C" (Other: control/format/surrogate/private-use/
    unassigned) and "Z" (Separator) closes that gap.
    """
    return any(unicodedata.category(char)[0] not in ("C", "Z") for char in value)


def load_operator_profile() -> OperatorProfile | None:
    """Return the confirmed operator profile, or None if not yet ready.

    Callers must check the return value; a None result means the caller
    must not render any operator-specific legal content.
    """
    if not is_legal_content_ready():
        return None
    return OperatorProfile(
        name=OPERATOR_NAME,
        contact_email=os.environ["DIGA_TRACKER_OPERATOR_CONTACT_EMAIL"],
        data_retention_period=os.environ["DIGA_TRACKER_DATA_RETENTION_PERIOD"],
        international_transfer_statement=INTERNATIONAL_TRANSFER_STATEMENT,
    )
