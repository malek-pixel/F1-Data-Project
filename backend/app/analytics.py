"""The single source of truth for every derived number in this application.

No metric is computed anywhere else -- not in a router, not in the frontend.
If a number appears in the UI, its formula lives in this file.

--------------------------------------------------------------------------
METRIC DEFINITIONS  (mirrored in METHODOLOGY.md -- keep the two in sync)
--------------------------------------------------------------------------
entry / start
    One `results` row: a driver classified in a race. The source has no
    status column, so a driver who retired on lap 1 is still an entry. This
    is the denominator for every rate below, and it is why they are labelled
    "per entry" and not "per finish".

win                     entries where position = 1
podium                  entries where position <= 3
win rate                wins / entries
podium rate             podiums / entries
average classified position
    mean(position) over entries. NOT average *finishing* position: with no
    DNF flag, a lap-1 retirement classified P19 contributes 19. It measures
    where an entry ended up in the final classification, including
    retirements. Lower is better; it is biased upward by unreliability.

driver contribution (within a constructor)
    A driver's share of that constructor's entries / wins / podiums over the
    selected span. Deliberately NOT "share of team points" -- the source has
    no points column, so a points share cannot be computed.

--------------------------------------------------------------------------
DELIBERATELY ABSENT -- required columns are not in the source
--------------------------------------------------------------------------
    pole rate, qualifying performance, grid position, fastest laps,
    DNF rate / finish rate / reliability, points, points-per-race,
    championship standings, lap times, sector times, pit stops, tyres.

Adding any of these requires new source columns first. Routers surface them
as an explicit "unavailable" state; they are never estimated or inferred.
"""
from __future__ import annotations

import logging
import sqlite3

# Minimum entries before a rate or average is treated as comparable. Below
# this, a driver with 2 entries and 1 win reads as a 50% win rate, which is
# true but not meaningful. Endpoints return the value plus `reliable: false`
# and let the UI mark it, rather than silently hiding the entity.
MIN_ENTRIES_FOR_RATES = 10

# Reusable aggregate over `results`. Every stat block in the app is this
# expression -- computing it once here is what keeps the numbers consistent.
_STATS_SELECT = """
    COUNT(*)                                        AS entries,
    SUM(CASE WHEN r.position  = 1 THEN 1 ELSE 0 END) AS wins,
    SUM(CASE WHEN r.position <= 3 THEN 1 ELSE 0 END) AS podiums,
    SUM(CASE WHEN r.position <= 5 THEN 1 ELSE 0 END) AS top5,
    SUM(CASE WHEN r.position <= 10 THEN 1 ELSE 0 END) AS top10,
    AVG(CAST(r.position AS REAL))                    AS avg_position,
    MIN(r.position)                                  AS best_position
"""


def _stats(row: sqlite3.Row | None) -> dict:
    """Turn a `_STATS_SELECT` row into the canonical stat block.

    Rates are None -- not 0.0 -- when there are no entries, so the UI can
    distinguish "no data" from "genuinely zero".
    """
    entries = (row["entries"] if row else 0) or 0
    if not entries:
        return {
            "entries": 0,
            "wins": 0,
            "podiums": 0,
            "top5": 0,
            "top10": 0,
            "win_rate": None,
            "podium_rate": None,
            "top5_rate": None,
            "top10_rate": None,
            "avg_classified_position": None,
            "best_classified_position": None,
            "rates_reliable": False,
        }
    return {
        "entries": entries,
        "wins": row["wins"],
        "podiums": row["podiums"],
        "top5": row["top5"],
        "top10": row["top10"],
        "win_rate": row["wins"] / entries,
        "podium_rate": row["podiums"] / entries,
        "top5_rate": row["top5"] / entries,
        "top10_rate": row["top10"] / entries,
        "avg_classified_position": round(row["avg_position"], 3),
        "best_classified_position": row["best_position"],
        "rates_reliable": entries >= MIN_ENTRIES_FOR_RATES,
    }


def like_pattern(text: str) -> str:
    """Escape LIKE wildcards so a user typing '%' searches for a literal '%'.

    Paired with `ESCAPE '\\'` in every LIKE clause below.
    """
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _season_filter(season_from: int | None, season_to: int | None) -> tuple[str, list]:
    """Build an optional season-range predicate with bound parameters.

    Parameterised throughout -- no value is ever interpolated into SQL.
    """
    clauses, params = [], []
    if season_from is not None:
        clauses.append("ra.season >= ?")
        params.append(season_from)
    if season_to is not None:
        clauses.append("ra.season <= ?")
        params.append(season_to)
    return (" AND " + " AND ".join(clauses) if clauses else ""), params


