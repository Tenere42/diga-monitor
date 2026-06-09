"""Streamlit change-feed dashboard for DiGA directory changes."""

from __future__ import annotations

import html
import re
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
LONG_TEXT_CONTEXT_WORDS = 36
MAX_DIFF_EXCERPT_TOKENS = 150
LONG_TEXT_CHAR_LIMIT = 400
LONG_TEXT_WORD_LIMIT = 60
LONG_TEXT_EXCERPT_CHARS = 500


def main() -> None:
    st.set_page_config(page_title="DiGA Monitor", layout="wide")
    render_page_header()

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
    if not grouped_events:
        st.info("Keine echten Änderungen seit Tracking Beginn erkannt.")
        return
    render_group_summary(grouped_events, filtered_events)
    for group in grouped_events:
        render_event_group(group)


def render_page_header() -> None:
    st.markdown(
        """
        <style>
        :root {
            --diga-header-title: #111827;
            --diga-header-text: #1f2937;
            --diga-header-muted: #4b5563;
            --diga-header-value: #111827;
        }
        @media (prefers-color-scheme: dark) {
            :root {
                --diga-header-title: #f9fafb;
                --diga-header-text: #f3f4f6;
                --diga-header-muted: #d1d5db;
                --diga-header-value: #ffffff;
            }
        }
        .diga-page-header {
            margin-bottom: 1rem;
        }
        .diga-page-title {
            color: var(--diga-header-title);
            font-size: 2.5rem;
            font-weight: 700;
            line-height: 1.15;
            margin: 0 0 0.35rem;
        }
        .diga-page-subtitle {
            color: var(--diga-header-text);
            font-size: 1.08rem;
            line-height: 1.45;
            margin: 0;
        }
        .diga-page-source {
            color: var(--diga-header-muted);
            font-size: 0.9rem;
            line-height: 1.45;
            margin-top: 0.35rem;
        }
        @media (max-width: 720px) {
            .diga-page-title {
                font-size: 2rem;
            }
            .diga-page-subtitle {
                font-size: 1rem;
            }
            .diga-page-source {
                font-size: 0.92rem;
            }
        }
        </style>
        <header class="diga-page-header">
            <h1 class="diga-page-title">DiGA Monitor</h1>
            <p class="diga-page-subtitle">Änderungen im DiGA-Verzeichnis transparent verfolgen</p>
            <div class="diga-page-source">Quelle: Offizielles DiGA-Verzeichnis des BfArM</div>
        </header>
        """,
        unsafe_allow_html=True,
    )


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
            color: var(--diga-header-value);
            font-size: 1rem;
            line-height: 1.45;
        }
        .status-label {
            color: var(--diga-header-muted);
            font-weight: 600;
            white-space: nowrap;
        }
        .status-value {
            color: var(--diga-header-value);
            font-weight: 500;
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
    elif change_type == "price_change":
        render_price_change(event)
    elif change_type == "new_diga":
        render_new_diga(event)
    elif change_type == "removed_diga":
        render_removed_diga(event)
    else:
        render_before_after(event)


def render_adjustment_header(index: int, event: dict[str, Any]) -> None:
    title, path = split_field_label(field_label(event))
    st.markdown(f"#### Anpassung {index}")
    st.markdown(f"**{html.escape(title)}**")
    if path:
        st.caption(f"Informationspfad: {path}")


def render_before_after(event: dict[str, Any]) -> None:
    before_value = event_previous_value(event)
    after_value = event_new_value(event)
    render_before_after_html(value_to_html(before_value), value_to_html(after_value))


def render_price_change(event: dict[str, Any]) -> None:
    analysis = analyze_price_change(event_previous_value(event), event_new_value(event))
    st.markdown(f"**{html.escape(analysis['title'])}**")
    if analysis.get("note"):
        st.caption(str(analysis["note"]))

    render_before_after_html(
        lines_to_html(analysis["before_lines"]),
        lines_to_html(analysis["after_lines"]),
    )

    with st.expander("Warum wurde diese Änderung erkannt?"):
        st.markdown(analysis["explanation"])
        if analysis.get("show_raw"):
            with st.expander("Rohdaten anzeigen"):
                st.markdown("**Geändertes Feld**")
                st.write(event_field_name(event))
                st.markdown("**Vorher**")
                st.json(event_previous_value(event))
                st.markdown("**Nachher**")
                st.json(event_new_value(event))


def render_new_diga(event: dict[str, Any]) -> None:
    render_before_after_html(
        "<p>Nicht im DiGA-Verzeichnis vorhanden</p>",
        "<p>Neu im DiGA-Verzeichnis aufgenommen</p>",
    )
    render_compact_entry(event_new_value(event), include_status_label="Status")


def render_removed_diga(event: dict[str, Any]) -> None:
    render_before_after_html(
        "<p>Im DiGA-Verzeichnis vorhanden</p>",
        "<p>Nicht mehr im aktuellen DiGA-Verzeichnis vorhanden / gestrichen</p>",
    )
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
    if is_long_text_change(event):
        render_long_text_change(event)
        return

    before_tokens, after_tokens, truncated = compact_text_diff(
        event["word_diff"],
        text_change_kind=event.get("text_change_kind"),
    )
    render_before_after_html(
        render_diff_column(before_tokens, side="before"),
        render_diff_column(after_tokens, side="after"),
    )

    if truncated:
        with st.expander("Vollständigen Vorher/Nachher Text anzeigen"):
            render_full_text(event)


def render_long_text_change(event: dict[str, Any]) -> None:
    tokens = event.get("word_diff") if isinstance(event.get("word_diff"), list) else []
    st.markdown(f"**{summarize_long_text_change(event, tokens)}**")

    before_tokens, after_tokens, truncated = compact_text_diff(
        tokens,
        context_words=LONG_TEXT_CONTEXT_WORDS,
        max_tokens=MAX_DIFF_EXCERPT_TOKENS,
    )
    if before_tokens or after_tokens:
        render_before_after_html(
            render_diff_column(before_tokens, side="before"),
            render_diff_column(after_tokens, side="after"),
            stacked=True,
        )
        if truncated:
            st.caption("Es wird nur der relevante Ausschnitt um die Änderung angezeigt.")
    else:
        st.info("Die Textänderung ist umfangreich. Die vollständigen Texte stehen im Aufklapper unten.")

    with st.expander("Vollständigen Vorher/Nachher Text anzeigen"):
        render_full_text(event)


def change_excerpt_html(text: str, tone: str) -> str:
    border_color = "#ef4444" if tone == "removed" else "#16a34a"
    background = "rgba(239, 68, 68, 0.14)" if tone == "removed" else "rgba(22, 163, 74, 0.14)"
    return (
        "<div style='"
        f"border-left:4px solid {border_color};"
        f"background:{background};"
        "color:inherit;padding:0.75rem 0.85rem;border-radius:6px;"
        "line-height:1.65;overflow-wrap:anywhere;white-space:normal;'>"
        f"{html.escape(text)}"
        "</div>"
    )


def is_long_text_change(event: dict[str, Any]) -> bool:
    before_text = str(event_previous_value(event) or "")
    after_text = str(event_new_value(event) or "")
    return (
        len(before_text) > LONG_TEXT_CHAR_LIMIT
        or len(after_text) > LONG_TEXT_CHAR_LIMIT
        or len(before_text.split()) > LONG_TEXT_WORD_LIMIT
        or len(after_text.split()) > LONG_TEXT_WORD_LIMIT
    )


def summarize_long_text_change(event: dict[str, Any], tokens: list[dict[str, str]]) -> str:
    removed_words = changed_word_count(tokens, "delete")
    added_words = changed_word_count(tokens, "insert")
    if removed_words and not added_words:
        return f"Text entfernt · ca. {removed_words} Wörter entfernt"
    if added_words and not removed_words:
        return f"Text ergänzt · ca. {added_words} Wörter ergänzt"
    if removed_words or added_words:
        return f"Text stark angepasst · ca. {removed_words} Wörter entfernt, ca. {added_words} Wörter ergänzt"
    return TEXT_KIND_LABELS.get(str(event.get("text_change_kind")), "Text stark angepasst")


def changed_word_count(tokens: list[dict[str, str]], op: str) -> int:
    return sum(len(str(token.get("text", "")).split()) for token in tokens if token.get("op") == op)


def changed_text_excerpt(tokens: list[dict[str, str]], op: str) -> str:
    changed_parts = [
        str(token.get("text", "")).strip()
        for token in tokens
        if token.get("op") == op and str(token.get("text", "")).strip()
    ]
    text = " ".join(changed_parts)
    text = " ".join(text.split())
    if len(text) <= LONG_TEXT_EXCERPT_CHARS:
        return text
    return text[:LONG_TEXT_EXCERPT_CHARS].rstrip() + "..."


def render_word_diff(tokens: list[dict[str, str]]) -> str:
    parts = []
    for token in tokens:
        text = html.escape(token.get("text", ""))
        op = token.get("op")
        if op == "insert":
            parts.append(
                "<span style='background:rgba(22,163,74,0.18);color:inherit;"
                f"border-bottom:2px solid #16a34a;padding:0 2px'>{text}</span>"
            )
        elif op == "delete":
            parts.append(
                "<span style='background:rgba(239,68,68,0.18);color:inherit;"
                f"border-bottom:2px solid #ef4444;text-decoration:line-through;padding:0 2px'>{text}</span>"
            )
        else:
            parts.append(text)
    return "<div style='line-height:1.8'>" + " ".join(parts) + "</div>"


def compact_text_diff(
    tokens: list[dict[str, str]],
    text_change_kind: str | None = None,
    context_words: int = EXCERPT_CONTEXT_WORDS,
    max_tokens: int = MAX_DIFF_EXCERPT_TOKENS,
) -> tuple[list[dict[str, str]], list[dict[str, str]], bool]:
    changed_indexes = [
        index
        for index, token in enumerate(tokens)
        if token.get("op") in {"insert", "delete"}
    ]
    if not changed_indexes:
        return tokens, tokens, False

    windows = build_diff_windows(changed_indexes, len(tokens), context_words, max_tokens)
    truncated_start = windows[0][0] > 0
    truncated_end = windows[-1][1] < len(tokens)

    before_tokens = [{"op": "ellipsis", "text": "..."}] if truncated_start else []
    after_tokens = [{"op": "ellipsis", "text": "..."}] if truncated_start else []
    for window_index, (start, end) in enumerate(windows):
        if window_index:
            before_tokens.append({"op": "ellipsis", "text": "..."})
            after_tokens.append({"op": "ellipsis", "text": "..."})
        for token in tokens[start:end]:
            op = token.get("op")
            if op in {"equal", "delete"}:
                before_tokens.append(token)
            if op in {"equal", "insert"}:
                after_tokens.append(token)
    if truncated_end:
        before_tokens.append({"op": "ellipsis", "text": "..."})
        after_tokens.append({"op": "ellipsis", "text": "..."})

    return before_tokens, after_tokens, truncated_start or truncated_end or len(windows) > 1


def build_diff_windows(
    changed_indexes: list[int],
    token_count: int,
    context_words: int,
    max_tokens: int,
) -> list[tuple[int, int]]:
    windows: list[tuple[int, int]] = []
    for index in changed_indexes:
        start = max(0, index - context_words)
        end = min(token_count, index + context_words + 1)
        if windows and start <= windows[-1][1]:
            windows[-1] = (windows[-1][0], max(windows[-1][1], end))
        else:
            windows.append((start, end))

    selected: list[tuple[int, int]] = []
    used_tokens = 0
    for start, end in windows:
        window_size = end - start
        if selected and used_tokens + window_size > max_tokens:
            break
        selected.append((start, end))
        used_tokens += window_size
    return selected or [windows[0]]


def render_diff_column(tokens: list[dict[str, str]], side: str) -> str:
    parts = []
    for token in tokens:
        op = token.get("op")
        text = html.escape(token.get("text", ""))
        if op == "delete" and side == "before":
            parts.append(
                "<mark style='background:rgba(239,68,68,0.18);color:inherit;"
                f"border-bottom:2px solid #ef4444;text-decoration:line-through;padding:0 2px'>{text}</mark>"
            )
        elif op == "insert" and side == "after":
            parts.append(
                "<mark style='background:rgba(22,163,74,0.18);color:inherit;"
                f"border-bottom:2px solid #16a34a;padding:0 2px'>{text}</mark>"
            )
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


def analyze_price_change(before_value: Any, after_value: Any) -> dict[str, Any]:
    before_periods = extract_price_periods(before_value)
    after_periods = extract_price_periods(after_value)
    before_lines = price_period_lines(before_periods)
    after_lines = price_period_lines(after_periods)
    before_amounts = {period["amount"] for period in before_periods if period.get("amount")}
    after_amounts = {period["amount"] for period in after_periods if period.get("amount")}

    if before_lines or after_lines:
        amount_changed = before_amounts != after_amounts
        periods_changed = normalize_lines(before_lines) != normalize_lines(after_lines)
        if amount_changed:
            title = "Preiswert geändert"
            explanation = "Der Preiswert wurde geändert."
            note = None
        elif periods_changed:
            title = "Preiszeitraum aktualisiert"
            explanation = (
                "Der Preiswert selbst wurde nicht geändert. Das BfArM hat den bisherigen "
                "Preiszeitraum angepasst oder einen neuen Preiszeitraum mit identischem Preis angelegt."
            )
            note = "Hinweis: Der Preiswert selbst wurde nicht verändert."
        else:
            title = "Keine sichtbare Preisänderung"
            explanation = (
                "Die gespeicherten Vergütungsdaten unterscheiden sich technisch, daraus lässt sich "
                "aber keine sichtbare fachliche Preisänderung ableiten."
            )
            note = None

        return {
            "title": title,
            "note": note,
            "explanation": explanation,
            "before_lines": before_lines or ["Keine Preisangaben gefunden"],
            "after_lines": after_lines or ["Keine Preisangaben gefunden"],
            "show_raw": title == "Keine sichtbare Preisänderung",
            "visible_change": periods_changed or amount_changed,
        }

    return {
        "title": "Technische Änderung in Preis-/Vergütungsdaten",
        "note": None,
        "explanation": (
            "Die Datenstruktur zur Vergütung wurde geändert. Eine fachliche Preisänderung "
            "konnte nicht eindeutig abgeleitet werden."
        ),
        "before_lines": ["Nicht eindeutig interpretierbare Vergütungsdaten"],
        "after_lines": ["Nicht eindeutig interpretierbare Vergütungsdaten"],
        "show_raw": True,
        "visible_change": False,
    }


def extract_price_periods(value: Any) -> list[dict[str, str | None]]:
    periods = []
    for item in ensure_list(value):
        if not isinstance(item, dict):
            continue
        period = find_period(item) or {}
        amounts = find_price_amounts(item)
        text_amounts = find_amounts_in_text(item)
        amount = first_present_value(amounts + text_amounts)
        periods.append(
            {
                "amount": amount,
                "start": format_date_value(period.get("start")),
                "end": format_date_value(period.get("end")),
            }
        )
    return periods


def ensure_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def find_period(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        for key in ("effective_period", "effectivePeriod", "period"):
            item = value.get(key)
            if isinstance(item, dict) and (item.get("start") or item.get("end")):
                return item
        for item in value.values():
            found = find_period(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_period(item)
            if found:
                return found
    return None


def find_price_amounts(value: Any) -> list[str]:
    amounts = []
    if isinstance(value, dict):
        currency = value.get("currency")
        amount = value.get("value")
        if currency and isinstance(amount, (int, float, str)) and not isinstance(amount, bool):
            amounts.append(f"{format_amount_value(amount)} {currency}")
        for item in value.values():
            amounts.extend(find_price_amounts(item))
    elif isinstance(value, list):
        for item in value:
            amounts.extend(find_price_amounts(item))
    return unique_values(amounts)


def find_amounts_in_text(value: Any) -> list[str]:
    text_values = []
    if isinstance(value, dict):
        for item in value.values():
            text_values.extend(find_amounts_in_text(item))
    elif isinstance(value, list):
        for item in value:
            text_values.extend(find_amounts_in_text(item))
    elif isinstance(value, str):
        for amount, currency in re.findall(r"(\d+(?:[.,]\d{1,2})?)\s*(€|EUR)", value, flags=re.IGNORECASE):
            text_values.append(f"{format_amount_value(amount)} {'EUR' if currency.upper() == 'EUR' else currency}")
    return unique_values(text_values)


def price_period_lines(periods: list[dict[str, str | None]]) -> list[str]:
    lines = []
    for index, period in enumerate(periods, start=1):
        amount = period.get("amount") or "Preis nicht angegeben"
        validity = format_validity(period.get("start"), period.get("end"))
        lines.append(f"Preiszeitraum {index}: {amount}, {validity}")
    return lines


def format_validity(start: str | None, end: str | None) -> str:
    if start and end:
        return f"gültig von {start} bis {end}"
    if start:
        return f"gültig ab {start}"
    if end:
        return f"gültig bis {end}"
    return "Gültigkeitszeitraum nicht angegeben"


def format_date_value(value: Any) -> str | None:
    if not value:
        return None
    text = str(value)
    for candidate in (text[:10], text):
        try:
            return datetime.strptime(candidate, "%Y-%m-%d").strftime("%d.%m.%Y")
        except ValueError:
            continue
    parsed = parse_datetime(text)
    if parsed:
        return parsed.astimezone(DISPLAY_TIMEZONE).strftime("%d.%m.%Y")
    return text


def format_amount_value(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    if text.endswith(".0"):
        return text[:-2]
    return text.replace(",", ".")


def lines_to_html(lines: list[str]) -> str:
    if not lines:
        return "<p><em>Keine Angaben</em></p>"
    items = "".join(f"<li>{html.escape(line)}</li>" for line in lines)
    return f"<ul>{items}</ul>"


def normalize_lines(lines: list[str]) -> list[str]:
    return [" ".join(line.lower().split()) for line in lines]


def first_present_value(values: list[str]) -> str | None:
    for value in values:
        if value:
            return value
    return None


def unique_values(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def render_before_after_html(before_html: str, after_html: str, stacked: bool = False) -> None:
    grid_class = "before-after-grid before-after-grid-stacked" if stacked else "before-after-grid"
    st.markdown(
        f"""
        <style>
        .before-after-grid {{
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.85rem;
            margin-top: 0.35rem;
        }}
        .before-after-card {{
            border: 1px solid rgba(148, 163, 184, 0.45);
            border-radius: 8px;
            padding: 0.85rem;
            background: rgba(148, 163, 184, 0.07);
            min-width: 0;
        }}
        .before-after-label {{
            color: var(--diga-header-muted, #4b5563);
            font-size: 0.84rem;
            font-weight: 700;
            letter-spacing: 0.02em;
            margin-bottom: 0.45rem;
            text-transform: uppercase;
        }}
        .before-after-content {{
            color: inherit;
            line-height: 1.65;
            overflow-wrap: anywhere;
            white-space: normal;
        }}
        .before-after-content p {{
            margin: 0;
        }}
        .before-after-grid-stacked {{
            grid-template-columns: 1fr;
        }}
        @media (max-width: 720px) {{
            .before-after-grid {{
                grid-template-columns: 1fr;
            }}
        }}
        </style>
        <div class="{grid_class}">
            <section class="before-after-card">
                <div class="before-after-label">Vorher</div>
                <div class="before-after-content">{before_html}</div>
            </section>
            <section class="before-after-card">
                <div class="before-after-label">Nachher</div>
                <div class="before-after-content">{after_html}</div>
            </section>
        </div>
        """,
        unsafe_allow_html=True,
    )


def value_to_html(value: Any) -> str:
    if value is None:
        return "<p><em>Kein Wert vorhanden</em></p>"
    if isinstance(value, dict):
        rows = [
            f"<p><strong>{html.escape(field_label(str(key)))}:</strong> {html.escape(format_inline_value(item))}</p>"
            for key, item in value.items()
            if item is not None
        ]
        return "".join(rows) or "<p><em>Keine Angaben</em></p>"
    if isinstance(value, list):
        if not value:
            return "<p><em>Keine Einträge</em></p>"
        items = "".join(f"<li>{html.escape(format_inline_value(item))}</li>" for item in value)
        return f"<ul>{items}</ul>"
    return f"<p>{render_inline_value(value)}</p>"


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
    if is_metadata_event(event):
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
        if event_or_field_name.get("user_facing_field_label"):
            return str(event_or_field_name["user_facing_field_label"])
        context_label = text_context_label(event_or_field_name)
        if context_label:
            return context_label
        field_name = event_field_name(event_or_field_name)
    else:
        field_name = event_or_field_name
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
        business_events = [
            event
            for event in all_group_events
            if not is_metadata_event(event) and has_user_visible_change(event)
        ]
        business_events = deduplicate_events(business_events)
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
    if field_name == "raw_public_fhir" or field_name.startswith("raw_public_fhir."):
        return True
    return any(
        marker in field_name
        for marker in ("last_updated", "updated_at", "timestamp", "checked_sources")
    )


def has_user_visible_change(event: dict[str, Any]) -> bool:
    if event.get("change_type") == "price_change":
        return bool(analyze_price_change(event_previous_value(event), event_new_value(event))["visible_change"])
    return normalize_display_value(event_previous_value(event)) != normalize_display_value(event_new_value(event))


def deduplicate_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduplicated = []
    seen = set()
    for event in events:
        signature = (
            event_field_name(event),
            normalize_display_value(event_previous_value(event)),
            normalize_display_value(event_new_value(event)),
        )
        if signature in seen:
            continue
        seen.add(signature)
        deduplicated.append(event)
    return deduplicated


def normalize_display_value(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(sorted(normalize_display_value(item) for item in value))
    if isinstance(value, dict):
        return "\n".join(
            f"{key}:{normalize_display_value(item)}"
            for key, item in sorted(value.items())
            if item is not None
        )
    return " ".join(str(value).split())


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
