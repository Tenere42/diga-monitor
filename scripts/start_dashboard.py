"""Prepare crawler-readable social metadata, then start the unchanged dashboard."""
from pathlib import Path
import os
import re
import sys

TITLE = "DiGA Tracker – Das DiGA Verzeichnis im Blick"
DESCRIPTION = "Neue DiGA, Status, Preise und Evidenz: Alle Änderungen im DiGA Verzeichnis im Blick. Keine Änderung verpassen."
URL = "https://www.diga-tracker.de/"
IMAGE = URL + "app/static/diga-tracker-social-v1.png"
START = "<!-- diga-social-preview:start -->"
END = "<!-- diga-social-preview:end -->"


def add_metadata(html: str) -> str:
    """Idempotently update the shipped HTML shell without touching JS assets."""
    if "</head>" not in html or not re.search(r"<title>.*?</title>", html, re.S):
        raise RuntimeError("Streamlit HTML shell changed; expected title/head missing")
    html = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n?", "", html, flags=re.S)
    html = re.sub(r"<title>.*?</title>", f"<title>{TITLE}</title>", html, count=1, flags=re.S)
    tags = f'''{START}
<meta name="description" content="{DESCRIPTION}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="DiGA Tracker">
<meta property="og:title" content="{TITLE}">
<meta property="og:description" content="{DESCRIPTION}">
<meta property="og:url" content="{URL}">
<meta property="og:image" content="{IMAGE}">
<meta property="og:image:type" content="image/png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="DiGA Tracker. Keine Änderung verpassen. Neue DiGA, Status, Preise, Evidenz.">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{TITLE}">
<meta name="twitter:description" content="{DESCRIPTION}">
<meta name="twitter:image" content="{IMAGE}">
{END}'''
    return html.replace("</head>", tags + "\n</head>", 1)


def main() -> None:
    import streamlit
    index = Path(streamlit.__file__).resolve().parent / "static" / "index.html"
    index.write_text(add_metadata(index.read_text(encoding="utf-8")), encoding="utf-8")
    os.execv(sys.executable, [sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.address=0.0.0.0", f"--server.port={os.environ.get('PORT', '8501')}",
        "--server.headless=true"])


if __name__ == "__main__":
    main()
