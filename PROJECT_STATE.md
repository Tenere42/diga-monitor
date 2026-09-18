# PROJECT_STATE.md

## Current objective

### Impressum follow-up — 2026-09-18

- Owner supplied and authorized publication of Leevsten GmbH operator details.
  `/impressum` now uses native Streamlit page routing and the existing styling.
  Footer links to Impressum independently of the newsletter gate; Datenschutz
  keeps its existing readiness gate and uses a root-relative URL.
- Local desktop/390px/320px page QA passed without horizontal overflow.
  Suite: 238 tests, 235 pass; only three accepted historical-count failures.
  Compilation and whitespace checks pass. Route tests were updated for the
  extracted tracker page callback; entrypoint navigation registration is tested.
- VAT information omitted. Preview and production branch deployments succeeded.
  https://www.diga-tracker.de/impressum verified with correct content, legal links,
  and no overflow at desktop/390/320px. The URL is configured in GitHub Actions
  repository variables and Railway production variables.
- Main monitoring-data update `6edc3e5` integrated before production rollout.
  Production temporarily tracks this PR branch; restore main after approved merge.
- Owner confirmed all four eligible addresses are theirs and authorized one
  campaign. Campaign #3 accepted at 2026-09-18T13:48:37Z, then marked sent.
  Gmail receipt verified: expected HTML, plain-text MIME and personalized native
  unsubscribe link/header. No unsubscribe click. Aggregate delivery counters were
  initially still zero; receipt at all four addresses is not yet established.
- Exactly one send through the real subscriber path replayed ACTICORE1's existing
  2026-09-16 new_diga event in memory. No persisted simulation. Runtime data/outputs
  hashes and contact membership/status hashes unchanged; zero R2 calls.
- PR #16 remains unmerged and awaits owner email inspection and merge approval.
  Detailed test evidence and remaining mail-client limits are in
  docs/change-notification-email.md.

## Previous integration record

### Change-notification email — 2026-09-17

- New branch `codex/change-notification-email` from main `0568e7879a260351fe2a82897150d494acc6709b`.
  PR #15 merged with explicit owner approval at `89fc043614b1fbb471e4835653d54fb7c95d8b38`; Railway deployment succeeded.
  PR #16 integrates this main commit and remains open, explicitly not approved for merge.
- Existing admin transactional and subscriber Campaign API paths share a new
  concise HTML/text renderer and repository template. One card per DiGA/public
  day, reliable German labels, neutral fallback and individual stable detail links.
- Shared link helpers preserve existing anchor hashes. Full historical email-link
  coverage resolves to current public groups. Missing old records retain the
  existing graceful fallback. No session state or subscriber PII in links.
- Subscriber campaigns retain native Brevo unsubscribe and confirmed-list
  delivery. Campaign text is provider-generated; deterministic local text previews
  are included. Admin transactional mail carries both HTML and text parts.
- `DIGA_TRACKER_IMPRESSUM_URL` is required for subscriber sends. Read-only live
  inspection found only Datenschutz; repository legal notes explicitly confirm
  no Impressum page. No URL/legal content was invented. Supply a real published
  destination before rollout; missing configuration safely prevents campaigns.
- Integrated suite: 237 tests, 234 passed; three accepted baseline failures
  (392 vs 369 twice, 27 vs 23 groups after importing main monitoring data). Compileall and diff whitespace checks pass.
- Four synthetic email fixtures inspected at desktop/390px/320px: correct CTA
  counts, long-name wrapping, footer/unsubscribe, no horizontal overflow.
  Repeated in Chrome after integration: all four fixtures at 1000/390/320px;
  inspected long-name layout screenshots at each width. Production homepage,
  actual ACTICORE1 detail and Datenschutz routes resolve. Synthetic fixture
  destinations are not real records; Impressum/unsubscribe delivery remain gated.
  Actual mail-client rendering and delivered text/unsubscribe remain unverified.
- Claude authentication preflight failed: ANTHROPIC_API_KEY unavailable; no OAuth
  fallback. Codex self-review completed; technical-only cards and unsafe error
  logging were fixed. Detailed architecture, QA and rollout notes are in
  `docs/change-notification-email.md`.
- Production config inspection found no Impressum destination or operator postal
  address, representative, or register/UID details. Existing privacy data only
  identifies Leevsten GmbH and its privacy contact. No legal facts were invented.
  The owner authorized one live subscriber test conditional on legal readiness;
  that prerequisite is unsatisfied, so zero campaigns/notifications were triggered.
  No production history, baseline, R2 data or Brevo configuration was changed.
  Imported operational files are byte-identical to merged main. Only PROJECT_STATE
  conflicted during integration; both relevant sections were retained.
- Supply verified publishable company details before implementing/configuring
  Impressum and running the single no-retry live test. Do not merge PR #16 until
  the owner has inspected the received email and explicitly approved the merge.

UI/UX refinements are implemented on `codex/ui-ux-refinements`, based on
`efbb61e5ae7c14825c54684d08de37ed93ab758f` of `codex/ui-redesign-black-white`.
This is a stacked change on the existing redesign, not a replacement based on
older `main`. Nothing has been merged or deployed by this task.
### PR #15 verification — 2026-09-17

