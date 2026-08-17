# Backend & Data — simple checklist

Updated 2026-08-17. Every ✅ has evidence; nothing is ticked because it looks done.

**Check it yourself** (all pass right now):

```
python -m pytest backend/tests -q       229 passed
cd frontend && npx vitest run            48 passed
python -m backend.etl.audit              38 checks, 0 failed
python supabase/verify_migrations.py     17/17 byte-exact
python -m backend.etl.crossvalidate      503 races, 0 discrepancies
python -m backend.etl.laps --status      lap ingestion progress
```

---

## 🔄 RUNNING RIGHT NOW — lap times

A background fetch is downloading per-lap timings for all 503 races. It is
**resumable**: if it stops, rerunning picks up exactly where it left off and
re-requests nothing.

| | |
|---|---|
| Progress | see `python -m backend.etl.laps --status` |
| Speed | ~35 races/hour (the API throttles hard) |
| Total time | ~15 hours |
| Restart it | `python -u -m backend.etl.laps` |

**When it finishes, run these three:**

```
python -m backend.etl.build_laps
python -m backend.etl.build
python -m backend.etl.supabase_import
```

Until then the lap table is genuinely partial, and every report says so —
coverage is printed as a fraction ("38/503 races"), never as a season range,
because the endpoints of a half-filled set are not coverage.

---

## ✅ DONE — one identity for a driver, at last

`/drivers/7` used to be **a different person** in SQLite and in Supabase.
Nothing had noticed, because nothing had ever compared them.

The cause: SQLite numbered entities by sorting names, Postgres by insertion
order. Two unrelated orderings. Even the text keys disagreed — Postgres had
`adrian-sutil`, SQLite had `sutil`.

Now both stores carry `slug`, the data source's own id, and it is **identical
in both**. Old numeric links still work.

## ✅ DONE — proof the two databases agree

Not just row counts. Row counts would pass even if every result were attached
to the wrong driver.

- All **503 race classifications**, position by position — identical
- **Career totals and points** per driver — identical
- **Season points** including sprints — identical
- Qualifying, sprints, pit stops, lap times, sessions — identical

## ✅ DONE — proof the two *implementations* agree

Same data can still give different answers, because SQLite and Postgres
calculate through separately written SQL. So the calculations are compared
too — championship standings across 2000, 2013, 2021 and 2025 (2021 chosen
because a version that forgot sprint points would look perfect before then).

This found a real bug: tied drivers came out in different orders. Both now
sort identically.

## ✅ DONE — new data

| Data | Rows | Covers |
|---|---|---|
| Lap times | in progress | per-race, resumable |
| Weekend timetable | 1,596 | 2006–2025 |
| Everything previously loaded | unchanged | verified again |

## ✅ DONE — Supabase went from 5 endpoints to 20

It was 5 of 30, and the code had **never been run against the real database**.
It has now. 20 endpoints work, and each one is only listed as working because
a test compares its answer to the SQLite answer.

The other 10 are listed **with reasons** in `backends.py`. They are
calculations that exist only in Python; copying them into the database would
mean defining the same number twice.

## ✅ DONE — the code stopped lying (again)

`analytics.py` — the file that calls itself the single source of truth —
listed **points, championship standings, grid, qualifying, DNFs, lap times and
pit stops** under "DELIBERATELY ABSENT". All of them exist. The same claim was
in the API documentation every consumer reads, and in four more places.

All fixed. And availability is now **counted from the database**, so this
particular lie cannot come back.

## ✅ DONE — bugs found this round

1. **Ten numbers were computed and then thrown away.** Points, DNFs, average
   grid, places gained and six more were calculated on every request and
   silently dropped before reaching you, because the response format didn't
   declare them. No error, no failing test — just missing.
2. **The migration files didn't match the database.** Two had been saved with
   Windows line endings while the database recorded Unix ones. The checksum
   file had been regenerated from those same files, so it agreed with itself.
3. **Your qualifying data has six real errors** — from the source, not us. Two
   drivers share P15 at Silverstone 2023, and there's no P20 in a 20-car
   session. Six sessions affected. Left exactly as published; a test pins them
   so a seventh can't slip in.
4. **A 33-minute lap** looked like a parsing bug. It's real — the 2023
   Australian GP red flag, counted inside the lap. My test was wrong, not the
   data.

---

## ❌ NOT DONE — practice results (no source)

The API has **no practice results at all** — `/practice`, `/fp1` and
`/sessions` all return errors. What exists is the *timetable*, and that is
what was loaded and what it is called.

Practice classifications would need F1's live-timing feed via a different
library, covering 2018 onward. That is a separate decision, not a detail, so
nothing was invented and no empty `practice_results` table was created — an
empty table would read as "nobody set a time".

## ❌ NOT DONE — still no source exists

**Car and engine specs** (your Car Library has nothing real), **tyres**,
**fastest laps**, **telemetry**, **sector times**.

## ❌ NOT DONE — remaining code work

| Item | State |
|---|---|
| **Routers still call SQLite directly** | The Supabase functions exist and are tested, but the API doesn't dispatch to them yet. Setting `F1_BACKEND=supabase` is not yet enough. |
| **10 endpoints have no Supabase version** | Listed with reasons in `backends.py` |
| **Frontend still links by number** | Works, but should move to slugs |
| **Pre-2000 seasons** | Not loaded (you chose not to) |

---

## ⚠️ TWO THINGS TO KNOW

**"Qualifying P1" is not "poles."** Counting fastest-qualifier gives Hamilton
107; his official count is 104. It is never labelled "poles", and a test locks
the number.

**Tied points are not resolved properly.** Drivers level on points are ordered
by wins, then podiums, then name — so the two backends agree. The real rule is
a countback and is not implemented. It is documented in both places rather
than pretended.

---

## 🤔 STILL YOUR CALL

1. **Pre-2000 data?** Would roughly triple the dataset.
2. **Practice results?** Needs a new data source and a new dependency.
3. **Sauber / BMW Sauber / Alfa Romeo are 3 separate teams** — historically
   correct; confirm that is how you want them shown.
