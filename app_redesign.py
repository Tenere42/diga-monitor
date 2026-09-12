"""Mobile-first DiGA Tracker redesign prototype.

This prototype intentionally reuses the proven data/change-detection helpers from
``app.py`` while replacing the public information architecture and presentation.
It is isolated on the redesign branch and does not alter production behavior.
"""

from __future__ import annotations

import html
from datetime import date
from typing import Any

import streamlit as st

import app as legacy
from src.change_events import DEFAULT_CHANGES_DIR
from src.dashboard_cache import change_files_signature, scan_history_signature
from src.legal_content import is_legal_content_ready
from src.scan_history import DEFAULT_SCAN_HISTORY_PATH
from src.subscribers import SignupOutcome, request_double_optin


QUICK_RANGES = {
    "7 Tage": 7,
    "30 Tage": 30,
    "Alle": None,
}

CHANGE_FILTERS = {
    "Alle": None,
    "Neu": {"new_diga"},
    "Status": {"status_change"},
    "Preis": {"price_change"},
    "Inhalt": {"text_change", "visible_diff_unresolved", "other_field_change"},
    "Gestrichen": {"removed_diga"},
}


def main() -> None:
    st.set_page_config(page_title="DiGA Tracker", layout="centered", initial_sidebar_state="collapsed")
    inject_styles()

    if st.query_params.get("view") == "datenschutz" and is_legal_content_ready():
        legacy.render_datenschutz_page()
        legacy.render_public_footer()
        return
    if st.query_params.get("view") == "confirmed" and is_legal_content_ready():
        legacy.render_subscription_confirmed_page()
        legacy.render_public_footer()
        return

    render_hero()
    render_alert_card()

    events, scan_history = legacy.load_dashboard_data(
        str(DEFAULT_CHANGES_DIR),
        change_files_signature(DEFAULT_CHANGES_DIR),
        str(DEFAULT_SCAN_HISTORY_PATH),
        scan_history_signature(DEFAULT_SCAN_HISTORY_PATH),
    )

    render_tracker_health(events, scan_history)
    filtered = render_smart_filters(events)
    render_feed(filtered)
    legacy.render_public_footer()


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --tracker-bg: #f7f8fa;
            --tracker-surface: #ffffff;
            --tracker-border: #e8eaee;
            --tracker-text: #111827;
            --tracker-muted: #667085;
            --tracker-soft: #f2f4f7;
            --tracker-green: #157f3b;
            --tracker-green-bg: #eefbf2;
            --tracker-red: #b42318;
            --tracker-red-bg: #fff3f2;
            --tracker-accent: #111827;
        }

        html, body, [class*="css"] {
            color: var(--tracker-text);
        }

        .stApp {
            background: var(--tracker-bg);
        }

        .block-container {
            max-width: 760px;
            padding-top: 1.15rem;
            padding-bottom: 3rem;
        }

        #MainMenu, footer, header[data-testid="stHeader"] {
            visibility: hidden;
        }

        .tracker-hero {
            padding: 0.35rem 0 0.85rem;
        }
        .tracker-kicker {
            color: var(--tracker-muted);
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.09em;
            text-transform: uppercase;
            margin-bottom: 0.35rem;
        }
        .tracker-title {
            font-size: clamp(2.15rem, 9vw, 3.6rem);
            line-height: 0.98;
            letter-spacing: -0.045em;
            margin: 0;
            font-weight: 800;
        }
        .tracker-subtitle {
            font-size: 1.03rem;
            line-height: 1.5;
            color: var(--tracker-muted);
            margin: 0.8rem 0 0;
            max-width: 36rem;
        }

        .tracker-card {
            background: var(--tracker-surface);
            border: 1px solid var(--tracker-border);
            border-radius: 18px;
            padding: 1rem;
            margin: 0.8rem 0;
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.03);
        }

        .tracker-health {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            color: var(--tracker-muted);
            font-size: 0.88rem;
            padding: 0.15rem 0 0.45rem;
            overflow-wrap: anywhere;
        }
        .tracker-dot {
            width: 8px;
            height: 8px;
            border-radius: 999px;
            background: #22c55e;
            flex: 0 0 auto;
        }

        .feed-head {
            display: flex;
            align-items: end;
            justify-content: space-between;
            gap: 1rem;
            margin: 1.35rem 0 0.5rem;
        }
        .feed-title {
            font-size: 1.25rem;
            font-weight: 750;
            letter-spacing: -0.02em;
        }
        .feed-count {
            color: var(--tracker-muted);
            font-size: 0.85rem;
            white-space: nowrap;
        }

        .change-card {
            background: var(--tracker-surface);
            border: 1px solid var(--tracker-border);
            border-radius: 18px;
            padding: 1rem;
            margin: 0.72rem 0;
        }
        .change-topline {
            color: var(--tracker-muted);
            font-size: 0.8rem;
            line-height: 1.4;
            margin-bottom: 0.3rem;
        }
        .change-name {
            font-weight: 780;
            font-size: 1.08rem;
            line-height: 1.25;
            letter-spacing: -0.015em;
        }
        .change-label {
            display: inline-flex;
            margin-top: 0.7rem;
            border-radius: 999px;
            background: var(--tracker-soft);
            padding: 0.28rem 0.55rem;
            font-size: 0.78rem;
            font-weight: 700;
        }
        .change-summary {
            font-size: 0.98rem;
            line-height: 1.55;
            margin: 0.72rem 0 0.45rem;
        }

        .compare-stack {
            display: grid;
            grid-template-columns: 1fr;
            gap: 0.55rem;
            margin-top: 0.75rem;
        }
        .compare-card {
            border-radius: 13px;
            border: 1px solid var(--tracker-border);
            padding: 0.75rem 0.8rem;
            min-width: 0;
        }
        .compare-before {
            background: #fbfbfc;
        }
        .compare-after {
            background: #fbfbfc;
        }
        .compare-label {
            color: var(--tracker-muted);
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            font-weight: 800;
            margin-bottom: 0.35rem;
        }
        .compare-value {
            line-height: 1.55;
            overflow-wrap: anywhere;
            font-size: 0.92rem;
        }
        .compare-value mark.removed {
            background: var(--tracker-red-bg);
            color: var(--tracker-red);
            text-decoration: line-through;
        }
        .compare-value mark.added {
            background: var(--tracker-green-bg);
            color: var(--tracker-green);
        }

        .bfarm-link {
            margin-top: 0.7rem;
            font-size: 0.86rem;
        }
        .bfarm-link a {
            color: var(--tracker-text);
            text-decoration: none;
            font-weight: 650;
        }

        div[data-testid="stForm"] {
            background: var(--tracker-surface);
            border: 1px solid var(--tracker-border);
            border-radius: 18px;
            padding: 0.9rem;
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.03);
        }

        div[data-baseweb="select"] > div,
        .stTextInput input,
        .stDateInput input {
            border-radius: 12px !important;
        }

        .stButton button,
        .stFormSubmitButton button {
            min-height: 44px;
            border-radius: 12px;
            font-weight: 700;
        }

        @media (min-width: 700px) {
            .block-container {
                padding-top: 2rem;
            }
            .compare-stack {
                grid-template-columns: 1fr 1fr;
            }
            .tracker-card,
            .change-card {
                padding: 1.15rem 1.2rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero() -> None:
    st.markdown(
        """
        <section class="tracker-hero">
            <div class="tracker-kicker">BfArM DiGA-Verzeichnis</div>
            <h1 class="tracker-title">DiGA Tracker</h1>
            <p class="tracker-subtitle">Alle relevanten Änderungen im DiGA-Verzeichnis. Einfach nachvollziehbar.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_alert_card() -> None:
    if not is_legal_content_ready():
        return

    st.markdown("#### Keine Änderung verpassen")
    st.caption("Wir schicken dir einen Alert, sobald der DiGA Tracker eine relevante Änderung erkennt.")

    with st.form("redesign_newsletter_signup", clear_on_submit=True):
        email = st.text_input("E-Mail", placeholder="name@beispiel.de", label_visibility="collapsed")
        consent = st.checkbox("Ich akzeptiere die Datenschutzerklärung und möchte DiGA Tracker Alerts erhalten.")
        submitted = st.form_submit_button("Alerts abonnieren", use_container_width=True)

    if not submitted:
        return
    if not consent:
        st.warning("Bitte bestätige die Datenschutzerklärung.")
        return

    result = request_double_optin(email)
    if result.outcome == SignupOutcome.CONFIRMATION_SENT:
        st.success(result.message_de)
    elif result.outcome == SignupOutcome.ALREADY_PENDING_OR_CONFIRMED:
        st.info(result.message_de)
    elif result.outcome == SignupOutcome.INVALID_EMAIL:
        st.warning(result.message_de)
    else:
        st.error(result.message_de)


def render_tracker_health(events: list[dict[str, Any]], scan_history: list[dict[str, Any]]) -> None:
    last_scan = legacy.latest_scan_timestamp(scan_history)
    st.markdown(
        '<div class="tracker-health">'
        '<span class="tracker-dot"></span>'
        f'<span>Tracker aktiv · letzter Scan {html.escape(last_scan)} · Tracking seit 31.05.2026</span>'
        '</div>',
        unsafe_allow_html=True,
    )


def render_smart_filters(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    st.markdown("#### Änderungen")

    range_col, type_col = st.columns(2)
    with range_col:
        range_label = st.selectbox("Zeitraum", list(QUICK_RANGES), index=1)
    with type_col:
        type_label = st.selectbox("Änderung", list(CHANGE_FILTERS), index=0)

    diga_names = sorted({str(event.get("diga_name")) for event in events if event.get("diga_name")})
    selected_diga = st.selectbox("DiGA", ["Alle DiGA", *diga_names]) if diga_names else "Alle DiGA"

    filtered = list(events)

    days = QUICK_RANGES[range_label]
    if days is not None:
        today = date.today()
        filtered = [
            event
            for event in filtered
            if (event_day := legacy.event_date(event)) is not None and 0 <= (today - event_day).days < days
        ]

    allowed_types = CHANGE_FILTERS[type_label]
    if allowed_types is not None:
        filtered = [event for event in filtered if event.get("change_type") in allowed_types]

    if selected_diga != "Alle DiGA":
        filtered = [event for event in filtered if event.get("diga_name") == selected_diga]

    return filtered


def render_feed(events: list[dict[str, Any]]) -> None:
    groups = legacy.group_events_by_diga(events)
    st.markdown(
        f'<div class="feed-head"><div class="feed-title">Neueste Änderungen</div>'
        f'<div class="feed-count">{len(groups)} Treffer</div></div>',
        unsafe_allow_html=True,
    )

    if not groups:
        st.info("Keine Änderungen für diese Filter. Passe den Zeitraum oder Änderungstyp an.")
        return

    for group in groups:
        render_group(group)


def render_group(group: dict[str, Any]) -> None:
    events = group.get("events") or []
    if not events:
        return

    event = events[0]
    manufacturer = group.get("manufacturer") or "Hersteller nicht angegeben"
    detected = legacy.format_datetime(group.get("detected_at"))
    label = public_change_label(event)
    summary = public_change_summary(event)

    st.markdown(
        '<article class="change-card">'
        f'<div class="change-topline">{html.escape(str(manufacturer))} · {html.escape(detected)}</div>'
        f'<div class="change-name">{html.escape(str(group.get("diga_name") or "Unbekannte DiGA"))}</div>'
        f'<div class="change-label">{html.escape(label)}</div>'
        f'<div class="change-summary">{html.escape(summary)}</div>'
        '</article>',
        unsafe_allow_html=True,
    )

    render_standard_compare(event)

    if len(events) > 1:
        with st.expander(f"{len(events) - 1} weitere Änderung(en) anzeigen"):
            for extra in events[1:]:
                st.markdown(f"**{public_change_label(extra)}**")
                st.write(public_change_summary(extra))
                render_standard_compare(extra)

    if group.get("bfarm_directory_url"):
        st.markdown(
            f'<div class="bfarm-link"><a href="{html.escape(str(group["bfarm_directory_url"]))}" target="_blank">Beim BfArM öffnen ↗</a></div>',
            unsafe_allow_html=True,
        )


def public_change_label(event: dict[str, Any]) -> str:
    change_type = event.get("change_type")
    if change_type == "new_diga":
        return "Neu aufgenommen"
    if change_type == "removed_diga":
        return "Gestrichen"
    if change_type == "status_change":
        return "Status geändert"
    if change_type == "price_change":
        return "Preis geändert"
    return "Inhalt geändert"


def public_change_summary(event: dict[str, Any]) -> str:
    change_type = event.get("change_type")
    before = legacy.event_previous_value(event)
    after = legacy.event_new_value(event)

    if change_type == "new_diga":
        return "Neu im DiGA-Verzeichnis aufgenommen."
    if change_type == "removed_diga":
        return "Nicht mehr im aktuellen DiGA-Verzeichnis gelistet."
    if change_type == "status_change":
        return f"Status: {clean_value(before)} → {clean_value(after)}"
    if change_type == "price_change":
        analysis = legacy.analyze_price_change(before, after)
        return str(analysis.get("title") or "Preisangaben wurden geändert.")

    field = legacy.field_label(event)
    if legacy.UNRESOLVED_FIELD_LABEL in field or "nicht eindeutig" in field.lower():
        return "Der Inhalt des BfArM-Eintrags wurde geändert."
    return f"{field} wurde geändert."


def render_standard_compare(event: dict[str, Any]) -> None:
    change_type = event.get("change_type")
    before = legacy.event_previous_value(event)
    after = legacy.event_new_value(event)

    if change_type == "new_diga":
        before_html = "<em>Nicht gelistet</em>"
        after_html = "Neu aufgenommen"
    elif change_type == "removed_diga":
        before_html = "Im Verzeichnis gelistet"
        after_html = "<em>Nicht mehr gelistet</em>"
    elif change_type == "text_change" and isinstance(event.get("word_diff"), list):
        before_tokens, after_tokens, _ = legacy.compact_text_diff(event["word_diff"])
        before_html = render_diff(before_tokens, "before")
        after_html = render_diff(after_tokens, "after")
    else:
        before_html = html.escape(clean_value(before))
        after_html = html.escape(clean_value(after))

    st.markdown(
        '<div class="compare-stack">'
        '<section class="compare-card compare-before">'
        '<div class="compare-label">Vorher</div>'
        f'<div class="compare-value">{before_html}</div>'
        '</section>'
        '<section class="compare-card compare-after">'
        '<div class="compare-label">Nachher</div>'
        f'<div class="compare-value">{after_html}</div>'
        '</section>'
        '</div>',
        unsafe_allow_html=True,
    )


def render_diff(tokens: list[dict[str, str]], side: str) -> str:
    parts: list[str] = []
    for token in tokens:
        op = token.get("op")
        text = html.escape(str(token.get("text", "")))
        if op == "ellipsis":
            parts.append("…")
        elif op == "delete" and side == "before":
            parts.append(f'<mark class="removed">{text}</mark>')
        elif op == "insert" and side == "after":
            parts.append(f'<mark class="added">{text}</mark>')
        elif op == "equal":
            parts.append(text)
    return " ".join(parts)


def clean_value(value: Any) -> str:
    if value is None or value == "":
        return "Kein Wert"
    if isinstance(value, str):
        normalized = legacy.normalize_status_value(value)
        if normalized:
            return legacy.STATUS_VALUE_LABELS.get(normalized, value)
        return " ".join(value.split())
    return " ".join(legacy.format_inline_value(value).split())


if __name__ == "__main__":
    main()
