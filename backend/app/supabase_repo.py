"""Supabase-backed data access. On the request path when F1_BACKEND=supabase.

STATUS
------
This module now serves requests. With F1_BACKEND unset the API reads SQLite,
as a fresh clone must; with F1_BACKEND=supabase the routers dispatch here for
every endpoint in backends.SUPABASE_CAPABILITIES, and raise rather than fall
back for anything else.

    React -> FastAPI -> SQLite    (default)
    React -> FastAPI -> Supabase  (F1_BACKEND=supabase)

The two must be indistinguishable from outside. The adapters at the foot of
this file exist for that reason alone: the views name things as the database
does (`display_name`, `driver_slug`) and the API contract names them as
analytics.py does (`name`, `slug`). Without the translation, switching
backends would change the shape of every payload -- which is not a backend
switch but a second, incompatible API sharing a URL.

WHAT PROVES IT
--------------
Three suites, each answering a different question:

  * test_store_parity.py    -- do the two DATABASES hold the same rows?
  * test_backend_parity.py  -- do the two IMPLEMENTATIONS compute the same
                               numbers from them?
  * test_api_payload_parity.py -- does the HTTP response match, field for
                               field, through the real app?

All three skip without credentials, and a skip is missing coverage rather
than a pass.

This docstring previously opened "NOT WIRED INTO THE RUNNING API", which was
true when written and stopped being true here.

READ-ONLY BY DESIGN
-------------------
Only the publishable/anon key is used here, and RLS grants that key SELECT
only. The API physically cannot write, verified by the security tests. The
service-role key is never imported, never logged and never sent to the browser;
ingestion is a separate server-side script.

WHY POSTGREST RATHER THAN A DIRECT CONNECTION
---------------------------------------------
PostgREST needs only the project URL and publishable key, both safe to hold in
application config, whereas a direct psycopg connection needs the database
password. Fewer secrets in more places is the wrong trade for a read-only
analytical API.

ANALYTICS LIVE IN THE DATABASE
------------------------------
Every aggregate is a view (v_driver_career_stats, v_teammate_comparisons, ...),
so this module selects and filters -- it does not calculate. That keeps the
"one definition per metric" rule intact across both backends.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# Imported for its side effect: populates os.environ from .env before the
# constants below are read. These are module-level, so load order matters.
from . import env as _env  # noqa: F401

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY", "")

# Timeout so a hung upstream surfaces as a clean 503 rather than a stuck worker.
TIMEOUT_SECONDS = 10


class SupabaseError(RuntimeError):
    """Upstream failure. Callers translate this into a 503."""


def configured() -> bool:
    """True when Supabase credentials are present.

    Read by this module's tests to decide whether to run or skip. It is *not*
    a runtime backend switch: no router consults it, so setting the variables
    does not move the API off SQLite. Both stores are produced by the same
    pipeline from the same CSV, so they are one source of truth with two
    materialisations -- not two competing datasets.
    """
    return bool(SUPABASE_URL and SUPABASE_KEY)


def query(
    resource: str,
    select: str = "*",
    filters: dict[str, str] | None = None,
    order: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
    exact_count: bool = False,
) -> tuple[list[dict[str, Any]], int | None]:
    """Run a PostgREST query. Returns (rows, total) -- total only when asked.

    Filters use PostgREST operator syntax (`eq.5`, `gte.2010`, `ilike.*ham*`)
    and are URL-encoded here; no value is ever concatenated into a raw SQL
    string, and the anon role cannot reach anything RLS does not allow.
    """
    if not configured():
        raise SupabaseError("Supabase is not configured")

    params: dict[str, str] = {"select": select}
    params.update(filters or {})
    if order:
        params["order"] = order
    if limit is not None:
        params["limit"] = str(limit)
    if offset:
        params["offset"] = str(offset)

    url = f"{SUPABASE_URL}/rest/v1/{resource}?{urllib.parse.urlencode(params)}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept": "application/json",
    }
    # `count=exact` returns the pre-pagination total in Content-Range, which is
    # what paginated list endpoints need and what avoids a second round trip.
    if exact_count:
        headers["Prefer"] = "count=exact"

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            rows = json.loads(response.read().decode("utf-8"))
            total = None
            if exact_count:
                content_range = response.headers.get("Content-Range", "")
                if "/" in content_range:
                    tail = content_range.rsplit("/", 1)[1]
                    total = int(tail) if tail.isdigit() else None
            return rows, total
    except urllib.error.HTTPError as error:
        # Upstream detail goes to the server log, never to the client.
        raise SupabaseError(f"Supabase returned {error.code}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise SupabaseError("Supabase unreachable") from error


def health() -> dict:
    """Coverage and entity counts, read from the analytical views."""
    seasons, _ = query("v_season_stats", select="season,races")
    counts = {}
    for name, resource in (
        ("drivers", "drivers"),
        ("constructors", "constructors"),
        ("circuits", "circuits"),
        ("results", "results"),
    ):
        _, total = query(resource, select="id", limit=1, exact_count=True)
        counts[name] = total or 0

    years = [row["season"] for row in seasons]
    return {
        "status": "ok",
        "backend": "supabase",
        "season_from": min(years) if years else None,
        "season_to": max(years) if years else None,
        "seasons": len(years),
        "races": sum(row["races"] for row in seasons),
        "results": counts["results"],
        "drivers": counts["drivers"],
        "constructors": counts["constructors"],
        "circuits": counts["circuits"],
        "live_data": False,
    }


def driver_career_stats(driver_id: int) -> dict | None:
    rows, _ = query("v_driver_career_stats", filters={"driver_id": f"eq.{driver_id}"})
    return rows[0] if rows else None


def teammate_records(driver_id: int) -> list[dict]:
    rows, _ = query(
        "v_teammate_comparisons",
        filters={"driver_id": f"eq.{driver_id}"},
        order="shared_races.desc",
    )
    return rows


def records() -> list[dict]:
    rows, _ = query("v_records")
    return rows


def metric_definitions() -> list[dict]:
    rows, _ = query("metric_definitions", filters={"active": "eq.true"}, order="metric_key")
    return rows

# ---------------------------------------------------------------------------
# View-backed endpoints.
#
# Every function here selects and filters; none of them calculate. The
# aggregate is the view's job, which is what keeps a metric defined once per
# store rather than once per caller.
#
# All of them take a `slug`, not an integer id. Integer ids in this database
# come from a serial sequence and do not match the SQLite build's, so an id
# accepted here would address a different entity there -- the exact bug the
# slug was introduced to remove.
# ---------------------------------------------------------------------------

def _one(resource: str, filters: dict[str, str], order: str | None = None) -> dict | None:
    rows, _ = query(resource, filters=filters, order=order, limit=1)
    return rows[0] if rows else None


def driver_by_slug(slug: str) -> dict | None:
    """Career stat block for one driver. None when the slug is unknown."""
    return _one("v_driver_career_stats", {"driver_slug": f"eq.{slug}"})


def constructor_by_slug(slug: str) -> dict | None:
    return _one("v_constructor_career_stats", {"constructor_slug": f"eq.{slug}"})


def circuit_by_slug(slug: str) -> dict | None:
    return _one("v_circuit_stats", {"circuit_key": f"eq.{slug}"})


def driver_seasons(slug: str) -> list[dict]:
    rows, _ = query(
        "v_driver_season_stats", filters={"driver_slug": f"eq.{slug}"}, order="season"
    )
    return rows


def constructor_seasons(slug: str) -> list[dict]:
    rows, _ = query(
        "v_constructor_season_stats",
        filters={"constructor_slug": f"eq.{slug}"},
        order="season",
    )
    return rows


def driver_circuits(slug: str) -> list[dict]:
    rows, _ = query(
        "v_driver_circuit_stats",
        filters={"driver_slug": f"eq.{slug}"},
        order="appearances.desc",
    )
    return rows


def driver_qualifying(slug: str) -> dict | None:
    """Qualifying summary.

    `qualifying_p1` is counted qualifying firsts, and is deliberately not
    called "poles": the two differ, and the field name says what was measured.
    """
    return _one("v_driver_qualifying_stats", {"driver_slug": f"eq.{slug}"})


def constructor_drivers(slug: str) -> list[dict]:
    rows, _ = query(
        "v_constructor_driver_contribution",
        filters={"constructor_slug": f"eq.{slug}"},
        order="wins.desc",
    )
    return rows


def standings(season: int, entity: str = "driver") -> list[dict]:
    """Championship standings for one season.

    ORDERED EXPLICITLY, NOT BY points_rank
    --------------------------------------
    `points_rank` assigns the same rank to drivers on equal points -- correct
    as a rank, but it leaves the order *within* a tie undefined, so the same
    query could return two tied drivers either way round. Sorting by it made
    this disagree with the SQLite implementation on three of four sampled
    seasons: in 2000, Wurz and de la Rosa both finished on 2 points and both
    stores ranked them 15th, but listed them in different orders.

    The tiebreak here matches analytics.standings exactly -- points, then
    wins, then podiums, then name -- so both backends produce one stable
    order.

    That tiebreak is NOT the official countback (most wins, then most second
    places, and so on down). Drivers level on points are ordered here for
    determinism, not adjudicated; the standings do not claim to resolve a real
    championship tie.
    """
    if entity == "driver":
        resource, name_column = "v_driver_standings", "display_name"
    else:
        resource, name_column = "v_constructor_standings", "constructor_name"
    rows, _ = query(
        resource,
        filters={"season": f"eq.{season}"},
        order=f"points.desc,wins.desc,podiums.desc,{name_column}.asc",
    )
    return rows


def seasons() -> list[dict]:
    rows, _ = query("v_season_stats", order="season")
    return rows


def season(year: int) -> dict | None:
    return _one("v_season_stats", {"season": f"eq.{year}"})


def circuits() -> list[dict]:
    rows, _ = query("v_circuit_stats", order="circuit_name")
    return rows


def races(season_year: int | None = None, limit: int = 50, offset: int = 0) -> tuple[list[dict], int | None]:
    """Race classifications, optionally one season, paginated.

    Returns the pre-pagination total alongside the page so a list endpoint
    does not need a second round trip to report it.
    """
    filters = {} if season_year is None else {"season": f"eq.{season_year}"}
    return query(
        "v_race_results",
        filters=filters,
        order="season,round,position",
        limit=limit,
        offset=offset,
        exact_count=True,
    )


def race(season_year: int, round_: int) -> list[dict]:
    """Full classification for one race, addressed by its natural key.

    (season, round) rather than a race id, for the same reason entities use
    slugs: race ids are store-local.
    """
    rows, _ = query(
        "v_race_results",
        filters={"season": f"eq.{season_year}", "round": f"eq.{round_}"},
        order="position",
    )
    return rows


_LEADERBOARD_SORTS = {
    "wins": "wins.desc",
    "podiums": "podiums.desc",
    "entries": "entries.desc",
    "win_rate": "win_rate.desc",
    "podium_rate": "podium_rate.desc",
    "avg_position": "avg_classified_position.asc",
    "name": None,  # resolved per entity below: the name column differs
    "points": "points.desc",
}


def leaderboard(
    entity: str = "driver",
    sort: str = "wins",
    limit: int = 50,
    offset: int = 0,
    min_entries: int = 1,
) -> tuple[list[dict], int | None]:
    """Ranked drivers or constructors, sorted and paginated in the database.

    `sort` is resolved through a fixed map, so the order clause can only ever
    be one of the known strings -- no caller-supplied text reaches the query.
    """
    if entity == "driver":
        resource, name_column = "v_driver_career_stats", "display_name"
    else:
        resource, name_column = "v_constructor_career_stats", "constructor_name"

    if sort not in _LEADERBOARD_SORTS:
        raise SupabaseError(f"unknown sort {sort!r}")
    order = _LEADERBOARD_SORTS[sort] or f"{name_column}.asc"

    return query(
        resource,
        filters={"entries": f"gte.{min_entries}"},
        order=order,
        limit=limit,
        offset=offset,
        exact_count=True,
    )


# ---------------------------------------------------------------------------
# Shape adapters.
#
# The views name things as the database does -- `display_name`, `driver_slug`,
# `avg_classified_position` -- and the API contract names them as
# analytics.py does. Without this translation, switching F1_BACKEND would
# change the shape of every payload, which is not a backend switch at all: it
# is a second, incompatible API that happens to share a URL.
#
# So these functions exist to make the two backends indistinguishable from
# outside. test_api_payload_parity.py asserts exactly that, field for field.
# ---------------------------------------------------------------------------

# Stat keys that analytics._stats() always emits. Listed explicitly rather
# than copied from whatever the view returned, so a view that grows a column
# cannot silently widen the API response.
_STAT_KEYS = (
    "entries", "wins", "podiums", "top5", "top10",
    "win_rate", "podium_rate", "top5_rate", "top10_rate",
    "avg_classified_position", "best_classified_position", "rates_reliable",
    "finishes", "dnfs", "dnf_rate", "points", "avg_grid", "avg_positions_gained",
)

# Rates arrive from Postgres as numeric strings over PostgREST's JSON. Left as
# strings they would serialise as `"0.276"` where SQLite gives `0.276`, and a
# client doing arithmetic would silently concatenate instead of adding.
_FLOAT_KEYS = frozenset({
    "win_rate", "podium_rate", "top5_rate", "top10_rate",
    "avg_classified_position", "dnf_rate", "points",
    "avg_grid", "avg_positions_gained",
})

MIN_ENTRIES_FOR_RATES = 10


def _number(value):
    """Coerce a PostgREST numeric to float, preserving None."""
    return None if value is None else float(value)


def _stat_block(row: dict | None) -> dict:
    """A view row rendered as the canonical stat block.

    Mirrors analytics._stats(), including its central rule: when there are no
    entries every rate is None rather than 0.0, so "no data" stays
    distinguishable from "genuinely zero".
    """
    if not row or not row.get("entries"):
        return {key: (0 if key in ("entries", "wins", "podiums", "top5", "top10") else None)
                for key in _STAT_KEYS} | {"rates_reliable": False}

    block = {}
    for key in _STAT_KEYS:
        value = row.get(key)
        block[key] = _number(value) if key in _FLOAT_KEYS else value

    # Derived here rather than read, because not every view computes it and a
    # missing key would serialise as null -- which reads as "unknown
    # reliability" instead of "below the threshold".
    block["rates_reliable"] = row["entries"] >= MIN_ENTRIES_FOR_RATES
    return block


def driver_detail(slug: str) -> dict | None:
    """Payload for /api/drivers/{id}, shaped exactly as the SQLite path."""
    row = driver_by_slug(slug)
    if row is None:
        return None
    return {
        "id": row["driver_id"],
        "slug": row["driver_slug"],
        "name": row["display_name"],
        # Descriptive columns live on the table, not the stats view.
        **_driver_descriptors(slug),
        "stats": _stat_block(row),
        "constructors": driver_constructor_history(slug),
    }


def _driver_descriptors(slug: str) -> dict:
    rows, _ = query(
        "drivers",
        select="nationality,date_of_birth,abbreviation,permanent_number",
        filters={"slug": f"eq.{slug}"},
        limit=1,
    )
    row = rows[0] if rows else {}
    return {
        "nationality": row.get("nationality"),
        "date_of_birth": row.get("date_of_birth"),
        "abbreviation": row.get("abbreviation"),
        "permanent_number": row.get("permanent_number"),
    }


def driver_constructor_history(slug: str) -> list[dict]:
    """Which constructors a driver raced for, and when.

    Read from driver_constructor_seasons, the derived table the ingestion
    maintains, so this is not a second definition of the relationship.
    """
    driver = driver_by_slug(slug)
    if driver is None:
        return []
    rows, _ = query(
        "driver_constructor_seasons",
        select="constructor_id,season_id,race_count",
        filters={"driver_id": f"eq.{driver['driver_id']}"},
    )
    return rows


def driver_seasons_detail(slug: str) -> list[dict]:
    """Season blocks shaped as analytics.by_season returns them."""
    return [
        {"season": row["season"], **_stat_block(row)}
        for row in driver_seasons(slug)
    ]


def constructor_detail(slug: str) -> dict | None:
    row = constructor_by_slug(slug)
    if row is None:
        return None
    rows, _ = query(
        "constructors", select="nationality", filters={"slug": f"eq.{slug}"}, limit=1
    )
    return {
        "id": row["constructor_id"],
        "slug": row["constructor_slug"],
        "name": row["constructor_name"],
        "nationality": rows[0].get("nationality") if rows else None,
        "stats": _stat_block(row),
        "seasons": [
            {"season": s["season"], **_stat_block(s)}
            for s in constructor_seasons(slug)
        ],
    }


def standings_detail(season_year: int, entity: str = "driver") -> list[dict]:
    """Standings shaped as analytics.standings returns them."""
    name_key = "display_name" if entity == "driver" else "constructor_name"
    slug_key = "driver_slug" if entity == "driver" else "constructor_slug"
    id_key = "driver_id" if entity == "driver" else "constructor_id"
    return [
        {
            "position": index,
            "id": row[id_key],
            "slug": row[slug_key],
            "name": row[name_key],
            "points": _number(row["points"]),
            "wins": row["wins"],
            "podiums": row["podiums"],
            # The standings views do not carry an entry count; it is not part
            # of the championship and is omitted rather than guessed.
            "entries": row.get("entries"),
        }
        for index, row in enumerate(standings(season_year, entity), start=1)
    ]


def leaderboard_page(
    entity: str = "driver",
    sort: str = "wins",
    limit: int = 50,
    offset: int = 0,
    min_entries: int = 1,
) -> dict:
    """A page of the ranking, shaped as analytics.leaderboard returns it."""
    rows, total = leaderboard(entity, sort, limit, offset, min_entries)
    id_key = "driver_id" if entity == "driver" else "constructor_id"
    slug_key = "driver_slug" if entity == "driver" else "constructor_slug"
    name_key = "display_name" if entity == "driver" else "constructor_name"
    return {
        "total": total or len(rows),
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": row[id_key],
                "slug": row[slug_key],
                "name": row[name_key],
                **_stat_block(row),
            }
            for row in rows
        ],
    }


# ---------------------------------------------------------------------------
# The last eight endpoints.
#
# These had no Postgres implementation, and the stated reason was sound: each
# was a metric defined only in analytics.py, so writing a view would have
# defined the same number twice.
#
# Migration 19 resolves that by MOVING the definitions rather than copying
# them. The aggregate now lives in the database; these functions select from
# it and reshape, exactly as every other function in this module does.
# ---------------------------------------------------------------------------

def search(term: str, limit: int = 8) -> list[dict]:
    """Cross-entity search, ranked the way the SQLite implementation ranks.

    PostgREST cannot join across tables in one request, which is why this had
    no implementation. `v_search_index` is one row per findable entity, so
    there is nothing left to join.

    Ranking happens here rather than in the view: prefix matches first, then
    by wins. That ordering depends on the search term, so it cannot be baked
    into a view -- and doing it in Python keeps it identical to the other
    backend rather than approximately similar.
    """
    text = (term or "").strip()
    if not text:
        return []

    # PostgREST's ilike wildcard is `*`, and `query` URL-encodes the value, so
    # no caller text reaches a SQL string.
    rows, _ = query("v_search_index", filters={"label": f"ilike.*{text}*"}, limit=200)

    lowered = text.lower()

    def rank(row: dict) -> tuple:
        position = row["search_key"].find(lowered)
        return (position if position >= 0 else 999, -(row["wins"] or 0))

    return [
        {
            "kind": row["kind"],
            "id": row["id"],
            "slug": row["slug"],
            "label": row["label"],
            "sublabel": "" if row["kind"] == "circuit" else f"{row['wins'] or 0} wins",
        }
        for row in sorted(rows, key=rank)[:limit]
    ]


def season_dominance(season_year: int) -> dict | None:
    """How concentrated one season was.

    win_share and points_share are NOT comparable with each other -- every
    scoring finisher dilutes points_share, so it is bounded far below 1.0
    however dominant the leader was. Both are returned; neither is a
    refinement of the other.
    """
    row = _one("v_season_dominance", {"season": f"eq.{season_year}"})
    if row is None:
        return None
    return {
        "season": row["season"],
        "races": row["races"],
        "distinct_driver_winners": row["distinct_driver_winners"],
        "top_driver_win_share": _number(row["top_driver_win_share"]),
        "top_driver_points_share": _number(row["top_driver_points_share"]),
    }


def era_summary() -> list[dict]:
    """Decade-level aggregates, with each decade's leading winners attached.

    Two queries rather than one: the top-three winners are a per-decade list,
    and PostgREST returns rows, not nested arrays. They are joined here so the
    payload matches the SQLite shape.
    """
    eras, _ = query("v_era_summary", order="decade")
    winners, _ = query("v_era_top_winners", order="decade,wins.desc")

    by_decade: dict[int, list[dict]] = {}
    for winner in winners:
        by_decade.setdefault(winner["decade"], []).append(
            {"name": winner["name"], "slug": winner["slug"], "wins": winner["wins"]}
        )

    return [
        {
            "decade": era["decade"],
            "label": era["label"],
            "seasons": era["seasons"],
            "races": era["races"],
            "drivers": era["drivers"],
            "constructors": era["constructors"],
            "largest_field": era["largest_field"],
            "top_winners": by_decade.get(era["decade"], []),
        }
        for era in eras
    ]


# Bucket LABELS are presentation and are safe to state here; the counts come
# from the view. The boundaries match advanced.distribution exactly.
_DISTRIBUTION_BUCKETS = (
    ("P1", "p1"),
    ("P2-P3", "p2_p3"),
    ("P4-P5", "p4_p5"),
    ("P6-P10", "p6_p10"),
    ("P11-P15", "p11_p15"),
    ("P16+", "p16_plus"),
)


def distribution(slug: str) -> dict:
    """Shape of a driver's finishing distribution.

    Median is nearest-rank, not interpolated: positions are ordinal, and an
    interpolated "position 7.5" is not a result anyone can finish in. Spread
    and IQR are NULL below five entries rather than computed, so a two-race
    driver does not get a confident-looking variance.
    """
    row = _one("v_driver_position_distribution", {"driver_slug": f"eq.{slug}"})
    if row is None or not row["entries"]:
        return {
            "entries": 0, "median": None, "stdev": None, "spread_reliable": False,
            "iqr": None, "worst": None, "histogram": [],
        }

    entries = row["entries"]
    return {
        "entries": entries,
        "median": _number(row["median"]),
        "stdev": _number(row["stdev"]),
        "spread_reliable": row["spread_reliable"],
        "iqr": _number(row["iqr"]),
        "worst": row["worst"],
        "histogram": [
            {"bucket": label, "count": row[column], "share": row[column] / entries}
            for label, column in _DISTRIBUTION_BUCKETS
        ],
    }


def compare(entity: str, left_slug: str, right_slug: str) -> dict:
    """Two entities side by side, plus the seasons they actually overlapped.

    `comparable` is False when they never raced in the same season. The stat
    blocks are still returned: withholding them would be less useful than
    showing them with the caveat attached.
    """
    fetch = driver_by_slug if entity == "driver" else constructor_by_slug
    left, right = fetch(left_slug), fetch(right_slug)
    if left is None or right is None:
        missing = left_slug if left is None else right_slug
        raise SupabaseError(f"unknown {entity}: {missing}")

    key = "driver_slug" if entity == "driver" else "constructor_slug"
    resource = "v_driver_season_stats" if entity == "driver" else "v_constructor_season_stats"
    left_seasons, _ = query(resource, select="season", filters={key: f"eq.{left_slug}"})
    right_seasons, _ = query(resource, select="season", filters={key: f"eq.{right_slug}"})

    shared = sorted({r["season"] for r in left_seasons} & {r["season"] for r in right_seasons})
    return {
        "left": _stat_block(left),
        "right": _stat_block(right),
        "shared_seasons": shared,
        "comparable": bool(shared),
    }


def cars() -> list[dict]:
    """Car specifications.

    Empty in both stores, and that is the honest answer rather than an
    omission: no source this project ingests supplies chassis or engine
    detail. The table exists so the absence is visible and countable.
    """
    rows, _ = query("cars")
    return rows


def dataset_availability() -> dict[str, int]:
    """Row count per dataset, read from the database.

    Counted, never listed. A hand-maintained record of what is missing becomes
    wrong the moment something is ingested, which has happened to this project
    more than once.
    """
    rows, _ = query("v_dataset_availability")
    return {row["dataset"]: row["rows_present"] for row in rows}
