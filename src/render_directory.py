"""Render public DiGA directory detail pages with a real browser.

This module is intentionally optional. It is used for audit archives and for
checking the visible page structure, not for the regular snapshot diff.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_RENDERED_PAGES_DIR = Path("data/rendered_pages")


def render_diga_entry(
    url: str,
    diga_id: str,
    output_root: Path = DEFAULT_RENDERED_PAGES_DIR,
    *,
    slug: str | None = None,
    timestamp: str | None = None,
    save_pdf: bool = True,
    save_png: bool = True,
    timeout_ms: int = 45_000,
) -> dict[str, Any]:
    """Render a DiGA detail page and save optional PDF/PNG audit artifacts."""

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - depends on optional package
        raise RuntimeError(
            "Playwright is not installed. Install it with `pip install playwright` "
            "and then run `python -m playwright install chromium`."
        ) from exc

    render_timestamp = timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_slug = slugify(slug or diga_id or "diga")
    output_dir = output_root / render_timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    base_name = f"{safe_filename(diga_id)}_{safe_slug}"
    pdf_path = output_dir / f"{base_name}.pdf"
    png_path = output_dir / f"{base_name}.png"
    structure_path = output_dir / f"{base_name}_structure.json"

    result: dict[str, Any] = {
        "url": url,
        "diga_id": diga_id,
        "timestamp": render_timestamp,
        "output_dir": str(output_dir),
        "pdf_path": str(pdf_path) if save_pdf else None,
        "png_path": str(png_path) if save_png else None,
        "structure_path": str(structure_path),
        "accordions_opened": 0,
        "visible_structure_count": 0,
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1800}, device_scale_factor=1)
        try:
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        except PlaywrightTimeoutError:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(2_000)

        dismiss_cookie_banner(page)
        result["accordions_opened"] = open_expandable_sections(page)
        page.wait_for_timeout(1_000)

        structure = extract_visible_structure(page)
        result["visible_structure_count"] = len(structure)
        with structure_path.open("w", encoding="utf-8") as file:
            json.dump(
                {
                    "url": url,
                    "diga_id": diga_id,
                    "timestamp": render_timestamp,
                    "visible_structure": structure,
                },
                file,
                ensure_ascii=False,
                indent=2,
            )
            file.write("\n")

        if save_pdf:
            page.pdf(
                path=str(pdf_path),
                format="A4",
                print_background=True,
                margin={"top": "12mm", "right": "10mm", "bottom": "12mm", "left": "10mm"},
            )
        if save_png:
            page.screenshot(path=str(png_path), full_page=True)
        browser.close()

    return result


def dismiss_cookie_banner(page: Any) -> None:
    """Best-effort handling for consent banners without depending on one vendor."""

    for pattern in [
        re.compile("Alle akzeptieren", re.IGNORECASE),
        re.compile("Akzeptieren", re.IGNORECASE),
        re.compile("Einverstanden", re.IGNORECASE),
        re.compile("Zustimmen", re.IGNORECASE),
    ]:
        try:
            button = page.get_by_role("button", name=pattern).first
            if button.is_visible(timeout=1_000):
                button.click(timeout=1_000)
                page.wait_for_timeout(500)
                return
        except Exception:
            continue


def open_expandable_sections(page: Any) -> int:
    """Open visible accordions/details elements before archiving the page."""

    opened = 0
    page.evaluate(
        """
        () => {
          document.querySelectorAll('details:not([open])').forEach((node) => {
            node.setAttribute('open', '');
          });
        }
        """
    )

    for _ in range(5):
        clicked_this_round = 0
        locators = page.locator(
            'button[aria-expanded="false"], [role="button"][aria-expanded="false"], '
            '[aria-controls][aria-expanded="false"]'
        )
        count = min(locators.count(), 80)
        for index in range(count):
            target = locators.nth(index)
            try:
                if not target.is_visible(timeout=500):
                    continue
                target.click(timeout=1_500)
                clicked_this_round += 1
                opened += 1
                page.wait_for_timeout(150)
            except Exception:
                continue
        if clicked_this_round == 0:
            break

    accordion_headings = page.locator("h2, h3").filter(
        has_text=re.compile(
            "Weitere Informationen|Informationen zum|\u00c4nderungshistorie|Aenderungshistorie|Bewertungsentscheidung",
            re.IGNORECASE,
        )
    )
    count = min(accordion_headings.count(), 80)
    for index in range(count):
        heading = accordion_headings.nth(index)
        try:
            if not heading.is_visible(timeout=500):
                continue
            before_height = page.evaluate("() => document.body.scrollHeight")
            heading.click(timeout=1_500)
            page.wait_for_timeout(300)
            after_height = page.evaluate("() => document.body.scrollHeight")
            if after_height != before_height:
                opened += 1
        except Exception:
            try:
                changed = heading.evaluate(
                    """
                    (node) => {
                      const before = document.body.scrollHeight;
                      const target = node.closest('button, [role="button"], summary, div, section') || node;
                      target.click();
                      return document.body.scrollHeight !== before;
                    }
                    """
                )
                page.wait_for_timeout(300)
                if changed:
                    opened += 1
            except Exception:
                continue
    return opened


def extract_visible_structure(page: Any) -> list[dict[str, str]]:
    """Return visible headings and labels as a lightweight structure probe."""

    return page.evaluate(
        """
        () => {
          const isVisible = (el) => {
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style && style.visibility !== 'hidden' && style.display !== 'none'
              && rect.width > 0 && rect.height > 0;
          };
          const clean = (text) => (text || '').replace(/\\s+/g, ' ').trim();
          const nodes = Array.from(document.querySelectorAll([
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'summary',
            'button[aria-expanded]',
            '[role="button"][aria-expanded]',
            'dt', 'dd', 'label', 'p', 'li'
          ].join(','))).filter(isVisible);
          const state = { h1: '', h2: '', h3: '', h4: '', h5: '', h6: '', fieldLabel: '' };
          const rows = [];
          for (const el of nodes) {
            const tag = el.tagName.toLowerCase();
            const text = clean(el.innerText || el.textContent);
            if (!text) continue;
            if (/^h[1-6]$/.test(tag)) {
              state[tag] = text;
              const level = Number(tag.slice(1));
              for (let next = level + 1; next <= 6; next += 1) state[`h${next}`] = '';
              if (level >= 4) state.fieldLabel = text;
              rows.push({
                tag,
                content_type: 'heading',
                main_section: state.h2 || state.h1,
                section_title: state.h3 || '',
                subsection_title: state.h4 || state.h5 || state.h6 || '',
                field_label: text,
                display_path: [state.h2 || state.h1, state.h3, state.h4 || state.h5 || state.h6]
                  .filter(Boolean).join(' > '),
                text,
              });
              continue;
            }
            if (tag === 'dt' || tag === 'label') {
              state.fieldLabel = text;
            }
            if (text.length < 2) continue;
            rows.push({
              tag,
              content_type: tag === 'dt' || tag === 'label' ? 'label' : 'text',
              main_section: state.h2 || state.h1,
              section_title: state.h3 || '',
              subsection_title: state.h4 || state.h5 || state.h6 || '',
              field_label: state.fieldLabel || state.h4 || state.h3 || state.h2 || '',
              display_path: [state.h2 || state.h1, state.h3, state.h4 || state.h5 || state.h6, state.fieldLabel]
                .filter(Boolean).filter((value, index, arr) => arr.indexOf(value) === index).join(' > '),
              text,
            });
          }
          return rows.slice(0, 1500);
        }
        """
    )


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = value.replace("\u00e4", "ae").replace("\u00f6", "oe").replace("\u00fc", "ue").replace("\u00df", "ss")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")[:80] or "diga"


def safe_filename(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip())
    return value.strip("_") or "diga"
