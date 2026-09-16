"""Presentation-only primitives for the DiGA Tracker Streamlit frontend.

No data loading, routing, session state, or newsletter behavior belongs here.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any


STYLESHEET_PATH = Path(__file__).resolve().parents[1] / "assets" / "styles.css"


def stylesheet_html() -> str:
    """Load trusted repository CSS independently of the process working directory."""
    return f"<style>{STYLESHEET_PATH.read_text(encoding='utf-8')}</style>"


def public_header_html(*, newsletter_ready: bool = False, homepage: bool = False) -> str:
    """Native links and a semantic mobile disclosure; no JavaScript or widget state."""
    about = "#about" if homepage else "./#about"
    signup = "#newsletter" if homepage else "./#newsletter"
    links = (
        '<a href="?view=changes" target="_self">Änderungen</a>'
        f'<a href="{about}" target="_self">Über uns</a>'
    )
    if newsletter_ready:
        links += f'<a class="diga-nav-cta" href="{signup}" target="_self">Updates abonnieren</a>'
    return (
        '<header class="diga-site-header">'
        '<a class="diga-brand" href="./" target="_self" aria-label="DiGA Tracker – Startseite">DiGA Tracker</a>'
        f'<nav class="diga-desktop-nav" aria-label="Hauptnavigation">{links}</nav>'
        '<details class="diga-mobile-menu"><summary>Menü</summary>'
        f'<nav aria-label="Mobile Navigation">{links}</nav></details>'
        '</header>'
    )


def hero_html(*, newsletter_ready: bool) -> str:
    primary = ('<a class="diga-button" href="#newsletter" target="_self">Updates abonnieren</a>'
               if newsletter_ready else "")
    return (
        '<section class="diga-hero" aria-labelledby="hero-title">'
        '<p class="diga-eyebrow">TRANSPARENT. AKTUELL. UNABHÄNGIG.</p>'
        '<h1 id="hero-title">Der DiGA Markt<br>auf einen Blick.</h1>'
        '<p class="diga-hero-copy">Wir verfolgen automatisch alle Änderungen im '
        'BfArM DiGA-Verzeichnis und halten dich auf dem Laufenden.</p>'
        f'<div class="diga-actions">{primary}'
        '<a class="diga-text-link" href="#about" target="_self">Mehr erfahren</a></div>'
        '</section>'
    )


def market_snapshot_html(cards: list[tuple[str, int | None]], note: str) -> str:
    blocks = ''.join(
        '<div class="diga-kpi">'
        f'<dt>{html.escape(label)}</dt>'
        f'<dd>{value if value is not None else "—"}</dd></div>'
        for label, value in cards
    )
    return (
        '<section class="diga-market" aria-labelledby="market-title">'
        '<h2 id="market-title">Der Markt in Zahlen</h2>'
        f'<dl class="diga-kpi-grid">{blocks}</dl>'
        f'<p class="diga-meta">{html.escape(note)}</p></section>'
    )


def recent_changes_html(items: list[dict[str, Any]]) -> str:
    rows = []
    for item in items:
        pills = ''.join(f'<span class="diga-pill">{html.escape(label)}</span>'
                        for label in item['labels'])
        manufacturer = (f'<p class="diga-meta">{html.escape(item["manufacturer"])}</p>'
                        if item['manufacturer'] else '')
        rows.append(
            '<li class="diga-recent-item"><article>'
            f'<time class="diga-meta" datetime="{html.escape(item["timestamp"], quote=True)}">'
            f'{html.escape(item["date_label"])}</time>'
            f'<h3>{html.escape(item["name"])}</h3>'
            f'<div class="diga-pills">{pills}</div>'
            f'<p class="diga-change-summary">{html.escape(item["summary"])}</p>'
            f'{manufacturer}'
            f'<a class="diga-text-link" href="?view=changes#{html.escape(item["anchor"], quote=True)}" '
            f'target="_self" aria-label="Details zu {html.escape(item["name"], quote=True)}">Details ansehen</a>'
            '</article></li>'
        )
    content = ('<ol class="diga-recent-list">' + ''.join(rows) + '</ol>' if rows else
               '<p class="diga-meta">Bisher keine fachlichen Änderungen erkannt.</p>')
    return (
        '<section class="diga-recent" aria-labelledby="recent-title">'
        '<h2 id="recent-title">Letzte Änderungen</h2>' + content +
        '<a class="diga-button diga-button-secondary" href="?view=changes" target="_self">'
        'Alle Änderungen ansehen</a></section>'
    )


def about_html() -> str:
    return (
        '<section id="about" class="diga-about" aria-labelledby="about-title">'
        '<p class="diga-eyebrow">ÜBER DIGA TRACKER</p>'
        '<h2 id="about-title">Was wir beobachten</h2>'
        '<p>DiGA Tracker verfolgt automatisch Änderungen im offiziellen '
        'DiGA-Verzeichnis des BfArM – darunter Aufnahmestatus, Preisangaben '
        'und Inhalte der Verzeichniseinträge.</p>'
        '<p>Wir zeigen, was sich zwischen zwei Prüfungen verändert hat. '
        'Zeitangaben beziehen sich auf die Erkennung durch unseren Monitor. '
        'DiGA Tracker ist ein unabhängiges Angebot und kein Angebot des BfArM.</p>'
        '<a class="diga-text-link" href="https://diga.bfarm.de/de/verzeichnis" '
        'target="_blank" rel="noopener noreferrer">Zum offiziellen DiGA-Verzeichnis</a>'
        '</section>'
    )


def diff_text_html(text: str, *, removed: bool) -> str:
    """Escaped text with explicit, non-color insertion/deletion cues."""
    tag, label = ("del", "Entfernt") if removed else ("ins", "Ergänzt")
    return (
        f'<{tag} class="diga-diff-{tag}" title="{label}">'
        f'<span class="diga-sr-only">{label}: </span>{html.escape(text)}</{tag}>'
    )
