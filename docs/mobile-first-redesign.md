# DiGA Tracker — Mobile-first Redesign

## Product principle

The public site is a tracker, not a technical monitoring console. A visitor should understand within seconds:

1. What changed?
2. Which DiGA is affected?
3. When did it change?
4. What was before vs. after?
5. Do I want an alert next time?

The experience is designed mobile-first and must remain simple, fast and calm.

## Non-negotiables

- Brand: **DiGA Tracker**, not DiGA Monitor, in all user-facing UI.
- Smartphone is the primary viewport.
- No technical/internal terminology unless a user explicitly opens details.
- One consistent change-card pattern for every change type.
- One consistent visual language for before/after.
- Alerts are prominent but must not dominate the tracker.
- Filters must reduce cognitive load rather than expose implementation fields.
- Existing tracking/change-detection logic must remain untouched during the UI redesign.

## Audit of current UX/UI

### 1. Product identity
- UI still says "DiGA Monitor" in page title/header despite the public product being DiGA Tracker.
- Copy feels like an internal monitoring dashboard rather than a lightweight public tracker.

### 2. Mobile hierarchy
- Desktop-oriented wide layout remains the conceptual default.
- Several multi-column constructs collapse only responsively instead of being designed as mobile cards first.
- Important content competes with technical metadata and long text blocks.
- Cards are vertically very long on mobile.

### 3. Alert signup
- Signup is now visible near the top, but it is still presented as a full form section rather than a compact CTA.
- Consent copy creates substantial vertical weight on smartphone.
- Alert value proposition should be one sentence, with the form visually secondary.

### 4. Filters
Current date-only filtering is too weak for a tracker. Recommended user-facing filters:

- **Zeitraum:** Neueste / 7 Tage / 30 Tage / Alle
- **Änderung:** Alle / Neu / Status / Preis / Inhalt / Gestrichen
- **DiGA:** searchable select, shown only when useful

Avoid exposing internal field names, confidence values or implementation taxonomy.

Mobile default should be a single compact filter row/button opening secondary controls rather than permanently consuming screen height.

### 5. Change cards
Current cards mix multiple UI systems:
- red/green before-after cards
- yellow/status styling
- plain flowing text
- expanders
- different card structures depending on change type

Target: every change is represented by the same hierarchy:

**DiGA name**  
Manufacturer · date  
**Human-readable change label**  
Short change summary  
`Vorher` → `Nachher`  
Optional: Details / BfArM link

### 6. Before vs. after
Use one semantic system everywhere:
- Before = neutral/light muted surface, removed text highlighted red only where necessary
- After = neutral/light surface, new text highlighted green only where necessary
- Status changes may use status badges, but the before/after container itself remains consistent
- Yellow is reserved for warnings/uncertainty, never as an alternative representation of normal changes

On mobile, before and after are always stacked vertically. On desktop they may sit side-by-side.

### 7. Unresolved location messaging
"Abschnitt konnte nicht zugeordnet werden" currently appears too often and communicates implementation weakness to users.

New rule:
- Never make localization uncertainty the primary message.
- If the changed content itself is known, show the change normally and omit localization caveats.
- If location uncertainty materially affects interpretation, show a single subtle note under Details: "Bereich im BfArM-Eintrag nicht eindeutig zugeordnet."
- Repeated technical caveats within the same card are prohibited.

### 8. Information density
- "Fachliche Anpassungen", timestamps, metadata and path information currently compete with the actual change.
- "Informationspfad" and "Interner Schlüssel" are debugging concepts and must not be part of the default public view.
- Exact scan metadata belongs in a compact trust/status area, not inside every interaction.

### 9. Status information
Current three-item status grid uses too much prime space.
Target is one compact trust line, for example:

`● Tracker aktiv · letzter Scan 12:03 · Tracking seit 31.05.2026`

Last detected change can be displayed separately only if useful.

### 10. Navigation
The site does not need a conventional navigation bar. Keep it intentionally single-purpose.
Recommended top structure:

- DiGA Tracker wordmark/title
- short proposition
- compact alert CTA
- tracker status
- smart filters
- changes feed
- minimal footer/privacy

