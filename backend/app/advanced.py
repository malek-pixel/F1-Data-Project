"""Advanced motorsport analytics.

Companion to `analytics.py`, which holds the core stat block. This module adds
the metrics that need more than a single aggregate: distribution shape,
teammate head-to-head, circuit specialisation, season dominance and era
summaries.

--------------------------------------------------------------------------
THE CENTRAL PROBLEM THIS MODULE ADDRESSES
--------------------------------------------------------------------------
A race result is a joint product of car and driver. Raw finishing statistics
cannot separate them: a driver in a dominant car outscores a better driver in
a poor one, every time. Nothing in a results-only dataset resolves that.

Teammate comparison is the closest available control. Two drivers in the same
constructor in the same race have, to a first approximation, equivalent
machinery -- so the finishing gap between them is the least car-contaminated
signal this dataset can produce. It is the reason `teammate_records` exists
and why it is weighted more heavily in the UI than raw career totals.

It is still not a measure of driver skill. See LIMITATIONS on each function.
"""
from __future__ import annotations

import sqlite3
import statistics
from collections import defaultdict

# --------------------------------------------------------------------------
# Sample-size thresholds
#
# Each is chosen from the actual distribution of this dataset, not copied
# between metrics. The numbers below come from the feasibility pass:
#   entries per driver     median 40; 118 of 129 drivers have >= 10
#   driver-circuit combos  median 2;  797 of 2720 have >= 5
#   teammate pairings      244 total; 165 have >= 10 shared races
# --------------------------------------------------------------------------

#: Minimum entries before a rate (win/podium/top-10) is treated as comparable.
#: Below this a single result swings the rate by 10+ points.
MIN_ENTRIES_FOR_RATES = 10

#: Minimum entries before a standard deviation is reported at all. Variance
#: from fewer than 5 observations describes the sample, not the driver.
MIN_ENTRIES_FOR_SPREAD = 5

#: Minimum appearances at a circuit before "specialist" language is used.
#: 3 would admit a driver who happened to score once in three visits; 5 keeps
#: 797 driver-circuit combinations, which is ample coverage.
MIN_APPEARANCES_FOR_SPECIALISM = 5

#: Minimum shared races before a teammate head-to-head is called comparable.
#: A part-season pairing can be 3-1 on pure chance.
MIN_SHARED_RACES = 5


# --------------------------------------------------------------------------
# Metric registry -- the single source of truth for definitions
# --------------------------------------------------------------------------
# Served at /api/analytics/metrics and rendered on the Methodology page, so
# the documented definition and the implemented one cannot drift apart.

