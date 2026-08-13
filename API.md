# API

Read-only REST over the 2000–2025 race-classification dataset.
Base path `/api`. Interactive docs at `/docs` when the server is running.

Every derived number comes from `backend/app/analytics.py`. Definitions are in
[METHODOLOGY.md](METHODOLOGY.md).

---

## Conventions

**The stat block.** Most responses embed the same object:

```json
{
  "entries": 428,
  "wins": 32,
  "podiums": 106,
  "win_rate": 0.0747,
  "podium_rate": 0.2477,
  "avg_classified_position": 8.682,
  "best_classified_position": 1,
  "rates_reliable": true
}
```

- `entries` — race classifications, **including retirements**. The denominator for every rate.
- `avg_classified_position` — mean final classification, **not** average finishing position.
- Rates are `null` when `entries` is 0, and `0.0` when there are entries but no wins. These are different facts.
- `rates_reliable` is `false` below 10 entries. The value is still returned; clients mark it rather than hiding it.

**Errors** return `{"detail": "..."}` with a real status code. Database faults
log server-side and return a generic 503 — internals are never exposed.

| Status | Meaning |
|---|---|
| 200 | OK |
| 400 | Semantically invalid (e.g. comparing an entity with itself) |
| 404 | No such entity |
| 422 | Failed parameter validation (unknown sort key, out-of-range limit) |
| 503 | Data store unavailable — retryable |

**Pagination.** List endpoints take `limit` (1–200, default 50) and `offset`,
returning `{total, limit, offset, items}`. `total` is the count *before*
pagination but *after* filtering.

**Sorting.** `sort` accepts `wins`, `podiums`, `entries`, `win_rate`,
`podium_rate`, `avg_position`, `name`. Anything else is a 422 — the ORDER BY
clause is resolved through a fixed map, never interpolated.

---

## Meta

### `GET /api/health`
Liveness, dataset coverage and entity counts, so a client can confirm which
build it is reading before rendering a number.

```json
{
  "status": "ok",
  "season_from": 2000, "season_to": 2025, "seasons": 26,
  "races": 503, "results": 10550,
  "drivers": 129, "constructors": 38,
  "circuits": 39, "circuits_with_map": 24,
  "live_data": false
}
```

The frontend renders every "129 drivers"-style figure from this payload rather
than hardcoding it in copy, so the interface cannot describe a dataset it is no
longer serving.

`live_data` is permanently `false`. This is a static historical dataset.

---

## Drivers

### `GET /api/drivers`
Paginated, filtered, sorted leaderboard.

| Param | Type | Notes |
|---|---|---|
| `search` | string ≤100 | Substring match; LIKE wildcards are escaped and matched literally |
| `sort` | enum | Default `wins` |
| `constructor_id` | int | Only entries recorded for this constructor |
| `min_entries` | int ≥1 | Excludes small samples from the ranking |
| `season_from` / `season_to` | int | Restrict the window |
| `limit` / `offset` | int | |

### `GET /api/drivers/{id}`
`{id, name, stats, constructors[]}` — career block plus per-season constructor
history. A mid-season switch appears as two rows, not merged.

### `GET /api/drivers/{id}/stats`
Stat block alone. Accepts `season_from` / `season_to`.

### `GET /api/drivers/{id}/seasons`
Season-by-season stat blocks, ascending. Drives the wins-by-season and
average-position charts.

---

## Constructors

### `GET /api/constructors`
As `/api/drivers`, without `constructor_id`.

### `GET /api/constructors/{id}`
`{id, name, stats, seasons[]}`.

### `GET /api/constructors/{id}/stats`
Stat block alone; accepts a season range.

### `GET /api/constructors/{id}/drivers`
Driver contribution. Optional `season`.

Adds `entry_share`, `win_share`, `podium_share` — each driver's share of **this
constructor's** totals, so they sum to 1.0. A share is `null` when the team
recorded none of that result type (never `0.0`, which would imply a share of a
real total).

There is no points share. The source has no points column.

---

## Circuits

### `GET /api/circuits`
All circuits, optional `search` over name and country.

`has_map` is `false` for the 15 circuits with no track-map SVG. They are
returned as normal entities — the client renders a map-unavailable state.

### `GET /api/circuits/{id}`
Circuit, stat block, every winner (most recent first), and the top 10 drivers
and constructors at that circuit.

---

## Races and seasons

### `GET /api/seasons`
Per-season counts: races, entries, distinct drivers, distinct constructors.

### `GET /api/seasons/{season}`
Season summary with `drivers[]`, `constructors[]` and `races_list[]`.

**`ranking_basis` is always `"wins"`.** These are *not* championship standings —
no points column exists, so entities are ranked by wins, then podiums, then
average classified position. Clients must label this.

404 for a season with no races.

### `GET /api/races`
Optional `season`, `circuit_id`, `limit` (≤500), `offset`.

### `GET /api/races/{id}`
Race metadata plus the full classification in order.

---

## Analysis

### `GET /api/compare/{entity}`
`entity` is `drivers` or `constructors`. Requires `left` and `right` ids.

```json
{
  "left": { "...stats" }, "right": { "...stats" },
  "left_name": "Fernando Alonso", "right_name": "Sebastian Vettel",
  "shared_seasons": [2007, "…", 2022],
  "comparable": true,
  "left_shared": { "...stats" }, "right_shared": { "...stats" },
  "methodology": "Career totals cover 2000-2025 only. …"
}
```

`left_shared` / `right_shared` restrict both sides to their overlapping seasons
— the like-for-like view. They are absent when the careers never overlap.

`comparable` is `false` when there is no overlap or either side is below the
entry threshold.

**No winner is declared.** Career totals across different eras, entry counts and
machinery are not a like-for-like comparison; the response returns what a client
needs to say so.

400 when `left == right`. 422 for an unknown entity type.

### `GET /api/records`
Dataset records, each with a `methodology` string. Rate-based records apply the
entry threshold as a hard filter, so a one-race driver cannot top a rate table.
Scope is 2000–2025 — never all-time.

### `GET /api/insights`
Calculated observations, optional `limit` (1–20). Each carries a `basis` naming
the query behind it.

Descriptive only. The dataset holds no explanatory variables, so no insight
asserts a cause.

### `GET /api/dataset/summary`
Schema shape, row counts, coverage, `available_fields`, `unavailable_fields`
and `known_issues`. No filesystem paths or connection details.

### `GET /api/cars`
Constructor-seasons grouped by constructor — the Car Library's unit, since the
source carries no chassis designations. Each car reports races, entries, wins,
podiums, best classified position, average classified position, the drivers who
raced it, and an `era` (`current` / `recent` / `retired`) derived from the
season relative to the dataset's last. `chassis_available` is always `false`
until a chassis dataset is added.

### `GET /api/search`
Global search across drivers, constructors, circuits, races and seasons. `q`
(1–100 chars, required), `limit` (1–25). Prefix matches rank first, then by
wins. A query containing a four-digit year is split into a season filter and a
name, so `2004 monza` finds the 2004 Italian Grand Prix.

---

## Security

- Every value is a bound parameter; nothing is interpolated into SQL.
- LIKE wildcards in user input are escaped and matched literally.
- Sort keys and entity types resolve through fixed maps.
- Connections open `mode=ro`; the API cannot write.
- CORS is restricted to configured origins via `F1_ALLOWED_ORIGINS`, never wildcarded.
- Only `GET` is allowed.