- Re-ran all 223 tests: 220 pass, the same three historical-count failures
  (386 versus 369 twice; 25 versus 23 groups). No history/data changed.
- Local Edge/Playwright QA at 1440px and 390px, including 390x420 focused
  newsletter viewport: homepage, consent validation, mocked signup success,
  overview navigation and re-entry detail checked. No horizontal overflow.
- Fixed the narrow newsletter submit wrapper using native
  `use_container_width=True`. Re-entry shows entfernt → vorläufig, one BfArM
  action, and no internal diagnostic expander. DOI HTML inspected at both widths.
- Browser QA used a local-only fixture with mocked signup and a synthetic
  re-entry; no real email/contact mutation. Physical iOS keyboard and actual
  Gmail/Outlook rendering remain unverified. Local baseline snapshot is absent,
  so homepage market KPIs correctly show unavailable values.
- Brevo API key/template ID and Claude API key are unavailable. Repository DOI
  template remains prepared only; live activation requires explicit approval,
  native token verification and a controlled end-to-end DOI test.
- Ready for code review/merge decision with the known baseline failures and
  device/provider QA limitations above. Do not merge or activate automatically.

Mobile newsletter/DOI polish is prepared on `codex/mobile-newsletter-doi-polish`
from verified current main `72a87f0960ca3f93ebb45e175a6be6a79ec123d3` (PR #14
merged the previous UI refinements). This task must not merge or deploy.

### Public status and detail actions — 2026-09-17

- Continued on the same `codex/mobile-newsletter-doi-polish` branch after
  `67fffe4c4072de81232997dbd661cb6f7ca4589a`; no branch replacement.
- Central presentation labels: provisional → vorläufig, permanent/listed →
  dauerhaft, removed → entfernt. Explicit status fields also handle known
  aliases and unknown categories without exposing raw enums. Exact scalar enums,
  nested status metadata, before/after values and homepage summaries use this
  mapping; arbitrary prose and non-status technical aliases are not translated.
- Re-entry removed → provisional renders entfernt → vorläufig. Display helpers
  copy/format values without modifying stored events or assuming transition order.
- Removed the entire “Warum wurde diese Änderung erkannt?” component and nested
  raw-data expander. Parsed prices retain their summaries; unparseable price
  changes retain actual before/after values directly, without the internal box.
- Removed the inline BfArM action from compact lifecycle metadata. The standardized
  bottom area is the sole external action on public details, including URLs found
  inside new/removed entry data. Invalid/missing entry links are omitted; Zurück
  remains. Existing valid diga.bfarm.de entry URLs are preserved exactly.
- Full suite: 223 tests, 220 passed, same three baseline failures. Re-ran those
  against verified current main 72a87f0: two failures at 386 vs 369 events and one
  at 25 vs 23 public groups, identical to this branch. New status/transition,
  non-mutation, price-information retention, absent-expander and single-link
  AppTest checks pass. compileall and git diff --check pass.
- Newsletter/DOI functions compared by AST to 67fffe4 and remain unchanged;
  subscriber code, mobile CSS, dependency/configuration changes and prepared
  Brevo email template have no diff from that commit. No production data changes.
- Publication remains blocked by the known approval policy; no push attempted.
  Nothing merged, deployed or activated in Brevo.

### Mobile newsletter and DOI polish — 2026-09-17

- Native Brevo `redirectionUrl` now normalizes the known legacy production
  confirmation destination to `https://www.diga-tracker.de`. Custom preview
  destinations remain untouched. Previously issued `?view=confirmed` URLs render
  the ordinary homepage. No unsigned-query success banner or subscriber mutation.
- Newsletter uses a keyed normal-flow container, safe-area spacing, dynamic
  mobile app viewport height, 16px input text, 48px input/button targets and
  comfortable card padding. No fixed/sticky signup, fixed card height or JS scroll.
- Native `enter_to_submit=False` removes Streamlit's Enter instruction at source;
  validation and accessibility text are not hidden. Explicit submit remains.
  Minimum Streamlit raised to 1.39 for that API.
- Inline HTML DOI email asset: `templates/brevo-doi-confirmation.html`. White,
  restrained 560px fluid layout, black full-width CTA and documented native API
  placeholder `{{ params.DOIurl }}`. Existing template ID and sender are untouched.
  This is a reviewable artifact, NOT an uploaded/activated Brevo template.
- Brevo key/template ID are absent. Active email markup/token expression and live
  delivery, confirmation, redirect and list transitions could not be checked.
  See docs/newsletter-doi-polish.md for rollout/QA requirements. No live contact
  mutation, test email, production config edit, merge or deployment occurred.
- Full suite: 217 tests, 214 passed; the same three failures were reproduced on
  clean current main before editing: historical event counts 386 vs 369 (two
  tests) and public group count 25 vs 23 (one test). All new/relevant tests pass.
  git diff --check and compileall pass. AST comparison verifies DOI request,
  re-subscription, transport, consent, transient email cleanup and logging are
  unchanged, apart from the native form option and redirect configuration.