# --------------------------------------------------------------------------
# Entity stats
# --------------------------------------------------------------------------

def entity_stats(
    conn: sqlite3.Connection,
    entity: str,
    entity_id: int,
    season_from: int | None = None,
    season_to: int | None = None,
) -> dict:
    """Career (or season-range) stat block for a driver, constructor or circuit.

    `entity` selects the column to filter on; it is validated against a fixed
    allow-list, never taken from user input directly.
    """
    column = {"driver": "r.driver_id", "constructor": "r.constructor_id", "circuit": "ra.circuit_id"}[entity]
    where, params = _season_filter(season_from, season_to)
    row = conn.execute(
        f"""
        SELECT {_STATS_SELECT}
        FROM results r JOIN races ra ON ra.id = r.race_id
        WHERE {column} = ?{where}
        """,
        [entity_id, *params],
    ).fetchone()
    return _stats(row)


def by_season(
    conn: sqlite3.Connection,
    entity: str,
    entity_id: int,
) -> list[dict]:
    """Season-by-season breakdown. Powers the wins-by-season and
    average-position-over-time charts, and the season table."""
    column = {"driver": "r.driver_id", "constructor": "r.constructor_id", "circuit": "ra.circuit_id"}[entity]
    rows = conn.execute(
        f"""
        SELECT ra.season, {_STATS_SELECT}
        FROM results r JOIN races ra ON ra.id = r.race_id
        WHERE {column} = ?
        GROUP BY ra.season
        ORDER BY ra.season
        """,
        [entity_id],
    ).fetchall()
    return [{"season": row["season"], **_stats(row)} for row in rows]


def driver_constructor_history(conn: sqlite3.Connection, driver_id: int) -> list[dict]:
    """Which constructors a driver raced for, per season, with entry counts.

    A driver can appear for two constructors in one season (mid-season
    switch, reserve drives) -- that is represented as two rows, not merged.
    """
    rows = conn.execute(
        f"""
        SELECT ra.season, c.id AS constructor_id, c.name AS constructor_name, {_STATS_SELECT}
        FROM results r
        JOIN races ra        ON ra.id = r.race_id
        JOIN constructors c  ON c.id  = r.constructor_id
        WHERE r.driver_id = ?
        GROUP BY ra.season, c.id
        ORDER BY ra.season, entries DESC
        """,
        [driver_id],
    ).fetchall()
    return [
        {
            "season": row["season"],
            "constructor_id": row["constructor_id"],
            "constructor_name": row["constructor_name"],
            **_stats(row),
        }
        for row in rows
    ]


def constructor_driver_contribution(
    conn: sqlite3.Connection,
    constructor_id: int,
    season: int | None = None,
) -> list[dict]:
    """Each driver's share of a constructor's entries, wins and podiums.

    Shares are of *this constructor's* totals over the selected span, so they
    sum to 1.0 (entries always; wins/podiums only when the team has any).
    Share of points is not offered -- see the module docstring.
    """
    where, params = ("" if season is None else " AND ra.season = ?"), ([] if season is None else [season])
    rows = conn.execute(
        f"""
        SELECT d.id AS driver_id, d.name AS driver_name, {_STATS_SELECT}
        FROM results r
        JOIN races ra   ON ra.id = r.race_id
        JOIN drivers d  ON d.id  = r.driver_id
        WHERE r.constructor_id = ?{where}
        GROUP BY d.id
        ORDER BY wins DESC, entries DESC, d.name
        """,
        [constructor_id, *params],
    ).fetchall()

    total_entries = sum(row["entries"] for row in rows)
    total_wins = sum(row["wins"] for row in rows)
    total_podiums = sum(row["podiums"] for row in rows)

    def share(value: int, total: int) -> float | None:
        return value / total if total else None

    return [
        {
            "driver_id": row["driver_id"],
            "driver_name": row["driver_name"],
            **_stats(row),
            "entry_share": share(row["entries"], total_entries),
            "win_share": share(row["wins"], total_wins),
            "podium_share": share(row["podiums"], total_podiums),
        }
        for row in rows
    ]