METRICS: list[dict] = [
    {
        "key": "entries",
        "name": "Entries (starts)",
        "formula": "COUNT(results rows)",
        "columns": ["position"],
        "level": "career / season / circuit",
        "definition": (
            "One classified race entry. The denominator for every rate in this application."
        ),
        "edge_cases": "No status column exists, so a lap-1 retirement counts as an entry.",
        "limitations": "Not a count of finishes. Entries cannot be split into finishes and retirements.",
        "min_sample": None,
    },
    {
        "key": "avg_classified_position",
        "name": "Average classified position",
        "formula": "mean(position)",
        "columns": ["position"],
        "level": "career / season / circuit",
        "definition": "Mean final classification across all entries. Lower is better.",
        "edge_cases": "Retirements are included at their classified position, inflating the mean.",
        "limitations": (
            "Not a measure of pace. Biased upward by unreliability and by races with large fields. "
            "Not comparable across eras without noting field size and retirement rates."
        ),
        "min_sample": None,
    },
    {
        "key": "median_classified_position",
        "name": "Median classified position",
        "formula": "median(position)",
        "columns": ["position"],
        "level": "career / season",
        "definition": "The middle classification. Robust to a handful of extreme results.",
        "edge_cases": "Even sample sizes use the mean of the two central values.",
        "limitations": (
            "Read alongside the mean, never instead of it. A mean far above the median indicates "
            "occasional very poor classifications — typically retirements — rather than "
            "consistently weaker running."
        ),
        "min_sample": None,
    },
    {
        "key": "position_stdev",
        "name": "Finishing spread (standard deviation)",
        "formula": "sample standard deviation of position",
        "columns": ["position"],
        "level": "career / season",
        "definition": "Dispersion of classified positions. Lower means more repeatable results.",
        "edge_cases": f"Not reported below {MIN_ENTRIES_FOR_SPREAD} entries.",
        "limitations": (
            "Low spread is not inherently good: a driver consistently classified 15th has a low "
            "spread. Interpret only together with the mean. Retirements inflate spread, so this "
            "partly measures car reliability rather than driver consistency."
        ),
        "min_sample": MIN_ENTRIES_FOR_SPREAD,
    },
    {
        "key": "win_rate",
        "name": "Win rate",
        "formula": "wins / entries",
        "columns": ["position"],
        "level": "career / season / circuit",
        "definition": "Share of entries resulting in a win.",
        "edge_cases": "null when entries = 0; 0.0 when entries exist but no wins.",
        "limitations": "Dominated by car competitiveness. Not a driver-skill measure.",
        "min_sample": MIN_ENTRIES_FOR_RATES,
    },
    {
        "key": "top10_rate",
        "name": "Top-10 rate",
        "formula": "COUNT(position <= 10) / entries",
        "columns": ["position"],
        "level": "career / season / circuit",
        "definition": "Share of entries classified in the top ten.",
        "edge_cases": "Applied uniformly across all seasons.",
        "limitations": (
            "Field sizes vary from 20 to 24 across the covered period, so a top-10 finish is not "
            "equally difficult in every season. Historically it also tracked the points boundary "
            "only from 2010. This metric is purely positional by design -- points are "
            "available and are reported separately rather than folded into it."
        ),
        "min_sample": MIN_ENTRIES_FOR_RATES,
    },
    {
        "key": "teammate_h2h",
        "name": "Teammate head-to-head",
        "formula": "races finished ahead of teammate / races both classified",
        "columns": ["position", "constructor", "race"],
        "level": "driver pair within a constructor",
        "definition": (
            "Across races where both drivers started for the same constructor, the share in which "
            "this driver was classified ahead. The closest available control for car performance."
        ),
        "edge_cases": (
            "Only races where both drivers appear for that constructor are counted, so unequal "
            "season lengths and mid-season replacements cannot distort the ratio. Ties are "
            "impossible — classification order is strictly unique within a race."
        ),
        "limitations": (
            "No finishing status exists, so a mechanical retirement is counted as a loss. This "
            "systematically penalises the driver who suffered more failures, independently of "
            "pace. Treat as a results comparison, not a pace comparison."
        ),
        "min_sample": MIN_SHARED_RACES,
    },
    {
        "key": "teammate_position_delta",
        "name": "Teammate position delta",
        "formula": "mean(teammate position - own position) over shared races",
        "columns": ["position", "constructor", "race"],
        "level": "driver pair within a constructor",
        "definition": "Average positions gained on the teammate. Positive means finishing ahead.",
        "edge_cases": "Computed only over races both drivers were classified in.",
        "limitations": (
            "Inherits the retirement problem above, and is sensitive to a small number of large "
            "gaps — one retirement while the teammate finishes 3rd can move the mean by several "
            "positions. Read with the head-to-head count, which is not distance-weighted."
        ),
        "min_sample": MIN_SHARED_RACES,
    },
    {
        "key": "circuit_specialism",
        "name": "Circuit performance delta",
        "formula": "career avg classified position - avg classified position at circuit",
        "columns": ["position", "race"],
        "level": "driver x circuit",
        "definition": (
            "How much better (positive) or worse (negative) a driver's classification is at one "
            "circuit than across their career."
        ),
        "edge_cases": f"Requires at least {MIN_APPEARANCES_FOR_SPECIALISM} appearances at the circuit.",
        "limitations": (
            "Confounded with career timing: a circuit a driver only visited during their strongest "
            "seasons will show a positive delta regardless of any circuit-specific ability. This "
            "is an observation about where results clustered, not evidence of track suitability."
        ),
        "min_sample": MIN_APPEARANCES_FOR_SPECIALISM,
    },
    {
        "key": "season_dominance",
        "name": "Season win share",
        "formula": "wins / races in season",
        "columns": ["position", "race"],
        "level": "season",
        "definition": "Proportion of a season's races won by one driver or constructor.",
        "edge_cases": "Denominator is races actually held that season, which varies from 16 to 24.",
        "limitations": (
            "Normalised for calendar length but not for grid size or regulation era. "
            "Reported alongside points share, which measures a different thing: a season "
            "can be uneven on wins and close on points."
        ),
        "min_sample": None,
    },
]

