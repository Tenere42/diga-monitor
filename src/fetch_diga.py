"""Fetch real DiGA entries from the public BfArM DiGA directory."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://diga.bfarm.de"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"
TOKEN_URL = f"{BASE_URL}/api/diga-vz/tokens"
FHIR_BASE_URL = f"{BASE_URL}/api/fhir/v3.0"
DEFAULT_TIMEOUT_SECONDS = 30
FHIR_COUNT = 1000

FHIR_PROFILES = {
    "health_apps": (
        "DeviceDefinition",
        "https://fhir.bfarm.de/StructureDefinition/HealthApp",
    ),
    "catalog_entries": (
        "CatalogEntry",
        "https://fhir.bfarm.de/StructureDefinition/HealthAppCatalogEntry",
    ),
    "manufacturers": (
        "Organization",
        "https://fhir.bfarm.de/StructureDefinition/HealthAppManufacturer",
    ),
    "modules": (
        "DeviceDefinition",
        "https://fhir.bfarm.de/StructureDefinition/HealthAppModule",
    ),
    "prescription_units": (
        "ChargeItemDefinition",
        "https://fhir.bfarm.de/StructureDefinition/HealthAppPrescriptionUnit",
    ),
    "questionnaires": (
        "Questionnaire",
        "https://fhir.bfarm.de/StructureDefinition/HealthAppQuestionnaire",
    ),
    "questionnaire_responses": (
        "QuestionnaireResponse",
        "https://fhir.bfarm.de/StructureDefinition/HealthAppQuestionnaireResponse",
    ),
}


def fetch_diga_entries() -> list[dict[str, Any]]:
    """Fetch and normalize all public DiGA directory entries.

    The scraper discovers DiGA detail URLs from the public sitemap and enriches
    them with FHIR resources used by the public BfArM directory frontend.
    """
    session = build_session()
    directory_urls = discover_directory_urls(session)
    directory_ids = {directory_id_from_url(url): url for url in directory_urls}

    fhir_data = fetch_fhir_data(session)
    records = build_records(fhir_data=fhir_data, directory_ids=directory_ids)

    records_by_id = {record["id"]: record for record in records}
    for diga_id, directory_url in directory_ids.items():
        records_by_id.setdefault(
            diga_id,
            {
                "id": diga_id,
                "name": None,
                "manufacturer": None,
                "status": "unknown",
                "indication": [],
                "bfarm_directory_url": directory_url,
                "descriptive_texts": {},
                "structured_text_sections": [],
                "evidence_summary_text": None,
                "change_history": [],
                "pricing_information": [],
                "source_update_notice": {
                    "last_updated_at": None,
                    "notice_text": None,
                    "data_notice": "Wiedergabe der vom Hersteller \u00fcbermittelten Angaben",
                    "checked_sources": [],
                },
                "source": "BfArM sitemap only; no matching FHIR record found",
            },
        )

    return sorted(records_by_id.values(), key=lambda entry: entry["id"])


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/json",
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
            "Referer": f"{BASE_URL}/de/verzeichnis",
            "User-Agent": (
                "Mozilla/5.0 (compatible; DiGAChangeMonitor/1.0; "
                "+https://diga.bfarm.de)"
            ),
            "X-Locale": "de",
            "X-Tenant": "diga-vz",
        }
    )
    return session


def discover_directory_urls(session: requests.Session) -> list[str]:
    response = session.get(SITEMAP_URL, timeout=DEFAULT_TIMEOUT_SECONDS)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "xml")
    urls = []
    for loc in soup.find_all("loc"):
        url = loc.get_text(strip=True)
        if re.fullmatch(r"https://diga\.bfarm\.de/de/verzeichnis/\d{5}", url):
            urls.append(url)
    return sorted(set(urls))


def directory_id_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def fetch_fhir_data(session: requests.Session) -> dict[str, list[dict[str, Any]]]:
    token = os.getenv("DIGA_API_TOKEN") or create_public_token(session)
    fhir_session = requests.Session()
    fhir_session.headers.update(session.headers)
    fhir_session.headers.update(
        {
            "Accept": "application/fhir+json, application/json",
            "Authorization": f"Bearer {token}",
        }
    )

    return {
        key: fetch_fhir_resources(fhir_session, resource_type, profile)
        for key, (resource_type, profile) in FHIR_PROFILES.items()
    }


def create_public_token(session: requests.Session) -> str:
    response = session.post(
        TOKEN_URL,
        json={"data": {"type": "tokens", "attributes": {}}},
        headers={
            "Accept": "application/vnd.api+json",
            "Content-Type": "application/vnd.api+json",
            "X-Locale": "de",
            "X-Tenant": "diga-vz",
        },
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("data", {}).get("id")
    if not token:
        raise RuntimeError("BfArM token response did not include a token id")
    return str(token)


def fetch_fhir_resources(
    session: requests.Session,
    resource_type: str,
    profile: str,
) -> list[dict[str, Any]]:
    resources = []
    url = f"{FHIR_BASE_URL}/{resource_type}"
    params: dict[str, Any] | None = {"_count": FHIR_COUNT, "_profile": profile}

    while url:
        response = session.get(url, params=params, timeout=DEFAULT_TIMEOUT_SECONDS)
        response.raise_for_status()
        bundle = response.json()
        resources.extend(
            entry["resource"]
            for entry in bundle.get("entry", [])
            if isinstance(entry, dict) and isinstance(entry.get("resource"), dict)
        )
        url = next_bundle_link(bundle)
        params = None

    return resources


def next_bundle_link(bundle: dict[str, Any]) -> str | None:
    for link in bundle.get("link", []):
        if link.get("relation") == "next" and link.get("url"):
            return str(link["url"])
    return None


def build_records(
    fhir_data: dict[str, list[dict[str, Any]]],
    directory_ids: dict[str, str],
) -> list[dict[str, Any]]:
    manufacturers = index_by_reference(fhir_data["manufacturers"], "Organization")
    modules_by_app = group_by_reference(
        fhir_data["modules"],
        "parentDevice.reference",
    )
    prescriptions_by_module = group_prescription_units(fhir_data["prescription_units"])
    questionnaires_by_url = {
        questionnaire.get("url"): questionnaire
        for questionnaire in fhir_data["questionnaires"]
        if questionnaire.get("url")
    }
    responses_by_app = group_by_reference(
        fhir_data["questionnaire_responses"],
        "subject.reference",
    )

    records = []
    for catalog_entry in fhir_data["catalog_entries"]:
        health_app = find_health_app(catalog_entry, fhir_data["health_apps"])
        if not health_app:
            continue

        diga_id = identifier_value(health_app, "DigaId") or health_app.get("id")
        if not diga_id:
            continue
        diga_id = str(diga_id)

        app_ref = f"DeviceDefinition/{health_app.get('id')}"
        manufacturer = manufacturers.get(
            nested_value(health_app, "manufacturerReference.reference")
        )
        app_modules = modules_by_app.get(app_ref, [])
        prescription_units = [
            unit
            for module in app_modules
            for unit in prescriptions_by_module.get(f"DeviceDefinition/{module.get('id')}", [])
        ]
        questionnaire_responses = responses_by_app.get(app_ref, [])

        descriptive_texts = extract_descriptive_texts(
            health_app,
            catalog_entry,
            questionnaire_responses,
            questionnaires_by_url,
        )
        records.append(
            {
                "id": diga_id,
                "name": first_text(
                    nested_value(health_app, "deviceName.0.name"),
                    nested_value(health_app, "name"),
                    nested_value(health_app, "title"),
                ),
                "manufacturer": organization_name(manufacturer),
                "status": infer_status(catalog_entry),
                "indication": extract_indications(prescription_units),
                "bfarm_directory_url": directory_ids.get(
                    diga_id,
                    urljoin(BASE_URL, f"/de/verzeichnis/{diga_id}"),
                ),
                "descriptive_texts": descriptive_texts,
                "structured_text_sections": build_structured_text_sections(descriptive_texts),
                "evidence_summary_text": extract_evidence_summary_text(
                    questionnaire_responses,
                    questionnaires_by_url,
                ),
                "change_history": extract_change_history(catalog_entry),
                "pricing_information": extract_pricing_information(prescription_units),
                "source_update_notice": build_source_update_notice(
                    catalog_entry,
                    health_app,
                    manufacturer,
                    app_modules,
                    questionnaire_responses,
                    prescription_units,
                ),
                "raw_public_fhir": {
                    "catalog_entry_id": catalog_entry.get("id"),
                    "health_app_id": health_app.get("id"),
                    "module_ids": [module.get("id") for module in app_modules],
                    "prescription_unit_ids": [
                        unit.get("id") for unit in prescription_units
                    ],
                },
            }
        )

    return records


def find_health_app(
    catalog_entry: dict[str, Any],
    health_apps: list[dict[str, Any]],
) -> dict[str, Any] | None:
    reference = first_reference(catalog_entry)
    if reference:
        for health_app in health_apps:
            if reference == f"DeviceDefinition/{health_app.get('id')}":
                return health_app
    return None


def first_reference(resource: dict[str, Any]) -> str | None:
    for value in walk_values(resource):
        if isinstance(value, dict) and isinstance(value.get("reference"), str):
            reference = value["reference"]
            if reference.startswith("DeviceDefinition/"):
                return reference
    return None


def index_by_reference(
    resources: list[dict[str, Any]],
    resource_type: str,
) -> dict[str, dict[str, Any]]:
    return {
        f"{resource_type}/{resource.get('id')}": resource
        for resource in resources
        if resource.get("id")
    }


def identifier_value(resource: dict[str, Any], identifier_name: str) -> str | None:
    identifiers = resource.get("identifier", [])
    if not isinstance(identifiers, list):
        return None

    for identifier in identifiers:
        if not isinstance(identifier, dict):
            continue
        system = str(identifier.get("system", ""))
        if system.rstrip("/").endswith(f"/{identifier_name}"):
            value = identifier.get("value")
            return str(value).zfill(5) if value is not None else None
    return None


def group_by_reference(
    resources: Iterable[dict[str, Any]],
    reference_path: str,
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for resource in resources:
        reference = nested_value(resource, reference_path)
        if isinstance(reference, str):
            grouped.setdefault(reference, []).append(resource)
    return grouped


def group_prescription_units(
    prescription_units: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for unit in prescription_units:
        for reference in references_in_resource(unit, "DeviceDefinition/"):
            grouped.setdefault(reference, []).append(unit)
    return grouped


def references_in_resource(resource: dict[str, Any], prefix: str) -> set[str]:
    references = set()
    for value in walk_values(resource):
        if isinstance(value, dict) and isinstance(value.get("reference"), str):
            reference = value["reference"]
            if reference.startswith(prefix):
                references.add(reference)
    return references


def infer_status(catalog_entry: dict[str, Any]) -> str:
    text = " ".join(str(value) for value in walk_values(catalog_entry)).lower()
    if "dauerhaft" in text or "permanent" in text:
        return "listed"
    if "vorl\u00e4ufig" in text or "vorlaeufig" in text or "provisional" in text:
        return "provisional"
    if "gestrichen" in text or "entfernt" in text or "removed" in text:
        return "removed"
    if nested_value(catalog_entry, "validityPeriod.end"):
        return "removed"
    return "listed"


def extract_indications(prescription_units: list[dict[str, Any]]) -> list[str]:
    indications = []
    for unit in prescription_units:
        for coding in coding_values(unit):
            code = str(coding.get("code") or "")
            if not re.match(r"^[A-Z]\d", code):
                continue
            text = " ".join(
                value
                for value in [code, coding.get("display")]
                if value
            )
            if text and text not in indications:
                indications.append(text)
    return indications


def extract_descriptive_texts(
    health_app: dict[str, Any],
    catalog_entry: dict[str, Any],
    questionnaire_responses: list[dict[str, Any]],
    questionnaires_by_url: dict[str, dict[str, Any]],
) -> dict[str, str]:
    texts: dict[str, str] = {}

    for key, value in string_leaves(health_app):
        if is_public_description_key(key, value):
            texts[f"health_app.{key}"] = clean_text(value)

    for key, value in string_leaves(catalog_entry):
        if is_public_description_key(key, value):
            texts[f"catalog_entry.{key}"] = clean_text(value)

    for response in questionnaire_responses:
        questionnaire = questionnaires_by_url.get(response.get("questionnaire"))
        question_labels = question_text_by_link_id(questionnaire) if questionnaire else {}
        for answer in questionnaire_answers(response):
            label = question_labels.get(answer["link_id"], answer["link_id"])
            if answer["text"]:
                texts[f"questionnaire.{label}"] = clean_text(answer["text"])

    return dict(sorted(texts.items()))


def extract_evidence_summary_text(
    questionnaire_responses: list[dict[str, Any]],
    questionnaires_by_url: dict[str, dict[str, Any]],
) -> str | None:
    evidence_parts = []
    evidence_keywords = (
        "evidenz",
        "versorgungseffekt",
        "studie",
        "nachweis",
        "evaluation",
        "endpunkt",
    )
    for response in questionnaire_responses:
        questionnaire = questionnaires_by_url.get(response.get("questionnaire"))
        question_labels = question_text_by_link_id(questionnaire) if questionnaire else {}
        for answer in questionnaire_answers(response):
            label = question_labels.get(answer["link_id"], answer["link_id"])
            label_lower = label.lower()
            if is_steckbrief_question(label_lower):
                continue
            if any(keyword in label_lower for keyword in evidence_keywords):
                evidence_parts.append(f"{label}: {answer['text']}")

    if not evidence_parts:
        return None
    return clean_text("\n\n".join(evidence_parts))


def is_steckbrief_question(label_lower: str) -> bool:
    return "steckbrief" in label_lower


def build_structured_text_sections(descriptive_texts: dict[str, str]) -> list[dict[str, str]]:
    sections = []
    for field_path, text in sorted(descriptive_texts.items()):
        context = structural_context_from_field_path(field_path)
        sections.append(
            {
                "field_path": f"descriptive_texts.{field_path}",
                "stable_key": stable_text_key("descriptive_texts", field_path, context),
                "main_section": context["main_section"],
                "tab_label": context["main_section"],
                "accordion_title": context["section_title"],
                "source_area_label": context["main_section"],
                "section_title": context["section_title"],
                "subsection_title": context["subsection_title"],
                "question_label": context["question_label"],
                "field_label": context["field_label"],
                "display_path": context["display_path"],
                "localization_confidence": context["localization_confidence"],
                "raw_text": text,
                "text": text,
            }
        )
    return sections


def structural_context_from_field_path(field_path: str) -> dict[str, str]:
    label = text_label_from_field_path(field_path)
    main_section = main_section_from_field_path(field_path, label)
    subsection_title = label if label else "Nicht eindeutig zugeordneter Textabschnitt"
    display_path = " > ".join(
        part
        for part in (main_section, subsection_title)
        if part and part != "Nicht eindeutig zugeordneter Textabschnitt"
    )
    if not display_path:
        display_path = "Nicht eindeutig zugeordneter Textabschnitt"
    return {
        "main_section": main_section,
        "section_title": main_section,
        "subsection_title": subsection_title,
        "question_label": label,
        "field_label": label,
        "display_path": display_path,
        "localization_confidence": "high" if label else "low",
    }


def text_label_from_field_path(field_path: str) -> str:
    if field_path.startswith("questionnaire."):
        return field_path.removeprefix("questionnaire.")
    return field_path.split(".", 1)[-1].replace("_", " ")


def main_section_from_field_path(field_path: str, label: str) -> str:
    if field_path.startswith("questionnaire."):
        return section_from_question_label(label)
    if field_path.startswith(("health_app.", "catalog_entry.")):
        return "Beschreibung der DiGA"
    return "Nicht eindeutig zugeordneter Textabschnitt"


def section_from_question_label(label: str) -> str:
    normalized = label.lower()
    if any(
        marker in normalized
        for marker in (
            "versorgungseffekt",
            "nachweis",
            "pico",
            "studie",
            "studiendesign",
            "erprobungszeitraum",
            "medizinischer nutzen",
            "patientenrelevante struktur",
        )
    ):
        return "Informationen zum positiven Versorgungseffekt"
    if any(marker in normalized for marker in ("datenschutz", "datensicherheit", "datenverarbeitung")):
        return "Informationen zu Datenschutz und Datensicherheit"
    if any(marker in normalized for marker in ("zweckbestimmung", "zielsetzung", "wirkungsweise", "inhalt", "nutzung")):
        return "Weitere Informationen zur digitalen Gesundheitsanwendung"
    if any(marker in normalized for marker in ("preis", "kosten", "vergütung")):
        return "Weitere Informationen"
    return "Beschreibung der DiGA"


def stable_text_key(root: str, field_path: str, context: dict[str, str]) -> str:
    parts = [
        root,
        context.get("main_section", ""),
        context.get("section_title", ""),
        context.get("question_label", ""),
        field_path,
    ]
    return "|".join(normalize_stable_key_part(part) for part in parts if part)


def normalize_stable_key_part(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def extract_change_history(catalog_entry: dict[str, Any]) -> list[dict[str, Any]]:
    history = []
    history_extension = extension_by_url(
        catalog_entry,
        "https://fhir.bfarm.de/StructureDefinition/HealthAppCatalogEntryHistory",
    )
    if not history_extension:
        return history

    for entry in child_extensions(history_extension, "entry"):
        fields = extension_fields(entry)
        title = first_text(
            nested_value(fields, "title.valueString"),
            nested_value(fields, "type.valueCoding.display"),
            nested_value(fields, "type.valueCoding.code"),
        )
        remark = first_text(nested_value(fields, "remark.valueString"))
        history.append(
            {
                "date": first_text(nested_value(fields, "date.valueDateTime")),
                "title": title,
                "type": nested_value(fields, "type.valueCoding.code"),
                "type_display": nested_value(fields, "type.valueCoding.display"),
                "remark": remark,
                "text": clean_text(
                    " ".join(
                        value
                        for value in [
                            first_text(nested_value(fields, "date.valueDateTime")),
                            title,
                            remark,
                        ]
                        if value
                    )
                ),
            }
        )

    return history


def extract_pricing_information(
    prescription_units: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    prices = []
    for unit in prescription_units:
        price = {
            "title": unit.get("title"),
            "effective_period": unit.get("effectivePeriod"),
            "price_components": unit.get("propertyGroup")
            or unit.get("priceComponent")
            or [],
        }
        text_values = [
            value
            for _, value in string_leaves(unit)
            if "\u20ac" in value or "EUR" in value.upper() or "preis" in value.lower()
        ]
        if text_values:
            price["text"] = sorted(set(clean_text(value) for value in text_values))
        prices.append(price)
    return prices


def build_source_update_notice(
    catalog_entry: dict[str, Any],
    health_app: dict[str, Any],
    manufacturer: dict[str, Any] | None,
    app_modules: list[dict[str, Any]],
    questionnaire_responses: list[dict[str, Any]],
    prescription_units: list[dict[str, Any]],
) -> dict[str, Any]:
    candidates = [
        ("catalog_entry", nested_value(catalog_entry, "meta.lastUpdated")),
        ("health_app", nested_value(health_app, "meta.lastUpdated")),
        (
            "manufacturer",
            nested_value(manufacturer, "meta.lastUpdated") if manufacturer else None,
        ),
    ]
    candidates.extend(
        (f"module.{module.get('id')}", nested_value(module, "meta.lastUpdated"))
        for module in app_modules
    )
    candidates.extend(
        (
            f"questionnaire_response.{response.get('id')}",
            nested_value(response, "meta.lastUpdated"),
        )
        for response in questionnaire_responses
    )
    candidates.extend(
        (
            f"prescription_unit.{unit.get('id')}",
            nested_value(unit, "meta.lastUpdated"),
        )
        for unit in prescription_units
    )

    dated_candidates = [
        {"source": source, "last_updated": str(last_updated)}
        for source, last_updated in candidates
        if last_updated
    ]
    latest = max(
        (candidate["last_updated"] for candidate in dated_candidates),
        default=None,
    )

    return {
        "last_updated_at": latest,
        "notice_text": format_source_update_notice(latest),
        "data_notice": "Wiedergabe der vom Hersteller \u00fcbermittelten Angaben",
        "checked_sources": sorted(
            dated_candidates,
            key=lambda candidate: candidate["last_updated"],
            reverse=True,
        ),
    }


def format_source_update_notice(last_updated: str | None) -> str | None:
    if not last_updated:
        return None
    try:
        parsed = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.astimezone()
        return f"Zuletzt aktualisiert am {parsed:%d.%m.%Y} um {parsed:%H:%M}"
    except ValueError:
        return f"Zuletzt aktualisiert am {last_updated}"


def organization_name(organization: dict[str, Any] | None) -> str | None:
    if not organization:
        return None
    return first_text(organization.get("name"), organization.get("alias"))


def extension_by_url(resource: dict[str, Any], url: str) -> dict[str, Any] | None:
    for extension in resource.get("extension", []):
        if isinstance(extension, dict) and extension.get("url") == url:
            return extension
    return None


def child_extensions(resource: dict[str, Any], url: str) -> list[dict[str, Any]]:
    return [
        extension
        for extension in resource.get("extension", [])
        if isinstance(extension, dict) and extension.get("url") == url
    ]


def extension_fields(resource: dict[str, Any]) -> dict[str, dict[str, Any]]:
    fields = {}
    for extension in resource.get("extension", []):
        if isinstance(extension, dict) and extension.get("url"):
            fields[str(extension["url"])] = extension
    return fields


def questionnaire_answers(resource: dict[str, Any]) -> list[dict[str, str]]:
    answers = []
    for item in flatten_items(resource.get("item", [])):
        link_id = str(item.get("linkId") or "unknown")
        values = []
        for answer in item.get("answer", []):
            values.extend(extract_answer_values(answer))
        text = clean_text(" ".join(values))
        if text:
            answers.append({"link_id": link_id, "text": text})
    return answers


def question_text_by_link_id(questionnaire: dict[str, Any] | None) -> dict[str, str]:
    if not questionnaire:
        return {}
    labels = {}
    for item in flatten_items(questionnaire.get("item", [])):
        if item.get("linkId") and item.get("text"):
            labels[str(item["linkId"])] = clean_text(str(item["text"]))
    return labels


def flatten_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened = []
    for item in items:
        flattened.append(item)
        flattened.extend(flatten_items(item.get("item", [])))
    return flattened


def extract_answer_values(answer: dict[str, Any]) -> list[str]:
    values = []
    for key, value in answer.items():
        if key.startswith("value"):
            if isinstance(value, str):
                values.append(value)
            elif isinstance(value, (int, float, bool)):
                values.append(str(value))
            elif isinstance(value, dict):
                values.extend(
                    str(part)
                    for part in [
                        value.get("text"),
                        value.get("display"),
                        nested_value(value, "coding.0.display"),
                        nested_value(value, "coding.0.code"),
                    ]
                    if part
                )
    return values


def coding_values(resource: Any) -> list[dict[str, Any]]:
    codings = []
    if isinstance(resource, dict):
        if "code" in resource and "display" in resource:
            codings.append(resource)
        if isinstance(resource.get("coding"), list):
            codings.extend(
                coding for coding in resource["coding"] if isinstance(coding, dict)
            )
        for value in resource.values():
            codings.extend(coding_values(value))
    elif isinstance(resource, list):
        for value in resource:
            codings.extend(coding_values(value))
    return codings


def string_leaves(resource: Any, path: str = "") -> list[tuple[str, str]]:
    leaves = []
    if isinstance(resource, dict):
        for key, value in resource.items():
            child_path = f"{path}.{key}" if path else key
            leaves.extend(string_leaves(value, child_path))
    elif isinstance(resource, list):
        for index, value in enumerate(resource):
            leaves.extend(string_leaves(value, f"{path}.{index}"))
    elif isinstance(resource, str):
        leaves.append((path, resource))
    return leaves


def is_public_description_key(key: str, value: str) -> bool:
    if len(value.strip()) < 40:
        return False
    key_lower = key.lower()
    return any(
        marker in key_lower
        for marker in (
            "description",
            "summary",
            "summaries",
            "steckbrief",
            "text",
            "subtitle",
            "information",
            "purpose",
            "effect",
        )
    )


def walk_values(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_values(child)


def nested_value(resource: Any, path: str) -> Any:
    value = resource
    for part in path.split("."):
        if isinstance(value, list) and part.isdigit():
            index = int(part)
            value = value[index] if index < len(value) else None
        elif isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return clean_text(value)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    return clean_text(item)
    return None


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