# --------------------------------------------------------------------------
# Leaderboards
# --------------------------------------------------------------------------

# ORDER BY fragments. `name` MUST stay qualified as e.name: the query joins
# `races`, which also has a `name` column, so a bare `name` is ambiguous and
# SQLite rejects the whole statement.
_LEADERBOARD_SORTS = {
    "wins": "wins DESC, podiums DESC, entries DESC",
    "podiums": "podiums DESC, wins DESC, entries DESC",
    "entries": "entries DESC, wins DESC",
    "win_rate": "CAST(wins AS REAL) / entries DESC, wins DESC",
    "podium_rate": "CAST(podiums AS REAL) / entries DESC, podiums DESC",
    "avg_position": "avg_position ASC",
    "name": "e.name ASC",
}


def leaderboard(
    conn: sqlite3.Connection,
    entity: str,
    sort: str = "wins",
    search: str | None = None,
    season_from: int | None = None,
    season_to: int | None = None,
    circuit_id: int | None = None,
    constructor_id: int | None = None,
    min_entries: int = 1,
    limit: int = 50,
    offset: int = 0,
    count_total: bool = True,
) -> dict:
    """Paginated, server-side-filtered ranking of drivers or constructors.

    Filtering and sorting happen in SQL so the client never downloads the
    full result set to sort it locally. `sort` is resolved through a fixed
    map -- the ORDER BY clause can only ever be one of the known strings.

    `count_total=False` skips the COUNT over the grouped set, which costs about
    as much as the page query itself. Callers that only want the top row (the
    records page runs seven of these) do not need a total.
    """
    table, id_column = {
        "driver": ("drivers", "r.driver_id"),
        "constructor": ("constructors", "r.constructor_id"),
    }[entity]
    order = _LEADERBOARD_SORTS[sort]

    where, params = _season_filter(season_from, season_to)
    if circuit_id is not None:
        where += " AND ra.circuit_id = ?"
        params.append(circuit_id)
    if constructor_id is not None and entity == "driver":
        where += " AND r.constructor_id = ?"
        params.append(constructor_id)
    if search:
        where += " AND e.name LIKE ? ESCAPE '\\'"
        params.append(like_pattern(search))

    base = f"""
        SELECT e.id, e.name, {_STATS_SELECT}
        FROM results r
        JOIN races ra   ON ra.id = r.race_id
        JOIN {table} e  ON e.id  = {id_column}
        WHERE 1=1{where}
        GROUP BY e.id
        HAVING entries >= ?
    """
    query_params = [*params, min_entries]

    rows = conn.execute(
        f"{base} ORDER BY {order} LIMIT ? OFFSET ?", [*query_params, limit, offset]
    ).fetchall()
    total = (
        conn.execute(f"SELECT COUNT(*) FROM ({base})", query_params).fetchone()[0]
        if count_total
        else len(rows)
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [{"id": row["id"], "name": row["name"], **_stats(row)} for row in rows],
    }


# --------------------------------------------------------------------------
# Season / race views
# --------------------------------------------------------------------------

def season_summary(conn: sqlite3.Connection, season: int) -> dict | None:
    """Season-level totals plus the wins-based driver and constructor tables.

    IMPORTANT: these are *not* championship standings. The source has no
    points column, so drivers and constructors are ranked by wins, then
    podiums, then average classified position. A season's actual champion may
    differ. Every consumer must label this as a wins-based ranking.
    """
    race_count = conn.execute("SELECT COUNT(*) FROM races WHERE season = ?", [season]).fetchone()[0]
    if not race_count:
        return None

    def table(entity: str) -> list[dict]:
        return leaderboard(conn, entity, sort="wins", season_from=season, season_to=season, limit=1000)["items"]

    return {
        "season": season,
        "races": race_count,
        "entries": conn.execute(
            "SELECT COUNT(*) FROM results r JOIN races ra ON ra.id = r.race_id WHERE ra.season = ?", [season]
        ).fetchone()[0],
        "ranking_basis": "wins",
        "drivers": table("driver"),
        "constructors": table("constructor"),
    }


def race_results(conn: sqlite3.Connection, race_id: int) -> list[dict]:
    """Full classification for one race, in classification order."""
    rows = conn.execute(
        """
        SELECT r.position, d.id AS driver_id, d.name AS driver_name,
               c.id AS constructor_id, c.name AS constructor_name
        FROM results r
        JOIN drivers d       ON d.id = r.driver_id
        JOIN constructors c  ON c.id = r.constructor_id
        WHERE r.race_id = ?
        ORDER BY r.position
        """,
        [race_id],
    ).fetchall()
    return [dict(row) for row in rows]


