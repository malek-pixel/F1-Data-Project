# Methodology

What every number in this application means, how it is calculated, and what
the dataset cannot support.

Definitions here are mirrored by docstrings in `backend/app/analytics.py`,
which is the only place calculations live. If the two ever disagree, the code
is authoritative and this file is a bug.

---

## 1. Source data

| | |
|---|---|
| File | `results.csv` |
| Rows | 10,550 |
| Coverage | Seasons 2000–2025, 503 races |
| Columns | `season, round, race_name, date, position, driver, constructor` |
| Entities | 129 drivers, 38 constructors, 39 circuits |
| Origin | Ergast-derived race classifications |

There are seven columns. That single fact determines everything below.

### The `position` column is not a finishing status

`position` holds **final classification order, 1..N**. Values are integers
only — there is no `DNF`, `DNS`, `DSQ`, `NC` or `status` column anywhere in
the source. A driver who retired on lap 1 still receives a classification
number.

Consequence: this application **cannot** distinguish a finish from a
retirement. Every metric derived from `position` is a metric about
*classification*, and is named accordingly.

---

## 2. Capability matrix

What the design asks for, versus what seven columns can support.

### Buildable — implemented

| Metric | Formula | Notes |
|---|---|---|
| Entries (starts) | `COUNT(results)` | One row = one classified entry |
| Wins | `COUNT(position = 1)` | |
| Podiums | `COUNT(position <= 3)` | |
| Win rate | `wins / entries` | Denominator is entries, not finishes |
| Podium rate | `podiums / entries` | |
| Average classified position | `AVG(position)` | Includes retirements — see §3 |
| Best classified position | `MIN(position)` | |
| Wins/podiums by season | Grouped by `season` | Drives the season charts |
| Career timeline | Season range per entity | |
| Constructor history | Driver × constructor × season | Mid-season switches kept separate |
| Driver contribution | Share of team entries/wins/podiums | **Not** share of points — see below |
| Circuit records | Grouped by `circuit_id` | Circuit derived — see §4 |
| Head-to-head | Career blocks + shared-season window | See §5 |

### Degraded — implemented, but not what the label usually means

| Design element | What it actually is | Why |
|---|---|---|
| Season "standings" | **Both are returned.** `standings` is the real championship (points, race + sprint); `drivers[]`/`constructors[]` stay wins-ordered with `ranking_basis: "wins"` | The two answer different questions: a driver can lead on wins without winning the title. Clients must label the wins-ordered tables. |
| "Average finishing position" | **Average classified position** | Retirements are ranked, not flagged |
| Driver contribution to team | Share of **entries / wins / podiums** | The design asked for share of team points; points do not exist in the source |

### Unavailable — deliberately not implemented

Not estimated, not inferred, not filled with placeholders. Endpoints expose
these through `/api/dataset/summary`, which **measures** availability by
probing the database rather than reading a list. Only two fields are left:

- Telemetry
- Car specifications (chassis, engine, power, weight, aero) — the `cars` table
  exists and is deliberately empty; no source this project ingests supplies it

Adding either requires new source columns first.

#### What this list used to say

Everything below was on the unavailable list above, and every item of it has
since been ingested. The list was not updated, so the project's own
methodology reference spent several ingestions telling readers that data it
holds hundreds of thousands of rows of did not exist:

Each line below records what the list *used to* claim, against what the
database actually holds:

- Qualifying results and grid position — used to be listed as absent; there are
  9,577 qualifying rows, and `grid` is set on all 10,550 results.
- Fastest laps — used to be listed as absent; 8,725 results carry a
  fastest-lap time, covering 2004–2025.
- Finishing status, and the DNF and finish rates built on it — used to be
  listed as absent; `classification` is set on all 10,550 results.
- Championship points and standings — used to be listed as absent; `points` is
  set on all 10,550 results and standings are served for all 26 seasons.
- Race lap timing, lap by lap — used to be listed as absent; there are 552,138
  lap timings across all 503 races.
- Sector times and tyre compounds — used to be listed as absent; 211,257
  practice laps carry them, for practice sessions only.
- Pit stops — used to be listed as absent; 12,192 rows, 2011 onward.
- Sprint results — used to be listed as absent; 480 rows, 2021 onward.

