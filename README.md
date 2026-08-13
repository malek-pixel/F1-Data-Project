# F1 Data Project

An analytical application over Formula 1 race classifications, 2000–2025.
FastAPI + SQLite backend, React + TypeScript frontend, reproducible ETL.

The design goal was not a dashboard that looks complete. It was a system whose
numbers can be audited: every derived figure has one definition, one formula and
one place it is computed, and every metric the data cannot support is shown as
explicitly unavailable rather than estimated, hidden, or filled with a plausible
number.

---

## What it does

- **Driver, constructor and circuit explorers** — career and season records, searchable and sorted server-side
- **Race and season explorers** — full classifications for all 503 races
- **Teammate analysis** — head-to-head against every teammate, counted only over races both drivers started for the same constructor. The closest control for car performance this dataset allows
- **Consistency** — median, spread and a finishing-band histogram, because a mean of P8 describes both a reliable eighth and podiums-alternating-with-retirements
- **Circuit records** — each driver's record at a circuit against their own career norm
- **Season dominance and era views** — win share normalised by races held
- **Head-to-head comparison** — raw totals and per-start rates shown separately, with an overlapping-seasons window, because career totals across different eras are not a like-for-like comparison
- **Records, eras and season dominance** — calculated, each stating its own methodology
- **Dataset explorer** — schema, coverage, and the dataset's own known issues
- **Car library** — one entry per constructor-season, grouped by team and era
- **Metric definitions** — every formula, denominator and limitation, on the Insights page
- **Global search** — a full page (`/search`) plus the ⌘K palette, both keyboard-navigable

## What it deliberately does not do

The source is seven columns. These are absent and are **never** estimated:

> qualifying · grid position · pole positions · fastest laps · finishing status
> (DNF/DNS/DSQ) · championship points · points-per-race · championship standings
> · lap times · sector times · pit stops · tyre compounds · telemetry · sprint
> results · car specifications

Two consequences worth stating up front:

1. **`position` is classification order, not finishing status.** There is no status column, so a driver who retired on lap 1 still carries a classification number. The metric is therefore *average classified position*, never "average finish", and DNF rate is not computed.
2. **Season tables rank by wins, not points.** They are not championship standings, and every screen that shows one says so.

The Car Library page ships as an honest empty shell: no car data exists in the
source, so it documents the schema real data would populate instead of inventing
chassis or power figures.

---

## Architecture

```
f1_fetch.py            one-off acquisition, the only script that uses the network
     ↓
results.csv            committed to the repo; the single source of truth
     ↓
backend/etl/build.py   validate → normalise → load; aborts on any fatal finding
     ↓
data/f1.db             SQLite build artefact, gitignored, rebuilt in ~1s
     ↓
FastAPI                opens the DB read-only; all calculation lives in
                       backend/app/analytics.py and advanced.py
     ↓
React + TypeScript     presentation and formatting only; derives no metric
```

**SQLite is the production data store.** A PostgreSQL/Supabase materialisation
of the same CSV exists and is documented in [docs/database.md](docs/database.md),
but **no router calls it** — it is not on any request path, its 24 tests skip
without credentials, and it is not re-verifiable from this repository. See
`backend/app/supabase_repo.py` for its status. Nothing in the setup below
requires it.

---

## Stack

| Layer | Choice | Why |
|---|---|---|
| ETL | Python, stdlib `csv` + `sqlite3` | The dataset is 10,550 rows; pandas would be a dependency for nothing |
| Database | SQLite | Single-file, indexed, rebuilt from source on every run |
| API | FastAPI + Pydantic | Parameter validation at the boundary, OpenAPI for free |
| Frontend | React + TypeScript + Vite | — |
| Charts | Hand-rolled SVG | Same code as configuring a library, inherits the design tokens exactly, accessible table fallback per chart |
| Styling | CSS custom properties | The design system *is* a token set; a utility framework would restate it |
| Tests | pytest, Vitest + Testing Library | |

Runtime frontend dependencies: `react`, `react-dom`, `react-router-dom`.

---

## Setup

Requires Python 3.11+ and Node 18+.

```bash
# 1. Build the database from source (idempotent, ~1s)
pip install -r requirements.txt
python -m backend.etl.build --report

# 2. API on :8000
uvicorn backend.app.main:app --reload

# 3. Frontend on :5173 (separate terminal)
cd frontend && npm install && npm run dev
```

`--report` prints the full data-quality report. The build **fails and writes
nothing** on any fatal finding, so a corrupt source cannot reach the database.

No environment variables are required to run locally. `F1_ALLOWED_ORIGINS`
overrides the CORS allow-list (comma-separated) when the frontend is served
from somewhere other than `localhost:5173`. There are no secrets, no external
API calls and no network dependency — the pipeline reads one CSV in the repo.

## Tests

