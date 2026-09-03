"""Operator/legal readiness gate for the public newsletter feature.

The newsletter signup form, the confirmed-subscriber alert dispatch, and
the Datenschutzerklaerung page are all gated behind ``is_legal_content_ready``.
Until every legally required fact below is confirmed (either by a human
via environment configuration, or -- for the international-transfer
statement -- sourced from the payment/hosting providers' own published
documentation, never invented here), the entire feature stays invisible
on the public site: **no placeholder text, no partial page, no dead
link is ever shown to a visitor.** This module holds no subscriber data
of any kind.

Verantwortlicher (data controller) is confirmed as "Leevsten GmbH" by the
project owner.

Minimal-disclosure principle (explicit project decision, see
docs/legal-notes.md): this module requires only what has an identified
legal basis, and nothing more. In particular:

- A postal/street address is intentionally NOT required and NOT
  collected here. Under the Swiss revDSG baseline this project uses
  (Art. 19 DSG: "Identität und Kontaktdaten des Verantwortlichen"),
  contact data does not have to mean a physical address -- a reachable
  contact email is sufficient contact data for a privacy notice. A
  German-style Impressum (which typically does require a postal
  address) is explicitly out of scope for this project (see
  docs/legal-notes.md) as a non-commercial Swiss information offering.
  Do not add an address field back without first re-establishing that a
  concrete legal duty requires one -- the project owner's address is
  also their private residential address and must not be published
  without that established necessity.
- Commercial register information is intentionally NOT required and NOT
  collected here for the same reason: it is an Impressum-style
  identification duty, not a DSG Art. 19 privacy-notice requirement.
- The international-transfer statement is NOT collected as free-form
  human input (a prior version of this gate did that and was corrected
  after review). Instead it is a fixed, sourced statement below, based
  on the two vendors this feature actually uses -- Brevo (email/DOI
  delivery) and Railway (hosting) -- and their own published Data
  Processing Agreements/documentation. See docs/legal-notes.md for the
  exact sources and the date they were checked. If those vendors'
  terms change, this statement must be re-verified and updated, not
  just re-confirmed by a human typing a new sentence.
"""

from __future__ import annotations

import os
import unicodedata
from dataclasses import dataclass


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
    """
    if os.getenv(LEGAL_READY_ENV_VAR, "").strip().lower() != "true":
        return False
    return not missing_operator_fields()


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
