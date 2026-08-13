# Backend & Data — what's done, what's missing

Updated 2026-08-13. Everything marked done has evidence beside it.

**Verification commands** (all pass on a configured clone):

```
python -m pytest backend/tests -q         162 passed, 0 skipped
python -m backend.etl.audit               31 checks, 0 failed, 1 known warn
python supabase/verify_migrations.py      11/11 byte-exact
python -m backend.etl.crossvalidate       503 races, 0 discrepancies
python -m backend.etl.verify_env          read YES, write YES
python -m backend.etl.supabase_import     idempotent, all checks pass
```

---

## 1. What's done

### Data accuracy — now independently corroborated

| Claim | Evidence |
|---|---|
| Every race is correct | 503/503 cross-validated vs Jolpica-F1 on winner, constructor, date, race name |
| Every **row** is correct | All 10,550 matched on driver + constructor. 0 mismatches |
| Points are correct | Championship totals reproduce the **official standings exactly for all 26 seasons** — including half-point races and sprint points |
| Provenance | Both sources SHA-256 checksummed; checksum written by the pipeline itself |

This is corroboration by an independent record, not internal consistency. It is
the strongest accuracy claim this project can currently make — and it is still
not a claim of perfection: it validates results, not qualifying or lap data,
and Jolpica is authoritative but not infallible.

### Data added this session

| Dataset | Rows | Note |
|---|---|---|
| Finishing status | 10,550 | 8,367 classified · 2,073 retired · 71 withdrawn · 39 disqualified |
| Championship points | 10,550 | Reproduces official standings exactly |
| Grid positions | 10,550 | `grid = 0` means pit-lane start — a real value, never NULL |
| Laps completed | 10,550 | |
| Sprint results | 480 | 24 events, 2021–2025, **separate table** |
| Driver/constructor detail | — | nationality, DOB available from source |

### Schema, security, tooling

- 11 migrations checked in, each **byte-verified** against what the database ran
- 31 integrity checks as build gates; a *new* warning fails the build
- RLS verified live — public key reads, cannot write; staging unreachable
- `data_corrections` log: append-only, reason + evidence required
- Coverage matrix distinguishes cross-validated / structural / no source
- Backend switch (`F1_BACKEND`), unsupported endpoints raise rather than fall back
- `.env` loader + `verify_env` with a real connection test

### Bugs found and fixed

1. **The ingestion pipeline had never run.** It connected with `dict_row` but read rows positionally, so unpacking yielded column *names* — `int(season)` received the string `'season'`. This explains the NULL checksum found on day one.
2. **Two stale driver keys** (`nelson-piquet-jr-`, `toma-enge`) from a superseded slug rule that left a trailing hyphen and dropped `š` instead of folding it. Would have created duplicate drivers on every import. Caught by reconciliation, which **failed closed and rolled back**.
3. **Direct DB host is IPv6-only** and does not resolve on most networks — switched to the pooler.
4. **Sprint points missing** — found because championship totals were short by exactly 7/21/45/38/29 from 2021.

---

## 2. What's still missing

### Data — needs ingestion (source exists, work not done)

| Missing | Blocks |
|---|---|
| **Qualifying** | Pole positions, grid-vs-qualifying analysis |
| **Lap times** | Race pace, stint analysis |
| **Pit stops** | Strategy analysis |
| **Practice sessions** | Not modelled |
| **Pre-2000 seasons** | Data starts 2000; Jolpica has 1950 onward |
| **Driver/circuit detail columns** | Fetched but not yet loaded into their (existing, empty) columns |

All are reachable from Jolpica with the pipeline that now works.

### Data — no clean source

| Missing | Why |
|---|---|
| **Cars, engines, tyres** | Jolpica has no chassis or specification data. `cars` stays empty rather than invented |
| **Telemetry** | No source, and deliberately not relational |

### Backend code

| Item | State |
|---|---|
| **Supabase serving the app** | Switch works, reads verified, but `supabase_repo` implements ~5 of 20 endpoints. App still runs on SQLite. The analytical views also predate the new columns and don't expose status/points yet |
| **Frontend** | Not touched. Nothing renders DNF rate, points, grid or sprints yet — the API returns them, the UI ignores them |
| **Historical points systems** | Points are stored as awarded, which is correct. Not modelled as rules per era |

---

## 3. Needs your decision

- **Entity IDs differ between the two stores.** `/drivers/7` is André Lotterer on Supabase, Andrea Kimi Antonelli on SQLite — the two databases sort accented names differently and assign IDs by sort order. Fixing it changes URLs, so it is your call. Parity tests pin the divergence so it cannot be forgotten.
- **Constructor identity.** Sauber / BMW Sauber / Alfa Romeo are three rows. Correct historically; worth confirming it matches how you want them displayed.

---

## 4. Honest bottom line

**Race results for 2000–2025 are now verified against an independent record,
and carry finishing status, points, grid and laps.** Championship standings
reproduce official figures exactly. The pipeline is reproducible, idempotent,
gated by 31 checks, and fails closed.

**Not done:** qualifying, laps, pit stops and pre-2000 are still absent; the
app still reads SQLite rather than Supabase; and no frontend work has been
done, so none of the new data is visible to a user yet.
