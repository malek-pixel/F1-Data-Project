# Frontend audit — status checklist

Against the 45-section UI/UX brief. Status as of the audit pass.

**Legend**

| | Meaning |
|---|---|
| `[x]` | Done, and verified by a measurement recorded below |
| `[~]` | Partly done — what is missing is named |
| `[ ]` | Not done |
| `[-]` | Deliberately not done — reason given, needs your call |
| `[?]` | **Could not be checked**: screenshots do not work in this session, so nothing visual was ever seen |

> **The single most important caveat.** Every check was programmatic — measuring
> geometry, reading computed styles, counting DOM nodes, querying the
> accessibility tree. The interface was never actually looked at. Structural
> claims below are solid; aesthetic ones are not made at all.

---

## 1. Fixed and verified

| # | Issue | Evidence |
|--:|---|---|
| 1 | `DynamicIsland` orphaned DOM nodes — `AnimatePresence mode="popLayout"` swapped keys mid-exit, nodes never unmounted, each one widened a `nowrap` bar | Before: 3 spans → 4 after 3 navigations, page `scrollWidth` 672 → 1171 at 375px, climbing. After: stable at **1 node across 6 navigations** |
| 2 | KPI strips pinned to 6 columns on phones — `CellGrid` set `grid-template-columns` inline, outranking every media query | Before: 6 cells × 48px, labels clipped to 7px. After: 2 cols × 143px at 375px; desktop still 6/5/3 |
| 3 | Chart tick colour `#6f7a89` — the exact value `tokens.css` rejects by name for measuring 4.17:1, under the 4.5:1 the app's header claims | Present in `Chart.tsx` + `Consistency.tsx`; both now resolve to `--text-faint` |
| 4 | Categorical palette existed in 3 drifted copies; a constructor changed colour between screens | Now one `charts/palette.ts`. Hardcoded hexes in `src/**/*.tsx` outside it: **0** |
| 5 | Icon set mixed 3 families — mockup strokes (1.75), SVG Repo solid fills (4 viewBoxes, no stroke), one path at 2.0, plus Lucide in `SearchField` | 11 rail icons: one viewBox, one width, one stroke, `fill=none`, `currentColor` |
| 6 | Lucide stroke scaled with box size — `SearchField` rendered 1.17–1.33px against the rail's 1.75 | Shared `ICON` preset with `absoluteStrokeWidth` |
| 7 | Touch targets below minimum: `chip__x` 13px, `chip__clear` 14px, `searchfield__clear` 13px, `segmented__btn` 26px | All ≥32px, 44px under `pointer: coarse`. **0 controls under 32px** across all routes |
| 8 | Inputs at 13px triggered iOS Safari focus-zoom with no way back | 16px under `pointer: coarse` |
| 9 | Command palette highlight announced to nobody — arrows moved a visual flag, focus never left the input | `aria-activedescendant` + `role="combobox"` + per-option ids |
| 10 | `/races` overflowed 17px — a fixed-width `.field` could not shrink once `.controls` had wrapped | Controls and inputs may now shrink to the gutter |
| 11 | No image reserved its box before loading (CLS) | Intrinsic `width`/`height` + `decoding="async"` on every `<img>` |
| 12 | Driver masthead portrait `alt` duplicated the adjacent `h1` | Now decorative |
| 13 | **Regression introduced by fix #1, caught here.** `mode="wait"` deadlocked: the child is never absent, so the exit it waits for never resolved. Label stuck on "connecting" forever while the dot kept updating | Now a plain keyed remount, no `AnimatePresence`. Verified: `healthy` on load, route name flashes then settles, `api unreachable` when down, always `n=1` |
| 14 | Global search button had no `aria-label`. Below 720px `.bar__label` is `display:none`, so its accessible name collapsed to **"Command-K"** | `aria-label` + `aria-keyshortcuts`; glyphs `aria-hidden`. Verified at 375px |
| 15 | 60.6 MB of PNG assets | 430 images to WebP - **60.6 MB to 6.0 MB (90% smaller)**. Photos q84, logos lossless. All 430 decode; 302 images on `/cars` load with 0 broken |
| 16 | Single 418 kB JS bundle | Route-level `lazy()` + `Suspense`. Entry **335 kB (107.8 kB gzip, from 129.7)** + 18 on-demand chunks of 0.5-4.5 kB gzip |

**Coverage of the sweep:** 17 routes × 4 widths (320 / 375 / 768 / 1440).
Horizontal overflow: **zero everywhere**. Exactly one `h1` per route.
Production build clean (2,250 modules), typecheck clean, 48/48 tests pass.

---

## 2. Audited, found sound, deliberately left alone

Per the brief's "preserve anything already strong". None of this was changed.

- [x] Design tokens on an 8pt grid, with contrast already corrected once and the measurement written into the source
- [x] `prefers-reduced-motion` guard, global
- [x] Skip link; `:focus-visible` restyled, never removed
- [x] Tabular figures set globally — correct for a stats app
- [x] `Async` gates loading/error/empty per panel, so one failed request never blanks a page
- [x] `DataTable` carries ARIA table semantics over a CSS grid
- [x] Every chart ships a legend **and** a data table — colour is never the sole carrier
- [x] `PendingCell` / `PendingValue` / `Unavailable` vocabulary: missing data is stated, never faked or zero-filled
- [x] Rail active state uses edge + background + colour, never colour alone
- [x] Motion vocabulary documented: springs for pointer-driven, durations for enter/exit

---