- Claude preflight: ANTHROPIC_API_KEY unavailable; self-review completed.
  Saved browser permission still blocks local preview; no prohibited workaround
  attempted. iPhone keyboard, 390px/reduced viewport and email-client rendering
  remain unverified. Automated checks are not visual QA.
- Source obtained through the read-only GitHub connector because git fetch cannot
  reach its configured proxy. Imported main commit and tree match GitHub hashes.
  Sparse checkout excludes the 38MB operational data/baseline blob; its tracked
  Git entry is preserved unchanged. Current source/history event files are exact.

### UI/UX refinements — 2026-09-16

- Homepage KPIs say “Dauerhaft gelistet” / “Vorläufig gelistet”; newsletter
  introduction matches the requested text exactly. Signup behavior is unchanged.
- Overview is “Alle Änderungen”; individual detail heading is “Änderungen”.
  Removed the duplicate “Änderungen im Detail” expander. All its events already
  use the same full detail renderer behind “Details ansehen”; no values lost.
- Removed generic localization failure sentences while retaining before/after
  values, text diffs, price information and specific factual diagnostics.
- Shared black/white primary styles cover homepage CTA, overview/home navigation,
  detail overview link, BfArM links (including native links), and bottom “Zurück”.
  Bottom external/back actions stack at every width. Mobile buttons are full-width,
  with 48px minimum targets, consistent padding/radius and hover/focus cues.
- Replaced date range calendar with 7/14/30/90/180 Tage dropdown, default 30.
  Start = Berlin today minus (days - 1); both boundaries inclusive. Event timestamps
  convert to Berlin calendar dates before filtering; tomorrow is excluded.
- Validation: full unittest suite: 212 tests, 210 passed, two existing historical-data failures
  (380 current events versus frozen expectations of 369). Both independently
  reproduced against unchanged base app.py. New calendar tests cover all periods,
  full today, midnight boundaries, DST, leap day, year boundary and invalid dates.
  Navigation, all detail events, BfArM URL preservation, labels, duplicate removal,
  newsletter reruns and responsive CSS contracts are tested. git diff --check and
  compileall pass. Logs are in ignored work/ui-refinements-*.log.
- Claude: CLI exists, but required API-key preflight failed because
  ANTHROPIC_API_KEY is unavailable. No review findings were produced; no OAuth
  fallback attempted. Explicit Codex self-review found and addressed the remaining
  native BfArM links needing the shared primary style; no substantive open code
  findings. Monitoring, storage, data, newsletter behavior and deployment config
  have no implementation changes.
- Visual QA is outstanding: local Playwright could not start (WinError 5), and
  browser-control access to the local preview was denied by approval review.
  No browser viewport/overflow/appearance validation is claimed. Verify on phones
  and desktop before merge/deploy. Automated checks do not replace visual QA.
- Publication: GitHub connector rejected the write needed to publish this branch
  because approval policy is never. Local commit only; no push or PR created.

### Phase C.1 simplified homepage and direct details — 2026-09-16

- Started clean at `6b7860123e57b4ad50124ddb7c43536fb75b1193` on the redesign
  branch. Header now contains only the DiGA Tracker homepage link. Removed
  disclosure/desktop navigation markup and obsolete menu, eyebrow and about CSS.
- Homepage sequence: hero, KPIs, latest changes, existing newsletter, footer.
  Removed the entire standalone explanation section; merged concise factual
  copy about new DiGA/status/prices/other changes into the newsletter introduction.
  No duplicate form, new widgets, consent/state/DOI change or live Brevo calls.
- Homepage and overview detail links use `?view=changes&detail=change-<hash>`.
  Identifier reuses the unchanged SHA-256-derived DiGA ID + Berlin date group
  anchor, never a position. General overview remains `?view=changes`.
- Direct routing resolves against the complete eligible public daily groups,
  before any search/lifecycle/date controls. Exactly one matched group renders
  all its adjustments through existing detail functions, with badges/time and
  available BfArM link. Invalid, empty, directory or ambiguous IDs fail closed
  with a not-found message and overview link. No silent fallback to another item.
- Detail has a restrained back-to-overview link; brand returns home. URL state
  survives reruns/fresh AppTest sessions; ordinary links allow browser history.
  No DOM/hash dependency. Existing daily grouping and mutable same-day group
  contents remain intentional; this is not an immutable per-scan event URL.
- Full suite: 205 tests, 203 passed, the same two historical failures, zero new
  regressions. New checks cover simplified homepage, one form, direct links,
  correct full-group rendering, reload/overview navigation, invalid/sentinel IDs
  and identity/date stability. Existing legal routes, newsletter and Phase C
  public semantics/freshness tests pass. Updated obsolete header expectations
  and AppTest's list-valued query-param assertion during review.
- Self-review: newsletter AST identical after normalizing only introduction
  copy. Existing taxonomy/KPI/freshness/grouping/dedup/detail/price helpers are
  unchanged. Protected paths and raw data have no diff. Removed unused section
  wrappers/styles rather than leaving empty space. Desktop width and wrapping
  rules remain. No merge or production deployment; one normal push after commit.
