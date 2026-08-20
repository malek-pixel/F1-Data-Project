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

These are absent from every source this project ingests, and are **never**
estimated, inferred, or filled with a plausible number:

> telemetry · car specifications · sector times outside practice · the official
> **pole position** award · the official **fastest lap** award

The last two are subtler than "no data": qualifying P1 is ingested and counted,
but it does not reproduce official pole tallies in the sprint era, so it is
labelled `qualifying_p1` and never "poles". The quickest lap anyone drove is
likewise available wherever lap timings are, but the *award* carries
eligibility rules no source publishes, so the two are never presented as the
same thing.

This list is short because it used to be long. Points, championship standings,
grid, qualifying, finishing status, lap times, pit stops and sprints were all
absent when this project started and have since been ingested — see
[§ Dataset](#dataset). The list above is maintained by hand and will go stale
the same way, which is why the application does not rely on it:
`/api/dataset/summary` reports availability by **counting rows**, and
`backend/etl/audit.py` fails the build if a dataset that should be there is
not.

Two consequences worth stating up front:

1. **`position` is classification order, not finishing status.** A driver who retired on lap 1 still carries a classification number, so the metric is *average classified position*, never "average finish". Retirements are identifiable via `status` / `classification`, and DNF rate is computed and reported alongside it.
2. **Season *tables* rank by wins; season *standings* are the real championship.** They are two different things on purpose. The stat tables sort by wins and say so. `/seasons/{season}/standings` is race points plus sprint points, verified against the official result — champion and exact total — for all 26 seasons.

The Car Library page ships as an honest empty shell: no car data exists in the
source, so it documents the schema real data would populate instead of inventing
chassis or power figures.

---

## Architecture

```
f1_fetch.py            one-off acquisition, the only script that uses the network
backend/etl/jolpica.py     ↓
backend/etl/practice.py    ↓  (also network; also one-off)
     ↓
results.csv            committed; the spine — one row per classification
data/jolpica_*.csv     committed; points, grid, status, qualifying, sprints,
                       pit stops, lap timings, sessions, entity detail
data/fastf1_*.csv      committed; practice laps, compounds, sectors
     ↓
backend/etl/build.py   validate → normalise → load; aborts on any fatal finding.
                       The jolpica/fastf1 extracts are OPTIONAL inputs: a clone
                       missing one still builds, which is why the audit asserts
                       coverage floors rather than trusting their presence
     ↓
data/f1.db             SQLite build artefact, gitignored, rebuilt in ~1s
     ↓
FastAPI                opens the DB read-only; all calculation lives in
                       backend/app/analytics.py and advanced.py
     ↓
React + TypeScript     presentation and formatting only; derives no metric
```

**Two stores, one dataset.** The same CSV is materialised as `data/f1.db`
(SQLite) and as a hosted Postgres project (Supabase). `F1_BACKEND` selects
which one answers, per request, and **28 of 30 routes dispatch through it** —
`test_api_payload_parity.py` compares 77 request paths across both stores,
response for response.

This paragraph used to say "**no router calls it** — it is not on any request
path". That was true when written and stopped being true without the sentence
changing, which is the failure this project keeps having.

SQLite remains the default, and is the only leg with no external dependency: a
fresh clone builds and serves without credentials. Nothing in the setup below
requires Supabase. The 24 tests that exercise it skip when
`SUPABASE_URL` / `SUPABASE_ANON_KEY` are unset, and a skip is missing coverage
rather than a pass. Schema and migrations: [docs/database.md](docs/database.md).

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
python -m pytest backend/tests -q      # 393 passed, 1 skipped (with Supabase credentials)
cd frontend && npm test                # 59 passed
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
| `test_supabase.py` | Schema, RLS and the public-key boundary on the hosted project. Skips without credentials — a skip is missing coverage, not a pass |
| `test_api_payload_parity.py` | **77 request paths, both backends, response for response.** The suite that has to be green before "the Supabase leg works" means anything |
| `test_store_parity.py` / `test_backend_parity.py` | The two databases hold the same rows; the two implementations compute the same numbers |

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

### Data sources and attribution

Two independent providers. They are never blended: each has its own tables, its
own coverage window, and its own verification level in the audit, because a
reader comparing two numbers needs to know when they came from different places.

| Source | Provides | Coverage | Licence / terms |
|---|---|---|---|
| [**Jolpica-F1**](https://github.com/jolpica/jolpica-f1) — the maintained successor to the retired Ergast API | Race results, championship points, finishing status, grid, qualifying, sprints, pit stops, lap timings, fastest-lap awards | 2000–2025 | Open API, Ergast lineage. Rate limited to 500 requests/hour |
| [**FastF1**](https://github.com/theOehrly/Fast-F1) — reads Formula 1's live-timing service | Practice-session laps, tyre compounds, sector times, speed traps | 2018–2025 | MIT-licensed library; timing data © Formula 1 |

**Attribution.** Race data originates from the Ergast Developer API lineage,
now maintained as Jolpica-F1. Practice timing is retrieved through FastF1, which
reads Formula One's official live-timing feed; that data remains the property of
Formula 1. This project is unofficial and is not associated with, endorsed by,
or affiliated with Formula 1, the FIA, or any team.

`data/fastf1_practice_laps.csv` is committed so the build is reproducible
offline. It is a derived extract — lap times, sectors and compounds — not a
redistribution of the upstream feed, and it can be regenerated from scratch with
`python -m backend.etl.practice`.

### Verification

Spot-checked against known F1 history:

| | Computed | |
|---|---|---|
| Most wins | Lewis Hamilton, 105 | ✓ |
| Most podiums | Lewis Hamilton, 202 | ✓ |
| Most wins in a season | Max Verstappen, 19 (2023) | ✓ |
| Most wins at one circuit | Lewis Hamilton, 9 (Silverstone) | ✓ |
| 2021 top two | Verstappen 10, Hamilton 8 | ✓ |

Spot checks are not verification, though, and are not relied on as such.
`python -m backend.etl.crossvalidate` checks the dataset against Jolpica-F1
race by race — three requests per season, cached on disk:

| Checked | Scope | Result |
|---|---|---|
| Winner, winning constructor, date, race name | 503 races | 0 discrepancies |
| Qualifying P1 | 459 poles (the source itself is partial before 2003) | 0 discrepancies |
| Circuit identity | 39 circuits, as a 1:1 mapping | 0 discrepancies |

Circuits are checked as a **bijection**, not by name, because names
legitimately differ between sources ("Albert Park Circuit" vs "Albert Park
Grand Prix Circuit") without being a disagreement about where the race was
held. What must hold is that each source circuit maps to exactly one local
circuit and back — which is the failure `circuit_map.csv` can actually
produce, and is invisible to a name comparison. The check found the one real
split on its first run: Jolpica files the 2020 Sakhir GP under the same
circuit as the Bahrain GP, while this project separates the Outer Circuit
(3.543 km) from the full track (5.412 km). The local split is the more precise
model and is kept, recorded as a named exception rather than flattened.

What this proves and does not: Jolpica is independent of this project's
**pipeline**, not of its **provider**. A clean run means fetching, folding,
joining, mapping and storing did not corrupt anything between source and
database. It is not independent confirmation of Formula 1's own record.

The build is also **deterministic**, not merely repeatable — two builds in two
processes produce byte-identical table content, so surrogate ids and therefore
every `/drivers/{id}` URL survive a rebuild. Enforced by
`backend/tests/test_reproducibility.py`.

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
| [docs/database.md](docs/database.md) | PostgreSQL/Supabase schema and migrations |
| [docs/frontend-data-contract.md](docs/frontend-data-contract.md) | Page → data → source → transformation → UI, and which store answers what |
| [docs/qa-matrix.md](docs/qa-matrix.md) | What was tested in the integration phase, and what was not |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Recovery, migration safety, the access model, deployment and monitoring |

---

## Known limitations

- Coverage begins in 2000 — no figure here is an all-time Formula 1 record
- Telemetry and car specifications are absent from every source this project ingests; the `cars` table exists and is deliberately empty
- Pole position is not recorded as such. Qualifying P1 is counted and labelled `qualifying_p1`: the two diverge in the sprint era
- Season lengths vary 16–24 races; cross-era season totals are not normalised
- The 2002 French GP carries 20 rows but runs to P22 — an upstream omission, reported by the validator rather than patched
- `circuit_map.csv` encodes external knowledge, not source data; it should be reviewed when a season is added
- Data is static. Nothing is live, and no screen implies an in-progress race
- Driver portraits, car photos and team logos are third-party images and the repository records no source or licence for any of them. Every one has a graceful labelled fallback, so they can be removed without breaking a layout — see [docs/CAR_PHOTOS.md](docs/CAR_PHOTOS.md)
- There is no monitoring, error reporting or alerting. If the deployed app breaks, nothing tells anyone — see [docs/OPERATIONS.md](docs/OPERATIONS.md) §6
- Constructor standings apply two documented FIA championship penalties (McLaren 2007, Racing Point 2020) that cannot be reached by summing race results — see [METHODOLOGY.md](METHODOLOGY.md) §6.1
- The Supabase leg needs credentials: without them its tests skip and parity is unverified rather than verified-good. The 24 migrations are checked in and `python supabase/verify_migrations.py` checks each file against the SQL the database recorded as applied

## Roadmap

Items 1–3 of the original roadmap — qualifying and grid, finishing status, and
points — have been **delivered**, and lap timings with them. What is left:

1. **Car metadata** → the Car Library page is already built against its absence, and stays an empty shell until a source exists
2. **Telemetry** → a different scale of data, and out of scope
3. **Observability** → the deployed app currently reports nothing when it breaks; see [docs/OPERATIONS.md](docs/OPERATIONS.md) § 6

Anything added here needs a source first. Nothing on this list will be
estimated to make a page look finished.
