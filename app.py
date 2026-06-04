"""Streamlit change-feed dashboard for DiGA directory changes."""

from __future__ import annotations

import html
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import streamlit as st

from src.change_events import DEFAULT_CHANGES_DIR, load_change_events
from src.scan_history import load_scan_history


TRACKING_START_DATE = date(2026, 5, 31)
DISPLAY_TIMEZONE = ZoneInfo("Europe/Berlin")
SNAPSHOT_DIR = Path("data/snapshots")
SNAPSHOT_FILENAME_PREFIX = "diga_snapshot_"
SNAPSHOT_FILENAME_SUFFIX = ".json"

CHANGE_LABELS = {
    "new_diga": "Neue DiGA",
    "removed_diga": "Nicht mehr gefunden",
    "status_change": "Statusänderung",
    "text_change": "Textänderung",
    "price_change": "Preisänderung",
    "other_field_change": "Sonstige Feldänderung",
}

FIELD_LABELS = {
    "evidence_summary_text": "Bewertungsentscheidung des BfArM",
    "descriptive_texts": "Beschreibung der DiGA",
    "pricing_information": "Vergütung / Preisangaben",
    "source_update_notice": "Aktualisierungshinweis im DiGA-Verzeichnis",
    "source_update_notice.notice_text": "Aktualisierungshinweis im DiGA-Verzeichnis",
    "source_update_notice.last_updated_at": "Zuletzt aktualisiert",
    "status": "Aufnahmestatus",
    "name": "Name der DiGA",
    "indication": "Anwendungsgebiet / Indikation",
    "manufacturer": "Hersteller",
    "manufacturer_website": "Herstellerlink / Website",
    "bfarm_directory_url": "BfArM-Verzeichniseintrag",
    "platforms": "Plattformen",
    "languages": "Sprachen",
    "modules": "Module / Funktionsumfang",
}

TEXT_KIND_LABELS = {
    "text_removed": "Text entfernt",
    "text_added": "Text ergänzt",
    "text_modified": "Text angepasst",
    "text_replaced": "Formulierung angepasst",
    "mixed_text_change": "Text geändert",
}

EXCERPT_CONTEXT_WORDS = 22
TECHNICAL_FIELD_MARKERS = (
    "raw_public_fhir",
    "fhir",
    "extension",
    "resource",
    "system",
    "coding",
    "identifier",
)
PRICE_FIELD_MARKERS = (
    "pricing_information",
    "price",
    "preis",
    "vergütung",
    "prescription_unit",
    "public price",
    "manufacturer price",
    "price_components",
)


def main() -> None:
    st.set_page_config(page_title="DiGA Monitor", layout="wide")
    st.title("DiGA Monitor")
    st.markdown("Änderungen im DiGA-Verzeichnis transparent verfolgen")
    st.caption("Quelle: Offizielles DiGA-Verzeichnis des BfArM")

    events = load_change_events(DEFAULT_CHANGES_DIR)
    events = sorted(events, key=lambda event: event.get("detected_at", ""), reverse=True)
    real_events = [event for event in events if is_real_change_event(event)]
    scan_history = load_scan_history()

    render_status_information(real_events, scan_history)

    filtered_events = render_filters(real_events)

    st.divider()
    if not filtered_events:
        st.info("Keine echten Änderungen seit Tracking Beginn erkannt.")
        return

    grouped_events = group_events_by_diga(filtered_events)
    render_group_summary(grouped_events, filtered_events)
    for group in grouped_events:
        render_event_group(group)


