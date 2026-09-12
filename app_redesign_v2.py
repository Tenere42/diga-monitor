"""Second mobile-first DiGA Tracker redesign prototype.

This version focuses on a simple smartphone experience while reusing the proven
monitoring and change-detection logic from ``app.py``. Production ``app.py`` is
not modified on this branch.
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


QUICK_RANGES: dict[str, int | None] = {
    "7 Tage": 7,
    "30 Tage": 30,
    "90 Tage": 90,
    "Alle": None,
}

CHANGE_FILTERS: dict[str, set[str] | None] = {
    "Alle": None,
    "Neu": {"new_diga"},
    "Status": {"status_change"},
    "Preis": {"price_change"},
    "Inhalt": {"text_change", "visible_diff_unresolved", "other_field_change"},
    "Gestrichen": {"removed_diga"},
}

CHANGE_LABELS = {
    "new_diga": "Neu aufgenommen",
    "removed_diga": "Gestrichen",
    "status_change": "Status geändert",
    "price_change": "Preis geändert",
    "text_change": "Inhalt geändert",
    "visible_diff_unresolved": "Inhalt geändert",
    "other_field_change": "Inhalt geändert",
}



def main() -> None:
    st.set_page_config(
        page_title="DiGA Tracker",
        page_icon="🔎",
        layout="centered",
        initial_sidebar_state="collapsed",
    )
    inject_styles()

    if st.query_params.get("view") == "datenschutz" and is_legal_content_ready():
        render_compact_header()
        legacy.render_datenschutz_page()
        legacy.render_public_footer()
        return

    if st.query_params.get("view") == "confirmed" and is_legal_content_ready():
        render_compact_header()
        legacy.render_subscription_confirmed_page()
        legacy.render_public_footer()
        return

    events, scan_history = legacy.load_dashboard_data(
        str(DEFAULT_CHANGES_DIR),
        change_files_signature(DEFAULT_CHANGES_DIR),
        str(DEFAULT_SCAN_HISTORY_PATH),
        scan_history_signature(DEFAULT_SCAN_HISTORY_PATH),
    )

    render_hero(events, scan_history)
    render_alert_signup()
    filtered = render_filters(events)
    render_feed(filtered)
    render_footer()



def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --dt-bg: #f6f7f9;
            --dt-surface: #ffffff;
            --dt-text: #101828;
            --dt-muted: #667085;
            --dt-border: #eaecf0;
            --dt-soft: #f2f4f7;
            --dt-accent: #111827;
            --dt-green: #067647;
            --dt-green-bg: #ecfdf3;
            --dt-red: #b42318;
            --dt-red-bg: #fef3f2;
            --dt-blue: #175cd3;
            --dt-blue-bg: #eff8ff;
            --dt-amber: #b54708;
            --dt-amber-bg: #fffaeb;
        }

        .stApp { background: var(--dt-bg); }
        .block-container {
            max-width: 720px;
            padding: 0.8rem 0.9rem 3rem;
        }
        #MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; }

        .dt-brand {
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:1rem;
            padding:0.2rem 0 0.55rem;
        }
        .dt-brand-name {
            font-size:0.86rem;
            font-weight:800;
            letter-spacing:-0.01em;
            color:var(--dt-text);
        }
        .dt-brand-source {
            color:var(--dt-muted);
            font-size:0.75rem;
            text-align:right;
        }

        .dt-hero {
            padding:0.8rem 0 0.9rem;
        }
        .dt-kicker {
            color:var(--dt-blue);
            font-size:0.76rem;
            font-weight:800;
            letter-spacing:0.08em;
            text-transform:uppercase;
            margin-bottom:0.35rem;
        }
        .dt-title {
            margin:0;
            color:var(--dt-text);
            font-size:clamp(2.35rem, 12vw, 4.5rem);
            line-height:0.94;
            letter-spacing:-0.055em;
            font-weight:850;
        }
        .dt-subtitle {
            color:var(--dt-muted);
            font-size:1rem;
            line-height:1.5;
            margin:0.75rem 0 0;
            max-width:34rem;
        }

        .dt-health {
            display:flex;
            align-items:center;
            gap:0.45rem;
            margin-top:0.8rem;
            color:var(--dt-muted);
            font-size:0.82rem;
            line-height:1.4;
        }
        .dt-dot {
            width:8px;
            height:8px;
            border-radius:50%;
            background:#12b76a;
            flex:0 0 auto;
        }

        .dt-section-title {
            color:var(--dt-text);
            font-size:1.05rem;
            font-weight:800;
            letter-spacing:-0.02em;
            margin:1.5rem 0 0.55rem;
        }

        .dt-card {
            background:var(--dt-surface);
            border:1px solid var(--dt-border);
            border-radius:18px;
            padding:1rem;
            margin:0.7rem 0;
            box-shadow:0 1px 2px rgba(16,24,40,.025);
        }
        .dt-meta {
            color:var(--dt-muted);
            font-size:0.78rem;
            line-height:1.4;
            margin-bottom:0.28rem;
        }
        .dt-name {
            color:var(--dt-text);
            font-size:1.08rem;
            line-height:1.25;
            font-weight:800;
            letter-spacing:-0.02em;
        }
        .dt-badge {
            display:inline-flex;
            align-items:center;
            margin-top:0.62rem;
            border-radius:999px;
            padding:0.28rem 0.58rem;
            font-size:0.74rem;
            font-weight:800;
            background:var(--dt-soft);
            color:var(--dt-text);
        }
        .dt-summary {
            color:var(--dt-text);
            font-size:0.96rem;
            line-height:1.5;
            margin-top:0.68rem;
        }

        .dt-compare {
            display:grid;
            grid-template-columns:1fr;
            gap:0.55rem;
            margin-top:0.78rem;
        }
        .dt-compare-box {
            border:1px solid var(--dt-border);
            border-radius:13px;
            padding:0.72rem 0.78rem;
            min-width:0;
        }
        .dt-before { background:var(--dt-red-bg); }
        .dt-after { background:var(--dt-green-bg); }
        .dt-compare-label {
            font-size:0.7rem;
            font-weight:850;
            letter-spacing:0.07em;
            text-transform:uppercase;
            margin-bottom:0.32rem;
        }
        .dt-before .dt-compare-label { color:var(--dt-red); }
        .dt-after .dt-compare-label { color:var(--dt-green); }
        .dt-compare-value {
            color:var(--dt-text);
            font-size:0.9rem;
            line-height:1.5;
            overflow-wrap:anywhere;
            white-space:normal;
        }
        .dt-compare-value mark.removed {
            background:#fee4e2;
            color:var(--dt-red);
            text-decoration:line-through;
            padding:0 2px;
        }
        .dt-compare-value mark.added {
            background:#d1fadf;
            color:var(--dt-green);
            padding:0 2px;
        }

        .dt-link {
            display:inline-flex;
            margin-top:0.7rem;
            font-size:0.84rem;
            font-weight:700;
            color:var(--dt-blue);
            text-decoration:none;
        }

        .dt-empty {
            background:var(--dt-surface);
            border:1px solid var(--dt-border);
            border-radius:18px;
            padding:1.15rem;
            color:var(--dt-muted);
            text-align:center;
            line-height:1.5;
        }

        div[data-testid="stForm"] {
            background:var(--dt-surface);
            border:1px solid var(--dt-border);
            border-radius:18px;
            padding:0.9rem;
        }
        .stButton button, .stFormSubmitButton button {
            min-height:46px;
            border-radius:12px;
            font-weight:800;
        }
        div[data-baseweb="select"] > div,
        .stTextInput input,
        .stDateInput input {
            min-height:44px;
            border-radius:12px !important;
        }
        div[data-testid="stSelectbox"] label,
        div[data-testid="stTextInput"] label {
            font-size:0.78rem;
        }

        @media (max-width: 640px) {
            .block-container { padding-left:0.72rem; padding-right:0.72rem; }
            .dt-brand-source { display:none; }
            .dt-card { padding:0.9rem; border-radius:16px; }
            .dt-title { font-size:clamp(2.6rem, 15vw, 3.65rem); }
        }
        @media (min-width: 700px) {
            .block-container { padding-top:1.7rem; }
            .dt-compare { grid-template-columns:1fr 1fr; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )



def render_compact_header() -> None:
    st.markdown(
        "<div class='dt-brand'><div class='dt-brand-name'>DiGA Tracker</div>"
        "<div class='dt-brand-source'>Quelle: BfArM DiGA-Verzeichnis</div></div>",
        unsafe_allow_html=True,
    )



def render_hero(events: list[dict[str, Any]], scan_history: list[dict[str, Any]]) -> None:
    render_compact_header()
    last_scan = legacy.latest_scan_timestamp(scan_history)
    latest_change = legacy.latest_real_change_timestamp(events)
    st.markdown(
        "<section class='dt-hero'>"
        "<div class='dt-kicker'>Änderungen im Blick behalten</div>"
        "<h1 class='dt-title'>DiGA Tracker</h1>"
        "<p class='dt-subtitle'>Neue DiGA, Statuswechsel, Preise und relevante Inhaltsänderungen – übersichtlich an einem Ort.</p>"
        "<div class='dt-health'><span class='dt-dot'></span>"
        f"<span>Aktiv · letzter Scan {html.escape(last_scan)} · letzte Änderung {html.escape(latest_change)}</span></div>"
        "</section>",
        unsafe_allow_html=True,
    )



def render_alert_signup() -> None:
    if not is_legal_content_ready():
        return

    st.markdown("<div class='dt-section-title'>Keine Änderung verpassen</div>", unsafe_allow_html=True)
    st.caption("Kostenloser E-Mail Alert bei relevanten Änderungen im DiGA-Verzeichnis.")

    with st.form("mobile_first_alert_signup", clear_on_submit=True):
        email = st.text_input("E-Mail", placeholder="name@beispiel.de", label_visibility="collapsed")
        consent = st.checkbox("Ich akzeptiere die Datenschutzerklärung und möchte Alerts erhalten.")
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



def render_filters(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    st.markdown("<div class='dt-section-title'>Änderungen</div>", unsafe_allow_html=True)

    range_label = st.segmented_control(
        "Zeitraum",
        options=list(QUICK_RANGES),
        default="30 Tage",
        label_visibility="collapsed",
    ) or "30 Tage"

    type_label = st.segmented_control(
        "Änderungstyp",
        options=list(CHANGE_FILTERS),
        default="Alle",
        label_visibility="collapsed",
    ) or "Alle"

    diga_names = sorted({str(event.get("diga_name")) for event in events if event.get("diga_name")})
    selected_diga = st.selectbox(
        "DiGA",
        ["Alle DiGA", *diga_names],
        label_visibility="collapsed",
        placeholder="DiGA filtern",
    ) if diga_names else "Alle DiGA"

    filtered = list(events)
    days = QUICK_RANGES[range_label]
    if days is not None:
        today = date.today()
        filtered = [
            event
            for event in filtered
            if (event_day := legacy.event_date(event)) is not None
            and 0 <= (today - event_day).days < days
        ]

    allowed_types = CHANGE_FILTERS[type_label]
    if allowed_types is not None:
        filtered = [event for event in filtered if event.get("change_type") in allowed_types]

    if selected_diga != "Alle DiGA":
        filtered = [event for event in filtered if event.get("diga_name") == selected_diga]

    return filtered



def render_feed(events: list[dict[str, Any]]) -> None:
    groups = legacy.group_events_by_diga(events)
    st.caption(f"{len(groups)} {'Treffer' if len(groups) != 1 else 'Treffer'}")

    if not groups:
        st.markdown(
            "<div class='dt-empty'><strong>Keine Änderungen gefunden.</strong><br>"
            "Wähle einen längeren Zeitraum oder einen anderen Filter.</div>",
            unsafe_allow_html=True,
        )
        return

    for group in groups:
        render_group(group)



def render_group(group: dict[str, Any]) -> None:
    events = group.get("events") or []
    if not events:
        return

    primary = choose_primary_event(events)
    remaining = [event for event in events if event is not primary]
    manufacturer = group.get("manufacturer") or "Hersteller nicht angegeben"
    detected = legacy.format_datetime(group.get("detected_at"))
    summary = public_change_summary(primary)
    label = CHANGE_LABELS.get(str(primary.get("change_type")), "Inhalt geändert")

    st.markdown(
        "<article class='dt-card'>"
        f"<div class='dt-meta'>{html.escape(str(manufacturer))} · {html.escape(detected)}</div>"
        f"<div class='dt-name'>{html.escape(str(group.get('diga_name') or 'Unbekannte DiGA'))}</div>"
        f"<div class='dt-badge'>{html.escape(label)}</div>"
        f"<div class='dt-summary'>{html.escape(summary)}</div>"
        "</article>",
        unsafe_allow_html=True,
    )

    render_compare(primary)

    if remaining:
        with st.expander(f"{len(remaining)} weitere Änderung{'en' if len(remaining) != 1 else ''}"):
            for extra in remaining:
                st.markdown(f"**{CHANGE_LABELS.get(str(extra.get('change_type')), 'Inhalt geändert')}**")
                st.caption(public_change_summary(extra))
                render_compare(extra)

    if group.get("bfarm_directory_url"):
        st.markdown(
            f"<a class='dt-link' href='{html.escape(str(group['bfarm_directory_url']))}' target='_blank'>BfArM Eintrag öffnen ↗</a>",
            unsafe_allow_html=True,
        )



def choose_primary_event(events: list[dict[str, Any]]) -> dict[str, Any]:
    priority = {
        "new_diga": 0,
        "removed_diga": 1,
        "status_change": 2,
        "price_change": 3,
        "text_change": 4,
        "visible_diff_unresolved": 5,
        "other_field_change": 6,
    }
    return min(events, key=lambda event: priority.get(str(event.get("change_type")), 99))



def public_change_summary(event: dict[str, Any]) -> str:
    change_type = event.get("change_type")
    before = legacy.event_previous_value(event)
    after = legacy.event_new_value(event)

    if change_type == "new_diga":
        return "Neu im DiGA-Verzeichnis aufgenommen."
    if change_type == "removed_diga":
        return "Nicht mehr im aktuellen DiGA-Verzeichnis gelistet."
    if change_type == "status_change":
        return f"Status von {clean_value(before)} auf {clean_value(after)} geändert."
    if change_type == "price_change":
        analysis = legacy.analyze_price_change(before, after)
        return str(analysis.get("title") or "Preisangaben wurden geändert.")
    if change_type in {"text_change", "visible_diff_unresolved", "other_field_change"}:
        field = safe_public_field_label(event)
        return f"{field} wurde aktualisiert." if field else "Ein Inhalt im DiGA-Eintrag wurde aktualisiert."
    return "Der DiGA-Eintrag wurde aktualisiert."



def safe_public_field_label(event: dict[str, Any]) -> str | None:
    label = legacy.field_label(event).strip()
    bad_fragments = (
        "nicht eindeutig",
        "interner schlüssel",
        "unbekannter bereich",
    )
    if not label or any(fragment in label.lower() for fragment in bad_fragments):
        return None
    return label.split(" > ")[-1]



def render_compare(event: dict[str, Any]) -> None:
    change_type = event.get("change_type")

    if change_type == "new_diga":
        render_compare_html("Nicht gelistet", "Neu gelistet")
        return
    if change_type == "removed_diga":
        render_compare_html("Im Verzeichnis gelistet", "Nicht mehr gelistet")
        return

    before = legacy.event_previous_value(event)
    after = legacy.event_new_value(event)

    if change_type == "text_change" and isinstance(event.get("word_diff"), list):
        before_html, after_html = text_diff_html(event)
        render_compare_html(before_html, after_html, raw_html=True)
        return

    if change_type == "price_change":
        analysis = legacy.analyze_price_change(before, after)
        before_lines = analysis.get("before_lines") or []
        after_lines = analysis.get("after_lines") or []
        render_compare_html("<br>".join(map(html.escape, before_lines)), "<br>".join(map(html.escape, after_lines)), raw_html=True)
        return

    render_compare_html(clean_value(before), clean_value(after))



def text_diff_html(event: dict[str, Any]) -> tuple[str, str]:
    tokens = event.get("word_diff") or []
    before_tokens, after_tokens, _ = legacy.compact_text_diff(tokens)
    return render_tokens(before_tokens, "before"), render_tokens(after_tokens, "after")



def render_tokens(tokens: list[dict[str, str]], side: str) -> str:
    parts: list[str] = []
    for token in tokens:
        op = token.get("op")
        text = html.escape(str(token.get("text") or ""))
        if op == "ellipsis":
            parts.append("…")
        elif op == "delete" and side == "before":
            parts.append(f"<mark class='removed'>{text}</mark>")
        elif op == "insert" and side == "after":
            parts.append(f"<mark class='added'>{text}</mark>")
        elif op == "equal":
            parts.append(text)
    return " ".join(parts)



def render_compare_html(before: str, after: str, raw_html: bool = False) -> None:
    before_value = before if raw_html else html.escape(before)
    after_value = after if raw_html else html.escape(after)
    st.markdown(
        "<div class='dt-compare'>"
        "<section class='dt-compare-box dt-before'>"
        "<div class='dt-compare-label'>Vorher</div>"
        f"<div class='dt-compare-value'>{before_value}</div>"
        "</section>"
        "<section class='dt-compare-box dt-after'>"
        "<div class='dt-compare-label'>Nachher</div>"
        f"<div class='dt-compare-value'>{after_value}</div>"
        "</section>"
        "</div>",
        unsafe_allow_html=True,
    )



def clean_value(value: Any) -> str:
    if value is None or value == "":
        return "Keine Angabe"
    if isinstance(value, str):
        return legacy.format_value(value)
    if isinstance(value, dict):
        preferred_keys = ("status", "name", "indication", "manufacturer")
        compact = [f"{key}: {value[key]}" for key in preferred_keys if value.get(key)]
        if compact:
            return " · ".join(compact)
    if isinstance(value, list):
        return ", ".join(map(str, value[:5])) + (" …" if len(value) > 5 else "")
    text = str(value)
    return text if len(text) <= 500 else text[:497] + "…"



def render_footer() -> None:
    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
    if is_legal_content_ready():
        st.markdown(
            "<div style='font-size:.8rem;color:#667085;padding-top:.8rem;border-top:1px solid #eaecf0;'>"
            "DiGA Tracker · <a href='?view=datenschutz' target='_self' style='color:#667085'>Datenschutz</a>"
            "</div>",
            unsafe_allow_html=True,
        )


if __name__ == "__main__":
    main()
