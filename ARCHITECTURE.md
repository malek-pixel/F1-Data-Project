# Architecture

## Shape

```
results.csv                    source of truth for facts
    │
    ├── backend/etl/build.py   validate → normalize → load   (reproducible, idempotent)
    │      └── circuit_map.csv curated race_name → circuit resolution
    ▼
data/f1.db                     SQLite build artefact, not tracked in git
    │
    ├── backend/app/analytics.py   source of truth for CALCULATIONS
    ├── backend/app/routers/       REST surface, input validation
    ▼
    │
    ├── supabase/migrations/*.sql  the same data as Postgres views
    ▼
backends.serve() ── picks the store per request (F1_BACKEND)
    │
FastAPI (:8000)  ── /api ──▶  React + Vite (:5173)   presentation only
```

## The one rule everything else follows

**Facts come from `results.csv`. Derived numbers come from `analytics.py`. Nothing else calculates.**

A router does not compute a rate. A React component does not sum a column. If a
number appears in the UI, there is exactly one function that produced it and one
docstring that defines it. This is what makes the numbers auditable, and it is
why the same stat block appears identically on a driver page, a leaderboard row
and a comparison panel.

## Layers

### `backend/etl/` — the pipeline

`build.py` drops and rebuilds `data/f1.db` on every run. There is no incremental
path and no migration story, deliberately: the database is a pure function of
`results.csv` plus `circuit_map.csv`, so it cannot drift from its source.

Validation runs before any write. Fatal findings (duplicate entries, broken
references, unmapped race names, malformed dates) abort the build with the
database untouched. Warnings (a known upstream gap, a circuit without a track
map) are reported and proceed. `--report` prints the full data-quality report.

`circuit_map.csv` exists because `results.csv` has no circuit column and
`race_name` is not a stable circuit key — five Grands Prix changed venue inside
the covered window. The map is a plain CSV so it can be reviewed and diffed, and
the build fails on any unmapped `(race_name, season)` pair rather than silently
dropping a race.

### `backend/app/analytics.py` — the calculations

Every metric, with its formula, denominator, edge-case behaviour and known
limitation in the docstring. The module header lists what is deliberately
*absent* and why, so the reason a metric is missing is recorded next to the ones
that exist.

`_STATS_SELECT` is the single aggregate expression behind every stat block.
Reusing it is what guarantees a driver's win count is the same number on every
screen it appears.

### `backend/app/routers/` — the API

Thin. Parse and validate input, call analytics, return a schema. Query
parameters are constrained by FastAPI (`ge`/`le`/`Literal`), so bad input is
rejected with a 422 before a query runs. Sort keys resolve through a fixed
dictionary — an ORDER BY clause can only ever be one of the known strings. LIKE
patterns are escaped. Nothing is interpolated into SQL.

Connections open in SQLite read-only mode (`mode=ro`). A bug in a router raises
rather than corrupting the dataset.

### `backend/app/backends.py` — which store answers

The same dataset is materialised twice: `data/f1.db` (SQLite, rebuilt from the
CSV) and a hosted Postgres project (Supabase, read over PostgREST). `F1_BACKEND`
selects between them per request.

`serve(endpoint, sqlite_impl, supabase_impl)` runs whichever the active backend
provides and **raises rather than falling back**. A silent fallback would let
the Supabase leg appear to work while never being exercised — which is exactly
what happened for as long as two thirds of the routes never called `serve` at
all, and what the payload-parity suite failed to catch while it was comparing
one store against itself.

28 of 30 routes dispatch. `/api/insights` has no Postgres implementation and
returns 501 under Supabase; `/api/analytics/metrics` returns Python constants
and touches no store. `test_api_payload_parity.py` compares 77 request paths
across both stores, response for response.

The metric definitions live in `analytics.py` for SQLite and in the migration
views for Postgres. Where a definition would otherwise be written twice — the
record list, the dominance basis string, the rounding rule — it is a shared
Python constant that both legs read.

### `frontend/` — presentation

React + TypeScript + Vite. `src/types.ts` mirrors `schemas.py`. Components
render what the API returns and format it; they do not derive.

Three dependencies beyond React: `react-router-dom`. That is the list.
Charts are hand-rolled SVG, styling is a token stylesheet transcribed from the
design system, and data fetching is one `useApi` hook. Each of those was cheaper
to write than to configure, and each avoids a layer between the design tokens
and the output.

## Cross-cutting decisions

**Unavailable is a rendered state, not an omission.** `<Unavailable>` shows a
metric the dataset cannot support and names the missing column. A reader can
distinguish "we do not have this data" from "this value is zero" from "someone
forgot to build this".