- Actual browser QA remains outstanding on Railway ui-preview at
  320/375/390/430/768/1440px, including long details, focus, spacing and browser
  back behavior. AppTest does not establish visual correctness.

### Phase C public Changes view — 2026-09-16

- Started clean at `58af253b7254b8d385c3084ce8bc06e946cc62aa` on the existing
  redesign branch. Public-only adapter `src/public_changes.py` centralizes
  concrete identity validation, NEU / AKTUALISIERT / ENTFERNT and subjects
  STATUS / PREIS / EVIDENZ / ANWENDUNG / TECHNIK / DATENSCHUTZ / HERSTELLER /
  ANGABEN. Trusted fields precede context; uncertain localization falls back to
  ANGABEN unless original fields support a subject. Reactivation and status
  changes to removed remain AKTUALISIERT; only removed_diga maps to ENTFERNT.
- Synthetic directory_metric_change, sentinel identity/name and missing concrete
  identity are excluded only at the public boundary. Raw history, monitoring,
  technical exclusions, no-op detection, deduplication and grouping are unchanged.
  Current corpus: 380 stored events preserved, 23 public groups / 169 displayed
  adjustments (four aggregate adjustments removed from the former 25 / 173).
- Homepage previews and Changes badges share classification. Five public groups
  maximum; existing stable identity/date anchors retained. Public 30-day KPI
  still counts deduplicated displayed adjustments, not groups/unique DiGA, but
  excludes aggregate diagnostics. At Sep 16: 13 rather than 15. Snapshot KPIs
  Aktiv/Dauerhaft/Vorläufig remain unchanged. A new DiGA plus its two counter
  events contributes one public adjustment.
- Changes view: name/manufacturer search over loaded public events, Alle/Neu/
  Aktualisiert/Entfernt controls, existing date filter, chronological compact
  groups with wrapping badges and expandable existing before/after details.
  Newsletter appears once after the feed, including empty filter results.
  Unresolved details retain original price/text rendering with simpler wording.
- Daily grouping still combines multiple scans. Mixed lifecycle days retain all
  represented category badges; filters select matching events before grouping.
  No per-scan rewrite or change to stored timestamps/identity was introduced.
- Freshness function is unchanged: latest scan_history timestamp, snapshot
  fallback, Berlin conversion, including zero-change scans. Preview staleness
  remains a branch-local artifact issue; no runtime GitHub/R2 fetching added.
- Removed checkbox-wrapper focus-within outline. Existing control focus-visible
  and actual email input focus styles remain. Newsletter backend, keys, consent,
  pending/result state, routes and DOI functions are unchanged. No live Brevo.
  Native mobile menu retained; no scroll-to-close or JavaScript added.
- Full suite: 201 tests, 199 passed, two unchanged historical failures expecting
  369 rather than 380 events, zero new failures. Tests cover taxonomy, identity,
  aggregate exclusion/KPI, public chronology/details, search/filters, mixed
  lifecycle groups, uncertain context and checkbox CSS. Existing newsletter,
  privacy/confirmation and freshness tests continue to pass.
- Codex self-review: AST comparison confirms only four existing app functions
  changed (Changes renderer, homepage preview/groups, public adjustment count).
  All existing business/detail functions, newsletter, freshness and caches are
  identical. Protected paths, raw data, historical tests and configuration have
  no diff. Low-confidence context cannot override trusted field classification;
  generic manufacturer words in clinical-purpose text do not become HERSTELLER.
- Structural responsive review targets 320/375/390/430/768/1440px: bounded width,
  wrapping badge/filter rows, existing before/after wrapping and touch targets.
  Browser visual QA remains required on Railway ui-preview; no actual viewport
  render is claimed. Mobile checkbox keyboard focus needs real-device verification.
- No merge or production deployment. One normal push will be attempted after
  commit; external publication is required if the known sandbox proxy blocks it.

### Phase B.2 mobile polish — 2026-09-16

- Started clean at `c8bd320c908773fe855dfa66a8518ae6616ca847` on
  `codex/ui-redesign-black-white`, following the user's real-iPhone review.
- Hero now reads “Alle DiGA. Alle Änderungen.” with the exact requested short
  copy and one gated signup CTA; eyebrow and secondary CTA removed. Explanation
  reduced to one paragraph. No newsletter, routing or legal behavior changed.
- “Das Verzeichnis in Zahlen” uses Aktiv / Dauerhaft / Vorläufig / Änderungen ·
  30 Tage. All validated KPI calculations and unavailable states are unchanged.
  Freshness uses the latest parseable scan timestamp, validated snapshot fallback,
  then an explicit unavailable state; Berlin formatting without a timezone label.
- Maximum five existing newest eligible groups retained. Name first, one short
  taxonomy label, compact status/price/text summary, timestamp and stable detail
  link; no manufacturer paragraph or verbose field/evidence text. Additional
  adjustments are indicated by count. Full changes dashboard remains intact.
