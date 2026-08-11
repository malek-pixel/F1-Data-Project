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

## Known issues

| Issue | Handling |
|---|---|
| 2002 French GP: 20 rows but classification runs to P22 | Upstream omission. Denominators count rows present, never `max(position)` |
| No finishing status | Documented everywhere a position-derived metric appears |
| Circuit identity is derived | `circuit_map.csv` encodes external knowledge; build fails on unmapped races |
| Season lengths vary 16–24 races | Cross-era season totals are not normalised; records state this |
| Coverage starts 2000 | No figure here is an all-time F1 record |
