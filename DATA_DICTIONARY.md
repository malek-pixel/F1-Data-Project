# Data Dictionary

Source: `results.csv` → `data/f1.db` via `backend/etl/build.py`.

---

## Source file — `results.csv`

10,550 rows, seven columns. This is everything the project has.

| Column | Type | Description |
|---|---|---|
| `season` | int | Calendar year, 2000–2025 |
| `round` | int | Round number within the season, 1..N, contiguous |
| `race_name` | str | Grand Prix name. **Not a stable circuit key** — see `circuit_map.csv` |
| `date` | ISO date | Race date. Year always equals `season` |
| `position` | int | **Final classification order, 1..N. Not finishing status** — see below |
| `driver` | str | Driver display name |
| `constructor` | str | Constructor display name |

### On `position`

There is no `status`, `DNF`, `DNS` or `DSQ` column. A driver who retired on lap
1 still carries a classification number. Nothing in this dataset can distinguish
a finish from a retirement, which is why every derived metric is named for
*classification* rather than *finishing*.

---

## Database tables

### `drivers`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Surrogate key, assigned at build time |
| `name` | TEXT UNIQUE | Display name from source |

129 rows.

### `constructors`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Surrogate key |
| `name` | TEXT UNIQUE | Display name from source |

38 rows. Historically distinct constructors are **not** merged: Sauber, BMW
Sauber and Alfa Romeo are three rows, as are Renault, Lotus F1 and Alpine. The
source already groups Ergast-style; nothing is flattened further without
evidence.

### `circuits`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Surrogate key |
| `slug` | TEXT UNIQUE | Asset key; matches `frontend/public/circuits/<slug>.svg` when present |
| `name` | TEXT | Circuit name |
| `country` | TEXT | Host country |
| `has_map` | INTEGER | 1 when a track-map SVG ships, else 0 |

39 rows, 24 with `has_map = 1`. Circuits without a map are kept as entities and
render an explicit map-unavailable state — never dropped, never given a
substitute outline.

Derived, not sourced: circuit identity comes from `circuit_map.csv`.

### `races`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Surrogate key |
| `season` | INTEGER | |
| `round` | INTEGER | |
| `name` | TEXT | `race_name` from source |
| `date` | TEXT | ISO date |
| `circuit_id` | INTEGER FK → `circuits.id` | |

503 rows. `UNIQUE (season, round)`.

### `results`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `race_id` | INTEGER FK → `races.id` | |
| `driver_id` | INTEGER FK → `drivers.id` | |
| `constructor_id` | INTEGER FK → `constructors.id` | |
| `position` | INTEGER | Classification order — see the note above |

10,550 rows. `UNIQUE (race_id, driver_id)`.

### `build_meta`
Key/value provenance written at build time: source file, row count, season range.

---

## Derived metrics

Defined once in `backend/app/analytics.py`. Full rationale in `METHODOLOGY.md`.

| Metric | Formula | Notes |
|---|---|---|
| `entries` | `COUNT(results)` | Denominator for all rates. Includes retirements |
| `wins` | `COUNT(position = 1)` | |
| `podiums` | `COUNT(position <= 3)` | |
| `win_rate` | `wins / entries` | `null` when entries = 0 |
| `podium_rate` | `podiums / entries` | `null` when entries = 0 |
| `avg_classified_position` | `AVG(position)` | Lower is better. Biased upward by unreliability |
| `best_classified_position` | `MIN(position)` | |
| `rates_reliable` | `entries >= 10` | Flag, not a filter — the UI marks small samples |
| `entry_share` / `win_share` / `podium_share` | driver total / constructor total | Share of **results**, not points |

---

## Fields that do not exist

Not estimated, not inferred, not approximated. Adding any of these requires new
source columns.

Grid position · qualifying results · pole positions · fastest laps · finishing
status (DNF/DNS/DSQ) · championship points · points-per-race · championship
standings · lap times · sector times · lap-by-lap timing · pit stops · tyre
compounds · telemetry · sprint results · car specifications (chassis, engine,
power, weight, aero)

---

## Units

Every unit-bearing column, and the unit it is actually in. Determined from the
stored values, not assumed from the column name. Nothing in this project
converts between units: values are stored exactly as the source published them
and are only ever formatted for display, so no figure here is the result of a
silent conversion.

| Table.column | Type | Unit | Verified by |
|---|---|---|---|
| `lap_times.time_ms` | INTEGER | **milliseconds** | `time_text` `1:40.366` stores as `100366` |
| `lap_times.time_text` | TEXT | `M:SS.mmm` as published | — |
| `practice_laps.lap_time` | REAL | **seconds** | range 54.064–163.162 |
| `practice_laps.sector1/2/3` | REAL | **seconds** | same scale as `lap_time` |
| `practice_laps.speed_trap` | REAL | **km/h** | range 32–362 |
| `results.fastest_lap_speed` | REAL | **km/h** | range 89.54–257.32 |
| `results.fastest_lap_time` | TEXT | `M:SS.mmm` as published | — |
| `pit_stops.duration` | TEXT | **see the warning below** | — |
| `circuits.latitude`/`longitude` | REAL | **decimal degrees**, WGS 84 | — |

Note the deliberate asymmetry: lap timings are milliseconds in `lap_times` and
seconds in `practice_laps`, because that is how each source publishes them.
The two are never compared or combined anywhere in the codebase — `time_ms` is
only ever ordered and minimised within `lap_times`, and `lap_time` only within
`practice_laps`. **Do not introduce arithmetic across the two without an
explicit conversion.**

### `pit_stops.duration` is text in two different formats

It holds both `12.804` (seconds) and `6:50.005` (`M:SS.mmm`), exactly as the
source publishes it. Today nothing aggregates it — the API passes it through
verbatim to be displayed — which is why the mixed format is harmless.

It will not stay harmless if someone aggregates it. `AVG(duration)` in SQLite
coerces `'6:50.005'` to `6`, so an average over this column silently mixes
minutes with seconds and returns a number that looks plausible and is wrong.
Parse it to a single unit first, or add a numeric column beside it.

---

## Known issues

| Issue | Handling |
|---|---|
| 2002 French GP: 20 rows but classification runs to P22 | Upstream omission. Denominators count rows present, never `max(position)` |
| No finishing status | Documented everywhere a position-derived metric appears |
| Circuit identity is derived | `circuit_map.csv` encodes external knowledge; build fails on unmapped races |
| Season lengths vary 16–24 races | Cross-era season totals are not normalised; records state this |
| Coverage starts 2000 | No figure here is an all-time F1 record |
