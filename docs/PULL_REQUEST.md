# Backend, data enrichment, and production readiness

This branch is the project. `main` holds only the original standalone analysis
scripts; everything else — ETL, database, API, frontend, tests, docs, CI —
arrives here. 712 files, 50 commits.

It ends with a full production-readiness audit, which is where the two most
serious defects were found.

---

## 1. What the dataset contains

| Dataset | Rows | Coverage | Source |
|---|---|---|---|
| Race classifications | 10,550 | 2000–2025, 503 races | Ergast lineage / Jolpica-F1 |
| Lap timings | **552,138** | 2000–2025, **503/503 races** | Jolpica-F1 |
| Practice laps | 211,257 | 2018–2025, 464 sessions | FastF1 |
| Tyre compounds | 210,096 | 2018–2025 | FastF1 |
| Sector times | 185,427 | 2018–2025 | FastF1 |
| Pit stops | 12,192 | 2011–2025 | Jolpica-F1 |
| Qualifying | 9,577 | 2003–2025 complete; 2000–02 partial | Jolpica-F1 |
| Sprints | 480 | 2021–2025 | Jolpica-F1 |
| Weekend timetable | 1,596 | 2006–2025 | Jolpica-F1 |

Practice timing, tyre compounds and sector times were previously reported as
having no source. True of Jolpica, which publishes none of them; not true of
every source — FastF1 reads Formula 1's live timing, which does. The two
providers stay in separate tables with separate verification levels, because
blending them is how two sources start disagreeing with no way to tell which
one is wrong.

Every source extract is committed as a CSV, so a fresh clone builds the whole
database offline. Verified: three independent rebuilds produced a
**byte-identical** database (`md5 5f45e8dc…`), lap and practice tables intact.

---

## 2. The two defects that mattered

### The 2007 constructors' champion was wrong

Constructor standings were derived by summing driver points. A championship
penalty is applied by the FIA to the *championship*, not to the classifications
it is summed from, and the source records only the results:

| Season | Constructor | Summed | Official | |
|---|---|---|---|---|
| 2007 | McLaren | 218 | **0** | Excluded (FIA WMSC, 13 Sept 2007). **Ferrari won it with 204.** |
| 2020 | Racing Point | 210 | **195** | −15 (brake ducts). Position unchanged. |

Everything else reconciled exactly — all 26 driver champions, their exact
points totals, and every other constructor total sampled across five seasons.

The fix models **the deduction**, not a hand-entered final total: the total is
still derived, then the FIA's penalty applied. A typed-in total could not be
checked against anything. One table serves both backends. Wins and podiums are
deliberately not adjusted — McLaren won eight races in 2007 and those races
happened. Adjusted rows carry a `penalty` object through the API into the
frontend types, so a changed number is never silent.

### Eight endpoints returned bare 500s on a malformed URL

An id wider than SQLite's signed 64-bit integer raised `OverflowError`, which
is not `sqlite3.Error`, so the API's database handler never caught it. The
request died as `500 Internal Server Error` with no `detail` body — the one
shape the client cannot render, and one it offers to retry forever because it
classifies 5xx as retryable. Reachable by typing a long number in the URL.

Bounded at the lookup and on the path/query parameters that had a lower bound
only, restoring an invariant `entities.py`'s own docstring already claimed.

---

## 3. Earlier in the branch

**One identity across two stores.** `/drivers/7` referred to a different person
in SQLite than in Postgres — integer keys were assigned by enumerating sorted
names independently in each store. Entities now carry a source-derived `slug`
that means the same thing everywhere; integer ids still resolve so existing
links do not break.

**Stale absence claims.** A recurring class of bug where the UI said data was
missing that the database already held. Now caught by a test
(`test_no_stale_absence_claims.py`) rather than by someone noticing.

**Three parity suites**, because each catches what the others cannot: store
parity (same rows), backend parity (same capability), payload parity (same
JSON shape).

---

## 4. Production-readiness audit

**Security.** Git history scanned — no credential ever committed. No secret in
the production bundle. The browser never talks to Supabase directly; every
request goes through the API, so no Supabase key of any kind reaches a client.
CORS is allow-listed and `GET`-only.