- Reduced top/hero/section/list spacing using existing tokens. Native mobile
  disclosure retained; 44px navigation targets, wrapping text, two-column phone
  KPIs/four desktop columns, and focus rules retained. No framework or script.
- Installed Streamlit 1.63 frontend confirms `stMainMenu` and
  `stStatusWidgetRunningIcon` hooks. Self-review rejected hiding `stStatusWidget`
  because it also contains connection errors and Stop/Rerun controls. Only the
  menu/running animation are hidden; native header moved into normal flow.
- Loading review: both data caches already use show_spinner=False. Content
  signatures still read files on reruns; cold loads and query navigation still
  require work. No cache/invalidation or required signup rerun was bypassed.
  No measured browser performance claim is made.
- Full suite: 190 tests, 188 passed, the same two historical failures; zero new
  regressions. Added exact copy, compact preview, Berlin summer/winter freshness,
  fallback and narrow-chrome coverage. Existing routes, one form, consent and
  mocked result persistence pass. No live Brevo request.
- Codex self-review: only homepage_change_items/render_homepage changed among
  pre-existing app functions. Newsletter, dashboard, caches and business helpers
  are AST-identical to the starting commit. Full-data Phase A comparison remains
  identical: 380 raw, 263 eligible, 25 groups, 173 adjustments; four date filters
  and all price analyses match. Protected files and historical tests unchanged.
- Structural CSS review targets 320/375/390/430/768/1440px; actual browser widths
  tested: none. Prior browser permission denial was not debugged again. Real-device
  QA on the branch's Railway ui-preview remains required after publication;
  clipping/overflow, menu, focus, anchor behavior and actual spacing are unverified.
- No merge or production deployment. One normal push attempt is planned after
  the focused local commit; if sandbox networking blocks it, publish externally.

### Phase B.1 QA attempt / blocked visual review — 2026-09-16

- Started clean on `codex/ui-redesign-black-white` at
  `905391b4cb4b96fd2dc3cf12f0aa8cbeb617d5ff`. Implementation unchanged;
  this is a documentation-only handoff, not completed visual QA.
- Started Streamlit 1.63 locally at `http://127.0.0.1:8507` using the ignored
  preview harness with dummy legal facts and a mocked DOI function. No live
  Brevo request or signup was made.
- Chrome browser automation rejected the local URL because a saved browser
  permission blocks it. Retried once after the user reported enabling access;
  the same policy denial remained. No alternate browser or permission bypass
  was attempted. Actual viewports reviewed: **none**. All requested widths
  (320/375/390/430/768/1440px), screenshots, menu/anchor/keyboard behavior,
  touch targets, visual signup states, and horizontal overflow remain unverified.
- No browser-confirmed visual defect or UI fix. Existing AppTest checks pass
  for homepage structure, a single signup form, consent, mocked submission and
  result persistence, changes filters/details, and privacy/confirmation routes.
  These checks do not establish visual correctness or pending/error appearance.
- Full suite rerun: 186 tests, 184 pass, the same two historical-test failures;
  zero new failures. Read-only Phase A comparison also passes: 380 raw / 263
  eligible events, 25 groups, 173 adjustments, four date-filter cases and all
  price analyses identical. Existing newsletter behavioral AST is identical
  after excluding the Phase B heading/anchor; 110 other existing helpers match.
- Historical discrepancy proven from Git: the frozen audit at
  `7f162516c4c285454a75b33217d8d5e812480553` contains 369 events, ending with
  `changes_20260824T0754472624370000.json`. Its projection through current code
  still has 22 groups and exactly matches the committed SHA-256
  `96daa8ad6a12277e9758f6aab229fbc9bfcf35f5827bb0aac6b7fb03ba56f197`.
  No original change files differ. Monitoring commits `f8569bf`, `197c314`,
  and `10d17cd` added September 1/7/9 files with 6/3/2 events respectively:
  369 + 11 = 380, with no exact duplicate events. This is corpus growth,
  not altered eligibility, deduplication, or UI event processing.
- A count-only test update would still be incorrect: the September 7 file
  includes two `directory_metric_change` events for `__directory__` without
  `snapshot_context`, as intentionally emitted by the pre-existing
  `directory_metric_event` producer. All other current events have embedded
  context. The old safety assertion assumes every event is a per-DiGA event.
  Tests and protected audit fixtures were left unchanged. A follow-up should
  scope frozen projection equivalence to its original corpus and distinguish
  directory-level events from per-DiGA context checks, preserving both safeguards.
- Self-review: only this handoff document changed; no protected files, data,
  secrets, production configuration, or application behavior changed. README
  requires no update. No merge or deployment. Network remains sandbox-disabled
  (`CODEX_SANDBOX_NETWORK_DISABLED=1`, HTTPS proxy `http://127.0.0.1:9`), so
  publication is unavailable and no push was attempted.
- Remaining gate: resolve the saved browser permission before completing actual
  visual/interaction QA. This branch is not yet visually cleared for merge.

### Phase B validation / handoff — 2026-09-16