METRICS_BY_KEY = {m["key"]: m for m in METRICS}


# --------------------------------------------------------------------------
# Distribution
# --------------------------------------------------------------------------

def _positions(conn: sqlite3.Connection, driver_id: int | None = None,
               constructor_id: int | None = None, season: int | None = None) -> list[int]:
    where, params = [], []
    if driver_id is not None:
        where.append("r.driver_id = ?"); params.append(driver_id)
    if constructor_id is not None:
        where.append("r.constructor_id = ?"); params.append(constructor_id)
    if season is not None:
        where.append("ra.season = ?"); params.append(season)
    clause = " AND ".join(where) or "1=1"
    return [
        row[0]
        for row in conn.execute(
            f"SELECT r.position FROM results r JOIN races ra ON ra.id = r.race_id WHERE {clause}",
            params,
        )
    ]


def distribution(conn: sqlite3.Connection, driver_id: int | None = None,
                 constructor_id: int | None = None, season: int | None = None) -> dict:
    """Shape of an entity's finishing distribution.

    Mean alone hides the difference between a driver who is reliably 5th and
    one who alternates podiums with retirements. Median and spread separate
    those two cases; the histogram lets a reader see it directly.
    """
    positions = _positions(conn, driver_id, constructor_id, season)
    if not positions:
        return {
            "entries": 0, "median": None, "stdev": None, "spread_reliable": False,
            "iqr": None, "worst": None, "histogram": [],
        }

    ordered = sorted(positions)
    n = len(ordered)

    def percentile(p: float) -> float:
        """Nearest-rank percentile. No interpolation -- positions are ordinal,
        and an interpolated 'position 7.5' is not a meaningful quantity."""
        return float(ordered[min(n - 1, max(0, int(round(p * (n - 1)))))])

    # Buckets chosen to match how results are actually discussed: the podium,
    # the points-paying region, and everything behind it.
    buckets = [("P1", 1, 1), ("P2–P3", 2, 3), ("P4–P5", 4, 5), ("P6–P10", 6, 10),
               ("P11–P15", 11, 15), ("P16+", 16, 99)]

    return {
        "entries": n,
        "median": statistics.median(ordered),
        # Sample (not population) stdev: these entries are a sample of possible
        # results, not the entire population of a driver's conceivable races.
        "stdev": round(statistics.stdev(ordered), 3) if n >= MIN_ENTRIES_FOR_SPREAD else None,
        "spread_reliable": n >= MIN_ENTRIES_FOR_SPREAD,
        "iqr": round(percentile(0.75) - percentile(0.25), 2) if n >= MIN_ENTRIES_FOR_SPREAD else None,
        "worst": ordered[-1],
        "histogram": [
            {"bucket": label, "count": sum(1 for p in ordered if lo <= p <= hi),
             "share": sum(1 for p in ordered if lo <= p <= hi) / n}
            for label, lo, hi in buckets
        ],
    }