The lesson is the one `backend/tests/test_no_stale_absence_claims.py` was
written for and this file evaded: a claim about absent data has to be checked
against the data, because prose cannot fail a build. Pole positions remain
absent as such — qualifying P1 is counted and labelled `qualifying_p1`, which
is not the same statistic (see below).

> The design mockup's own Methodology screen describes a richer pipeline
> (nightly Ergast ingest, DuckDB warehouse, grid position and fastest lap
> marked present). That is design fiction against sample data. The real
> pipeline and the real field availability are what is documented here —
> data honesty outranks design fidelity.

---

## 3. Metric definitions in full

### Entry (start)
One row in `results`: a driver classified in a race. Because the source has
positions include retirements, an entry does **not** imply the driver finished. This is
the denominator for every rate.

### Win rate — `wins / entries`
The denominator is stated because it is ambiguous in common usage. Alternatives
rejected: `wins / races in the seasons the driver was active` (punishes
part-season drivers arbitrarily), `wins / finishes` (requires a status column
that does not exist).

### Podium rate — `podiums / entries`
A podium is `position <= 3`. Same denominator as win rate.

### Average classified position — `AVG(position)`
**Lower is better.** This is *not* average finishing position. A driver who
retires early and is classified P19 contributes 19 to the mean exactly as if
they had driven to P19. The metric is therefore biased upward by
unreliability, and is not comparable across eras with different retirement
rates without that caveat.

It is reported anyway — with this caveat attached — because it is the best
consistency measure the source supports.

### Small-sample handling
Rates below **10 entries** are returned with `rates_reliable: false`. A driver
with 2 entries and 1 win genuinely has a 50% win rate; the flag lets the UI
mark it rather than silently hiding the driver or the number.

Rate-based **records** apply the threshold as a hard filter, so a single-race
driver cannot top the win-rate table.

### Zero versus null
A rate is `null` when there are no entries, and `0.0` when there are entries
but no wins. These are different facts and the API keeps them different.
`win_share` is `null` when a constructor never won — not `0.0`, which would
imply a share of a real total.

---

## 4. Circuit identity

`results.csv` has no circuit column. Circuits are derived from `race_name`
via `backend/etl/circuit_map.csv`, a curated season-aware map.

A season range is required because several Grands Prix moved venue inside the
2000–2025 window:

| Grand Prix | Venues |
|---|---|
| European | Nürburgring (2000–07) → Valencia (2008–12) → Baku (2016) |
| German | Hockenheim / Nürburgring, alternating from 2009 |
| French | Magny-Cours (2000–08) → Paul Ricard (2018–22) |
| Japanese | Suzuka → Fuji (2007–08) → Suzuka |
| United States | Indianapolis (2000–07) → Austin (2012–) |

Circuits sharing a venue under different race names are unified: San Marino
and Emilia Romagna both resolve to Imola; Austrian and Styrian both resolve to
the Red Bull Ring; Brazilian and São Paulo both resolve to Interlagos.

The build **fails** if any `(race_name, season)` pair in the source has no
matching rule, so a new race name cannot silently fall through.

**Limitation:** this map encodes external F1 knowledge, not information
present in `results.csv`. It is auditable as a plain CSV and should be
reviewed if a new season is added.

**Track maps:** 24 of 39 circuits ship an SVG. The remaining 15 are stored
with `has_map = 0` and render a map-unavailable state — the circuit is never
dropped and never given a substitute shape.

---

## 5. Comparison methodology

Head-to-head returns career blocks for both entities plus:

- `shared_seasons` — seasons in which both were active
- `left_shared` / `right_shared` — stats restricted to that overlapping window
- `comparable` — false when there is no overlap, or either side is below the
  entry threshold

No winner is declared. Career totals across non-overlapping eras, different
entry counts and different machinery are not a like-for-like comparison, and
the API returns the information needed to say so rather than a verdict.

---

## 6. Known data issues

| Issue | Effect |
|---|---|
| 2002 French GP has 20 classification rows but runs to P22 | Two entries absent upstream. Denominators count rows present, never `max(position)`, so this understates that race's field size rather than inventing entries. |
| No finishing status | See §2 — the single largest limitation |
| Coverage starts at 2000 | All records are "within 2000–2025", never all-time |
| Season lengths vary (16–24 races) | Cross-era season totals are not normalised; records state this |
| Constructor identity | Entities follow the source's naming, which already groups Ergast-style (Sauber ↔ BMW Sauber ↔ Alfa Romeo are separate rows). Distinct constructors are never merged without evidence. |
| Championship penalties are not in the results | See §6.1 below. Two constructor totals cannot be reached by summing race results. |