def render_filters(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    event_dates = [event_date(event) for event in events if event_date(event)]
    min_date = TRACKING_START_DATE
    max_date = max(event_dates + [TRACKING_START_DATE, date.today()])
    selected_range = st.date_input(
        "Zeitraum",
        value=(TRACKING_START_DATE, max_date),
        min_value=TRACKING_START_DATE,
        max_value=max_date,
    )

    start_date, end_date = normalize_date_range(selected_range, min_date, max_date)

    return [
        event
        for event in events
        if event_date_in_range(event, start_date, end_date)
    ]


def render_status_information(
    real_events: list[dict[str, Any]],
    scan_history: list[dict[str, Any]],
) -> None:
    st.markdown(
        """
        <style>
        .status-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 1rem;
            margin: 1rem 0 1.25rem;
        }
        .status-item {
            color: #31333f;
            font-size: 1rem;
            line-height: 1.45;
        }
        .status-label {
            font-weight: 600;
            white-space: nowrap;
        }
        .status-value {
            margin-top: 0.15rem;
            white-space: nowrap;
        }
        @media (max-width: 720px) {
            .status-grid {
                grid-template-columns: 1fr;
            }
            .status-label,
            .status-value {
                white-space: normal;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    items = [
        ("Tracking aktiv seit:", "31.05.2026"),
        ("Letzter erfolgreicher Scan:", latest_scan_timestamp(scan_history)),
        ("Letzte erkannte Änderung:", latest_real_change_timestamp(real_events)),
    ]
    blocks = "\n".join(
        (
            "<div class='status-item'>"
            f"<div class='status-label'>{html.escape(label)}</div>"
            f"<div class='status-value'>{html.escape(value)}</div>"
            "</div>"
        )
        for label, value in items
    )
    st.markdown(
        f"<div class='status-grid'>{blocks}</div>",
        unsafe_allow_html=True,
    )


def render_development_warning(events: list[dict[str, Any]]) -> None:
    available_types = {event.get("change_type") for event in events if event.get("change_type")}
    fields = {event.get("field_name") for event in events}
    if available_types == {"other_field_change"} and fields == {"source_update_notice"}:
        st.warning(
            "Hinweis: Die aktuell angezeigten Änderungen stammen aus einer "
            "Entwicklungsbereinigung und sind keine echten BfArM-Änderungen."
        )


def render_group_summary(groups: list[dict[str, Any]], events: list[dict[str, Any]]) -> None:
    affected_diga = len(groups)
    adjustments = sum(len(group["events"]) for group in groups)
    st.caption(
        f"{affected_diga} betroffene DiGA · "
        f"{adjustments} {'fachliche Anpassung' if adjustments == 1 else 'fachliche Anpassungen'}"
    )


def render_event_group(group: dict[str, Any]) -> None:
    events = group["events"]
    with st.container(border=True):
        header_cols = st.columns([4, 2, 2, 1.5])
        header_cols[0].markdown(f"### {html.escape(str(group.get('diga_name') or 'Unbekannte DiGA'))}")
        header_cols[0].caption(f"Hersteller: {group.get('manufacturer') or 'Nicht verfügbar'}")
        header_cols[1].markdown("**Fachliche Anpassungen**")
        header_cols[1].caption(str(len(events)))
        header_cols[2].markdown("**Änderung erkannt am:**")
        header_cols[2].caption(format_datetime(group.get("detected_at")))
        if group.get("bfarm_directory_url"):
            header_cols[3].link_button("BfArM-Eintrag öffnen", group["bfarm_directory_url"])
        if group.get("source_update_notice"):
            st.caption(f"BfArM-Eintrag zuletzt aktualisiert: {group['source_update_notice']}")

        st.divider()
        for index, event in enumerate(events, start=1):
            if index > 1:
                st.divider()
            _indent_col, content_col = st.columns([0.04, 0.96])
            with content_col:
                render_adjustment_header(index, event)
                render_event_details(event)


def render_event(event: dict[str, Any]) -> None:
    title = f"{event_title_label(event)} · {event.get('diga_name', 'Unbekannte DiGA')}"
    with st.container(border=True):
        if event.get("simulated"):
            st.caption(f"Simulation · {event.get('simulation_category', 'Testfall')}")
        st.markdown(f"### {html.escape(title)}")
        timeline_cols = st.columns(3)
        timeline_cols[0].markdown(f"**Änderung erkannt:**  \n{format_datetime(event.get('detected_at'))}")
        timeline_cols[1].markdown(
            f"**Letzter bekannter Zustand:**  \n{format_datetime(event.get('previous_snapshot_timestamp'))}"
        )
        timeline_cols[2].markdown(
            f"**Neuer Zustand:**  \n{format_datetime(event.get('current_snapshot_timestamp'))}"
        )
        meta_cols = st.columns([1, 1])
        meta_cols[0].caption(f"Hersteller: {event.get('manufacturer') or 'Nicht verfügbar'}")
        if event.get("bfarm_directory_url"):
            meta_cols[1].link_button("BfArM-Eintrag öffnen", event["bfarm_directory_url"])

        render_event_details(event)


def render_event_details(event: dict[str, Any]) -> None:
    change_type = event.get("change_type", "other_field_change")
    if change_type == "text_change" and event.get("word_diff"):
        render_text_change(event)
    elif change_type == "new_diga":
        render_new_diga(event)
    elif change_type == "removed_diga":
        render_removed_diga(event)
    elif is_price_event(event):
        render_price_change(event)
    elif is_technical_event(event):
        render_technical_change(event)
    else:
        render_before_after(event)


def render_adjustment_header(index: int, event: dict[str, Any]) -> None:
    title, path, internal_label = adjustment_display_info(event)
    st.markdown(f"#### Anpassung {index}")
    st.markdown(f"**{html.escape(title)}**")
    if path:
        st.caption(f"Informationspfad: {path}")
    if internal_label:
        st.caption(internal_label)


def render_before_after(event: dict[str, Any]) -> None:
    before_value = event_previous_value(event)
    after_value = event_new_value(event)
    before_col, after_col = st.columns(2)
    before_col.markdown("**Vorher**")
    render_value_box(before_col, before_value)
    after_col.markdown("**Nachher**")
    render_value_box(after_col, after_value)


def render_price_change(event: dict[str, Any]) -> None:
    summary = summarize_price_change(event_previous_value(event), event_new_value(event))
    if summary:
        st.markdown(f"**{summary['title']}**")
        if summary.get("note"):
            st.caption(summary["note"])
        render_key_value_columns(summary.get("before", []), summary.get("after", []))
        render_price_explanation(summary)
        render_raw_source(event)
        return
    render_before_after(event)


def render_technical_change(event: dict[str, Any]) -> None:
    summary = summarize_technical_change(event)
    st.caption(summary)
    before_value = concise_technical_value(event_previous_value(event))
    after_value = concise_technical_value(event_new_value(event))
    render_key_value_columns(
        [("Vorher", before_value)],
        [("Nachher", after_value)],
    )
    render_raw_source(event)


def render_new_diga(event: dict[str, Any]) -> None:
    before_col, after_col = st.columns(2)
    before_col.markdown("**Vorher**")
    before_col.info("Nicht im DiGA-Verzeichnis vorhanden")
    after_col.markdown("**Nachher**")
    after_col.success("Neu im DiGA-Verzeichnis aufgenommen")
    render_compact_entry(event_new_value(event), include_status_label="Status")


def render_removed_diga(event: dict[str, Any]) -> None:
    before_col, after_col = st.columns(2)
    before_col.markdown("**Vorher**")
    before_col.info("Im DiGA-Verzeichnis vorhanden")
    after_col.markdown("**Nachher**")
    after_col.warning("Nicht mehr im aktuellen DiGA-Verzeichnis vorhanden / gestrichen")
    render_compact_entry(event_previous_value(event), include_status_label="Letzter bekannter Status")


def render_compact_entry(value: Any, include_status_label: str) -> None:
    if not isinstance(value, dict):
        render_value_box(st, value)
        return
    rows = [
        ("Name", value.get("name")),
        ("Hersteller", value.get("manufacturer")),
        (include_status_label, value.get("status")),
        ("Anwendungsgebiet / Indikation", value.get("indication")),
    ]
    for label, item in rows:
        if item:
            st.markdown(f"**{label}:** {html.escape(format_inline_value(item))}")
    if value.get("bfarm_directory_url"):
        st.link_button("BfArM-Eintrag öffnen", value["bfarm_directory_url"])


def render_text_change(event: dict[str, Any]) -> None:
    if event.get("text_change_kind"):
        st.caption(TEXT_KIND_LABELS.get(event["text_change_kind"], "Text geändert"))
    before_tokens, after_tokens, truncated = compact_text_diff(
        event["word_diff"],
        text_change_kind=event.get("text_change_kind"),
    )
    before_col, after_col = st.columns(2)
    before_col.markdown("**Vorher**")
    before_col.markdown(render_diff_column(before_tokens, side="before"), unsafe_allow_html=True)
    after_col.markdown("**Nachher**")
    after_col.markdown(render_diff_column(after_tokens, side="after"), unsafe_allow_html=True)

    if truncated:
        with st.expander("Vollständigen Text anzeigen"):
            render_full_text(event)


def render_word_diff(tokens: list[dict[str, str]]) -> str:
    parts = []
    for token in tokens:
        text = html.escape(token.get("text", ""))
        op = token.get("op")
        if op == "insert":
            parts.append(f"<span style='background:#d9f7d9;padding:0 2px'>{text}</span>")
        elif op == "delete":
            parts.append(f"<span style='background:#ffd7d7;text-decoration:line-through;padding:0 2px'>{text}</span>")
        else:
            parts.append(text)
    return "<div style='line-height:1.8'>" + " ".join(parts) + "</div>"


def compact_text_diff(
    tokens: list[dict[str, str]],
    text_change_kind: str | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]], bool]:
    changed_indexes = [
        index
        for index, token in enumerate(tokens)
        if token.get("op") in {"insert", "delete"}
    ]
    if not changed_indexes:
        return tokens, tokens, False

    start = max(0, changed_indexes[0] - EXCERPT_CONTEXT_WORDS)
    end = min(len(tokens), changed_indexes[-1] + EXCERPT_CONTEXT_WORDS + 1)
    selected = tokens[start:end]
    truncated_start = start > 0
    truncated_end = end < len(tokens)

    before_tokens = [{"op": "ellipsis", "text": "..."}] if truncated_start else []
    after_tokens = [{"op": "ellipsis", "text": "..."}] if truncated_start else []
    previous_op = None
    for token in selected:
        op = token.get("op")
        if op in {"equal", "delete"}:
            before_tokens.append(token)
        if op in {"equal", "insert"}:
            after_tokens.append(token)
        elif op == "delete" and previous_op != "delete" and text_change_kind == "text_removed":
            after_tokens.append({"op": "removed_placeholder", "text": "[Text entfernt]"})
        elif op == "insert" and previous_op != "insert" and text_change_kind == "text_added":
            before_tokens.append({"op": "added_placeholder", "text": "[Text ergänzt]"})
        previous_op = op
    if truncated_end:
        before_tokens.append({"op": "ellipsis", "text": "..."})
        after_tokens.append({"op": "ellipsis", "text": "..."})

    return before_tokens, after_tokens, truncated_start or truncated_end


def render_diff_column(tokens: list[dict[str, str]], side: str) -> str:
    parts = []
    for token in tokens:
        op = token.get("op")
        text = html.escape(token.get("text", ""))
        if op == "delete" and side == "before":
            parts.append(f"<mark style='background:#ffd7d7;text-decoration:line-through;padding:0 2px'>{text}</mark>")
        elif op == "insert" and side == "after":
            parts.append(f"<mark style='background:#d9f7d9;padding:0 2px'>{text}</mark>")
        elif op == "ellipsis":
            parts.append(f"<span style='color:#6b7280'>{text}</span>")
        elif op in {"removed_placeholder", "added_placeholder"}:
            parts.append(f"<span style='color:#6b7280;font-style:italic'>{text}</span>")
        else:
            parts.append(text)
    return "<div style='line-height:1.8'>" + " ".join(parts) + "</div>"


def render_simulation_summary(events: list[dict[str, Any]]) -> None:
    simulated_count = sum(1 for event in events if event.get("simulated"))
    if simulated_count:
        st.info(f"Simulierte Szenarien: {simulated_count}")


def render_grouped_simulations(events: list[dict[str, Any]]) -> None:
    non_simulated = [event for event in events if not event.get("simulated")]
    for event in non_simulated:
        render_event(event)

    categories = [
        "Aufnahme und Status",
        "Texte und Bewertung",
        "Verordnung und Preis",
        "Technische und organisatorische Angaben",
        "Plattformen und Links",
        "Sonstige Felder",
    ]
    simulated_events = [event for event in events if event.get("simulated")]
    for category in categories:
        category_events = [
            event
            for event in simulated_events
            if event.get("simulation_category") == category
        ]
        if not category_events:
            continue
        st.subheader(category)
        for event in category_events:
            render_event(event)


def render_full_text(event: dict[str, Any]) -> None:
    st.markdown("**Vorher**")
    render_wrapped_text(event_previous_value(event))
    st.markdown("**Nachher**")
    render_wrapped_text(event_new_value(event))


def render_wrapped_text(value: Any) -> None:
    text = html.escape(format_value(value))
    text = text.replace("\n", "<br>")
    st.markdown(
        (
            "<div style='white-space:normal; overflow-wrap:anywhere; word-break:normal; "
            "line-height:1.65; border:1px solid #e5e7eb; border-radius:6px; padding:0.85rem; "
            "background:#fafafa; max-height:28rem; overflow-y:auto;'>"
            f"{text}</div>"
        ),
        unsafe_allow_html=True,
    )


def render_value_box(container: Any, value: Any) -> None:
    if value is None:
        container.markdown("_Kein Wert vorhanden_")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if item is not None:
                container.markdown(f"**{field_label(str(key))}:** {html.escape(format_inline_value(item))}")
        return
    if isinstance(value, list):
        if not value:
            container.markdown("_Keine Einträge_")
            return
        for item in value:
            container.markdown(f"- {html.escape(format_inline_value(item))}")
        return
    container.markdown(render_inline_value(value), unsafe_allow_html=True)


def render_key_value_columns(
    before_rows: list[tuple[str, Any]],
    after_rows: list[tuple[str, Any]],
) -> None:
    before_col, after_col = st.columns(2)
    before_col.markdown("**Vorher**")
    render_key_value_rows(before_col, before_rows)
    after_col.markdown("**Nachher**")
    render_key_value_rows(after_col, after_rows)


def render_key_value_rows(container: Any, rows: list[tuple[str, Any]]) -> None:
    if not rows:
        container.markdown("_Keine fachlich darstellbaren Details_")
        return
    for label, value in rows:
        if value is None or value == "":
            continue
        container.markdown(f"**{html.escape(label)}:** {render_inline_value(value)}", unsafe_allow_html=True)


def render_price_explanation(summary: dict[str, Any]) -> None:
    explanation = summary.get("explanation")
    if not explanation:
        return
    with st.expander("Warum wurde diese Änderung erkannt?"):
        st.markdown(str(explanation))
        explanation_before = summary.get("explanation_before") or summary.get("before") or []
        explanation_after = summary.get("explanation_after") or summary.get("after") or []
        render_key_value_columns(explanation_before, explanation_after)


def render_raw_source(event: dict[str, Any]) -> None:
    with st.expander("Rohdaten anzeigen"):
        details = {
            "changed_field": event.get("changed_field"),
            "field_name": event.get("field_name"),
            "before_value": event_previous_value(event),
            "after_value": event_new_value(event),
        }
        st.json(details)


def format_inline_value(value: Any) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{key}: {format_inline_value(item)}" for key, item in value.items() if item is not None)
    if isinstance(value, list):
        return ", ".join(format_inline_value(item) for item in value)
    return str(value)


def render_inline_value(value: Any) -> str:
    text = format_inline_value(value)
    status_style = status_badge_style(text)
    if not status_style:
        return html.escape(text)
    return (
        "<span style='display:inline-flex;align-items:center;border-radius:999px;"
        "padding:0.18rem 0.55rem;font-weight:600;font-size:0.92rem;"
        f"{status_style}'>{html.escape(text)}</span>"
    )


def status_badge_style(value: str) -> str | None:
    normalized = value.strip().lower()
    if "vorläufig" in normalized:
        return "background:#fff3bf;color:#7a4f01;border:1px solid #ffd43b;"
    if "dauerhaft" in normalized:
        return "background:#d3f9d8;color:#14532d;border:1px solid #69db7c;"
    if "gestrichen" in normalized:
        return "background:#ffe3e3;color:#8a1f1f;border:1px solid #ffa8a8;"
    return None


def is_real_change_event(event: dict[str, Any]) -> bool:
    if event.get("simulated"):
        return False
    if event.get("development") or event.get("is_development") or event.get("baseline_cleanup"):
        return False

    field_name = event_field_name(event).lower()
    before_value = event_previous_value(event)
    if before_value is None and field_name == "source_update_notice":
        return False
    if before_value is None and "checked_sources" in field_name:
        return False
    return True


def field_label(event_or_field_name: dict[str, Any] | str) -> str:
    if isinstance(event_or_field_name, dict):
        if is_numeric_field_label(event_field_name(event_or_field_name)):
            return "Nicht zugeordnete Feldänderung"
        if is_technical_event(event_or_field_name):
            return technical_field_title(event_or_field_name)
        if event_or_field_name.get("user_facing_field_label"):
            return str(event_or_field_name["user_facing_field_label"])
        context_label = text_context_label(event_or_field_name)
        if context_label:
            return context_label
        field_name = event_field_name(event_or_field_name)
    else:
        field_name = event_or_field_name
        if is_numeric_field_label(field_name):
            return "Nicht zugeordnete Feldänderung"
        if is_technical_field_name(field_name):
            return "Technische Änderung im BfArM-Datenmodell"
    root = field_name.split(".", 1)[0]
    return FIELD_LABELS.get(field_name) or FIELD_LABELS.get(root) or root or "Unbekannter Bereich"


def text_context_label(event: dict[str, Any]) -> str | None:
    section_title = event.get("section_title") or event.get("source_area_label")
    subsection_title = event.get("subsection_title")
    parts = [str(part) for part in (section_title, subsection_title) if part]
    if not parts:
        return None
    return " > ".join(dict.fromkeys(parts))


def split_field_label(label: str) -> tuple[str, str | None]:
    parts = [part.strip() for part in label.split(" > ") if part.strip()]
    if len(parts) >= 2:
        return parts[-1], " > ".join(parts[:-1])
    return label, None


def adjustment_display_info(event: dict[str, Any]) -> tuple[str, str | None, str | None]:
    internal_name = event_field_name(event)
    if is_price_event(event):
        return price_field_title(event), None, internal_field_caption(internal_name)
    if is_numeric_field_label(internal_name):
        return "Nicht zugeordnete Feldänderung", None, internal_field_caption(internal_name)
    if is_technical_event(event):
        return technical_field_title(event), None, internal_field_caption(internal_name)

    label = field_label(event)
    title, path = split_field_label(label)
    if is_numeric_field_label(title):
        return "Nicht zugeordnete Feldänderung", path, f"Interne Feld-ID: {title}"
    if is_technical_field_name(title):
        return "Technische Änderung", path, internal_field_caption(internal_name or title)
    return title, path, None


def is_price_event(event: dict[str, Any]) -> bool:
    haystack = " ".join(
        str(part).lower()
        for part in (
            event.get("change_type"),
            event_field_name(event),
            event.get("user_facing_field_label"),
        )
        if part
    )
    return any(marker in haystack for marker in PRICE_FIELD_MARKERS)


def is_technical_event(event: dict[str, Any]) -> bool:
    field_name = event_field_name(event)
    label = str(event.get("user_facing_field_label") or "")
    return (
        is_numeric_field_label(field_name)
        or is_numeric_field_label(label)
        or is_technical_field_name(field_name)
        or is_technical_field_name(label)
    )


def is_numeric_field_label(value: Any) -> bool:
    return str(value or "").strip().isdigit()


def is_technical_field_name(value: Any) -> bool:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in TECHNICAL_FIELD_MARKERS)


def technical_field_title(event: dict[str, Any]) -> str:
    field_name = event_field_name(event).lower()
    before_value = event_previous_value(event)
    after_value = event_new_value(event)
    if field_name == "raw_public_fhir" or field_name.startswith("raw_public_fhir."):
        if list_items_added(before_value, after_value) or list_items_removed(before_value, after_value):
            return "Technische Datenstruktur aktualisiert"
        if "versionid" in field_name.lower():
            return "Interne Version aktualisiert"
        return "Technische Änderung im BfArM-Datenmodell"
    return "Technische Änderung"


def price_field_title(event: dict[str, Any]) -> str:
    summary = summarize_price_change(event_previous_value(event), event_new_value(event))
    if summary:
        return str(summary["title"])
    return "Preis / Vergütung"


def internal_field_caption(field_name: str) -> str | None:
    if not field_name:
        return None
    if is_numeric_field_label(field_name):
        return f"Interne Feld-ID: {field_name}"
    return f"Internes Feld: {field_name}"


def summarize_technical_change(event: dict[str, Any]) -> str:
    before_value = event_previous_value(event)
    after_value = event_new_value(event)
    added_items = list_items_added(before_value, after_value)
    removed_items = list_items_removed(before_value, after_value)
    if added_items:
        return f"Neue interne Ressource hinzugefügt: {', '.join(map(str, added_items))}"
    if removed_items:
        return f"Interne Ressource entfernt: {', '.join(map(str, removed_items))}"
    if "versionid" in event_field_name(event).lower():
        return "Interne BfArM-Version wurde aktualisiert."
    return "Technische Änderung im BfArM-Datenmodell."


def concise_technical_value(value: Any) -> str:
    if value is None:
        return "Kein Wert vorhanden"
    if isinstance(value, list):
        simple_items = [str(item) for item in value if not isinstance(item, (dict, list))]
        if len(simple_items) == len(value):
            return ", ".join(simple_items) if simple_items else "Keine Einträge"
        return f"{len(value)} interne Einträge"
    if isinstance(value, dict):
        if value.get("id"):
            return f"Interne Ressource {value['id']}"
        if value.get("resourceType"):
            return f"Interne Datenressource: {value['resourceType']}"
        return f"{len(value)} interne Felder"
    return str(value)


def list_items_added(before_value: Any, after_value: Any) -> list[Any]:
    if not isinstance(before_value, list) or not isinstance(after_value, list):
        return []
    before_items = {stable_item_key(item) for item in before_value}
    return [item for item in after_value if stable_item_key(item) not in before_items]


def list_items_removed(before_value: Any, after_value: Any) -> list[Any]:
    if not isinstance(before_value, list) or not isinstance(after_value, list):
        return []
    after_items = {stable_item_key(item) for item in after_value}
    return [item for item in before_value if stable_item_key(item) not in after_items]


def stable_item_key(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json_dumps(value)
    return str(value)


def summarize_price_change(before_value: Any, after_value: Any) -> dict[str, Any] | None:
    before_periods = extract_price_periods(before_value)
    after_periods = extract_price_periods(after_value)

    if before_periods or after_periods:
        return summarize_price_period_change(before_periods, after_periods)

    before_price = extract_simple_price(before_value)
    after_price = extract_simple_price(after_value)
    if before_price and after_price and normalize_price(before_price) != normalize_price(after_price):
        return {
            "title": "Preis geändert",
            "explanation": "Der Preiswert wurde geändert.",
            "before": [("Preis", before_price)],
            "after": [("Preis", after_price)],
        }

    return technical_price_change_summary()


def summarize_price_period_change(
    before_periods: list[dict[str, Any]],
    after_periods: list[dict[str, Any]],
) -> dict[str, Any]:
    removed = list_price_periods_removed(before_periods, after_periods)
    added = list_price_periods_added(before_periods, after_periods)

    if not removed and not added:
        return technical_price_change_summary()

    removed_prices = {period.get("price_key") for period in removed if period.get("price_key")}
    added_prices = {period.get("price_key") for period in added if period.get("price_key")}
    same_price = bool(removed_prices and removed_prices == added_prices)
    if same_price and removed and added:
        return {
            "title": "Preiszeitraum aktualisiert",
            "note": "Der Preiswert selbst wurde nicht verändert.",
            "explanation": (
                "Der Preiswert selbst wurde nicht geändert. Das BfArM hat den bisherigen "
                "Preiszeitraum beendet und einen neuen Preiszeitraum mit identischem Preis angelegt."
            ),
            "before": price_period_rows(removed),
            "after": price_period_rows(added),
            "explanation_before": price_period_explanation_rows(removed),
            "explanation_after": price_period_explanation_rows(added),
        }

    if removed and added:
        title = "Preis geändert" if removed_prices != added_prices else "Preis / Vergütung aktualisiert"
        return {
            "title": title,
            "explanation": (
                "Der Preiswert wurde geändert."
                if title == "Preis geändert"
                else "Die Angaben zu Preis und Zeitraum wurden aktualisiert."
            ),
            "before": price_period_rows(removed),
            "after": price_period_rows(added),
            "explanation_before": price_period_explanation_rows(removed),
            "explanation_after": price_period_explanation_rows(added),
        }

    if added:
        return {
            "title": "Neuer Preiszeitraum ergänzt",
            "explanation": "Ein neuer Preiszeitraum wurde ergänzt.",
            "before": [("Preiszeitraum", "Nicht vorhanden")],
            "after": price_period_rows(added),
            "explanation_before": [("Preiszeitraum", "Nicht vorhanden")],
            "explanation_after": price_period_explanation_rows(added),
        }

    return {
        "title": "Preiszeitraum entfernt",
        "explanation": "Ein Preiszeitraum wurde entfernt.",
        "before": price_period_rows(removed),
        "after": [("Preiszeitraum", "Nicht mehr vorhanden")],
        "explanation_before": price_period_explanation_rows(removed),
        "explanation_after": [("Preiszeitraum", "Nicht mehr vorhanden")],
    }


def technical_price_change_summary() -> dict[str, Any]:
    return {
        "title": "Technische Änderung in Preis/Vergütungsdaten",
        "note": (
            "Die BfArM-Datenstruktur zur Vergütung wurde angepasst. "
            "Eine fachliche Preisänderung konnte nicht eindeutig abgeleitet werden."
        ),
        "explanation": (
            "Die technische Datenstruktur zur Vergütung wurde geändert. "
            "Eine fachliche Preisänderung konnte nicht eindeutig abgeleitet werden."
        ),
        "before": [("Einordnung", "Vorherige interne Preisstruktur")],
        "after": [("Einordnung", "Neue interne Preisstruktur")],
        "technical_details": True,
    }


def extract_price_periods(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        periods: list[dict[str, Any]] = []
        for item in value:
            periods.extend(extract_price_periods(item))
        return periods
    if not isinstance(value, dict):
        return []

    period = extract_effective_period(value)
    amounts = extract_amounts(value)
    if period and amounts:
        return [
            {
                "price": amount,
                "price_key": normalize_price(amount),
                "period": period,
                "period_key": price_period_key(period),
            }
            for amount in amounts
        ]

    periods: list[dict[str, Any]] = []
    for item in value.values():
        periods.extend(extract_price_periods(item))
    return periods


def extract_amounts(value: Any) -> list[str]:
    amounts: list[str] = []
    if isinstance(value, dict):
        amount = amount_from_dict(value)
        if amount:
            amounts.append(amount)
        for item in value.values():
            amounts.extend(extract_amounts(item))
    elif isinstance(value, list):
        for item in value:
            amounts.extend(extract_amounts(item))
    return list(dict.fromkeys(amounts))


def amount_from_dict(value: dict[str, Any]) -> str | None:
    if "value" not in value or "currency" not in value:
        return None
    amount = value.get("value")
    currency = value.get("currency")
    if amount is None or currency is None:
        return None
    return f"{format_price_number(amount)} {currency}"


def format_price_number(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).replace(".", ",")


def extract_effective_period(value: dict[str, Any]) -> dict[str, str | None] | None:
    period = value.get("effective_period") or value.get("effectivePeriod") or value.get("period")
    if not isinstance(period, dict):
        return None
    start = period.get("start")
    end = period.get("end")
    if not start and not end:
        return None
    return {
        "start": str(start) if start else None,
        "end": str(end) if end else None,
    }


def price_period_key(period: dict[str, str | None]) -> str:
    return f"{period.get('start') or ''}|{period.get('end') or ''}"


def list_price_periods_added(
    before_periods: list[dict[str, Any]],
    after_periods: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    before_keys = {price_period_identity(period) for period in before_periods}
    return [period for period in after_periods if price_period_identity(period) not in before_keys]


def list_price_periods_removed(
    before_periods: list[dict[str, Any]],
    after_periods: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    after_keys = {price_period_identity(period) for period in after_periods}
    return [period for period in before_periods if price_period_identity(period) not in after_keys]


def price_period_identity(period: dict[str, Any]) -> str:
    return f"{period.get('price_key') or ''}|{period.get('period_key') or ''}"


def price_period_rows(periods: list[dict[str, Any]]) -> list[tuple[str, Any]]:
    return [
        (f"Preiszeitraum {index}", format_price_period(period))
        for index, period in enumerate(periods, start=1)
    ]


def price_period_explanation_rows(periods: list[dict[str, Any]]) -> list[tuple[str, Any]]:
    if len(periods) == 1:
        period = periods[0]
        rows: list[tuple[str, Any]] = [("Preis", period.get("price"))]
        rows.extend(period_detail_rows(period.get("period")))
        return rows
    return price_period_rows(periods)


def period_detail_rows(period: Any) -> list[tuple[str, Any]]:
    if not isinstance(period, dict):
        return []
    start = format_date_label(period.get("start"))
    end = format_date_label(period.get("end"))
    if start and end:
        return [("gültig von", f"{start} bis {end}")]
    if start:
        return [("gültig seit", start)]
    if end:
        return [("gültig bis", end)]
    return []


def format_price_period(period: dict[str, Any]) -> str:
    price = str(period.get("price") or "Preis nicht angegeben")
    period_label = format_period_label(period.get("period"))
    if period_label:
        return f"{price}, {period_label}"
    return price


def format_period_label(period: Any) -> str:
    if not isinstance(period, dict):
        return ""
    start = format_date_label(period.get("start"))
    end = format_date_label(period.get("end"))
    if start and end:
        return f"gültig von {start} bis {end}"
    if start:
        return f"gültig ab {start}"
    if end:
        return f"gültig bis {end}"
    return ""


def format_date_label(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return value


def extract_simple_price(value: Any) -> str | None:
    if isinstance(value, str):
        return value if contains_price(value) else None
    amounts = extract_amounts(value)
    return amounts[0] if amounts else None


def contains_price(value: str) -> bool:
    normalized = value.lower()
    return "€" in value or "eur" in normalized or any(char.isdigit() for char in value)


def normalize_price(value: str) -> str:
    return value.replace(" ", "").replace(",", ".").lower()


def event_title_label(event: dict[str, Any]) -> str:
    if event.get("change_type") == "status_change" and str(event_new_value(event)).lower() == "gestrichen":
        return "Streichung"
    return CHANGE_LABELS.get(str(event.get("change_type")), str(event.get("change_type") or "Änderung"))


def event_field_name(event: dict[str, Any]) -> str:
    return str(event.get("changed_field") or event.get("field_name") or "")


def event_previous_value(event: dict[str, Any]) -> Any:
    return event.get("previous_value", event.get("before_value"))


def event_new_value(event: dict[str, Any]) -> Any:
    return event.get("new_value", event.get("after_value"))


def group_events_by_diga(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, date | None], list[dict[str, Any]]] = {}
    for event in events:
        key = (event_diga_key(event), event_date(event))
        groups.setdefault(key, []).append(event)

    result = []
    for (_diga_key, group_date), all_group_events in groups.items():
        business_events = [event for event in all_group_events if not is_metadata_event(event)]
        if not business_events:
            continue
        business_events = sorted(
            business_events,
            key=lambda event: (
                parse_datetime(event.get("detected_at")) or datetime.min.replace(tzinfo=timezone.utc),
                field_label(event),
            ),
            reverse=True,
        )
        latest_event = business_events[0]
        result.append(
            {
                "date": group_date,
                "diga_name": latest_event.get("diga_name") or "Unbekannte DiGA",
                "manufacturer": first_present(business_events, "manufacturer"),
                "bfarm_directory_url": first_present(business_events, "bfarm_directory_url"),
                "detected_at": timestamp_value(business_events, "detected_at", latest=True),
                "previous_snapshot_timestamp": timestamp_value(
                    business_events,
                    "previous_snapshot_timestamp",
                    latest=False,
                ),
                "current_snapshot_timestamp": timestamp_value(
                    business_events,
                    "current_snapshot_timestamp",
                    latest=True,
                ),
                "source_update_notice": source_update_notice_label(all_group_events),
                "events": business_events,
            }
        )

    return sorted(
        result,
        key=lambda group: parse_datetime(group.get("detected_at")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )


def event_group_title(group: dict[str, Any]) -> str:
    name = str(group.get("diga_name") or "Unbekannte DiGA")
    adjustment_count = len(group.get("events") or [])
    if adjustment_count <= 1:
        return f"Änderung · {name}"
    return f"{name} · {adjustment_count} fachliche Anpassungen"


def event_diga_key(event: dict[str, Any]) -> str:
    return str(
        event.get("diga_id")
        or event.get("diga_name")
        or event.get("bfarm_directory_url")
        or "unknown"
    ).lower()


def is_metadata_event(event: dict[str, Any]) -> bool:
    field_name = event_field_name(event).lower()
    metadata_fields = {
        "source_update_notice",
        "source_update_notice.checked_sources",
        "source_update_notice.last_updated_at",
        "source_update_notice.notice_text",
    }
    if field_name in metadata_fields:
        return True
    return any(
        marker in field_name
        for marker in ("last_updated", "updated_at", "timestamp", "checked_sources")
    )


def source_update_notice_label(events: list[dict[str, Any]]) -> str | None:
    for event in events:
        if event_field_name(event) == "source_update_notice.last_updated_at":
            value = event_new_value(event)
            if isinstance(value, str):
                formatted = format_datetime(value)
                return formatted if formatted != value else None
    return None


def first_present(events: list[dict[str, Any]], key: str) -> Any:
    for event in events:
        value = event.get(key)
        if value:
            return value
    return None


def timestamp_value(events: list[dict[str, Any]], key: str, latest: bool) -> Any:
    values = [
        (parsed, event.get(key))
        for event in events
        if (parsed := parse_datetime(event.get(key)))
    ]
    if not values:
        return None
    selected = max(values, key=lambda item: item[0]) if latest else min(values, key=lambda item: item[0])
    return selected[1]


def latest_scan_timestamp(scan_history: list[dict[str, Any]]) -> str:
    snapshot_timestamp = latest_snapshot_timestamp()
    if snapshot_timestamp:
        return format_local_datetime(snapshot_timestamp)

    history_dates = [
        parsed
        for scan in scan_history
        if (parsed := parse_datetime(scan.get("scan_timestamp")))
    ]
    if history_dates:
        return format_local_datetime(max(history_dates))

    return "Noch kein erfolgreicher Scan"


def latest_snapshot_timestamp() -> datetime | None:
    timestamps = [
        parsed
        for path in SNAPSHOT_DIR.glob(f"{SNAPSHOT_FILENAME_PREFIX}*{SNAPSHOT_FILENAME_SUFFIX}")
        if (parsed := parse_snapshot_timestamp(path))
    ]
    if not timestamps:
        return None
    return max(timestamps)


def parse_snapshot_timestamp(path: Path) -> datetime | None:
    filename = path.name
    if not filename.startswith(SNAPSHOT_FILENAME_PREFIX) or not filename.endswith(SNAPSHOT_FILENAME_SUFFIX):
        return None
    raw_timestamp = filename.removeprefix(SNAPSHOT_FILENAME_PREFIX).removesuffix(SNAPSHOT_FILENAME_SUFFIX)
    try:
        return datetime.strptime(raw_timestamp, "%Y%m%dT%H%M%S%fZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def latest_real_change_timestamp(events: list[dict[str, Any]]) -> str:
    dates = [parsed for event in events if (parsed := parse_datetime(event.get("detected_at")))]
    if not dates:
        return "Bisher keine Änderungen erkannt"
    return format_local_datetime(max(dates))


def event_date(event: dict[str, Any]) -> date | None:
    parsed = parse_datetime(event.get("detected_at"))
    return parsed.astimezone(DISPLAY_TIMEZONE).date() if parsed else None


def event_date_in_range(event: dict[str, Any], start_date: date, end_date: date) -> bool:
    current = event_date(event)
    return bool(current and start_date <= current <= end_date)


def normalize_date_range(value: Any, min_date: date, max_date: date) -> tuple[date, date]:
    if isinstance(value, (tuple, list)) and len(value) == 2:
        return value
    if isinstance(value, date):
        return value, value
    return min_date, max_date


def parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_datetime(value: Any) -> str:
    parsed = parse_datetime(value)
    if not parsed:
        return str(value or "")
    return format_local_datetime(parsed)


def format_local_datetime(value: datetime) -> str:
    return value.astimezone(DISPLAY_TIMEZONE).strftime("%d.%m.%Y %H:%M")


def format_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json_dumps(value)


def json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
