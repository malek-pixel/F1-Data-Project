# Database

> **Status: built, not wired in.** The application you get by following
> [README.md](../README.md) serves every request from the local SQLite build
> (`data/f1.db`). The Supabase schema below is real and reproducible from its
> migrations, and `backend/app/supabase_repo.py` reads it, but no router calls
> that module today — see the status note at the top of the file. Both stores
> are built from the same `results.csv` by the same validation rules, so the
> numbers agree; only the SQLite path is exercised by the running app and by
> the 109 tests that execute on a fresh clone.

Supabase / PostgreSQL 17 is the PostgreSQL materialisation of the dataset.

| | |
|---|---|
| Project | `f1-data-project` (`qdrxgymohkitpxedukdb`) |
| Region | eu-central-1 |
| Engine | PostgreSQL 17.6 |
| Migrations | 8, applied in order against the hosted project, checked in under `supabase/migrations/` |
| Security advisories | 1 INFO, deliberate — see [Security](#security) |

> **Verification status (re-audited 2026-08-13).** The hosted project was
> reachable and was audited directly rather than from these notes.
>
> **Now re-verifiable from this repository.** All 8 migrations were recovered
> from `supabase_migrations.schema_migrations` and checked in under
> `supabase/migrations/`. They are not transcriptions-by-eye: each file's md5
> is recorded in `supabase/migrations/CHECKSUMS.md5` against the md5 Postgres
> holds for the SQL it actually applied, and `python supabase/verify_migrations.py`
> recomputes them. All 8 match byte-for-byte.
>
> **Still not re-verifiable.** `backend/tests/test_supabase.py` (24 cases)
> still skips unless `SUPABASE_URL` and `SUPABASE_ANON_KEY` are set, which they
> are not in a fresh clone. The RLS results table below therefore remains a
> record of a past check, not something a clone can prove — though the policies
> producing it are now readable in migrations 02, 05, 07 and 08.

---

## The rule that shapes the schema

The source is **seven columns**: `season, round, race_name, date, position, driver, constructor`.

Everything else the schema could plausibly hold does not exist. The design rule
is therefore split:

**Dimension tables carry the descriptive columns a named future source would
fill** — `drivers.nationality`, `drivers.date_of_birth`, `circuits.latitude`.
They are NULL, and NULL honestly means *not yet known*. Ergast's `drivers.csv`
and `circuits.csv` are the concrete sources that would populate them.

**The `results` fact table carries only measured columns.** There is no
`points`, `grid`, `laps`, `status` or `fastest_lap` column — not because F1
lacks them, but because a column that is NULL across all 10,550 rows breaks
every aggregate and invites exactly the zero-substitution that would turn
"unknown" into "zero". Adding them is one migration when a source provides them.

A test enforces this: `test_no_points_or_status_columns_exist`.

### `position` is not a finishing status

`results.position` is **final classification order, 1..N**. The source has no
status column, so a driver who retired on lap 1 still carries a position
number. Every metric derived from it is named *classified*, never *finishing*.
This single fact constrains the entire analytical layer.

---

## Tables

### Provenance
| Table | Rows | Purpose |
|---|---|---|
| `data_sources` | 1 | Where data came from. Never invented attribution. |
| `datasets` | 1 | Version, coverage, row count, SHA-256 of the source file. |
| | | *Correction, 2026-08-13:* `checksum` was NULL — the stored row predated the code that writes it, so the column's stated guarantee was not being met. Backfilled to `63ec510c…6f7b` only after proving the file matches: all 10,550 rows were fingerprinted on both sides (md5 of the sorted seven-column projection) and agree exactly, `e4231564629c4abd8110daab82a60a0b`. It was not filled in on the strength of a matching row count. |
| `data_quality_checks` | 13 | Every check from the last import, with severity. |
| `metric_definitions` | 11 | Published methodology — definition, formula, limitations, sample rule. |

### Dimensions
| Table | Rows | Notes |
|---|---|---|
| `seasons` | 26 | 2000–2025. Race count is *not* stored — it is derivable, and a stored copy can silently disagree with the rows. |
| `circuits` | 39 | `circuit_key` is a derived slug; `svg_asset` NULL for the 15 with no track map. |
| `drivers` | 129 | `display_name` is authoritative. `first_name`/`last_name` are NULL — "Juan Pablo Montoya" cannot be split reliably, so it is not guessed. |
| `constructors` | 38 | Historically distinct constructors are separate rows. Sauber, BMW Sauber and Alfa Romeo are three entities and are never merged without evidence. |
| `cars` | **0** | Created because the product has a Car Library. Deliberately empty: the source has no car data and inventing chassis or engine values is prohibited. |

### Facts
| Table | Rows | Notes |
|---|---|---|
| `races` | 503 | `UNIQUE (season_id, round)`. |
| `results` | 10,550 | `UNIQUE (race_id, driver_id)` — verified against the source before enforcing: 0 duplicates. |
| `driver_constructor_seasons` | 638 | Derived from results, never hand-entered. A mid-season switch produces two rows for one driver in one season. |

### Ingestion
| Table | Purpose |
|---|---|
| `staging_results` | Raw text landing zone. Server-side only — no grant, no policy. |
| `circuit_map` | 53 curated rules resolving `race_name` → circuit. |

---

## Circuit identity is derived, not sourced

The source has no circuit column, and `race_name` is not a stable key: the
European, German, French, Japanese and United States Grands Prix all changed
venue inside 2000–2025. `circuit_map` encodes that as season-ranged rules.

The import **fails** on any `(race_name, season)` with no matching rule rather
than dropping the race silently.

**Limitation:** this table encodes external F1 knowledge, not source data. It
is auditable as plain rows and must be reviewed when a season is added.

---

## Analytical layer

Eleven views. Views, not materialized views: the dataset is 10,550 rows, so
materialisation would add refresh complexity for no measurable gain. Revisit
only when a measurement says otherwise.

```
v_race_results                       row-level join with readable names
v_driver_career_stats                entries, wins, podiums, top5/10, rates,
                                     mean, median, stdev, best, reliability flag
v_driver_season_stats                the same, per season
v_driver_circuit_stats               per circuit, with delta vs own career norm
v_constructor_career_stats           note: entries are per-car, races_contested is per-race
v_constructor_season_stats
v_constructor_driver_contribution    share of team results — never share of points
v_teammate_comparisons               head-to-head over shared races
v_season_stats                       NOT championship standings
v_circuit_stats
v_records                            calculated, never hardcoded
```

Definitions mirror `backend/app/analytics.py` exactly. Divergence is a bug.

### Reconciliation — Python vs PostgreSQL

Two independent implementations of the same definitions, compared across six
drivers spanning eras and career lengths:

```
metrics compared   66   (entries, wins, podiums, top5, top10, win_rate,
                         top10_rate, mean, median, stdev, best × 6 drivers)
discrepancies       0
```

Teammate view verified separately: Hamilton–Bottas 75–25 over 100 shared races,
Hamilton–Russell 34–34 over 68, matching the Python implementation exactly.

### Two aggregation traps, handled

**Constructor double-counting.** A constructor fields two cars, so a race
produces two result rows. `entries` counts classifications; `races_contested`
counts distinct races. Using the wrong one doubles a team's apparent starts.

**Teammates are race-scoped, not career-scoped.** Two drivers are teammates in
a race when both have a row for the *same race and same constructor*. Only
those races count — which is what prevents a 22-race driver being compared
unfairly against a mid-season replacement.

---

## Security

**Model:** public read, no public writes.

| Role | Permission |
|---|---|
| `anon`, `authenticated` | `SELECT` on all public tables and views |
| `anon`, `authenticated` | **no** INSERT/UPDATE/DELETE policy and no grant |
| `staging_results` | no policy, no grant — server-side only |
| ingestion | service role / direct connection, server-side only |

There is deliberately **no** write policy rather than a restrictive one: a
policy that exists can be widened by accident; an absent policy cannot.

**Open advisory, deliberate.** The linter reports one INFO:
`rls_enabled_no_policy` on `staging_results`. That is the intended state, not a
gap — staging has RLS on, no policy and no grant, so it is unreachable from any
public key. The advisory fires because the linter cannot distinguish "forgot a
policy" from "deliberately has none". Left as-is; adding a policy to silence it
would weaken the table.

Checked empirically with the publishable key — the only key a browser holds —
against the hosted project at the time. Not re-verifiable from this repository
(see the verification status note above):

```
public READ drivers            200  allowed
public READ analytical view    200  allowed
public INSERT drivers          401  blocked
public INSERT results          401  blocked
public UPDATE results          401  blocked
public DELETE results          401  blocked
staging_results                401  not exposed
```

These are assertions in `backend/tests/test_supabase.py`, not a one-off check.

**Keys.** The API loads `SUPABASE_URL` and `SUPABASE_ANON_KEY` only — a test
parses the module and fails if any other `os.getenv` name appears. The
service-role key and database password are never read by application code,
never logged, and never sent to a client. `.env` is gitignored;
`.env.example` is the committed template.

---

## Indexes

Chosen from real query patterns, not added blindly.

```sql
results(race_id) · results(driver_id) · results(constructor_id)
results(position) WHERE position <= 10     -- partial: podium/top-10 filters
results(race_id, constructor_id)           -- teammate self-join, 75x speedup
races(season_id) · races(circuit_id) · races(race_date)
driver_constructor_seasons(driver_id | constructor_id | season_id)
GIN trigram on drivers.display_name, constructors.constructor_name,
              circuits.circuit_name       -- substring search without a scan
```

`pg_trgm` lives in the `extensions` schema, not `public` — the security
advisor flags extensions in `public`, and the linter now returns clean.

---

## Ingestion

```
results.csv
   ↓  staging_results          raw text; nothing rejected at load time
   ↓  validate in staging      types, ranges, circuit resolution
   ↓  upsert dimensions        seasons, circuits, drivers, constructors
   ↓  upsert races → results
   ↓  derive driver_constructor_seasons
   ↓  record data-quality checks + dataset provenance
   ↓  reconcile against the source file
```

**Idempotent.** Every promotion is an upsert on a natural key, and entity keys
are deterministic slugs (accents folded, non-alphanumerics collapsed), so
re-running updates rather than duplicates.

**Fails closed.** Staging validation failures abort before promotion; the whole
import runs in one transaction, so a failure leaves the database untouched
rather than half-populated.

Run with `python -m backend.etl.supabase_import` (needs `SUPABASE_DB_URL`), or
`--dry-run` to validate without writing.

### Last import

```
source CSV rows       10,550
staged                10,550
valid                 10,550        rejected 0
circuits resolved         39
seasons 26 · races 503 · drivers 129 · constructors 38 · driver-seasons 638
reconciliation        15/15 checks pass
```

### Known issues, reported not patched

| Issue | Handling |
|---|---|
| 2002 French GP: 20 rows but classification runs to P22 | Upstream omission. Recorded as a `warn` check. Denominators count rows present, never `max(position)`. |
| 15 of 39 circuits have no track map | `svg_asset` NULL; UI renders a map-unavailable state, never a substitute shape. |
| `cars` empty | No car data exists. Populating it with invented specifications is prohibited. |

---

## Backup and recovery

| Category | Recoverable? |
|---|---|
| `results.csv` | **The only irreplaceable artefact.** Everything else derives from it. |
| Migrations | In the repository since 2026-08-13, checksum-verified against the applied SQL. |
| `circuit_map` seed | In the repository. |
| All tables | Rebuildable: run migrations, run the import. |
| All views | Rebuildable from migration 06. |

No derived analytics are stored, so nothing derived can become irreplaceable.

---

## Future expansion

The schema is shaped for these; none are implemented, because implementing an
empty table to look impressive is not the same as supporting a dataset.

| Dataset | Shape it would take |
|---|---|
| Qualifying | New `qualifying_results` table keyed on (race, driver) |
| Lap times | New `lap_times` table keyed on (race, driver, lap) |
| Pit stops | New `pit_stops` table |
| Weather | New `race_weather` table keyed on race |
| Cars | Populate the existing `cars` table; `results.car_id` FK already exists |
| Finishing status | A column on `results` — the single highest-value addition, unlocking DNF rate and separating pace from reliability in teammate analysis |
| Telemetry | Deliberately *not* relational. Would need separate storage; never inside result rows. |
