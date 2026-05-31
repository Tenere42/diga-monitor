"""Generate safe simulated DiGA change events for dashboard and email testing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.change_events import save_change_events, word_level_diff
from src.change_events import classify_text_change
from src.diff import display_name, entry_identity
from src.notifications import build_email_body, log_notification
from src.snapshot import DEFAULT_SNAPSHOT_DIR, latest_snapshot_paths, load_snapshot


DEFAULT_SIMULATION_REPORT_PATH = Path("outputs/simulation_report.md")

REMOVED_SENTENCE = "Für die DiGA konnte kein positiver Versorgungseffekt nachgewiesen werden."

CATEGORY_STATUS = "Aufnahme und Status"
CATEGORY_TEXT = "Texte und Bewertung"
CATEGORY_PRICE = "Verordnung und Preis"
CATEGORY_ORG = "Technische und organisatorische Angaben"
CATEGORY_LINKS = "Plattformen und Links"
CATEGORY_OTHER = "Sonstige Felder"


@dataclass(frozen=True)
class SimulationScenario:
    key: str
    title: str
    category: str
    change_type: str
    changed_field: str
    user_facing_field_label: str
    previous_value: Any
    new_value: Any
    summary_de: str


def run_simulation(
    selection: str,
    notify: bool = False,
    dry_run: bool = False,
    snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR,
) -> tuple[list[dict[str, Any]], Path | None]:
    if notify and not dry_run:
        raise ValueError("Simulation notifications are dry-run only. Add --dry-run.")

    entry, previous_timestamp, current_timestamp = load_simulation_context(snapshot_dir)
    scenarios = select_scenarios(selection)
    detected_at = datetime.now(timezone.utc).isoformat()
    events = [
        scenario_to_event(scenario, entry, detected_at, previous_timestamp, current_timestamp)
        for scenario in scenarios
    ]
    output_path = save_change_events(events, detected_at=detected_at)
    write_simulation_report(events, output_path)

    if notify:
        subject = f"DiGA Watch: {len(events)} Änderung(en) erkannt"
        print()
        print("Dry-run: email would be sent with this content:")
        print()
        print("To: (Simulation, kein SMTP-Versand)")
        print(f"Subject: {subject}")
        print()
        print(build_email_body(events, dashboard_url_from_env()))
        log_notification(
            recipient="(Simulation, kein SMTP-Versand)",
            number_of_changes=len(events),
            subject=subject,
            status="skipped",
            error_message="Simulation dry-run: email not sent.",
        )

    return events, output_path


def load_simulation_context(snapshot_dir: Path) -> tuple[dict[str, Any], str, str]:
    paths = latest_snapshot_paths(snapshot_dir, limit=2)
    if not paths:
        raise ValueError("No real snapshot found. Run `py -m src.main run` first.")
    current_snapshot = load_snapshot(paths[-1])
    previous_snapshot = load_snapshot(paths[-2]) if len(paths) > 1 else current_snapshot
    entry = find_orthopy_entry(current_snapshot.entries) or current_snapshot.entries[0]
    return entry, previous_snapshot.created_at, current_snapshot.created_at


def find_orthopy_entry(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    for entry in entries:
        if "orthopy" in str(entry.get("name", "")).lower():
            return entry
    return None


def select_scenarios(selection: str) -> list[SimulationScenario]:
    scenarios = all_scenarios()
    aliases = {
        "all": "all-page-fields",
        "all-page-fields": "all-page-fields",
        "text-change": "bfarm-assessment-text-change",
        "price-change": "price-change",
        "status-change": "status-change",
        "new-diga": "new-diga",
        "removed-diga": "removed-diga",
        "study-evidence": "study-evidence-change",
        "study-evidence-change": "study-evidence-change",
    }
    normalized = aliases.get(selection, selection)
    if normalized == "all-page-fields":
        return scenarios
    matches = [scenario for scenario in scenarios if scenario.key == normalized]
    if not matches:
        valid = ", ".join(sorted({"all", "all-page-fields", *aliases, *(s.key for s in scenarios)}))
        raise ValueError(f"Unknown simulation scenario '{selection}'. Valid values: {valid}")
    return matches


def scenario_to_event(
    scenario: SimulationScenario,
    entry: dict[str, Any],
    detected_at: str,
    previous_snapshot_timestamp: str,
    current_snapshot_timestamp: str,
) -> dict[str, Any]:
    diga_id = entry_identity(entry, "unknown")
    diga_name = display_name(entry)
    manufacturer = entry.get("manufacturer")
    bfarm_directory_url = entry.get("bfarm_directory_url")
    if scenario.change_type == "new_diga" and isinstance(scenario.new_value, dict):
        diga_id = str(scenario.new_value.get("id") or "SIM-NEW-DIGA")
        diga_name = str(scenario.new_value.get("name") or "Neue Test-DiGA")
        manufacturer = scenario.new_value.get("manufacturer") or "Testhersteller GmbH"
        bfarm_directory_url = scenario.new_value.get("bfarm_directory_url") or "https://diga.bfarm.de/de/verzeichnis/simulation"
    elif scenario.change_type == "removed_diga" and isinstance(scenario.previous_value, dict):
        diga_id = str(scenario.previous_value.get("id") or diga_id)
        diga_name = str(scenario.previous_value.get("name") or diga_name)
        manufacturer = scenario.previous_value.get("manufacturer") or manufacturer
        bfarm_directory_url = scenario.previous_value.get("bfarm_directory_url") or bfarm_directory_url

    event = {
        "detected_at": detected_at,
        "diga_id": diga_id,
        "diga_name": diga_name,
        "manufacturer": manufacturer,
        "bfarm_directory_url": bfarm_directory_url,
        "change_type": scenario.change_type,
        "changed_field": scenario.changed_field,
        "field_name": scenario.changed_field,
        "user_facing_field_label": scenario.user_facing_field_label,
        "previous_value": scenario.previous_value,
        "new_value": scenario.new_value,
        "before_value": scenario.previous_value,
        "after_value": scenario.new_value,
        "previous_snapshot_timestamp": previous_snapshot_timestamp,
        "current_snapshot_timestamp": current_snapshot_timestamp,
        "summary_de": scenario.summary_de,
        "simulated": True,
        "simulation_name": scenario.key,
        "simulation_category": scenario.category,
    }
    if scenario.change_type == "text_change" and isinstance(scenario.previous_value, str) and isinstance(scenario.new_value, str):
        event["word_diff"] = word_level_diff(scenario.previous_value, scenario.new_value)
        event["text_change_kind"] = classify_text_change(event["word_diff"])
        event["previous_excerpt"] = compact_excerpt(scenario.previous_value)
        event["new_excerpt"] = compact_excerpt(scenario.new_value)
    return event


def all_scenarios() -> list[SimulationScenario]:
    long_text_after = (
        "Zielsetzung, Wirkungsweise, Inhalt und Nutzung der digitalen Gesundheitsanwendung: "
        "Die Orthopy App unterstützt Patientinnen und Patienten bei Knieverletzungen."
    )
    long_text_before = f"{REMOVED_SENTENCE} {long_text_after}"
    return [
        s("new-diga", "Neue DiGA", CATEGORY_STATUS, "new_diga", "<entry>", "Name der DiGA", None, {"id": "SIM-NEW-DIGA", "name": "Neue Test-DiGA", "manufacturer": "Testhersteller GmbH", "status": "Vorläufig aufgenommen", "bfarm_directory_url": "https://diga.bfarm.de/de/verzeichnis/simulation"}, "Eine neue DiGA wurde aufgenommen."),
        s("removed-diga", "Nicht mehr gefunden", CATEGORY_STATUS, "removed_diga", "<entry>", "Name der DiGA", {"id": "00902", "name": "Orthopy bei Knieverletzungen", "manufacturer": "Orthopy Health GmbH", "status": "Dauerhaft aufgenommen", "bfarm_directory_url": "https://diga.bfarm.de/de/verzeichnis/00902"}, None, "Eine DiGA ist im aktuellen Verzeichnis nicht mehr vorhanden."),
        s("status-change", "Statusänderung", CATEGORY_STATUS, "status_change", "status", "Aufnahmestatus", "Vorläufig aufgenommen", "Dauerhaft aufgenommen", "Der Aufnahmestatus wurde von 'Vorläufig aufgenommen' auf 'Dauerhaft aufgenommen' geändert."),
        s("status-delisted-change", "Statusänderung zu gestrichen", CATEGORY_STATUS, "status_change", "status", "Aufnahmestatus", "Dauerhaft aufgenommen", "Gestrichen", "Der Aufnahmestatus wurde von 'Dauerhaft aufgenommen' auf 'Gestrichen' geändert."),
        s("name-change", "Namensänderung", CATEGORY_STATUS, "other_field_change", "name", "Name der DiGA", "Orthopy", "Orthopy bei Knieverletzungen", "Der Name der DiGA wurde geändert."),
        s("manufacturer-change", "Herstelleränderung", CATEGORY_ORG, "other_field_change", "manufacturer", "Hersteller", "Orthopy GmbH", "Orthopy Health GmbH", "Der Hersteller wurde geändert."),
        s("manufacturer-website-change", "Herstellerlink geändert", CATEGORY_LINKS, "other_field_change", "manufacturer_website", "Herstellerlink / Website", "https://old.example.test", "https://orthopy.health", "Der Herstellerlink wurde geändert."),
        s("bfarm-url-change", "BfArM URL geändert", CATEGORY_LINKS, "other_field_change", "bfarm_directory_url", "BfArM-Verzeichniseintrag", "https://diga.bfarm.de/de/verzeichnis/old", "https://diga.bfarm.de/de/verzeichnis/00902", "Der BfArM-Verzeichniseintrag wurde geändert."),
        s("description-change", "Beschreibung geändert", CATEGORY_TEXT, "text_change", "descriptive_texts.description", "Beschreibung der DiGA", "Die DiGA unterstützt die Rehabilitation.", "Die DiGA unterstützt die Rehabilitation nach Knieverletzungen.", "Im Abschnitt 'Beschreibung der DiGA' wurde Text ergänzt."),
        s("bfarm-assessment-text-change", "Bewertungstext geändert", CATEGORY_TEXT, "text_change", "evidence_summary_text", "Bewertungsentscheidung des BfArM", long_text_before, long_text_after, "Im Abschnitt 'Bewertungsentscheidung des BfArM' wurde ein Textabschnitt entfernt."),
        s("positive-effect-change", "Positiver Versorgungseffekt geändert", CATEGORY_TEXT, "text_change", "descriptive_texts.positive_healthcare_effect", "Nachweis positiver Versorgungseffekt", "Medizinischer Nutzen", "Medizinischer Nutzen und verbesserte Lebensqualität", "Im Abschnitt 'Nachweis positiver Versorgungseffekt' wurde Text ergänzt."),
        s("study-evidence-change", "Studienangaben geändert", CATEGORY_TEXT, "text_change", "descriptive_texts.study_evidence", "Studienangaben / Evidenz", "RCT mit 80 Teilnehmenden.", "RCT mit 120 Teilnehmenden.", "Die Formulierung im Abschnitt 'Studienangaben / Evidenz' wurde angepasst."),
        s("indication-change", "Indikation geändert", CATEGORY_PRICE, "other_field_change", "indication", "Anwendungsgebiet / Indikation", ["M23.2"], ["M23.2", "S83.2"], "Anwendungsgebiet oder ICD-Codes wurden geändert."),
        s("target-group-change", "Zielgruppe geändert", CATEGORY_TEXT, "text_change", "descriptive_texts.target_group", "Zielgruppe", "Erwachsene Patientinnen und Patienten.", "Erwachsene Patientinnen und Patienten mit Knieverletzungen.", "Im Abschnitt 'Zielgruppe' wurde Text ergänzt."),
        s("contraindication-change", "Kontraindikationen geändert", CATEGORY_TEXT, "text_change", "descriptive_texts.contraindications", "Kontraindikationen", "Keine bekannten Kontraindikationen.", "Akute Infektionen sind ausgeschlossen.", "Kontraindikationen wurden geändert."),
        s("age-group-change", "Altersgruppe geändert", CATEGORY_ORG, "other_field_change", "age_group", "Altersgruppe", "18 bis 65 Jahre", "18 bis 70 Jahre", "Die Altersgruppe wurde geändert."),
        s("gender-change", "Anwendbarkeit geändert", CATEGORY_ORG, "other_field_change", "gender_applicability", "Anwendbar für", "Alle Geschlechter", "Frauen und Männer", "Die Anwendbarkeit nach Geschlecht wurde geändert."),
        s("platform-change", "Plattform ergänzt", CATEGORY_LINKS, "other_field_change", "platforms", "Plattformen", ["iOS", "Android"], ["iOS", "Android", "Web"], "Im Abschnitt 'Plattformen' wurde eine Plattform ergänzt."),
        s("platform-removed-change", "Plattform entfernt", CATEGORY_LINKS, "other_field_change", "platforms", "Plattformen", ["iOS", "Android", "Web"], ["iOS", "Android"], "Im Abschnitt 'Plattformen' wurde eine Plattform entfernt."),
        s("app-store-link-change", "App Store Link geändert", CATEGORY_LINKS, "other_field_change", "links.app_store", "App Store Link", "https://apps.apple.com/old", "https://apps.apple.com/app/orthopy", "Der App Store Link wurde geändert."),
        s("google-play-link-change", "Google Play Link geändert", CATEGORY_LINKS, "other_field_change", "links.google_play", "Google Play Store Link", "https://play.google.com/old", "https://play.google.com/store/apps/details?id=orthopy", "Der Google Play Store Link wurde geändert."),
        s("web-app-link-change", "Webanwendung Link geändert", CATEGORY_LINKS, "other_field_change", "links.web_app", "Webanwendung Link", None, "https://app.orthopy.health", "Der Webanwendung-Link wurde geändert."),
        s("pzn-change", "PZN geändert", CATEGORY_PRICE, "other_field_change", "prescription_units.pzn", "PZN / Verordnungseinheit", "12345678", "87654321", "PZN oder Verordnungseinheit wurde geändert."),
        s("prescription-unit-change", "Verordnungseinheit geändert", CATEGORY_PRICE, "other_field_change", "prescription_units", "Verordnungseinheit", "90 Tage", "120 Tage", "Die Verordnungseinheit wurde geändert."),
        s("price-change", "Preis geändert", CATEGORY_PRICE, "price_change", "pricing_information", "Vergütung / Preisangaben", "589,00 €", "649,00 €", "Die Preisangabe wurde von 589,00 € auf 649,00 € geändert."),
        s("duration-change", "Anwendungsdauer geändert", CATEGORY_PRICE, "other_field_change", "descriptive_texts.application_duration", "Anwendungsdauer", "14 Wochen", "16 Wochen", "Die Anwendungsdauer wurde geändert."),
        s("required-services-change", "Ärztliche Leistungen geändert", CATEGORY_PRICE, "text_change", "descriptive_texts.required_medical_services", "Erforderliche ärztliche Leistungen", "Keine zusätzlichen Leistungen erforderlich.", "Ärztliche Verlaufskontrolle empfohlen.", "Erforderliche ärztliche Leistungen wurden geändert."),
        s("additional-services-change", "Zusätzliche Leistungen geändert", CATEGORY_PRICE, "text_change", "descriptive_texts.additional_services", "Zusätzliche Leistungen", "Keine zusätzlichen Leistungen.", "Optionaler technischer Support wurde ergänzt.", "Zusätzliche Leistungen wurden geändert."),
        s("medical-device-change", "Medizinprodukt geändert", CATEGORY_ORG, "other_field_change", "medical_device_information", "Medizinproduktangaben", "Medizinprodukt Version 1.0", "Medizinprodukt Version 1.1", "Medizinproduktangaben wurden geändert."),
        s("risk-class-change", "Risikoklasse geändert", CATEGORY_ORG, "other_field_change", "risk_class", "Risikoklasse", "I", "IIa", "Die Risikoklasse wurde geändert."),
        s("ce-change", "CE geändert", CATEGORY_ORG, "other_field_change", "conformity_information", "Konformität / CE", "CE gültig bis 2026", "CE gültig bis 2027", "Konformitäts- oder CE-Angaben wurden geändert."),
        s("data-protection-change", "Datenschutz geändert", CATEGORY_ORG, "text_change", "descriptive_texts.data_protection", "Datenschutz", "Daten werden in der EU verarbeitet.", "Daten werden ausschließlich in Deutschland verarbeitet.", "Datenschutzangaben wurden geändert."),
        s("security-change", "Informationssicherheit geändert", CATEGORY_ORG, "text_change", "descriptive_texts.information_security", "Informationssicherheit", "Penetrationstest durchgeführt.", "Penetrationstest und Audit durchgeführt.", "Angaben zur Informationssicherheit wurden geändert."),
        s("interoperability-change", "Interoperabilität geändert", CATEGORY_ORG, "text_change", "descriptive_texts.interoperability", "Interoperabilität", "PDF-Export verfügbar.", "PDF- und MIO-Export verfügbar.", "Interoperabilitätsangaben wurden geändert."),
        s("accessibility-change", "Barrierefreiheit geändert", CATEGORY_ORG, "text_change", "descriptive_texts.accessibility", "Barrierefreiheit", "Barrierearme Nutzung möglich.", "Barrierearme Nutzung und Screenreader-Unterstützung möglich.", "Barrierefreiheitsangaben wurden geändert."),
        s("language-change", "Sprachen geändert", CATEGORY_ORG, "other_field_change", "languages", "Sprachen", ["Deutsch"], ["Deutsch", "Englisch"], "Sprachen wurden geändert."),
        s("module-change", "Module geändert", CATEGORY_TEXT, "text_change", "modules", "Module / Funktionsumfang", "Trainingsmodul verfügbar.", "Trainings- und Edukationsmodul verfügbar.", "Die Formulierung im Abschnitt 'Module / Funktionsumfang' wurde angepasst."),
        s("source-update-notice-change", "Aktualisierungshinweis geändert", CATEGORY_OTHER, "other_field_change", "source_update_notice.notice_text", "Aktualisierungshinweis im DiGA-Verzeichnis", "Zuletzt aktualisiert am 01.05.2026 um 09:00", "Zuletzt aktualisiert am 31.05.2026 um 12:00", "Der Aktualisierungshinweis wurde geändert."),
        s("last-updated-change", "Zeitstempel geändert", CATEGORY_OTHER, "other_field_change", "source_update_notice.last_updated_at", "Zuletzt aktualisiert", "2026-05-01T09:00:00+02:00", "2026-05-31T12:00:00+02:00", "Der Zeitstempel der letzten Aktualisierung wurde geändert."),
        s("raw-fhir-change", "Raw FHIR geändert", CATEGORY_OTHER, "other_field_change", "raw_public_fhir.meta.versionId", "Sonstige Änderung im BfArM-Datensatz", "1", "2", "Ein nicht gemapptes Feld im BfArM-Datensatz wurde geändert."),
    ]


def s(
    key: str,
    title: str,
    category: str,
    change_type: str,
    changed_field: str,
    user_facing_field_label: str,
    previous_value: Any,
    new_value: Any,
    summary_de: str,
) -> SimulationScenario:
    return SimulationScenario(
        key=key,
        title=title,
        category=category,
        change_type=change_type,
        changed_field=changed_field,
        user_facing_field_label=user_facing_field_label,
        previous_value=previous_value,
        new_value=new_value,
        summary_de=summary_de,
    )


def compact_excerpt(value: str) -> str:
    words = value.split()
    if len(words) <= 36:
        return value
    return " ".join(words[:36]) + " ..."


def write_simulation_report(events: list[dict[str, Any]], event_file: Path | None) -> None:
    DEFAULT_SIMULATION_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Simulation Report",
        "",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"Event file generated: {event_file or 'None'}",
        "",
        "| Scenario | Category | Change type | Expected dashboard display | Expected email summary | Pass/Fail |",
        "|---|---|---|---|---|---|",
    ]
    for event in events:
        lines.append(
            "| {scenario} | {category} | {change_type} | {display} | {summary} | TODO |".format(
                scenario=event.get("simulation_name"),
                category=event.get("simulation_category"),
                change_type=event.get("change_type"),
                display=f"{event.get('user_facing_field_label')}: {event.get('summary_de')}",
                summary=event.get("summary_de"),
            )
        )
    DEFAULT_SIMULATION_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def dashboard_url_from_env() -> str:
    import os

    return os.getenv("DASHBOARD_URL", "")
