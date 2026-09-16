"""Presentation-only primitives for the DiGA Tracker Streamlit frontend.

No data loading, routing, session state, or newsletter behavior belongs here.
"""

from __future__ import annotations

import html
from pathlib import Path


STYLESHEET_PATH = Path(__file__).resolve().parents[1] / "assets" / "styles.css"


def stylesheet_html() -> str:
    """Load trusted repository CSS independently of the process working directory."""
    return f"<style>{STYLESHEET_PATH.read_text(encoding='utf-8')}</style>"


def public_header_html() -> str:
    """The existing header content, with the public product name."""
    return (
        '<header class="diga-page-header">'
        '<h1 class="diga-page-title">DiGA Tracker</h1>'
        '<p class="diga-page-subtitle">Änderungen im DiGA-Verzeichnis transparent verfolgen</p>'
        '<div class="diga-page-source">Quelle: Offizielles DiGA-Verzeichnis des BfArM</div>'
        '</header>'
    )


def diff_text_html(text: str, *, removed: bool) -> str:
    """Escaped text with explicit, non-color insertion/deletion cues."""
    tag, label = ("del", "Entfernt") if removed else ("ins", "Ergänzt")
    return (
        f'<{tag} class="diga-diff-{tag}" title="{label}">'
        f'<span class="diga-sr-only">{label}: </span>{html.escape(text)}</{tag}>'
    )