- Default route: compact desktop links/native mobile menu, requested hero copy
  and anchor CTAs, four KPIs, five newest existing DiGA/date groups, explanation,
  one existing signup form, and existing privacy footer. No JavaScript/framework,
  new search/filter chips, duplicate signup widgets or invented legal content.
- `?view=changes` contains the original full filter/group/detail experience.
  Privacy and confirmation routes preserve their readiness gate and behavior.
- KPI source: tracked `data/baseline/current_snapshot.json`, persisted by the
  existing monitor workflow. `directory_metrics.active_count` excludes removed
  and unknown entries and equals permanent + provisional; the other market
  cards use `status_counts.permanent` and `status_counts.provisional`.
  The read-only adapter validates all aggregates against existing
  `calculate_directory_metrics` semantics; missing/inconsistent input is
  unavailable, not zero. Cached summary is keyed by snapshot content signature.
- Inspected snapshot: 2026-09-15 19:24 UTC (21:24 Berlin), 80 total entries,
  62 active = 50 permanent + 12 provisional, 18 removed, 0 unknown. UI shows the
  snapshot's date explicitly and makes no live-data claim.
- Fourth KPI: deduplicated displayed adjustments in 30 Berlin calendar days,
  today included. For 2026-09-16: Aug 18–Sep 16, 15 adjustments. Counts are
  calculated from the unchanged full-dashboard grouping; no market status is
  inferred from change history. The homepage uses the full dashboard's default
  date eligibility (dated records on/after tracking start).
- Before/after comparison: 380 stored events, 263 eligible events, 25 groups,
  173 displayed adjustments; ordering/grouping, four date filters and every price
  analysis match Phase A. Existing business helpers/cache/legal functions are
  unchanged. Newsletter changes are limited to its heading and scroll anchor.
- Full suite: 186 tests, 184 pass, the same two pre-existing failures expecting
  369 historical events instead of 380. No protected fixtures were edited.
  New tests cover market semantics/inconsistency/unavailability/cache refresh,
  recent order/limit/date boundaries/escaping, routes, one form and mocked signup.
  No real Brevo request or signup occurred.
- Codex self-review (Claude unavailable): corrected a preview edge case that
  could include undated/pre-tracking records; added a default-filter equivalence
  test. Removed empty manufacturer markup. No business-logic or protected-file
  changes, duplicated forms, color-only cues, new generated selectors or scope
  expansion found. Mobile styling uses owned classes and the Phase A tokens.
- Browser access was denied earlier; actual rendering and menu/anchor/focus/
  overflow behavior remain unverified at 320/375/390/430/768/1440px. AppTest only
  verifies server/widget behavior. Visual review is required before deployment.
- Sandbox network remains disabled; no further connectivity debugging or push
  attempted. Publish the local commit externally when ready. Main untouched.

### Phase A validation / handoff — 2026-09-16

- Central CSS tokens, a presentation-only `src/ui.py`, and a light monochrome
  Streamlit theme replace scattered colored/OS-dark-mode presentation rules.
- Newsletter functions, business helpers, cache inputs, routes and render order
  were compared against the starting commit; behavioral code is unchanged.
  Full current-data comparison: 380 raw events, 263 eligible events, 25 groups,
  173 displayed adjustments; ordering/grouping and four date-filter cases match.
- The starting main suite has two pre-existing failures: historical tests expect
  369 events, but current data contains 380. Protected fixtures and existing
  tests were not changed to conceal this mismatch.
- Nine new presentation/Streamlit AppTest checks pass, including mocked signup,
  consent, reruns/result persistence and existing legal routes. No real Brevo
  request or signup was performed. Full suite: 169 tests, 167 pass, the same
  two baseline historical-count failures, no new failures.
- Claude was unavailable per task instruction. Codex self-review checked the
  protected-file boundary, unchanged business/newsletter logic, CSS hooks,
  non-color semantics, branding and Phase A scope. An obsolete native CSS hook
  and an overly broad text-color rule were removed during review.
- Browser access to the local preview was denied. Actual mobile/desktop
  rendering, overflow, keyboard focus and touch targets still need visual
  review at 320/375/390/430/768/1440px before Phase B. AppTest is not a visual test.
- The older production/configuration notes below are historical context, not a
  fresh verification of Railway settings or repository variables.

## Production status

DiGA Monitor is in production. The scheduler runs at 06:00, 09:00, 12:00, 15:00, and 18:00 in `Europe/Zurich`.

## Current architecture