**Null and zero are different.** A rate is `null` with no entries and `0.0` with
entries but no wins. This distinction survives the database, the API, the types
and the formatters — `num()`/`pct()` render `null` as an em dash, never as 0.

**Small samples are flagged, not hidden.** Rates below the entry threshold carry
`rates_reliable: false` and are marked in the UI. Records apply the threshold as
a hard filter so a one-race driver cannot top a rate table.

**Season rankings are labelled.** Alongside the real points standings, season tables also rank
by wins and every one of them says so on screen.

## Testing

| Suite | What it protects |
|---|---|
| `backend/tests/test_analytics.py` | Formulas, against a 12-row fixture with hand-computed answers |
| `backend/tests/test_data.py` | Pipeline integrity against the real build — counts, relationships, invariants |
| `backend/tests/test_api.py` | Contract: valid requests, 422s, 404s, empty results, pagination |
| `frontend/src/**/*.test.tsx` | States, formatting, table interaction |

Analytics tests deliberately run against a fixture rather than the real
database: asserting that a formula is correct requires numbers verifiable by
hand.

## Extending

**Adding a season.** This used to read "append to `results.csv`, check
`circuit_map.csv`, rebuild". That was the whole procedure when the database
held seven columns. It no longer is: `results.csv` is the spine, but points,
grid, status, qualifying, sprints, pit stops, lap timings and practice each
come from their own committed extract, and a season added to the spine alone
produces a database that is *structurally* valid and *materially* incomplete.

Order matters — each step's output is the next step's input:

| # | Step | Command |
|---|---|---|
| 1 | Extend the spine | append the season's classifications to `results.csv` |
| 2 | Cover new race names | add any new venue to `backend/etl/circuit_map.csv` (the build **fails** on an unmapped name rather than dropping the race) |
| 3 | Refetch Jolpica (network, 500 req/hour) | `python -m backend.etl.fetch_until_done` |
| 4 | Rewrite the enrichment extracts | `build_enrichment`, `build_dimensions`, `build_sessions` |
| 5 | Lap timings | `python -m backend.etl.laps_until_done` then `build_laps` |
| 6 | Practice (FastF1, 2018+) | `python -m backend.etl.practice` then `build_practice` |
| 7 | Rebuild | `python -m backend.etl.build --report` |
| 8 | Prove it | `python -m backend.etl.audit` **and** `python -m backend.etl.crossvalidate` |
| 9 | Push to Postgres | `python -m backend.etl.supabase_import`, then `pytest backend/tests -q` with credentials set |

**Step 8 is the gate, and it is designed to fail on a half-added season.** The
audit's coverage floors assert that every race from 2003 has qualifying, every
race has lap timings, every race from 2012 has pit stops, and that every season
carries the sprint, practice and timetable data its era should. Adding a season
to `results.csv` and stopping there trips **all six** — verified by inserting a
spine-only 2026 round into a copy of the database. That is the intended
behaviour: before those floors existed, the
same half-finished season passed the audit silently and the application
rendered the missing datasets as "unavailable", which tells a reader the data
does not exist rather than that it was not loaded.

Two things the pipeline cannot check for you:

* **`circuit_map.csv` encodes external knowledge, not source data.** A renamed
  or relocated Grand Prix needs a human decision about circuit identity.
* **`frontend/src/components/carPhoto.ts`** holds a hand-maintained list of
  seasons per constructor. It is presentation only — a missing entry degrades
  to a labelled fallback, never a wrong figure — but it will not pick up a new
  season on its own.

**Adding a metric:** define it in `analytics.py` with its docstring, add it to
the schema, surface it. Update `METHODOLOGY.md` in the same change.

**Adding car data:** a `cars` table keyed on `(constructor_id, season)` slots in
without reshaping existing tables. The Car Library page is already built against
that absence and will render real fields when they exist.

**Qualifying, points and status are ingested.** This section used to say they
were the missing columns behind "the largest set of currently impossible
metrics — championship standings, DNF rate, points-per-race, pole rate". All
of it is now served: `points` and `classification` on all 10,550 results,
9,577 qualifying rows, 552,138 lap timings, 12,192 pit stops, and the
fastest-lap enrichment for 2004 onward. Standings reproduce the official
champion and points total for every covered season.

Pole position remains genuinely absent *as such*: qualifying P1 is counted and
labelled `qualifying_p1`, because the two diverge in the sprint era and the
field name has to say what was measured.