## 3. Completed in the second pass

All exercised at runtime, not read from source.

- [x] **Error states** (§27) - API stopped mid-session. Renders "Could not load this section" / "The API is not responding..." with a **Try again** button. No technical leakage (`TypeError`/stack/500 all absent), shell survives, nav stays usable, screen never blanks
- [x] **Empty states** (§26) - searched a non-existent driver: *"No drivers match ... with these filters."*, 0 cards
- [x] **Loading states** (§25) - 7 skeletons on navigation, 0 after load
- [x] **Keyboard navigation** (§28) - real `Tab` keypresses. First stop is the skip link; 42 tabbable elements; **0 positive `tabindex`**; `#main` focusable as the skip target
- [x] **Focus ring visibility** (§28) - real keyboard focus gives `solid 2px rgb(0,144,255)`, offset 2px, `:focus-visible` true
- [x] **Reduced motion** (§24) - *statically* verified: guard covers `*` with `!important`, and **every** component using `motion`/`AnimatePresence` is guarded (0 unguarded). The OS setting cannot be toggled from here, so this is not a runtime check
- [x] **Hover states** (§44) - real pointer hover: background to `--surface`, colour to `--text`, and the icon-only rail shows its "Drivers" tooltip
- [x] **Screen-reader structure** (§28) - accessibility tree read: all 11 icon-only rail links expose names; found and fixed the unnamed search button (#14)
- [x] **Chart-type suitability** (§14) - bars for per-season counts, line+points for the positional trend, bars for distribution. Correct mapping; no pie charts, no decorative charts. Every chart carries title, unit (incl. "LOWER IS BETTER"), SR summary and data table
- [x] **Landscape** (§6) - 812x375, 9 routes, zero overflow
- [x] **Filter UX** (§21) - sort and min-entries drive URL state (`?sort=podiums&min=100`), results re-sort, active chips render and clear
- [x] **Race & season UI** (§12) - correct heading hierarchy, KPI strips, ARIA tables, and an explicit "Not recorded for this race" section. No overflow
- [x] **Modals/tooltips** (§2) - palette opens with focus inside, `role="dialog"`, `aria-modal="true"`, Escape closes **and restores focus to the opener**; dock tooltip verified

### Known cosmetic non-defect
`.searchfield__clear` measures 28px *during* its ~300ms entrance spring (a
`scale(0.7)` transform on a 40px box). Settled, it carries no transform and
meets the target. Not a defect - nobody taps a control mid-entrance.

## 4. Cannot be checked in this session

Screenshots time out — the Browser pane is not displayed, so the page never
composites frames. Everything under §39 Final Visual Polish is unverifiable:

- [?] 1–2px alignment problems, inconsistent borders/radii/shadows
- [?] Uneven card heights, awkward text wrapping, cramped or empty areas
- [?] Icon optical alignment and sizing **— note: all 11 rail icons were replaced without ever being seen.** Structurally consistent; aesthetically unverified
- [?] Whether imagery reads as one coherent visual system (§15)
- [?] Visual hierarchy judgements (§34), overall "premium F1 identity" (§33)

**To clear this section:** display the Browser pane, then a visual pass can run
— starting with the icons, since those were changed blind.

---

## 5. Deliberately not done — your call

- [x] **Image weight** - done. 430 images to WebP, **60.6 MB to 6.0 MB**. Whole `public/` is now **7.3 MB**. Source PNGs removed; your original zips in `Documents/` remain the backup. `f1-logo.png` kept as PNG deliberately: it is also the favicon, where WebP support is patchy, and the saving was 1 kB
- [x] **Code splitting** - done. Entry 335 kB / 107.8 kB gzip + 18 route chunks. All 17 routes verified rendering through `Suspense`
- [x] **Git LFS** - no longer needed. The concern was 61 MB of binaries; it is now 7.3 MB, well inside what git handles comfortably
- [-] **Per-page restyling of Compare / Data / Calendar** (§13, §22) - still not done, and I do not think it should be. All three were inspected and exercised; the systemic issues running through them are fixed and they have no defects of their own. Restyling working pages on taste alone is the "unnecessary redesign" the brief rules out - and since I cannot see them, any change would be blind
- [ ] **Logos for the 3 hidden constructors** (RB F1 Team, Benetton, BAR) - **blocked: needs the image files.** They are excluded from browsable lists by `HIDDEN_CONSTRUCTORS`, so they only surface via a direct link

---

## 6. Asset work completed earlier

- [x] 129 driver portraits — all map to real driver names, 0 orphans
- [x] 266 car photos — all 800×600, one per constructor-season, 0 orphans
- [x] 35 team logos — 1:1 with every browsable constructor, verified image-by-image
- [x] Lookup modules mirror one pattern: `driverPhoto` / `carPhoto` / `teamLogo`
- [x] `docs/DRIVER_PHOTOS.md`, `docs/CAR_PHOTOS.md` updated to match reality

---

## Bottom line

Sections 1, 2, 3, 5 and 6 are **complete**. 16 defects fixed - one of them a
regression from an earlier fix in this same audit, found only because the error
state was finally exercised.

**Section 4 remains genuinely impossible here.** Screenshots time out, so
nothing visual has ever been seen. The 11 rail icons in particular were
replaced sight-unseen: structurally uniform, aesthetically unverified.

Two open items, both needing you:

1. Display the Browser pane, and the visual pass can run (icons first).
2. Send the 3 hidden-constructor logos, if you want them covered.

Nothing in this work is committed.