def season_rounds(conn: sqlite3.Connection, season: int) -> list[dict]:
    """Every round of a season with its winner, in calendar order.

    One query rather than one per round: the round-by-round strip on the home
    page needs all 24, and 24 requests to render one panel is the N+1 this
    exists to avoid.

    LEFT JOIN on the winner, not INNER: a race with no position-1 row in the
    source must still appear in the calendar with a null winner, otherwise the
    strip would silently show a short season. Every round in the current
    dataset does have a winner; the join does not assume it.
    """
    rows = conn.execute(
        """
        SELECT ra.id AS race_id, ra.round, ra.name AS race_name, ra.date,
               ci.name AS circuit_name, ci.slug AS circuit_slug,
               d.id  AS winner_driver_id,      d.name AS winner_driver,
               c.id  AS winner_constructor_id, c.name AS winner_constructor
        FROM races ra
        JOIN circuits ci        ON ci.id = ra.circuit_id
        LEFT JOIN results r     ON r.race_id = ra.id AND r.position = 1
        LEFT JOIN drivers d     ON d.id = r.driver_id
        LEFT JOIN constructors c ON c.id = r.constructor_id
        WHERE ra.season = ?
        ORDER BY ra.round
        """,
        [season],
    ).fetchall()
    return [dict(row) for row in rows]


def circuit_winners(conn: sqlite3.Connection, circuit_id: int) -> list[dict]:
    """Every winner at a circuit, most recent first.

    Ordered by round as well as season: a circuit can host two races in one
    season (Silverstone 2020 ran the British and 70th Anniversary GPs; the Red
    Bull Ring ran Austrian and Styrian rounds in 2020 and 2021). Season alone
    leaves those pairs in undefined order.
    """
    rows = conn.execute(
        """
        SELECT ra.season, ra.id AS race_id, ra.name AS race_name,
               d.id AS driver_id, d.name AS driver_name,
               c.id AS constructor_id, c.name AS constructor_name
        FROM results r
        JOIN races ra        ON ra.id = r.race_id
        JOIN drivers d       ON d.id  = r.driver_id
        JOIN constructors c  ON c.id  = r.constructor_id
        WHERE ra.circuit_id = ? AND r.position = 1
        ORDER BY ra.season DESC, ra.round DESC
        """,
        [circuit_id],
    ).fetchall()
    return [dict(row) for row in rows]


# --------------------------------------------------------------------------
# Comparison
# --------------------------------------------------------------------------

def compare(conn: sqlite3.Connection, entity: str, left_id: int, right_id: int) -> dict:
    """Head-to-head between two entities of the same type.

    Reports the overlapping-seasons window alongside each career block. Two
    drivers whose careers barely overlap are not directly comparable on
    career totals, and the caller is given the numbers needed to say so
    rather than a single "winner" verdict.
    """
    left = entity_stats(conn, entity, left_id)
    right = entity_stats(conn, entity, right_id)

    def seasons(entity_id: int) -> set[int]:
        column = {"driver": "r.driver_id", "constructor": "r.constructor_id"}[entity]
        return {
            row[0]
            for row in conn.execute(
                f"SELECT DISTINCT ra.season FROM results r JOIN races ra ON ra.id = r.race_id WHERE {column} = ?",
                [entity_id],
            )
        }

    left_seasons, right_seasons = seasons(left_id), seasons(right_id)
    shared = sorted(left_seasons & right_seasons)

    result = {
        "left": left,
        "right": right,
        "shared_seasons": shared,
        "comparable": bool(shared) and left["rates_reliable"] and right["rates_reliable"],
    }
    if shared:
        window = (min(shared), max(shared))
        result["left_shared"] = entity_stats(conn, entity, left_id, *window)
        result["right_shared"] = entity_stats(conn, entity, right_id, *window)
    return result


# --------------------------------------------------------------------------
# Records, insights, dataset summary
# --------------------------------------------------------------------------