- Scheduled DiGA monitoring runs produce monitoring data and historical artifacts.
- R2 is configured for new archives and checkpoints.
- All 369 historical events now carry embedded `snapshot_context`; the dashboard no longer performs a runtime lookup in `data/snapshots/`.
- A reproducible audit classified all 842 legacy snapshots into 35 unique monitored states and 807 redundant snapshots. The resulting retention plan contains 57 deduplicated legacy/event/checkpoint/boundary/baseline objects, all verified in R2.
- All 842 legacy JSON snapshots have been removed from the current tree while retaining `data/snapshots/.gitkeep`; no R2 object or historical Git object was changed.
- GitHub is the shared source of truth for code and project handoff state.
- The automatic GitHub Actions Claude PR review has been removed. Substantial changes use the local Gauntlet workflow: Codex implements, Claude Code orchestrates independent Claude-Critic reviews, and Claude Code performs Git plumbing. `scripts.claude_review` remains available as a manually invoked local review tool with API-key authentication, a redacted connectivity preflight, isolated Claude configuration, and read-only tools.
- Dashboard inputs use content-addressed Streamlit caching: file-content signatures invalidate cached change events and scan history automatically on deployment changes.
- Notification sender and recipients are resolved independently from message creation and Brevo Transactional Email API transport. Production uses `DIGA_MONITOR_EMAIL_FROM`, `DIGA_MONITOR_EMAIL_FROM_NAME`, and `DIGA_MONITOR_EMAIL_TO`; no email address is hardcoded in Python.
- Public notification identity is unified on **DiGA Tracker** (email subject, greeting, signature, and the `notify-test` simulation; the `TEST / SIMULATION` marker itself is unchanged).
- The dashboard link in notification emails is resolved by `resolve_dashboard_url()` in `src/notifications.py`: it prefers `DIGA_MONITOR_DASHBOARD_URL` (naming-consistent with the other `DIGA_MONITOR_EMAIL_*` variables) and falls back to the legacy `DASHBOARD_URL` variable for as long as that stays set — code-verified precedence, unchanged this session. No dashboard URL is hardcoded in source.
- **Railway is now the production dashboard hosting.** The public dashboard (`app.py`, Streamlit) is deployed on Railway from this repository's `main` branch (Railpack build; repo-based `railway.json` sets `deploy.startCommand`, `.python-version` pins the Python runtime — see commit `1370a7f`). **Streamlit Community Cloud is no longer the production host.**
- **Production public URL: `https://www.diga-tracker.de`.** The domain is verified and reachable; `diga-tracker.de` (bare/apex) redirects to `https://www.diga-tracker.de`. DNS itself is managed outside this repository (GoDaddy + Railway custom domain) and was not touched here.
- The `DIGA_MONITOR_DASHBOARD_URL` GitHub repository variable should be set to `https://www.diga-tracker.de` so production notification emails link to the new domain; as of this update it has not yet been set (Claude Code/Codex has no GitHub write credentials in this environment — see "Next recommended step"), so email links still resolve to whatever the legacy `DASHBOARD_URL` variable currently holds.

## Last completed work

Documented the production URL switch to `https://www.diga-tracker.de`
(Railway-hosted dashboard, verified and reachable; `diga-tracker.de`
redirects to the `www` host; Streamlit Community Cloud is no longer
production). Code precedence for `DIGA_MONITOR_DASHBOARD_URL` over the
legacy `DASHBOARD_URL` was re-verified and needed no change. Setting the
`DIGA_MONITOR_DASHBOARD_URL` GitHub repository variable itself remains a
manual step (see "Next recommended step") — no GitHub write credentials
are available in this environment. No R2, baseline, history, or
change-detection logic was touched; no test email was sent; no DNS change
was made.

Before that: prepared the repository for the Railway migration (commit
`1370a7f` on `main`, committed directly per the small/low-risk rule since
it only added deploy config/docs/tests and changed no monitoring, R2, or
email logic): added `railway.json` (`deploy.startCommand`:
`streamlit run app.py --server.address=0.0.0.0 --server.port=$PORT
--server.headless=true`) so Railway needs no manually maintained Start
Command, added `.python-version` (`3.11`) for a deterministic Railpack
build, added `tests/test_railway_config.py`, and documented the setup in
README.md. `requirements.txt` was already complete for `app.py` (its only
third-party import is `streamlit`).

Before that: merged branch `codex/rebrand-diga-tracker` → `main` (merge commit on top of
`9aafc42`): unified the public notification identity on "DiGA Tracker" and
made the public dashboard URL configuration-driven via the new
`DIGA_MONITOR_DASHBOARD_URL` variable (legacy `DASHBOARD_URL` kept as a
documented technical fallback). Scope confined to branding strings, the
dashboard-URL resolver, `.env.example`, the DiGA Monitor workflow, README,
and tests; no R2, baseline, history, or change-detection logic was touched.

**Claude Review — deliberately overridden:** the Claude PR Review run for
this branch authenticated successfully via the API-key preflight and failed
exclusively with "Credit balance is too low," producing no substantive
findings to accept or reject. GitHub Actions unit tests for the branch
(`R2 Connectivity Check`, `mode=tests`) passed per the user's direct report.
The user explicitly decided to override the review-gate for this PR given
(a) the auth preflight worked, (b) the only failure was insufficient
Anthropic API credit, (c) tests were green, and (d) the change was scoped to
branding/dashboard-URL configuration only. Codex/Claude performed an
explicit self-review of the final diff instead (branding-string sweep,
dashboard-URL fallback order, workflow/env-var wiring, test coverage) and
found no issues before merging.

