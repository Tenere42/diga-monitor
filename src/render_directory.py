"""Render public DiGA directory detail pages with a real browser.

This module is intentionally optional. It is used for audit archives and for
checking the visible page structure, not for the regular snapshot diff.
"""

from __future__ import annotations

import json
import re
from hashlib import sha1
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
        content_sections = extract_content_sections(page, diga_id)
        stats = {
            "accordion_count": result["accordions_opened"],
            "visible_structure_count": len(structure),
            "content_section_count": len(content_sections),
            "field_value_count": sum(
                1 for section in content_sections if section.get("content_type") == "field_value"
            ),
            "fallback_count": 0,
        }
        result["visible_structure_count"] = len(structure)
        result["content_section_count"] = len(content_sections)
        result["field_value_count"] = stats["field_value_count"]
        result["example_paths"] = [
            " > ".join(section.get("path", []))
            for section in content_sections
            if is_meaningful_example_path(section.get("path", []))
        ]
        result["example_paths"] = result["example_paths"][:10]
        with structure_path.open("w", encoding="utf-8") as file:
            json.dump(
                {
                    "url": url,
                    "diga_id": diga_id,
                    "timestamp": render_timestamp,
                    "visible_structure": structure,
                    "content_sections": content_sections,
                    "stats": stats,
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


def inspect_rendered_structure_file(path: Path, output_path: Path | None = None) -> str:
    """Create a readable validation report for a rendered structure JSON file."""

    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    sections = [
        section
        for section in payload.get("content_sections", [])
        if isinstance(section, dict)
        and isinstance(section.get("path"), list)
        and is_content_path([str(part) for part in section.get("path", [])])
    ]
    report = render_structure_report(payload, sections)
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
    return report


def render_structure_report(payload: dict[str, Any], sections: list[dict[str, Any]]) -> str:
    stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
    paths = [path_tuple(section) for section in sections]
    unique_paths = {path for path in paths if path}
    field_value_count = sum(1 for section in sections if section.get("content_type") == "field_value")
    fallback_count = sum(1 for section in sections if is_low_confidence_or_fallback(section))
    top_level_sections = list(dict.fromkeys(path[0] for path in paths if path))

    lines = [
        "# Rendered DiGA Structure Preview",
        "",
        f"URL: {payload.get('url', '')}",
        f"DiGA-ID: {payload.get('diga_id', '')}",
        f"Timestamp: {payload.get('timestamp', '')}",
        "",
        "## Summary",
        "",
        f"- Content sections: {len(sections)}",
        f"- Field/value pairs: {field_value_count}",
        f"- Unique display paths: {len(unique_paths)}",
        f"- Low confidence / fallback items: {fallback_count}",
        f"- Opened accordions: {stats.get('accordion_count', payload.get('accordions_opened', 0))}",
        "",
        "## Top-Level Sections",
        "",
    ]

    if top_level_sections:
        lines.extend(f"- {section}" for section in top_level_sections)
    else:
        lines.append("- No top-level sections found")

    lines.extend(["", "## Structure", ""])
    lines.extend(render_tree_lines(paths))

    lines.extend(["", "## Field/Value Examples", ""])
    field_examples = [section for section in sections if section.get("content_type") == "field_value"][:20]
    if field_examples:
        for section in field_examples:
            display_path = " > ".join(path_tuple(section))
            preview = str(section.get("content_preview") or section.get("content") or "")
            lines.append(f"- **{display_path}**: {preview}")
    else:
        lines.append("- No field/value pairs found")

    if fallback_count:
        lines.extend(["", "## Low Confidence / Fallback Items", ""])
        for section in sections:
            if is_low_confidence_or_fallback(section):
                lines.append(f"- {' > '.join(path_tuple(section))}")

    return "\n".join(lines).rstrip() + "\n"


def render_tree_lines(paths: list[tuple[str, ...]]) -> list[str]:
    unique_paths = list(dict.fromkeys(path for path in paths if path))
    if not unique_paths:
        return ["No content sections found"]

    lines: list[str] = []
    emitted: set[tuple[str, ...]] = set()
    for path in unique_paths:
        for depth in range(1, len(path) + 1):
            prefix = path[:depth]
            if prefix in emitted:
                continue
            emitted.add(prefix)
            indent = "  " * (depth - 1)
            label = prefix[-1]
            marker = "-" if depth == 1 else ">"
            lines.append(f"{indent}{marker} {label}")
    return lines


def path_tuple(section: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(part).strip() for part in section.get("path", []) if str(part).strip())


def is_low_confidence_or_fallback(section: dict[str, Any]) -> bool:
    source_kind = str(section.get("source_kind") or "")
    confidence = str(section.get("localization_confidence") or "")
    return source_kind not in {"", "visible_directory"} or confidence.lower() in {"low", "fallback"}


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

    for _ in range(8):
        clicked_this_round = 0
        locators = page.locator(
            'button[aria-expanded="false"], [role="button"][aria-expanded="false"], '
            '[aria-controls][aria-expanded="false"], '
            'button:has(svg), button:has([class*="chevron" i]), [role="button"]:has(svg)'
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

    accordion_headings = page.locator("h2, h3, h4")
    count = min(accordion_headings.count(), 80)
    for _ in range(3):
        clicked_this_round = 0
        for index in range(count):
            heading = accordion_headings.nth(index)
            try:
                if not heading.is_visible(timeout=500):
                    continue
                changed = heading.evaluate(
                    """
                    (node) => {
                      const clean = (text) => (text || '').replace(/\\s+/g, ' ').trim();
                      const text = clean(node.innerText || node.textContent);
                      if (!text || text.length > 180) return false;
                      const before = document.body.scrollHeight;
                      const expandedBefore = document.querySelectorAll('[aria-expanded="false"]').length;
                      const target = node.closest('button, [role="button"], summary, [aria-controls], div, section') || node;
                      target.click();
                      const expandedAfter = document.querySelectorAll('[aria-expanded="false"]').length;
                      return document.body.scrollHeight !== before || expandedAfter < expandedBefore;
                    }
                    """
                )
                page.wait_for_timeout(300)
                if changed:
                    clicked_this_round += 1
                    opened += 1
            except Exception:
                continue
        if clicked_this_round == 0:
            break
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


def extract_content_sections(page: Any, diga_id: str) -> list[dict[str, Any]]:
    """Extract content sections from the rendered, visible DOM order."""

    raw_sections = page.evaluate(
        """
        () => {
          const root = document.querySelector('main') || document.body;
          const isVisible = (el) => {
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style && style.visibility !== 'hidden' && style.display !== 'none'
              && rect.width > 0 && rect.height > 0;
          };
          const clean = (text) => (text || '')
            .replace(/\\u00a0/g, ' ')
            .replace(/\\s+/g, ' ')
            .trim();
          const rejectText = (text) => {
            if (!text || text.length < 2) return true;
            const lowered = text.toLowerCase();
            return [
              'diga-verzeichnis',
              'bfarm-eintrag öffnen',
              'mehr erfahren',
              'zurück',
              'menü',
              'suche',
              'teilen',
              'kontakt',
              'impressum',
              'datenschutz',
              'informationen für fachkreise',
              'hilfe & support',
              'hilfe und support',
              'leichte sprache',
              'gebaerdensprache'
            ].includes(lowered);
          };
          const textOf = (el) => clean(el.innerText || el.textContent);
          const headingLevel = (el) => {
            const tag = el.tagName.toLowerCase();
            if (/^h[1-6]$/.test(tag)) return Number(tag.slice(1));
            if (el.getAttribute('role') === 'heading') {
              const level = Number(el.getAttribute('aria-level') || '4');
              return Number.isFinite(level) ? level : 4;
            }
            return 0;
          };
          const fontWeight = (el) => {
            const parsed = Number.parseInt(window.getComputedStyle(el).fontWeight, 10);
            return Number.isFinite(parsed) ? parsed : 400;
          };
          const directText = (el) => Array.from(el.childNodes)
            .filter((node) => node.nodeType === Node.TEXT_NODE)
            .map((node) => clean(node.textContent))
            .filter(Boolean)
            .join(' ');
          const isInlineLabel = (el, text) => {
            const tag = el.tagName.toLowerCase();
            if (tag === 'dt' || tag === 'label') return true;
            if (tag !== 'strong' && tag !== 'b') return false;
            if (text.length > 180) return false;
            const parentText = textOf(el.parentElement || el);
            return parentText === text || directText(el.parentElement || el).length === 0;
          };
          const isStyledFieldLabel = (el, text) => {
            const tag = el.tagName.toLowerCase();
            if (!['p', 'li', 'div', 'span'].includes(tag)) return false;
            if (text.length > 180) return false;
            if (/[.!?]$/.test(text)) return false;
            const ownText = directText(el);
            if (['div', 'span'].includes(tag) && ownText && ownText !== text) return false;
            if (el.querySelector('p, li, h1, h2, h3, h4, h5, h6')) return false;
            if (fontWeight(el) >= 600) return true;
            const color = window.getComputedStyle(el).color;
            if (color && color !== window.getComputedStyle(document.body).color) return true;
            const strongText = clean(Array.from(el.querySelectorAll('strong, b'))
              .map((node) => node.innerText || node.textContent)
              .join(' '));
            return Boolean(strongText && strongText === text);
          };
          const nodes = Array.from(root.querySelectorAll([
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            '[role="heading"]',
            'dt', 'dd', 'label', 'p', 'li', 'strong', 'b', 'div', 'span'
          ].join(','))).filter(isVisible);

          const sections = [];
          let pathByLevel = {};
          let current = null;
          let pendingLabel = null;
          let seen = new Set();

          const pushCurrent = () => {
            if (!current) return;
            current.content = clean(current.contentParts.join(' '));
            delete current.contentParts;
            if (!current.content && current.content_type !== 'heading') return;
            const dedupe = `${current.content_type}|${current.path.join(' > ')}|${current.content}`;
            if (seen.has(dedupe)) return;
            seen.add(dedupe);
            current.content_preview = current.content.length > 240
              ? `${current.content.slice(0, 237)}...`
              : current.content;
            sections.push(current);
          };
          const makePath = (level, title) => {
            const path = [];
            Object.keys(pathByLevel)
              .map(Number)
              .filter((knownLevel) => knownLevel > 1 && knownLevel < level)
              .sort((a, b) => a - b)
              .forEach((knownLevel) => {
                const value = pathByLevel[knownLevel];
                if (value && !path.includes(value)) path.push(value);
              });
            if (title && !path.includes(title)) path.push(title);
            return path;
          };
          const startSection = (level, title, contentType = 'section') => {
            pushCurrent();
            Object.keys(pathByLevel).map(Number).forEach((knownLevel) => {
              if (knownLevel >= level) delete pathByLevel[knownLevel];
            });
            pathByLevel[level] = title;
            current = {
              path: makePath(level, title),
              level,
              title,
              content: '',
              content_preview: '',
              content_type: contentType,
              source_kind: 'visible_directory',
              contentParts: []
            };
            pendingLabel = null;
          };

          for (const el of nodes) {
            const text = textOf(el);
            if (rejectText(text)) continue;
            const tag = el.tagName.toLowerCase();
            const level = headingLevel(el);

            if (level > 0) {
              if (level === 1) {
                pathByLevel = { 1: text };
                pushCurrent();
                current = null;
                pendingLabel = null;
              } else {
                startSection(Math.min(level, 6), text, 'section');
              }
              continue;
            }

            if (isInlineLabel(el, text)) {
              pendingLabel = text;
              continue;
            }
            if (isStyledFieldLabel(el, text)) {
              pendingLabel = text;
              continue;
            }
            if (tag === 'div' || tag === 'span') {
              continue;
            }

            if (tag === 'dd' && pendingLabel) {
              const levelForField = Math.max(...Object.keys(pathByLevel).map(Number).filter(Boolean), 2) + 1;
              pushCurrent();
              current = {
                path: makePath(levelForField, pendingLabel),
                level: levelForField,
                title: pendingLabel,
                content: '',
                content_preview: '',
                content_type: 'field_value',
                source_kind: 'visible_directory',
                contentParts: [text]
              };
              pushCurrent();
              current = null;
              pendingLabel = null;
              continue;
            }

            if (pendingLabel) {
              const levelForField = Math.max(...Object.keys(pathByLevel).map(Number).filter(Boolean), 2) + 1;
              pushCurrent();
              current = {
                path: makePath(levelForField, pendingLabel),
                level: levelForField,
                title: pendingLabel,
                content: '',
                content_preview: '',
                content_type: 'field_value',
                source_kind: 'visible_directory',
                contentParts: [text]
              };
              pushCurrent();
              current = null;
              pendingLabel = null;
              continue;
            } else if (!current) {
              startSection(2, pathByLevel[2] || pathByLevel[1] || 'Seiteninhalt', 'section');
            }

            current.contentParts.push(text);
          }
          pushCurrent();
          return sections;
        }
        """
    )

    sections = []
    for section in raw_sections:
        path = [str(part) for part in section.get("path", []) if str(part).strip()]
        title = str(section.get("title") or (path[-1] if path else "")).strip()
        content = str(section.get("content") or "").strip()
        if not path or (not title and not content):
            continue
        if not is_content_path(path):
            continue
        content_type = str(section.get("content_type") or "section")
        normalized_path = normalize_key_part(" > ".join(path))
        stable_key = f"{safe_filename(diga_id)}:{normalized_path}:{content_type}"
        sections.append(
            {
                "path": path,
                "level": int(section.get("level") or len(path)),
                "title": title,
                "content": content,
                "content_preview": str(section.get("content_preview") or content[:240]),
                "content_type": content_type,
                "source_kind": "visible_directory",
                "stable_key": stable_key,
            }
        )
    return sections


def is_content_path(path: list[str]) -> bool:
    if not path:
        return False
    if "Gebrauchsanweisung (PDF)" in path:
        return False
    rejected_roots = {
        "Seiteninhalt",
        "Informationen f\u00fcr Fachkreise",
        "Hilfe & Support",
        "Hilfe und Support",
        "Leichte Sprache",
        "Geb\u00e4rdensprache",
    }
    root = path[0]
    return root not in rejected_roots and not root.lower().startswith("www.")


def is_meaningful_example_path(path: Any) -> bool:
    return isinstance(path, list) and len(path) >= 2 and is_content_path([str(part) for part in path])


def normalize_key_part(value: str) -> str:
    value = slugify(value)
    digest = sha1(value.encode("utf-8")).hexdigest()[:10]
    return f"{value[:90]}-{digest}"


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = value.replace("\u00e4", "ae").replace("\u00f6", "oe").replace("\u00fc", "ue").replace("\u00df", "ss")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")[:80] or "diga"


def safe_filename(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip())
    return value.strip("_") or "diga"