def records(conn: sqlite3.Connection) -> list[dict]:
    """Dataset-wide records. Every entry states its own methodology.

    Rate-based records apply MIN_ENTRIES_FOR_RATES so a one-race driver with
    a single win cannot top the win-rate table.
    """
    def top(entity: str, sort: str, min_entries: int = 1) -> dict | None:
        # count_total=False: only the leading row is needed, and the COUNT over
        # the grouped set roughly doubles the cost of each of these calls.
        page = leaderboard(conn, entity, sort=sort, min_entries=min_entries, limit=1, count_total=False)
        return page["items"][0] if page["items"] else None

    best_season = conn.execute(
        """
        SELECT d.name, ra.season, COUNT(*) AS wins
        FROM results r
        JOIN races ra   ON ra.id = r.race_id
        JOIN drivers d  ON d.id  = r.driver_id
        WHERE r.position = 1
        GROUP BY d.id, ra.season
        ORDER BY wins DESC, ra.season
        LIMIT 1
        """
    ).fetchone()

    circuit_king = conn.execute(
        """
        SELECT d.name, ci.name AS circuit, COUNT(*) AS wins
        FROM results r
        JOIN races ra    ON ra.id = r.race_id
        JOIN circuits ci ON ci.id = ra.circuit_id
        JOIN drivers d   ON d.id  = r.driver_id
        WHERE r.position = 1
        GROUP BY d.id, ci.id
        ORDER BY wins DESC, d.name
        LIMIT 1
        """
    ).fetchone()

    entries = [
        ("Most wins (driver)", top("driver", "wins"), "wins", "Race wins, 2000-2025."),
        ("Most podiums (driver)", top("driver", "podiums"), "podiums", "Classified P1-P3, 2000-2025."),
        ("Most entries (driver)", top("driver", "entries"), "entries", "Race classifications, 2000-2025."),
        (
            "Highest win rate (driver)",
            top("driver", "win_rate", MIN_ENTRIES_FOR_RATES),
            "win_rate",
            f"wins / entries, minimum {MIN_ENTRIES_FOR_RATES} entries.",
        ),
        (
            "Best average classified position (driver)",
            top("driver", "avg_position", MIN_ENTRIES_FOR_RATES),
            "avg_classified_position",
            f"Mean classification incl. retirements, minimum {MIN_ENTRIES_FOR_RATES} entries.",
        ),
        ("Most wins (constructor)", top("constructor", "wins"), "wins", "Race wins, 2000-2025."),
        ("Most podiums (constructor)", top("constructor", "podiums"), "podiums", "Classified P1-P3, 2000-2025."),
    ]

    out = [
        {"record": label, "entity": item["name"], "value": item[field], "methodology": note}
        for label, item, field, note in entries
        if item
    ]
    if best_season:
        out.append(
            {
                "record": "Most wins in a single season (driver)",
                "entity": best_season["name"],
                "value": best_season["wins"],
                "context": str(best_season["season"]),
                "methodology": "Wins within one season. Season lengths vary (16-24 races), so totals are not era-normalised.",
            }
        )
    if circuit_king:
        out.append(
            {
                "record": "Most wins at one circuit (driver)",
                "entity": circuit_king["name"],
                "value": circuit_king["wins"],
                "context": circuit_king["circuit"],
                "methodology": "Wins at a single circuit across 2000-2025. Circuits appear in different numbers of seasons.",
            }
        )
    return out


def insights(conn: sqlite3.Connection, limit: int = 6) -> list[dict]:
    """Calculated observations, each traceable to a query in this module.

    Wording is descriptive only. These state what the data records, never why
    -- the dataset contains no causal variables. Generators live in
    `_INSIGHT_GENERATORS`; each returns zero or more insights and states the
    calculation behind them in `basis`.
    """
    out: list[dict] = []
    for generate in _INSIGHT_GENERATORS:
        # Stop once the caller has enough. The generators are ordered by
        # analytical value, and the two most expensive (teammate dominance,
        # circuit strength) run full self-joins -- the home page asks for
        # three insights and would otherwise pay for all six.
        if len(out) >= limit:
            break
        try:
            out.extend(generate(conn))
        except sqlite3.Error:
            # One failing generator must not blank the whole page, but a
            # silent skip would hide a broken query indefinitely -- so the
            # failure is logged with its generator name.
            logging.getLogger(__name__).exception("Insight generator %s failed", generate.__name__)
    return out[:limit]


