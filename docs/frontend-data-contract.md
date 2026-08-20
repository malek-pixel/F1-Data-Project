# Frontend ↔ database contract

What each page reads, where the number comes from, and what happens to it on
the way. Written during the integration/QA phase; the numbers in it were
measured, not recalled.

## Shape

```
results.csv + Jolpica enrichment + FastF1 practice
    │
    ├── backend/etl/            build  →  data/f1.db          (SQLite)
    └── backend/etl/            import →  hosted Postgres     (Supabase)
                                              │
    backend/app/analytics.py  ────────────────┤  every metric, defined once
    backend/app/advanced.py                   │
    supabase/migrations/*.sql (views)  ───────┘
                    │
    backend/app/backends.py     serve(endpoint, sqlite_impl, supabase_impl)
                    │
    backend/app/routers/        thin: validate, dispatch, return a schema
                    │
    frontend/src/services/api.ts    one fetch wrapper
    frontend/src/hooks/useApi.ts    one hook
                    │
    frontend/src/pages/             render and format. Never derive.
```

**The rule:** if a number appears in the UI, exactly one function or view
produced it. Components format; they do not calculate.

## Which store answers

`F1_BACKEND` selects the store per request. **28 of 30 routes** dispatch
through `backends.serve`; each is compared against the other store, response
for response, by `test_api_payload_parity.py` (77 paths).

The two that do not:

| Route | Why |
|---|---|
| `/api/insights` | No Postgres implementation. Calls `backends.require("insights")` so it returns **501** under Supabase rather than quietly serving the SQLite answer. |
| `/api/analytics/metrics` | Touches no store at all — it returns Python constants from `advanced.METRICS`. Dispatching it would compare a value with itself. |

Three routes fall back to SQLite for *filtered* variants only, and say so at
the call site: `search` and season-range filters on the driver and constructor
listings, `season` on the constructor-contribution and distribution endpoints,
and `search` on the circuit listing. `serve` is not reached in those cases, so
nothing claims Supabase served them.

## Page → data → source → transformation → UI

### Home (`/`)
| Needs | Endpoint | Source | Transformation |
|---|---|---|---|
| Season KPI strip | `/api/seasons/{season}` | `v_season_index`, `v_driver_standings`, `v_constructor_standings` | `standings_detail` ranks by points → wins → podiums → slug |
| Round-by-round strip | `/api/seasons/{season}/rounds` | `v_race_summary` | LEFT JOIN on the winner, so a round with no position-1 row still appears |
| Key insight | `/api/insights` | SQLite only | Composed narrative; 501 on Supabase |
| Data status | `/api/dataset/summary` | Row counts, probed | Availability is **measured per field**, never listed |

### Drivers (`/drivers`, `/drivers/{slug}`)
| Needs | Endpoint | Source | Transformation |
|---|---|---|---|
| Library cards | `/api/drivers` | `v_driver_career_stats` | Sort resolved through a fixed map, always ending in `slug` so pagination is stable; `nationality` carried on the row |
| Header stat block | `/api/drivers/{slug}` | `v_driver_career_stats` + `drivers` | `_stat_block` — rates `null` at zero entries, `rates_reliable` below 10 |
| Team timeline | same payload | `v_driver_constructor_seasons` | One row per (season, constructor); a mid-season switch is two rows, never merged |
| Career log | `/api/drivers/{slug}/seasons` | `v_driver_season_stats` | Per-season stat block |
| Qualifying P1 | `/api/drivers/{slug}/qualifying` | `v_driver_qualifying_stats`, `v_qualifying_coverage` | Labelled `qualifying_p1`, never "poles" — the two differ in the sprint era |
| Teammate H2H | `/api/drivers/{slug}/teammates` | `v_teammate_comparisons` | Spells below 5 shared races excluded from totals and counted separately |
| Circuit strength | `/api/drivers/{slug}/circuits` | `v_driver_circuit_stats` | Delta against the driver's own career average |

### Constructors, circuits, seasons, races
| Page | Endpoint | Source |
|---|---|---|
| Constructor detail | `/api/constructors/{slug}` | `v_constructor_career_stats`, `v_constructor_season_stats` |
| Driver contribution | `/api/constructors/{slug}/drivers` | `v_constructor_driver_stats` — shares of *this* team's totals |
| Circuit index | `/api/circuits` | `v_circuit_stats` (ordered by `sort_name`, a `collate "C"` key) |
| Circuit detail | `/api/circuits/{slug}` | `v_circuit_stats`, `v_circuit_winners`, `v_circuit_*_leaderboard` |
| Circuit specialists | `/api/circuits/{slug}/specialists` | `v_driver_circuit_stats`, ranked by delta |
| Season detail | `/api/seasons/{season}` | `v_season_index`, standings views, `v_race_summary` |
| Race weekend | `/api/races/{id}` | `v_race_summary`, `results`, `qualifying_results`, `sprint_results`, `pit_stops`, `lap_times`, `v_practice_results` |

Each session block on the race page reports its **own** availability with a
reason. "No qualifying recorded for this race" and "nobody qualified" look
identical in JSON otherwise, and only one is true.

## Identifiers

`id` is a surrogate key assigned independently by each store — Hamilton is 48
in SQLite and 65 in Postgres. **Link on `slug`.** The parity suite drops
store-local ids from comparison and asserts that `slug` can never join that
exclusion list.

Legacy numeric URLs still resolve: `fetch_one_or_404` accepts a slug or an
integer id, and the Supabase leg re-addresses by the slug it resolves.

## Caching

In-process, 300s TTL, **identity and whole-dataset aggregates only**:
name/nationality maps, coverage boundaries, and the records / circuits /
seasons / eras / dominance-timeline payloads. Each of those changes only when
the ETL runs.

Nothing season-scoped or entity-scoped is cached. Standings and race
classifications are exactly what must not go stale, and the current season is
what a reader is most likely looking at.

## Null vs zero

Survives the database, the view, the API, the TypeScript types and the
formatters. `num()`/`pct()` render `null` as an em dash and never as 0.

- `0` — verified zero. A driver with entries and no wins has `win_rate: 0.0`.
- `null` — not established. No entries means no rate.
- `<Unavailable>` — the dataset cannot support this metric, and the UI names
  the missing column.

Every "unavailable" string in the UI is now checked against the database by
`test_no_stale_absence_claims.py`.
