# Backend and data enrichment

Adds seven datasets, brings the Postgres materialisation to parity with the
SQLite one, and removes a class of bug where the application described data it
already had as missing.

## What this adds

| Dataset | Rows | Coverage | Source |
|---|---|---|---|
| Practice laps | 211,257 | 2018–2025, 464 sessions | FastF1 |
| Tyre compounds | 210,096 | 2018–2025 | FastF1 |
| Sector times | 185,427 | 2018–2025 | FastF1 |
| Lap timings | in progress | 2000–2025, per race | Jolpica-F1 |
| Fastest-lap awards | 8,725 | 2004–2025 | Jolpica-F1 |
| Weekend timetable | 1,596 | 2006–2025 | Jolpica-F1 |
| Constructor natural keys | 38 | — | Jolpica-F1 |

Practice classifications, tyre compounds and sector times were previously
reported as having no source. That was true of Jolpica, which publishes none of
them, but not of every source — FastF1 reads Formula 1's live timing, which
does. The two providers are kept in separate tables with separate verification
levels, because blending them is how two sources start disagreeing with no way
to tell which one is wrong.

## The identity bug

`/drivers/7` referred to a different person in SQLite than in Postgres.

Integer primary keys were assigned by enumerating sorted names in one store and
by a serial sequence in the other. The orderings are unrelated, so the two never
matched. Nothing detected it because nothing had ever compared them. Even the
text keys disagreed — `adrian-sutil` against `sutil`.

Both stores now carry `slug`, taken from the upstream source's own id, which
neither store invents. Routes resolve by slug or by legacy integer id, so
existing links keep working. All 19 entity links in the UI were migrated.

## Three parity suites, because each catches what the others cannot

| Suite | Question |
|---|---|
| `test_store_parity` | Do the two databases hold the same rows? |
| `test_backend_parity` | Do the two implementations compute the same numbers? |
| `test_api_payload_parity` | Does the HTTP response match, field for field? |

The first two passed while the API was still broken under `F1_BACKEND=supabase`
— the views name things as the database does and the contract names them as the
analytics layer does. Only comparing the responses caught it.

Row counts alone would have passed even if every result were attributed to the
wrong driver, which is why the comparisons are on values, keyed on slug.

## Bugs found

**Ten computed fields were being discarded.** Points, DNFs, average grid, places
gained and six more were calculated on every request and dropped before
serialisation, because the response models did not declare them. No error, no
failing test — the ingested points data simply never reached any client.

**Migration checksums agreed with themselves.** Two files were saved with CRLF
while the database recorded LF. The checksum file had been regenerated from
those same files, so verification passed while the files did not match what
Postgres actually ran. All 21 now verify against the database's own record.

**Six genuine errors in the qualifying data**, from the source: two drivers share
P15 at Silverstone 2023, and there is no P20 in a 20-car session. Left exactly as
published rather than renumbered, with a test pinning the set.

**A Supabase failure that looked like a network fault.** Loading 103k rows failed
with `SSL error: unexpected eof`. The real cause was a two-minute server
`statement_timeout`; Postgres cancels the statement and drops the connection, so
the client sees a broken socket. TCP keepalives were the obvious fix and changed
nothing, because the socket was never idle — it was working.

**A speedup that did not exist.** The lap fetcher read `JOLPICA_API_KEY` and,
when set, paced requests at 10,000/hour. That number was invented. Jolpica's
documentation says token authentication is "currently being implemented" and
publishes no authenticated figure. Setting the variable would have paced the
fetcher twenty times over the real limit. Removed.

## Claims the application was making that were no longer true

`analytics.py` — the file that calls itself the single source of truth — listed
points, championship standings, grid, qualifying, DNFs, lap times and pit stops
under "DELIBERATELY ABSENT". All of them existed. The same claim appeared in the
OpenAPI description, in four endpoint docstrings, in the README, and in four
places in the UI, including a panel telling users points and DNFs were
unavailable while the API served them.

Availability is now **counted from row counts** rather than listed, and a test
fails the build if any file claims a dataset is missing that the database has.
It found seven live claims on its first run.

## Endpoint coverage

Supabase went from 5 of 28 endpoints to 27. The remaining one, `insights`, is a
narrative assembled in Python from aggregates that are themselves all available
— only the phrasing is Python, and phrasing is not a metric.

Seven endpoints were previously listed as unimplementable because a view would
duplicate a metric definition. That was right about the danger and wrong about
the remedy: the definitions were **moved** into the database rather than copied,
and each was verified against the SQLite output before being switched over.

## Verification

```
python -m pytest backend/tests -q       286 passed
cd frontend && npx vitest run            49 passed
python -m backend.etl.audit              38 checks, 0 failed
python supabase/verify_migrations.py     21/21 byte-exact
python -m backend.etl.crossvalidate      503 races, 0 discrepancies
```

## Still absent, and verified as such

Car and engine specifications, and telemetry. The `cars` table wants
`chassis_name` and `engine_manufacturer`; Jolpica supplies a constructor name
and nationality, FastF1 supplies a team name and a colour. Neither has them, so
the table stays empty rather than being filled from an unsourced guess.

## Not included

Pre-2000 seasons, deferred by decision. Lap-time ingestion is still running —
the source caps at 500 requests/hour and the work is row-bound, so it is an
overnight job with no query shape that avoids it.