def _insight_period_leaders(conn: sqlite3.Connection) -> list[dict]:
    """Leading race-winner of each decade."""
    out: list[dict] = []
    decades = conn.execute(
        """
        SELECT (ra.season / 10) * 10 AS decade, d.name, COUNT(*) AS wins
        FROM results r
        JOIN races ra   ON ra.id = r.race_id
        JOIN drivers d  ON d.id  = r.driver_id
        WHERE r.position = 1
        GROUP BY decade, d.id
        ORDER BY decade, wins DESC
        """
    ).fetchall()
    seen: set[int] = set()
    for row in decades:
        if row["decade"] in seen:
            continue
        seen.add(row["decade"])
        out.append(
            {
                "kind": "period_leader",
                "headline": f"{row['name']} led the {row['decade']}s on race wins",
                "detail": f"{row['wins']} wins in seasons {row['decade']}-{min(row['decade'] + 9, 2025)}.",
                "basis": "COUNT(position = 1) grouped by decade and driver.",
            }
        )

    return out


def _insight_season_swings(conn: sqlite3.Connection) -> list[dict]:
    """Largest year-on-year change in a constructor's win count."""
    out: list[dict] = []
    swings = conn.execute(
        """
        WITH season_wins AS (
            SELECT c.id, c.name, ra.season, SUM(CASE WHEN r.position = 1 THEN 1 ELSE 0 END) AS wins
            FROM results r
            JOIN races ra       ON ra.id = r.race_id
            JOIN constructors c ON c.id  = r.constructor_id
            GROUP BY c.id, ra.season
        )
        SELECT a.name, a.season AS to_season, a.wins AS to_wins, b.wins AS from_wins
        FROM season_wins a JOIN season_wins b ON a.id = b.id AND a.season = b.season + 1
        ORDER BY ABS(a.wins - b.wins) DESC
        LIMIT 3
        """
    ).fetchall()
    for row in swings:
        direction = "gained" if row["to_wins"] > row["from_wins"] else "lost"
        out.append(
            {
                "kind": "season_swing",
                "headline": f"{row['name']} {direction} {abs(row['to_wins'] - row['from_wins'])} wins into {row['to_season']}",
                "detail": f"{row['from_wins']} wins in {row['to_season'] - 1}, {row['to_wins']} in {row['to_season']}.",
                "basis": "Year-on-year change in wins per constructor. Describes the change only; the dataset holds no explanatory variables.",
            }
        )
    return out


def _insight_teammate_dominance(conn: sqlite3.Connection) -> list[dict]:
    """Most one-sided teammate records over a meaningful shared sample.

    Teammate comparison is the closest this dataset gets to controlling for
    car performance, which makes it the most analytically valuable insight
    available -- but it still measures classification, not pace.
    """
    from .advanced import MIN_SHARED_RACES

    rows = conn.execute(
        """
        SELECT me.driver_id, d1.name AS driver, mate.driver_id AS mate_id, d2.name AS mate,
               co.name AS team, COUNT(*) AS shared,
               SUM(CASE WHEN me.position < mate.position THEN 1 ELSE 0 END) AS ahead
        FROM results me
        JOIN results mate ON mate.race_id = me.race_id
                         AND mate.constructor_id = me.constructor_id
                         AND mate.driver_id != me.driver_id
        JOIN drivers d1       ON d1.id = me.driver_id
        JOIN drivers d2       ON d2.id = mate.driver_id
        JOIN constructors co  ON co.id = me.constructor_id
        GROUP BY me.driver_id, mate.driver_id, me.constructor_id
        HAVING shared >= ?
        ORDER BY CAST(ahead AS REAL) / shared DESC, shared DESC
        LIMIT 2
        """,
        [max(MIN_SHARED_RACES, 15)],
    ).fetchall()
    return [
        {
            "kind": "teammate",
            "headline": f"{row['driver']} was classified ahead of {row['mate']} in {row['ahead']} of {row['shared']} shared races",
            "detail": f"At {row['team']} — {row['ahead'] / row['shared'] * 100:.0f}% of races the pair both started.",
            "basis": (
                "Races where both drivers started for the same constructor. Machinery is held roughly "
                "constant; retirements count as losses because the dataset has no finishing status."
            ),
        }
        for row in rows
    ]