```bash
python -m pytest backend/tests -q      # 109 passed, 24 skipped
cd frontend && npm test                # 37 passed
cd frontend && npm run typecheck       # tsc --noEmit
cd frontend && npm run build           # production bundle into frontend/dist
```

| Suite | Covers |
|---|---|
| `test_analytics.py` | Formulas, against a 12-row fixture with hand-computed answers |
| `test_data.py` | Real build: counts, relationships, per-race invariants, read-only enforcement |
| `test_api.py` | Contract: 422s, 404s, empty results, pagination, wildcard escaping |
| `test_advanced.py` | Teammate/distribution/dominance formulas, hand-computed in the fixture comments |
| frontend | Null-vs-zero formatting, states, sorting, error handling |
| `test_supabase.py` | **24 cases, all skipped without credentials.** They test the unwired PostgreSQL path, so a green run says nothing about it |

Analytics tests run against a fixture, not the real database — asserting a
formula is correct requires numbers verifiable by hand.

Every headline metric is also cross-checked by recomputing it from
`results.csv` with independent code (plain dicts, no SQL, nothing shared with
`backend/`), so a bug cannot hide identically in both the implementation and
its test. Latest run: **0 discrepancies**.

---

## Dataset

| | |
|---|---|
| Source | `results.csv` — Ergast-derived race classifications |
| Rows | 10,550 |
| Coverage | 2000–2025 · 503 races |
| Entities | 129 drivers · 38 constructors · 39 circuits |
| Columns | `season, round, race_name, date, position, driver, constructor` |

**Provenance.** `results.csv` was fetched from the Ergast API (jolpi.ca mirror)
by [`f1_fetch.py`](f1_fetch.py), which extracts seven fields per classification
and is resumable per season. It is the only script in the repository that
touches the network; it is not part of the build, and `results.csv` is
committed, so the application runs offline. The database records the SHA-256 of
the CSV it was built from in `build_meta`, so any `f1.db` can be traced back to
exact source bytes:

```bash
sqlite3 data/f1.db "SELECT * FROM build_meta"
```

**Circuit identity is derived.** The source has no circuit column, and
`race_name` is not a stable key — the European, German, French, Japanese and
United States Grands Prix all changed venue inside the covered window. Circuits
resolve through `backend/etl/circuit_map.csv`, a curated season-aware map, and
the build fails on any unmapped race name rather than dropping a race silently.

24 of 39 circuits ship a track-map SVG; the other 15 render a map-unavailable
state.

### Verification

Spot-checked against known F1 history:

| | Computed | |
|---|---|---|
| Most wins | Lewis Hamilton, 105 | ✓ |
| Most podiums | Lewis Hamilton, 202 | ✓ |
| Most wins in a season | Max Verstappen, 19 (2023) | ✓ |
| Most wins at one circuit | Lewis Hamilton, 9 (Silverstone) | ✓ |
| 2021 top two | Verstappen 10, Hamilton 8 | ✓ |

---

## Linkable state

Analytical views are URLs, so a finding can be bookmarked or shared:

```
/drivers/65                                driver profile
/drivers?sort=win_rate&min=50              filtered, sorted library
/compare?kind=drivers&left=65&right=124    a specific comparison
/seasons/2004                              season detail
/circuits/31                               circuit profile
```

Filter changes use history *replace*, so tweaking a filter does not bury the
previous page under a dozen back-button steps while the URL stays shareable.

---

## Documentation

| File | Contents |
|---|---|
| [METHODOLOGY.md](METHODOLOGY.md) | Capability matrix, every formula and denominator, limitations |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Layers, the calculation-locality rule, extension points |
| [DATA_DICTIONARY.md](DATA_DICTIONARY.md) | Every column, table and derived field |
| [API.md](API.md) | Endpoints, parameters, error contract |
| [docs/database.md](docs/database.md) | PostgreSQL/Supabase schema and migrations — **built, not wired in**: the running app serves from SQLite |

---

## Known limitations

- Coverage begins in 2000 — no figure here is an all-time Formula 1 record
- No finishing status, so reliability and DNF metrics are impossible
- Season lengths vary 16–24 races; cross-era season totals are not normalised
- The 2002 French GP carries 20 rows but runs to P22 — an upstream omission, reported by the validator rather than patched
- `circuit_map.csv` encodes external knowledge, not source data; it should be reviewed when a season is added
- Data is static. Nothing is live, and no screen implies an in-progress race
- The PostgreSQL/Supabase schema in `docs/database.md` cannot be rebuilt from this repository: no migration files are checked in, and its tests skip without credentials

## Roadmap

Ordered by how much each unlocks:

1. **Qualifying + grid** → pole rate, grid-vs-finish delta, race-craft metrics
2. **Finishing status** → DNF rate, finish rate, reliability — the single largest current gap
3. **Points** → real championship standings, points-per-race
4. **Car metadata** → the Car Library page is already built against its absence
5. Lap times and telemetry — a different scale of data and out of scope until the above exist
