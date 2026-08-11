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

**Season rankings are labelled.** No points column exists, so season tables rank
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

**Adding a season:** append to `results.csv`, check `circuit_map.csv` covers any
new race name, rebuild. The build fails loudly if it does not.

**Adding a metric:** define it in `analytics.py` with its docstring, add it to
the schema, surface it. Update `METHODOLOGY.md` in the same change.

**Adding car data:** a `cars` table keyed on `(constructor_id, season)` slots in
without reshaping existing tables. The Car Library page is already built against
that absence and will render real fields when they exist.

**Adding qualifying/points/status:** these unlock the largest set of currently
impossible metrics — championship standings, DNF rate, points-per-race, pole
rate. They require new source columns; nothing in the current pipeline
approximates them.