Previously: merged PR #5 (`codex/notification-recipient-config` → `main`,
commit `5c95bde68c54f01583ffb4fac62c0d8d2e06886f`): production Brevo sender
configuration and API-key-authenticated Claude review. 77/77 tests passed
before merge; the final Claude review rerun authenticated successfully and
produced no new findings, but failed exclusively with "Credit balance is too
low" and was consciously overridden for the merge.

## Current branch / PR

- Active implementation branch: `codex/ui-redesign-black-white` (Phase A + B;
  not merged or deployed).
- `codex/rebrand-diga-tracker` is merged into `main` and is a candidate for deletion, pending confirmation.
- Branches `codex/legacy-history-cleanup-prep`, `codex/notification-recipient-config`, `codex/remove-legacy-snapshots`, and `infra/claude-github-review` are fully merged (0 commits ahead of `main`) and are candidates for deletion, pending confirmation.
- Open PR #2 ("Test Claude PR review end to end", branch `test/claude-review-e2e`) is explicitly marked "Do not merge" in its description — a harmless one-sentence `PROJECT_STATE.md` change used only to validate the Claude PR review workflow, GitHub OIDC, and Anthropic Workload Identity Federation end to end. It remains open and untouched.
- Legacy cleanup merge: `e5c96da083a818cc9009d1b6dab6acb3d83b665e`
- No Git-history rewrite has occurred.

## Tests

- GitHub Actions run 33072662784: 48 tests passed and the hardened migration job completed successfully.
- Retention proof: 842/842 snapshots classified; 35 unique monitored states; 807 redundant snapshots; every unique state has a retained representative.
- R2: 57/57 retention objects verified by stored and calculated SHA-256, decompression, JSON parse, `created_at`, and source comparison.
- Restore integration: the R2 baseline object was restored to an isolated `data/baseline/current_snapshot.json` and loaded through the production loader with 79 entries.
- Cleanup verification passed before merge, including dashboard, scan/baseline, simulation/CLI, manifest, and restore checks.
- Claude CLI 2.1.223 is installed. Automated authentication no longer uses its stored personal OAuth account; it requires `ANTHROPIC_API_KEY` and an isolated temporary config directory.
- Dashboard benchmark fixture: 31 change files (17,763,374 bytes), 369 events, 252 real events, 21 groups, and 162 rendered adjustments. The measured end-to-end warm rerun path improved from about 452 ms uncached to about 99 ms cached in the local benchmark harness.
- GitHub Actions run 33094466784: all 54 tests passed for the dashboard performance change.
- GitHub Actions run 33252731862: all 74 tests passed for the API-key-only Claude review integration.
- No Python interpreter is available in this session's local environment, so `tests/` could not be re-run locally this session; test status above reflects the last GitHub Actions runs prior to the PR #5 merge. Rely on GitHub Actions for the authoritative result on the next change.
- `R2 Connectivity Check` (`mode=tests`, i.e. `python -m unittest discover -s tests`) on `codex/rebrand-diga-tracker` passed per the user's direct report before the rebrand merge; the exact run was not independently re-verified via the GitHub API in this session due to the unauthenticated rate limit (see below).

## Open risks/blockers

- Historical Git objects remain available because no history rewrite was performed.
- `ANTHROPIC_API_KEY` remains intentionally unavailable to the local Codex process; GitHub Actions now supplies it exclusively from the repository secret.
- No Python interpreter is installed in this session's local environment; local test/lint execution is not currently possible here.
- Several remote branches are fully merged into `main` and unused; deletion has not been requested or performed.
- Neither Claude Code nor Codex in this environment has GitHub API/UI write credentials (no `gh` CLI, no `GITHUB_TOKEN`, no authenticated browser session, no connected "Claude in Chrome"); setting repository variables, triggering `workflow_dispatch` runs, and opening/merging pull requests currently requires the user to act in the GitHub UI. Direct `git push`/local merge remains available and was used to land code/doc changes.
- `DIGA_MONITOR_DASHBOARD_URL` is not yet set as a GitHub Actions repository variable even though the production domain is now live; production notification emails still link to whatever the legacy `DASHBOARD_URL` variable currently holds until someone sets it (see "Next recommended step"). This is a configuration gap only — code precedence is already correct.

## Next recommended step

Review the Phase B homepage visually before planning Phase C. Resolve the two
pre-existing historical-test count expectations in a separate, authorized
data/test-maintenance task; this presentation change deliberately leaves them
untouched. Do not merge or deploy this branch without a subsequent decision.

The following production URL configuration follow-up is retained from the
earlier handoff and was not re-verified during Phase A:

1. In the `Tenere42/diga-monitor` repository, go to
   `Settings > Secrets and variables > Actions > Variables` and set (or
   update) the repository variable `DIGA_MONITOR_DASHBOARD_URL` to
   `https://www.diga-tracker.de`. This is the only step needed to switch
   production notification emails to the new domain; everything else
   (Railway hosting, DNS, redirect, code precedence) is already in place.
2. Otherwise, await the next ChatGPT decision/spec, or a decision on closing
   PR #2 and pruning the fully-merged stale branches (including
   `codex/rebrand-diga-tracker`, already merged).

## Last updated

2026-09-16 (Phase B homepage; production unchanged)