### 6.1 Championship penalties

A championship penalty is applied by the FIA to the **championship**, not to
the race classifications it is summed from. The source carries the race
results — correct, and unchanged by the penalty — and carries no record of the
deduction. Constructor standings are derived by summing driver points, so for
two seasons that sum disagreed with the official final table, and in one of
them it named the wrong champion.

| Season | Constructor | Scored | Official | Penalty |
|---|---|---|---|---|
| 2007 | McLaren | 218 | **0** | Excluded from the Constructors' Championship (FIA WMSC, 13 Sept 2007). Ferrari won the title with 204. |
| 2020 | Racing Point | 210 | **195** | 15 points deducted (FIA Stewards, Styrian GP, brake-duct protest upheld). Position (4th) unchanged. |

How this is handled:

* The penalty is modelled as **the deduction**, in
  `analytics.CONSTRUCTOR_PENALTIES` — not as a hand-entered final total. The
  total is still derived: sum the results, then apply what the FIA applied. A
  typed-in total could not be checked against anything.
* One table serves **both backends**, so SQLite and Supabase cannot disagree
  about a championship.
* **Race wins and podiums are not adjusted.** McLaren won eight races in 2007
  and those races happened; the exclusion removed championship points, not
  results. The row reads "0 points, 8 wins", which is the sporting outcome as
  the record holds it.
* **Driver points are untouched** — explicitly unaffected in both cases, which
  is why the driver standings already reconciled exactly for all 26 seasons.
* An adjusted row carries a `penalty` object through the API and into the
  frontend types, holding what was scored, what was removed, and the evidence.
  A number that changed for a reason the reader cannot see is the thing this
  project treats as fabrication.

Pinned by `backend/tests/test_api.py` against the official classifications,
including unpenalised seasons on either side so the correction cannot quietly
start applying where it does not belong.

---

## 7. Pipeline

```
results.csv
    │
    ▼  backend/etl/build.py
validate      types, ranges, duplicates, date/season agreement,
              per-race position uniqueness, circuit-map coverage
    │         fatal issues abort the build; the DB is not written
    ▼
normalize     stable integer IDs for drivers/constructors/circuits/races
              circuit resolved via circuit_map.csv (accent-folded match)
    │
    ▼
data/f1.db    SQLite, indexed, rebuilt from scratch on every run
    │
    ▼  backend/app/analytics.py     all calculations, defined once
    ▼  backend/app/routers/         REST API, read-only connections
    ▼  frontend                      presentation only, no business logic
```

The database is opened read-only by the API and is dropped and rebuilt on
every ETL run. There is no path by which records can be hand-edited into
drift from `results.csv`.

**This data is not live.** `/api/health` returns `live_data: false`. "Current
season" anywhere in the UI means *latest season in the dataset* (2025), never
a live or in-progress race.

---

## 8. Advanced metrics

Added in the analytics pass. Every one is defined once in
`backend/app/advanced.py` and published at `/api/analytics/metrics`, which is
the same object the Methodology page renders — so the definition shown beside a
number in the UI is the definition the code uses.

### The problem these address

A race result is a joint product of car and driver, and nothing in a
results-only dataset separates them. A driver in a dominant car outscores a
better driver in a poor one, every time. The metrics below do not solve that;
two of them narrow it.

### Teammate head-to-head — the most valuable metric here

```
h2h_rate           = races classified ahead of teammate / races both classified
position_delta     = mean(teammate position − own position) over shared races
```

**Why it matters.** Two drivers in the same constructor in the same race have,
to a first approximation, equivalent machinery. The finishing gap between them
is the least car-contaminated signal this dataset can produce.

**Method.** A pairing is `(driver, teammate, constructor)`. Only races where
**both** drivers have a result row for that constructor are counted — which is
what makes it fair. A driver who contested 22 races is compared with a
mid-season replacement over the races they actually shared, not over the full
season. Spells at different teams are kept separate: the same pair at two
constructors is two samples, not one. Ties cannot occur, since classification
order is strictly unique within a race.