**RLS tested, not just read.** Probed live against all 21 tables as `anon`:
`select` succeeds on public tables and is denied on `staging_results`;
`insert`, `update` and `delete` all return `42501 permission denied`, confirmed
with well-formed payloads against real columns. Enforced twice — no write
policy *and* revoked grants.

**Input.** Search fuzzed with SQL, XSS, Unicode, nulls, 5,000-character terms:
no crash, no leaked error. Every dynamic SQL identifier is allow-listed; values
are parameterised.

**Frontend.** No horizontal overflow at 320/375/430/768/1920 — three grids used
a bare `minmax(280px, 1fr)` and were fixed with the `min()` guard the codebase
already documented. Zero missing alts, unnamed controls, unlabelled inputs,
heading skips or positive tabindex across nine routes. 30 tab stops, all with a
visible focus ring, no traps; the command palette is a proper combobox that
restores focus on Escape. Contrast passes. Touch targets under 24px all clear
the WCAG 2.2 spacing exception.

**Failure states.** Offline, 503, malformed JSON and empty responses on
never-visited routes: no blank screens, no stale data shown as current, retry
present and recovery works. Two error messages were written for whoever deploys
this rather than whoever reads it ("Is the backend running?") and were
rewritten.

**Performance.** No N+1. Charts are hand-rolled SVG, ≤244 nodes, ≤4 ms reflow.
Heaviest page is `/cars` at 2,898 DOM nodes with 151/152 images lazy and every
image dimensioned. Lists paginate.

**Data.** 38 integrity checks, 0 failed, 2 documented upstream warnings. Zero
future-dated races, malformed dates or season/date mismatches. NULL and zero
stay distinct (`grid = 0` is a pit-lane start, not unknown). Units are now
documented per column, including the warning that `pit_stops.duration` is text
in two formats and must not be averaged.

---

## 5. CI

Added, and it earned its place immediately: it failed on its first two runs and
caught a defect nobody would have found locally.

`CHECKSUMS.md5` recorded the **CRLF** hashes of migrations 22 and 23 while the
repository stored LF. So `verify_migrations.py` passed on the single working
copy the checksums were generated from and failed on **every fresh checkout** —
every clone, every other machine, and CI. The check that exists to prove the
schema has not drifted was itself the thing that had drifted. Confirmed the SQL
was unchanged (content hash with CR stripped equals the checkout's hash), then
regenerated and pinned `eol=lf`.

CI runs the database build, both test suites, the data audit, the migration
checksums and the production build on every push. No secret is used or wanted —
the Supabase tests skip themselves without credentials, and adding a key would
hand it to every fork's pull request.

---

## 6. Verification

| Check | Result |
|---|---|
| Backend tests | **393 passed** locally, 1 skipped (Supabase leg runs when credentials are present; CI runs the SQLite leg) |
| Frontend tests | **59 passed** |
| Data integrity audit | **44 checks: 0 failed**, 2 warned (both upstream omissions) |
| Migration checksums | **24/24 match** |
| Production build | Clean; 343 kB main chunk (111 kB gzip) |
| Database reproducibility | Byte-identical across three rebuilds |
| `pip-audit` / `npm audit` | Both clean — **0 vulnerabilities**, with and without `--omit=dev` |

---

## 7. Known limitations

- **Coverage starts in 2000.** No figure here is an all-time F1 record.
- **Images are third-party and their provenance is not recorded.** 266 car
  photos, 129 driver portraits, 35 team logos, 25 circuit outlines. The repo
  documents no source or licence for any of them. Every image has a graceful
  labelled fallback, so they can be removed without breaking a layout.
- **No monitoring, error reporting or alerting.** If the deployed app breaks,
  nothing tells anyone. `docs/OPERATIONS.md` §6 lists the minimum worth adding.
- **No down-migrations.** A destructive schema change needs a restore point
  taken first; recovery procedure is in `docs/OPERATIONS.md` §2.
- **The Supabase leg is verified locally only.** Its parity tests skip in CI by
  design.
- **Not tested on Firefox or Safari**, and not tested with a real screen reader
  — ARIA semantics were verified programmatically, which is not the same thing.
- **`cars` and `engines` tables are deliberately empty.** No source ingested;
  they report `unavailable`, never `0`.

---

## 8. Not included

Telemetry, car specifications, and any live or in-progress race data. The
dataset is static and every screen says so.