### 11. Typography and spacing
- Reduce the number of heading levels visible inside cards.
- Use stronger spacing hierarchy instead of repeated dividers.
- Mobile card padding approximately 16px.
- Minimum touch target ~44px.
- Avoid tiny captions for information users actually need.

### 12. Change taxonomy
User-facing labels should be few and stable:
- Neu aufgenommen
- Status geändert
- Preis geändert
- Inhalt geändert
- Gestrichen

Technical types remain internal.

### 13. Long text changes
- Do not lead with full text blocks.
- Default to the smallest useful changed excerpt.
- Show full before/after only behind "Details anzeigen".
- Preserve highlighted inserted/deleted text consistently.

### 14. Price changes
- Primary line should state the actual outcome, e.g. `Preis: 599 € → 649 €`.
- Period metadata belongs below it.
- Technical/raw price structure remains hidden unless needed for diagnostics.

### 15. Status changes
- Show status badges as the summary: `Vorläufig → Dauerhaft`.
- Avoid an additional generic before/after explanation if the badge transition already communicates the change.

### 16. New/removed DiGA
- New listing and removal should be visually understandable without reading explanatory prose.
- Use concise status treatment and core metadata only.

### 17. Grouping
Multiple changes to the same DiGA on the same day should stay grouped, but the group should look like one story, not a container with multiple nested dashboard widgets.

### 18. BfArM link
- Keep it available but visually secondary.
- Prefer a text action such as `Beim BfArM öffnen ↗` rather than a large button competing with the content.

### 19. Dark mode
Current CSS partially adapts to system dark mode. Redesign must either support dark mode consistently or deliberately force a tested light appearance. Partial adaptation is worse than either choice.

### 20. Streamlit chrome
Hide/de-emphasize non-product Streamlit chrome where safely possible so the site feels like DiGA Tracker rather than a default Streamlit application.

### 21. Empty states
Empty result states should explain the filter outcome and offer `Filter zurücksetzen`, not imply that the tracker has never seen changes.

### 22. Loading/perceived performance
Keep initial hierarchy light. Avoid rendering unnecessary long detail content above the fold. Expensive/verbose details should remain collapsed.

### 23. Accessibility
- Do not communicate semantic state through color alone.
- Maintain sufficient contrast.
- Buttons and controls need clear labels and touch sizes.
- Before/after labels remain textual.

### 24. Copy consistency
Use one vocabulary throughout:
- DiGA Tracker
- Änderung
- Vorher
- Nachher
- Beim BfArM öffnen
- Alerts

Avoid switching among Monitor, Monitoring, fachliche Anpassung, Event and Änderung in public copy.

## Target mobile information architecture

1. **Hero**
   - DiGA Tracker
   - `Alle Änderungen im BfArM DiGA-Verzeichnis. Einfach nachvollziehbar.`

2. **Alert CTA**
   - compact card: `Keine Änderung verpassen`
   - email field + primary action
   - consent/legal content visually subordinate but compliant

3. **Tracker health**
   - single compact line

4. **Filters**
   - quick timeframe chips/select
   - change-type selector
   - optional DiGA search

5. **Feed**
   - newest first
   - grouped by DiGA/day
   - concise summary first
   - standardized before/after
   - details collapsed

6. **Footer**
   - privacy + operator only where required

## Implementation phases

### Phase A — structural cleanup
- Rename all public Monitor copy to Tracker.
- Establish a single mobile-first style layer.
- Replace status grid with compact tracker health.
- Introduce smart filter model.
- Remove public debug/localization noise.

### Phase B — unified cards
- One card shell for every change type.
- Consistent before/after component.
- Consistent labels, badges, metadata and actions.
- Long details collapsed.

### Phase C — polish
- Mobile spacing/typography/touch targets.
- Alert CTA polish.
- Empty/loading states.
- Desktop refinement after mobile is accepted.

## Acceptance criteria

At 390px width a user must be able to:
- identify the product and its purpose without scrolling,
- see how to subscribe to alerts,
- understand tracker freshness,
- filter the feed without navigating away,
- understand a typical change card without opening details,
- distinguish before and after without relying only on color,
- never see internal/debug terminology in the default view.