**Minimum sample:** 5 shared races. Below that a pairing can read 3–1 on chance.
Short spells are excluded from career totals and counted separately rather than
silently dropped.

**Limitation, and it is a serious one.** With no finishing status, a mechanical
retirement is simply a poor classification and counts as a head-to-head loss.
This systematically penalises whichever driver suffered more failures,
independently of pace. It measures who was *classified* ahead, not who was
quicker.

A worked example of why both numbers are shown: Hamilton leads Button 32–26 on
head-to-head at McLaren, yet has a **negative** average position delta (−0.97).
The head-to-head says he was classified ahead more often; the delta says his
losses were by larger margins. That is the retirement effect made visible.

### Distribution: median, spread, histogram

```
median  = median(position)
stdev   = sample standard deviation of position
iqr     = P75 − P25, nearest-rank (no interpolation — positions are ordinal)
```

A mean of P8 describes both a driver reliably eighth and one alternating
podiums with retirements. These separate the two cases.

**Reading the mean/median gap.** A mean well above the median indicates a
minority of much poorer classifications pulling the average up — typically
retirements, though the dataset cannot confirm that.

**Minimum sample:** 5 entries for spread. Below that, variance describes the
sample, not the driver.

**Limitation.** Low spread is not inherently good — a driver consistently
classified 15th has a low spread. Interpret only alongside the mean.

### Circuit performance delta

```
delta_vs_career = career avg classified position − avg classified position at circuit
```

Measured against the driver's **own** career average rather than the field, so
it answers "where did this driver do better than they usually did" without
needing to model car strength.

**Minimum sample:** 5 appearances. Below-threshold circuits are still shown,
flagged, but "specialist" language is withheld.

**Limitation.** Confounded with career timing. A circuit a driver only visited
during their strongest seasons shows a positive delta regardless of any
track-specific ability. This is an observation about where results clustered,
not evidence of track suitability.

### Season dominance

```
win_share = wins / races held that season
```

Normalised by calendar length, so a 19-win season in a 22-race year is
comparable with a 13-win season in an 18-race year. Reported alongside the
count of distinct race winners, which is the plainest concentration signal
available.

**Limitation.** Not normalised for grid size or regulation era.

**Points share is reported alongside it**, as each leader's share of all points
scored that season (race plus sprint, as awarded under that season's rules).

The two are **not on a common scale and must not be compared with each other**.
Every points-scoring finisher dilutes points share, so it is bounded well below
1.0 however dominant the leader was: 2023 reads 0.86 win share against 0.24
points share, and that gap is arithmetic, not a finding. Compare each against
the *same* measure in another season.

### Top-5 / top-10 rates

```
top10_rate = COUNT(position <= 10) / entries
```

**Limitation.** Field sizes range from 20 to 24 across the covered period, so a
top-10 finish is not equally difficult in every season. Purely positional — it
does not track the points boundary, which the dataset cannot represent.

---

## 9. What is deliberately *not* built

**No composite driver score.** A single number would have to weight career
length, car competitiveness, teammate strength and era against each other. No
defensible weighting exists for that, so the components are presented
separately and no overall ranking is produced.

**No predictive model.** There is no target variable worth predicting from
seven columns, no features that would justify one, and no evaluation set that
would make a claim about accuracy meaningful. A correct statistic is worth more
than an unvalidated model.

**No causal claims.** The dataset contains no explanatory variables — no car
specifications, no reliability data, no budgets. Insight wording is checked
against a banned-word list in the test suite (`because`, `caused`, `proves`,
`guaranteed`, `due to`) so a future generator cannot quietly introduce one.

### Sample-size thresholds, and why they differ

Each threshold is chosen from this dataset's actual distribution, not copied
between metrics:

| Threshold | Value | Justification |
|---|---|---|
| Rates (win, podium, top-10) | 10 entries | 118 of 129 drivers clear it; below 10 a single result moves a rate 10+ points |
| Spread (standard deviation) | 5 entries | Variance below this describes the sample, not the driver |
| Circuit specialism | 5 appearances | 3 would admit a one-off good run; 5 retains 797 driver-circuit combinations |
| Teammate head-to-head | 5 shared races | A part-season pairing can be 3–1 on chance |