def _insight_consistency(conn: sqlite3.Connection) -> list[dict]:
    """Drivers whose mean and median classification diverge most.

    A mean well above the median indicates a record punctuated by occasional
    very poor classifications -- typically retirements -- rather than
    consistently weaker running.
    """
    import statistics
    from collections import defaultdict

    from .advanced import MIN_ENTRIES_FOR_RATES

    threshold = max(MIN_ENTRIES_FOR_RATES, 50)

    # One query for every candidate's positions, grouped in Python. Calling
    # distribution() per driver issued 40 separate queries and dominated the
    # runtime of this endpoint.
    rows = conn.execute(
        """
        SELECT r.driver_id, d.name, r.position
        FROM results r JOIN drivers d ON d.id = r.driver_id
        WHERE r.driver_id IN (
            SELECT driver_id FROM results GROUP BY driver_id HAVING COUNT(*) >= ?
        )
        """,
        [threshold],
    ).fetchall()

    positions: dict[int, list[int]] = defaultdict(list)
    names: dict[int, str] = {}
    for row in rows:
        positions[row["driver_id"]].append(row["position"])
        names[row["driver_id"]] = row["name"]

    scored = []
    for driver_id, values in positions.items():
        mean = statistics.fmean(values)
        median = statistics.median(values)
        scored.append((mean - median, names[driver_id], mean, median, len(values)))
    scored.sort(reverse=True)

    return [
        {
            "kind": "consistency",
            "headline": f"{name} averaged P{mean:.1f} but had a median of P{median:.0f}",
            "detail": (
                f"Across {entries} entries. The gap of {gap:.1f} positions indicates a minority of much "
                f"poorer classifications pulling the mean up."
            ),
            "basis": (
                "mean(position) minus median(position) over a driver's entries. Describes distribution "
                "shape only; the dataset cannot attribute the poor classifications to a cause."
            ),
        }
        for gap, name, mean, median, entries in scored[:2]
    ]


def _insight_circuit_strength(conn: sqlite3.Connection) -> list[dict]:
    """Largest gap between a driver's record at one circuit and their career norm."""
    from .advanced import MIN_APPEARANCES_FOR_SPECIALISM

    rows = conn.execute(
        """
        SELECT d.name AS driver, ci.name AS circuit, COUNT(*) AS appearances,
               AVG(CAST(r.position AS REAL)) AS here,
               (SELECT AVG(CAST(r2.position AS REAL)) FROM results r2 WHERE r2.driver_id = d.id) AS career
        FROM results r
        JOIN races ra    ON ra.id = r.race_id
        JOIN circuits ci ON ci.id = ra.circuit_id
        JOIN drivers d   ON d.id  = r.driver_id
        GROUP BY d.id, ci.id
        HAVING appearances >= ?
        ORDER BY (career - here) DESC
        LIMIT 2
        """,
        [max(MIN_APPEARANCES_FOR_SPECIALISM, 6)],
    ).fetchall()
    return [
        {
            "kind": "circuit_strength",
            "headline": f"{row['driver']} averaged {row['career'] - row['here']:.1f} positions better at {row['circuit']}",
            "detail": (
                f"P{row['here']:.1f} across {row['appearances']} appearances there, against a career "
                f"average of P{row['career']:.1f}."
            ),
            "basis": (
                "Career average classified position minus the average at that circuit, over at least "
                f"{max(MIN_APPEARANCES_FOR_SPECIALISM, 6)} appearances. Confounded with career timing: a circuit visited "
                "mainly during a driver's strongest seasons will show a positive gap regardless of any "
                "track-specific ability."
            ),
        }
        for row in rows
    ]


def _insight_dominant_seasons(conn: sqlite3.Connection) -> list[dict]:
    """Seasons with the highest share of races won by one driver."""
    rows = conn.execute(
        """
        WITH per_season AS (SELECT season, COUNT(*) AS races FROM races GROUP BY season),
             driver_wins AS (
               SELECT ra.season, d.name, COUNT(*) AS wins
               FROM results r JOIN races ra ON ra.id = r.race_id JOIN drivers d ON d.id = r.driver_id
               WHERE r.position = 1 GROUP BY ra.season, d.id
             )
        SELECT w.season, w.name, w.wins, p.races, CAST(w.wins AS REAL) / p.races AS share
        FROM driver_wins w JOIN per_season p ON p.season = w.season
        ORDER BY share DESC LIMIT 2
        """
    ).fetchall()
    return [
        {
            "kind": "dominance",
            "headline": f"{row['name']} won {row['share'] * 100:.0f}% of the {row['season']} season",
            "detail": f"{row['wins']} wins from {row['races']} races.",
            "basis": (
                "wins / races held that season, so calendar length is normalised. Points-based "
                "dominance is not computed — the dataset has no points column."
            ),
        }
        for row in rows
    ]


