# Backend & Data — simple checklist

Updated 2026-08-17. Every ✅ has evidence; nothing is ticked because it looks done.

**Check it yourself** (all pass right now):

```
python -m pytest backend/tests -q       249 passed
cd frontend && npx vitest run            49 passed
python -m backend.etl.audit              38 checks, 0 failed
python supabase/verify_migrations.py     18/18 byte-exact
python -m backend.etl.crossvalidate      503 races, 0 discrepancies
python -m backend.etl.laps --status      lap ingestion progress
```

---

## 🔄 RUNNING RIGHT NOW — two downloads

Two background fetches. Both **resumable**: nothing already downloaded is ever
re-requested, so stopping and restarting costs only the time it was stopped.

| | Downloading | Check progress |
|---|---|---|
| **Laps** | per-lap timings, all 503 races | `python -m backend.etl.laps --status` |
| **Practice** | practice laps, tyres, sector times (2018+) | `python -m backend.etl.practice --status` |

### Can I close the laptop?

**No — sleeping the machine pauses both.** They are ordinary local processes,
not cloud jobs. Nothing is lost; they simply stop until it wakes.

* **Closing the lid / sleep** — pauses. Usually resumes on wake by itself.
* **Shutdown or restart** — the processes die. Nothing is lost, but you must
  restart them by hand (below).
* **Leaving it awake** — they finish on their own.

To keep it running unattended, set the power settings so the machine does not
sleep on its own, then leave it.

### Restart them (safe at any time, even if unsure)

```
python -u -m backend.etl.fetch_until_done practice laps
```

**One command, one terminal — do not run the two in parallel.** They look
independent and are not: FastF1 resolves each event through the same Jolpica
service the lap fetch uses, so running both starves each of quota. Measured
directly -- concurrently, lap failures went from 1 to 31 in minutes, while
practice sat in a six-minute rate-limit wait. Sequentially, both run clean.

The command loops until each dataset is complete and stops on its own if two
passes in a row achieve nothing, so it will not spin forever pretending to
work.

### Make it much faster

Set `JOLPICA_API_KEY` in `.env`. It raises the hourly request cap roughly
twentyfold and turns the lap fetch from an overnight job into under an hour.

### When BOTH report `"remaining": 0`, run these

```
python -m backend.etl.build_laps
python -m backend.etl.build_practice
python -m backend.etl.build
python -m backend.etl.supabase_import
python -m pytest backend/tests -q
```

Until then both tables are genuinely partial, and every report says so --
coverage prints as a fraction ("204/503 races"), never as a season range,
because the endpoints of a half-filled set are not coverage.

---|---|
| Progress | see `python -m backend.etl.laps --status` |
| Speed | limited by the API's ~500 requests/hour cap |
| Total time | ~9 hours unattended |
| Make it fast | set `JOLPICA_API_KEY` — raises the cap 20x, finishes in under an hour |
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

## ✅ DONE — the backend switch works

`F1_BACKEND=supabase` now genuinely serves. Three separate suites prove it,
because each catches something the others cannot:

| Suite | Question it answers |
|---|---|
| Store parity | Do the two databases hold the same rows? |
| Backend parity | Do the two implementations compute the same numbers? |
| API payload parity | Does the HTTP response match, field for field? |

The first two can both pass while the API is broken, which is exactly what
happened — the third caught season stats returning nulls from Postgres.

## ✅ DONE — the app links on slugs

All 19 entity links now use `/drivers/hamilton`, not `/drivers/48`. Six
payloads that had no slug to link on now carry one.

## ❌ NOT DONE — remaining code work

| Item | State |
|---|---|
| **10 endpoints have no Supabase version** | Listed **with reasons** in `backends.py`. Each is a calculation defined only in Python; copying it into the database would define the same number twice. |
| **Pre-2000 seasons** | Not loaded (you chose not to) |

---

## ⚠️ THREE THINGS TO KNOW

**"Qualifying P1" is not "poles."** Counting fastest-qualifier gives Hamilton
107; his official count is 104. It is never labelled "poles", and a test locks
the number.

**Tied points are not resolved properly.** Drivers level on points are ordered
by wins, then podiums, then name — so the two backends agree. The real rule is
a countback and is not implemented. It is documented in both places rather
than pretended.

**Qualifying has six real errors, from the source.** Two drivers share P15 at
Silverstone 2023, and there is no P20 in a 20-car session. Six sessions are
affected. Left exactly as published rather than renumbered, with a test
pinning the set so a seventh cannot appear unnoticed.

---

## 🤔 STILL YOUR CALL

1. **Pre-2000 data?** Would roughly triple the dataset.
2. **Practice results?** Needs a new data source and a new dependency.
3. **Sauber / BMW Sauber / Alfa Romeo are 3 separate teams** — historically
   correct; confirm that is how you want them shown.
