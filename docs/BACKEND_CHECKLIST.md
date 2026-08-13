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
| **Lap times** | Race pace, stint analysis |
| **Pit stops** | Strategy analysis |
| **Practice sessions** | Not modelled |
| **Pre-2000 seasons** | Data starts 2000; Jolpica has 1950 onward |

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

---

## Session 2 additions (2026-08-13, later)

Added and verified:

| Dataset | Rows | Coverage |
|---|---|---|
| Qualifying | 9,577 | Complete 2003–2025; **partial 2000–2002 (6–24%)** — a real source gap, represented as absent rows, never invented |
| Driver detail | 129 | Nationality + DOB 100%. Abbreviation 105/129, permanent number 62/129 — the rest are NULL because those drivers predate the concepts |
| Constructor nationality | 38 | 100% |
| Circuit location | 39 | Official name, locality, lat/long. Matched to slugs **via shared races**, not by name; the build fails if that mapping is not 1:1 |

**Circuit length, corner count and lap records remain absent** — no source
supplies them, so they are not columns at all.

### A wrong assumption, caught by its own check

The first qualifying load asserted "Q1/Q2/Q3 began in 2006" and failed on 107
rows, rolling back. The assumption was wrong: **2005 opened with aggregate
qualifying** — two flying laps, Saturday and Sunday, recorded as Q1 and Q2 and
summed. The source was right. Q3 is the true 2006 marker. The check now encodes
the actual history, and this is exactly why modern rules must never be assumed
to hold for earlier eras.

### OPEN DISCREPANCY — qualifying P1 is not "poles"

Counting qualifying P1 gives Lewis Hamilton **107**; his official pole count is
**104**. Two are sprint weekends, where 2021 awarded pole to the sprint winner
rather than the fastest qualifier. **That leaves one unexplained.**

Until it is investigated, qualifying P1 must **not** be relabelled "poles"
anywhere a user can see it. `test_qualifying_p1_is_not_published_as_official_poles`
pins the number so the discrepancy cannot drift silently.

### Still not done

- **Lap times** (~470k rows) and **pit stops** — not started
- **Practice sessions** — not started
- **Pre-2000 seasons** — not started; needs your call, it roughly triples the dataset
- **Supabase views** still predate every column added today, so the SQL and
  Python analytics have drifted apart
- **Frontend** — still shows none of this