# --------------------------------------------------------------------------
# Teammate analysis
# --------------------------------------------------------------------------

def teammate_records(conn: sqlite3.Connection, driver_id: int) -> list[dict]:
    """Head-to-head against every teammate, per constructor spell.

    METHOD
    Two drivers are teammates in a race when both have a result row for the
    same race AND the same constructor. Only those races are counted, which is
    what makes the comparison fair: a driver who contested 22 races is compared
    with a mid-season replacement only over the races they actually shared.

    Results are grouped by (teammate, constructor) rather than by teammate
    alone, because the same pair can be teammates at different teams in
    different years and those spells are not one sample.

    LIMITATION (important)
    With no status column, a retirement is simply a poor classification, so
    mechanical failures count as head-to-head losses. This measures who was
    classified ahead, not who was quicker.
    """
    rows = conn.execute(
        """
        SELECT me.race_id, ra.season, me.constructor_id, co.slug AS constructor_slug,
               co.name AS constructor_name,
               me.position AS my_pos, mate.driver_id AS mate_id,
               d.slug AS mate_slug, d.name AS mate_name,
               mate.position AS mate_pos
        FROM results me
        JOIN results mate
          ON mate.race_id = me.race_id
         AND mate.constructor_id = me.constructor_id
         AND mate.driver_id != me.driver_id
        JOIN races ra       ON ra.id = me.race_id
        JOIN constructors co ON co.id = me.constructor_id
        JOIN drivers d       ON d.id  = mate.driver_id
        WHERE me.driver_id = ?
        ORDER BY ra.season, ra.round
        """,
        [driver_id],
    ).fetchall()

    grouped: dict[tuple[int, int], dict] = {}
    for row in rows:
        key = (row["mate_id"], row["constructor_id"])
        spell = grouped.setdefault(
            key,
            {
                "teammate_id": row["mate_id"],
                "teammate_slug": row["mate_slug"],
                "teammate_name": row["mate_name"],
                "constructor_id": row["constructor_id"],
                "constructor_slug": row["constructor_slug"],
                "constructor_name": row["constructor_name"],
                "shared_races": 0,
                "ahead": 0,
                "behind": 0,
                "_delta_sum": 0,
                "_my_positions": [],
                "_mate_positions": [],
                "seasons": set(),
            },
        )
        spell["shared_races"] += 1
        # Classification order is strictly unique within a race, so there is
        # no tie branch to handle.
        if row["my_pos"] < row["mate_pos"]:
            spell["ahead"] += 1
        else:
            spell["behind"] += 1
        spell["_delta_sum"] += row["mate_pos"] - row["my_pos"]
        spell["_my_positions"].append(row["my_pos"])
        spell["_mate_positions"].append(row["mate_pos"])
        spell["seasons"].add(row["season"])

    out = []
    for spell in grouped.values():
        n = spell["shared_races"]
        out.append(
            {
                "teammate_id": spell["teammate_id"],
                "teammate_slug": spell["teammate_slug"],
                "teammate_name": spell["teammate_name"],
                "constructor_id": spell["constructor_id"],
                "constructor_slug": spell["constructor_slug"],
                "constructor_name": spell["constructor_name"],
                "seasons": sorted(spell["seasons"]),
                "shared_races": n,
                "ahead": spell["ahead"],
                "behind": spell["behind"],
                "h2h_rate": spell["ahead"] / n,
                # Positive = this driver finished ahead on average.
                "avg_position_delta": round(spell["_delta_sum"] / n, 3),
                "my_avg_position": round(statistics.fmean(spell["_my_positions"]), 3),
                "teammate_avg_position": round(statistics.fmean(spell["_mate_positions"]), 3),
                "comparable": n >= MIN_SHARED_RACES,
            }
        )
    out.sort(key=lambda s: (-s["shared_races"], s["teammate_name"]))
    return out


