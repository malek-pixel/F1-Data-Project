# F1 Dashboard — Scope for Claude Design

## Division of labor (read this first)
- **Claude Design** (this doc): visual design and interactive prototypes only. Mockups, layout, styling, chart appearance, component states. Can use fake/sample data.
- **Claude Code** (separate doc, already written): real FastAPI backend + React app wired to actual `results.csv` / SQLite data.
- Do not build a live-data app here. Do not build static images there. If asked to do the other one's job, stop and flag it.

## Context
F1 stats dashboard. Data available: seasons 2000–2025, driver/constructor/circuit results. No live telemetry, no lap times, no quali data confirmed yet — design for what's realistic (Phase 3 scope below), not the full wishlist.

---

## Visual direction
- **Tone**: broadcast-graphics feel, not a generic SaaS admin dashboard. Think F1 TV graphics / timing screens — dense but legible, not sterile.
- **Mode**: dark-first. Data viz on dark backgrounds is standard for motorsport UIs and makes team-color accents pop.
- **Color**: neutral dark base (near-black, not pure #000) + a small set of accent colors for UI chrome (do NOT hardcode current F1 team colors as permanent brand colors — teams/liveries change yearly, and the dataset spans 2000–2025 with teams that no longer exist e.g. Renault, Force India). Use team colors dynamically per-driver/constructor in charts only, not as the app's fixed palette.
- **Typography**: a condensed/technical sans for numbers and stat displays (motorsport timing-screen feel), a standard readable sans for body text. Numbers should be tabular/monospaced where compared in a list (lap times, points, positions) so digits align.
- **Density**: this is a stats app — resist the urge to over-pad with whitespace like a marketing site. Users scanning driver stats want information density closer to a spreadsheet-meets-dashboard, not a landing page.

## Pages to design (matches Claude Code Phase 3 — do not exceed this)

### 1. Home
- Current/most recent season standings (driver + constructor)
- Quick nav into the three Explorers
- No live "current race" widget — data isn't live, don't imply it is

### 2. Driver Explorer
- Driver list/search
- Individual driver page: win rate, podium rate, avg finishing position, career timeline. **No pole rate, fastest lap rate, DNF rate, or points-per-race — confirmed unavailable in the source data (no quali/fastest-lap/points/DNF columns). Do not design UI slots for these unless the Claude Code data layer says otherwise later.**
- Head-to-head comparison view: pick 2 drivers, compare on the stats above only — this is a smaller comparison than originally scoped, design it clean rather than padding it with placeholders for missing stats
- Chart types needed: bar (wins by season), line (avg finishing position over time), side-by-side bars (head-to-head)

### 3. Constructor Explorer
- Constructor list
- Individual constructor page: wins/podiums by season, avg finish, which drivers contributed what share of team points (this last one wants a stacked bar or similar — two drivers' contributions per season)

### 4. Circuit Explorer
- Circuit list
- Individual circuit page: most successful drivers/teams at that circuit, winners over time (timeline/list)

## Explicitly NOT in scope for this design pass
- Telemetry views, lap time overlays, sector comparisons (no data yet — Phase 5)
- Race replay, what-if simulator, AI Q&A interface (Phase 7 — do not design UI for features that don't have a backend plan yet)
- User accounts, auth, settings pages
- Mobile-first design — design for desktop/dashboard use first; note where it would break on mobile but don't build a full responsive pass yet

## Component inventory to produce
- Stat card (single metric + label, used across driver/constructor/circuit pages)
- Comparison table/panel (head-to-head)
- Season-by-season chart component (reusable across wins/points/podiums)
- Searchable list/table (drivers, constructors, circuits)
- Empty state (no data for a filter combination — will happen, e.g. a constructor that only existed 2 seasons)
- Loading state

## Deliverable expectations
- Interactive prototype(s) with sample/placeholder data — not final wiring
- Clear enough component boundaries that Claude Code can map them to real React components without re-deriving the layout
- Flag anywhere the design assumes data that may not exist (e.g. quali position, fastest lap) — those are unconfirmed per the data audit in the Claude Code scope
