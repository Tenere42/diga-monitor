"""Operator/legal readiness gate for the public newsletter feature.

The newsletter signup form, the confirmed-subscriber alert dispatch, and
the Datenschutzerklaerung page are all gated behind ``is_legal_content_ready``.
Until every legally required operator fact below is confirmed by a human
(via environment configuration, never invented here), the entire feature
stays invisible on the public site: **no placeholder text, no partial
page, no dead link is ever shown to a visitor.** This module holds no
subscriber data of any kind.

Verantwortlicher (data controller) is confirmed as "Leevsten GmbH" by the
project owner. Every other operator fact (postal address, contact email,
commercial register entry, retention/transfer specifics) must come from
the project owner or legal counsel before the switch below can go on.
"""

from __future__ import annotations

import os
import unicodedata
from dataclasses import dataclass


OPERATOR_NAME = "Leevsten GmbH"

# The master switch. Defaults to OFF (unset/anything other than "true").
# A human sets this explicitly, and only after every field below is set
# to real, confirmed values -- never as a way to "unblock" development.
LEGAL_READY_ENV_VAR = "NEWSLETTER_LEGAL_READY"

# Every one of these must be a non-empty environment variable before the
# feature is considered ready, regardless of the switch above. This is a
# second, independent safety net: even an accidental early flip of the
# switch cannot expose the feature with missing operator facts.
REQUIRED_OPERATOR_ENV_VARS = [
    "DIGA_TRACKER_OPERATOR_ADDRESS",
    "DIGA_TRACKER_OPERATOR_CONTACT_EMAIL",
    "DIGA_TRACKER_OPERATOR_REGISTER_INFO",
    "DIGA_TRACKER_DATA_RETENTION_PERIOD",
    # The Datenschutzerklärung's international-transfer section is a
    # legally required topic (Brevo/Railway sub-processor locations and
    # transfer safeguards), not merely an operator-identity fact -- but
    # it gates the same way: a confirmed value must exist, or the whole
    # feature stays hidden. It must never render as a deferred stub
    # ("details werden ergänzt...") to a public visitor.
    "DIGA_TRACKER_INTERNATIONAL_TRANSFER_BASIS",
]


@dataclass(frozen=True)
class OperatorProfile:
    name: str
    address: str
    contact_email: str
    register_info: str
    data_retention_period: str
    international_transfer_basis: str


def is_legal_content_ready() -> bool:
    """True only when a human has explicitly flipped the switch AND every
    required operator fact is present. Never true by omission or default.
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
        address=os.environ["DIGA_TRACKER_OPERATOR_ADDRESS"],
        contact_email=os.environ["DIGA_TRACKER_OPERATOR_CONTACT_EMAIL"],
        register_info=os.environ["DIGA_TRACKER_OPERATOR_REGISTER_INFO"],
        data_retention_period=os.environ["DIGA_TRACKER_DATA_RETENTION_PERIOD"],
        international_transfer_basis=os.environ["DIGA_TRACKER_INTERNATIONAL_TRANSFER_BASIS"],
    )