def teammate_summary(conn: sqlite3.Connection, driver_id: int) -> dict:
    """Career totals across every teammate spell that clears the threshold.

    Spells below MIN_SHARED_RACES are excluded from the totals rather than
    diluted into them, and counted separately so the exclusion is visible.
    """
    spells = teammate_records(conn, driver_id)
    counted = [s for s in spells if s["comparable"]]
    shared = sum(s["shared_races"] for s in counted)
    if not shared:
        return {
            "shared_races": 0, "ahead": 0, "behind": 0, "h2h_rate": None,
            "avg_position_delta": None, "teammates": len(spells),
            "excluded_short_spells": len(spells) - len(counted),
        }
    ahead = sum(s["ahead"] for s in counted)
    return {
        "shared_races": shared,
        "ahead": ahead,
        "behind": shared - ahead,
        "h2h_rate": ahead / shared,
        # Weighted by races in each spell, so a long partnership counts for
        # more than a four-race one.
        "avg_position_delta": round(
            sum(s["avg_position_delta"] * s["shared_races"] for s in counted) / shared, 3
        ),
        "teammates": len(counted),
        "excluded_short_spells": len(spells) - len(counted),
    }


# --------------------------------------------------------------------------
# Circuit specialisation
# --------------------------------------------------------------------------

def circuit_profile(conn: sqlite3.Connection, driver_id: int,
                    min_appearances: int = MIN_APPEARANCES_FOR_SPECIALISM) -> list[dict]:
    """Per-circuit record, with each circuit compared to the driver's own career.

    The delta is against the driver's own career average rather than the field,
    which answers "where did this driver do better than they usually did"
    without needing to model car strength.
    """
    career = conn.execute(
        "SELECT AVG(CAST(position AS REAL)) FROM results WHERE driver_id = ?", [driver_id]
    ).fetchone()[0]
    if career is None:
        return []

    rows = conn.execute(
        """
        SELECT ci.id, ci.name, ci.slug, COUNT(*) AS appearances,
               SUM(CASE WHEN r.position  = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN r.position <= 3 THEN 1 ELSE 0 END) AS podiums,
               AVG(CAST(r.position AS REAL)) AS avg_position,
               MIN(r.position) AS best
        FROM results r
        JOIN races ra    ON ra.id = r.race_id
        JOIN circuits ci ON ci.id = ra.circuit_id
        WHERE r.driver_id = ?
        GROUP BY ci.id
        ORDER BY appearances DESC, ci.name
        """,
        [driver_id],
    ).fetchall()

    return [
        {
            "circuit_id": row["id"],
            "circuit_name": row["name"],
            "slug": row["slug"],
            "appearances": row["appearances"],
            "wins": row["wins"],
            "podiums": row["podiums"],
            "avg_classified_position": round(row["avg_position"], 3),
            "best_classified_position": row["best"],
            # Positive = better here than their career norm.
            "delta_vs_career": round(career - row["avg_position"], 3),
            "meets_threshold": row["appearances"] >= min_appearances,
        }
        for row in rows
    ]


def circuit_specialists(conn: sqlite3.Connection, circuit_id: int,
                        min_appearances: int = MIN_APPEARANCES_FOR_SPECIALISM) -> list[dict]:
    """Drivers who outperformed their own career norm at this circuit.

    Ranked by the delta, not by raw results, so a midfield driver who reliably
    over-delivered here is not buried under front-runners who were quick
    everywhere.
    """
    rows = conn.execute(
        """
        SELECT d.id, d.slug, d.name,
               COUNT(*) AS appearances,
               SUM(CASE WHEN r.position  = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN r.position <= 3 THEN 1 ELSE 0 END) AS podiums,
               AVG(CAST(r.position AS REAL)) AS here,
               (SELECT AVG(CAST(r2.position AS REAL)) FROM results r2 WHERE r2.driver_id = d.id) AS career
        FROM results r
        JOIN races ra  ON ra.id = r.race_id
        JOIN drivers d ON d.id  = r.driver_id
        WHERE ra.circuit_id = ?
        GROUP BY d.id
        HAVING appearances >= ?
        ORDER BY (career - here) DESC
        """,
        [circuit_id, min_appearances],
    ).fetchall()
    return [
        {
            "driver_id": row["id"],
            "driver_slug": row["slug"],
            "driver_name": row["name"],
            "appearances": row["appearances"],
            "wins": row["wins"],
            "podiums": row["podiums"],
            "avg_here": round(row["here"], 3),
            "avg_career": round(row["career"], 3),
            "delta_vs_career": round(row["career"] - row["here"], 3),
        }
        for row in rows
    ]