#: Insight generators, run in order until `limit` is reached. Each is
#: independent, so adding a category means adding one function here.
_INSIGHT_GENERATORS = (
    _insight_teammate_dominance,
    _insight_dominant_seasons,
    _insight_consistency,
    _insight_circuit_strength,
    _insight_period_leaders,
    _insight_season_swings,
)


def dataset_summary(conn: sqlite3.Connection) -> dict:
    """Powers the Dataset Explorer. Schema shape and coverage only -- no
    filesystem paths, connection strings or other server internals."""
    tables = []
    for (name,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ):
        columns = conn.execute(f"PRAGMA table_info({name})").fetchall()
        tables.append(
            {
                "name": name,
                "rows": conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0],
                "columns": [{"name": c["name"], "type": c["type"], "nullable": not c["notnull"]} for c in columns],
            }
        )

    coverage = conn.execute("SELECT MIN(season) AS lo, MAX(season) AS hi FROM races").fetchone()
    return {
        "source": "results.csv (Ergast-derived race classifications)",
        "season_from": coverage["lo"],
        "season_to": coverage["hi"],
        "tables": tables,
        "available_fields": ["season", "round", "race_name", "date", "position", "driver", "constructor"],
        "unavailable_fields": [
            "grid position / qualifying",
            "fastest lap",
            "finishing status (DNF / DNS / DSQ)",
            "championship points",
            "lap times / sector times",
            "pit stops",
            "tyre compounds",
            "telemetry",
            "car specifications",
        ],
        # Rendered verbatim as text in the UI, so no markdown: backticks and
        # "--" would reach the reader as literal characters.
        "known_issues": [
            "2002 French Grand Prix carries 20 classification rows but runs to P22 — two rows absent upstream.",
            "The position column is classification order, not finishing status: retirements are ranked, not flagged.",
            "Circuit identity is derived from race_name via a curated season-aware map (backend/etl/circuit_map.csv).",
            "15 of 39 circuits ship no track-map SVG and render a map-unavailable state.",
        ],
    }


def search(conn: sqlite3.Connection, query: str, limit: int = 8) -> list[dict]:
    """Global search across drivers, constructors, circuits and seasons.

    Ranked by match position (prefix matches first), then by wins so the more
    prominent entity of two equal-quality matches surfaces first.
    """
    text = query.strip()
    if not text:
        return []
    pattern = like_pattern(text)

    out: list[dict] = []
    for kind, table, extra in [
        ("driver", "drivers", "SUM(CASE WHEN r.position = 1 THEN 1 ELSE 0 END)"),
        ("constructor", "constructors", "SUM(CASE WHEN r.position = 1 THEN 1 ELSE 0 END)"),
    ]:
        join = "r.driver_id" if kind == "driver" else "r.constructor_id"
        out += [
            {"kind": kind, "id": row["id"], "label": row["name"], "sublabel": f"{row['wins']} wins"}
            for row in conn.execute(
                f"""
                SELECT e.id, e.name, {extra} AS wins
                FROM {table} e LEFT JOIN results r ON {join} = e.id
                WHERE e.name LIKE ? ESCAPE '\\'
                GROUP BY e.id
                ORDER BY INSTR(LOWER(e.name), LOWER(?)), wins DESC
                LIMIT ?
                """,
                [pattern, text, limit],
            )
        ]

    out += [
        {"kind": "circuit", "id": row["id"], "label": row["name"], "sublabel": row["country"]}
        for row in conn.execute(
            "SELECT id, name, country FROM circuits WHERE name LIKE ? ESCAPE '\\' OR country LIKE ? ESCAPE '\\' "
            "ORDER BY INSTR(LOWER(name), LOWER(?)), name LIMIT ?",
            [pattern, pattern, text, limit],
        )
    ]

    if text.isdigit():
        out += [
            {"kind": "season", "id": row["season"], "label": str(row["season"]), "sublabel": f"{row['n']} races"}
            for row in conn.execute(
                "SELECT season, COUNT(*) AS n FROM races WHERE CAST(season AS TEXT) LIKE ? "
                "GROUP BY season ORDER BY season LIMIT ?",
                [f"{text}%", limit],
            )
        ]

    return out[: limit * 2]