# --------------------------------------------------------------------------
# Season dominance
# --------------------------------------------------------------------------

def season_dominance(conn: sqlite3.Connection, season: int) -> dict | None:
    """How concentrated a season's results were.

    Win share is normalised by races held, so a 19-win season in a 22-race year
    is comparable with a 13-win season in a 16-race year.

    Points share is reported alongside it, and the two answer different
    questions. Wins measure how often one competitor was first; points measure
    how much of the season's total scoring they took.

    They are not on a common scale and must not be compared against each
    other. Every points-paying finisher dilutes points_share, so it is bounded
    well below 1.0 no matter how dominant the leader was: 2023 reads 0.86 win
    share and 0.24 points share, and that gap is arithmetic, not a finding.
    Each is meaningful compared with the SAME measure in another season.

    Points share uses points as awarded under each season's own rules, race
    plus sprint, never recomputed from finishing position: the scoring system
    changed in 2003, 2010 and 2019, and half points exist.
    """
    races = conn.execute("SELECT COUNT(*) FROM races WHERE season = ?", [season]).fetchone()[0]
    if not races:
        return None

    def leaders(entity: str) -> list[dict]:
        table, column = ("drivers", "r.driver_id") if entity == "driver" else ("constructors", "r.constructor_id")
        rows = conn.execute(
            f"""
            SELECT e.id, e.name,
                   SUM(CASE WHEN r.position  = 1 THEN 1 ELSE 0 END) AS wins,
                   SUM(CASE WHEN r.position <= 3 THEN 1 ELSE 0 END) AS podiums,
                   COUNT(*) AS entries,
                   AVG(CAST(r.position AS REAL)) AS avg_position,
                   SUM(COALESCE(r.points, 0)) AS points
            FROM results r
            JOIN races ra  ON ra.id = r.race_id
            JOIN {table} e ON e.id  = {column}
            WHERE ra.season = ?
            GROUP BY e.id
            ORDER BY wins DESC, podiums DESC, avg_position ASC
            """,
            [season],
        ).fetchall()
        return [
            {
                "id": row["id"], "name": row["name"], "wins": row["wins"], "podiums": row["podiums"],
                "entries": row["entries"],
                "avg_classified_position": round(row["avg_position"], 3),
                "win_share": row["wins"] / races,
                "points": round(row["points"], 2),
            }
            for row in rows
        ]

    drivers, constructors = leaders("driver"), leaders("constructor")

    def points_share(rows: list[dict]) -> float | None:
        """Share of the season's points taken by its highest scorer.

        None rather than 0.0 when the season scored nothing at all, so "no
        points data for this season" stays distinguishable from "nobody
        scored" -- which has never happened.
        """
        total = sum(row["points"] for row in rows)
        if not total:
            return None
        return max(row["points"] for row in rows) / total
    # Number of distinct winners is the plainest dominance signal available:
    # a season won by two drivers was more concentrated than one won by eight.
    distinct_driver_winners = sum(1 for d in drivers if d["wins"] > 0)
    distinct_team_winners = sum(1 for c in constructors if c["wins"] > 0)

    return {
        "season": season,
        "races": races,
        "distinct_driver_winners": distinct_driver_winners,
        "distinct_constructor_winners": distinct_team_winners,
        "top_driver_win_share": drivers[0]["win_share"] if drivers else None,
        "top_constructor_win_share": constructors[0]["win_share"] if constructors else None,
        "top_driver_points_share": points_share(drivers),
        "top_constructor_points_share": points_share(constructors),
        "drivers": drivers[:10],
        "constructors": constructors[:10],
        "basis": (
            "win_share is wins / races held. points_share is the leader's points "
            "divided by ALL points scored that season, race plus sprint, as awarded "
            "under that season's rules. The two are NOT on the same scale and must "
            "not be read as competing estimates of one quantity: twenty drivers "
            "score points, so points_share has a floor far below 1.0 even in a "
            "season one driver dominates -- 2023 is 0.86 win share against 0.24 "
            "points share. Compare each across seasons, never against the other."
        ),
    }


def dominance_timeline(conn: sqlite3.Connection) -> list[dict]:
    """Per-season concentration across the whole dataset.

    Powers the era view: how many different drivers and teams won races each
    year, and what share the season's leader took.
    """
    races = {row[0]: row[1] for row in conn.execute("SELECT season, COUNT(*) FROM races GROUP BY season")}
    winners = conn.execute(
        """
        SELECT ra.season, r.driver_id, r.constructor_id, COUNT(*) AS wins
        FROM results r JOIN races ra ON ra.id = r.race_id
        WHERE r.position = 1
        GROUP BY ra.season, r.driver_id, r.constructor_id
        """
    ).fetchall()

    by_season: dict[int, dict] = defaultdict(lambda: {"drivers": defaultdict(int), "teams": defaultdict(int)})
    for row in winners:
        by_season[row["season"]]["drivers"][row["driver_id"]] += row["wins"]
        by_season[row["season"]]["teams"][row["constructor_id"]] += row["wins"]

    return [
        {
            "season": season,
            "races": races[season],
            "driver_winners": len(data["drivers"]),
            "constructor_winners": len(data["teams"]),
            "top_driver_win_share": max(data["drivers"].values()) / races[season] if data["drivers"] else 0.0,
            "top_constructor_win_share": max(data["teams"].values()) / races[season] if data["teams"] else 0.0,
        }
        for season, data in sorted(by_season.items())
    ]


def era_summary(conn: sqlite3.Connection) -> list[dict]:
    """Decade-level aggregates.

    Presented as periods rather than a ranking. Regulations, calendar length,
    field size and scoring all changed across these boundaries, so the rows
    describe each period; they do not rank them against each other.
    """
    rows = conn.execute(
        """
        SELECT (ra.season / 10) * 10 AS decade,
               COUNT(DISTINCT ra.season)         AS seasons,
               COUNT(DISTINCT ra.id)             AS races,
               COUNT(DISTINCT r.driver_id)       AS drivers,
               COUNT(DISTINCT r.constructor_id)  AS constructors,
               AVG(CAST(r.position AS REAL))     AS avg_field_position,
               MAX(r.position)                   AS largest_field
        FROM results r JOIN races ra ON ra.id = r.race_id
        GROUP BY decade ORDER BY decade
        """
    ).fetchall()

    out = []
    for row in rows:
        decade = row["decade"]
        champs = conn.execute(
            """
            SELECT d.name, COUNT(*) AS wins
            FROM results r JOIN races ra ON ra.id = r.race_id JOIN drivers d ON d.id = r.driver_id
            WHERE r.position = 1 AND ra.season >= ? AND ra.season < ?
            GROUP BY d.id ORDER BY wins DESC LIMIT 3
            """,
            [decade, decade + 10],
        ).fetchall()
        out.append(
            {
                "decade": decade,
                "label": f"{decade}s",
                "seasons": row["seasons"],
                "races": row["races"],
                "drivers": row["drivers"],
                "constructors": row["constructors"],
                "largest_field": row["largest_field"],
                "top_winners": [{"name": c["name"], "wins": c["wins"]} for c in champs],
            }
        )
    return out
