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
import re
import ssl
import time
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# Imported for its side effect: populates os.environ from .env before the
# constants below are read. These are module-level, so load order matters.
from . import advanced
from . import analytics
from . import env as _env  # noqa: F401
from .analytics import round_half_up as _round_half_up

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


# ---------------------------------------------------------------------------
# A tiny in-process cache for lookups that are constant within a build.
#
# Every PostgREST call is a network round trip -- measured at roughly 270ms
# from here -- so an endpoint's latency is essentially its request count. The
# race weekend made ten calls and took 2.6s; two of those were re-fetching the
# entire driver and constructor name maps on every request.
#
# ONLY IDENTITY AND COVERAGE ARE CACHED. Names, slugs and the coverage
# boundaries change when the ETL runs, never between two reads of a live
# dataset. Results, standings and anything season-scoped are deliberately NOT
# cached: staling those is exactly the failure caching is supposed to avoid,
# and the current season is the part a reader is most likely to be looking at.
#
# The TTL bounds how long a process can disagree with a fresh ingestion. A
# restart clears it, and nothing here is shared between workers.
# Bounded retry for transient link failures. Three attempts spans roughly a
# second of backoff, which covers the blips observed without turning a real
# outage into a long hang -- TIMEOUT_SECONDS still bounds each attempt.
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.25

CACHE_TTL_SECONDS = 300
_cache: dict[str, tuple[float, Any]] = {}


def _cached(key: str, produce):
    """Return `produce()`, reusing a value less than CACHE_TTL_SECONDS old."""
    now = time.monotonic()
    hit = _cache.get(key)
    if hit is not None and now - hit[0] < CACHE_TTL_SECONDS:
        return hit[1]
    value = produce()
    _cache[key] = (now, value)
    return value


def clear_cache() -> None:
    """Drop every cached lookup. Called by tests that change the store."""
    _cache.clear()


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
    # RETRIED, because the failure this saw in practice is transient.
    #
    # Running the suite repeatedly turned up a run where 64 tests failed at
    # once on SSL and connection errors: the link to the hosted project had
    # dropped for a few seconds. Every one of them passed on the next run.
    # That is a network blip, not a defect in any of those tests -- and left
    # unhandled it is also a 503 served to a reader for the same reason.
    #
    # Only connection-level failures and 5xx are retried. A 4xx is a bad
    # request and will be exactly as bad the second time, so retrying it just
    # doubles the latency of a genuine error.
    last: Exception | None = None
    for attempt in range(RETRY_ATTEMPTS):
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
            if error.code == 416:
                # Range Not Satisfiable: the offset is past the last row.
                # PostgREST calls that an error; SQLite calls it an empty
                # page, and an empty page is what it is -- a reader who
                # scrolls past the end has not broken anything. Left
                # unhandled this surfaced as "Data store unavailable. Retry
                # shortly.", which is both wrong and unactionable.
                #
                # The total still comes from Content-Range, so the caller can
                # report how many rows there actually are.
                total = None
                if exact_count:
                    content_range = error.headers.get("Content-Range", "")
                    if "/" in content_range:
                        tail = content_range.rsplit("/", 1)[1]
                        total = int(tail) if tail.isdigit() else None
                return [], total
            if error.code < 500:
                # Upstream detail goes to the server log, never to the client.
                raise SupabaseError(f"Supabase returned {error.code}") from error
            last = error
        except (urllib.error.URLError, TimeoutError, OSError, ssl.SSLError) as error:
            last = error

        if attempt + 1 < RETRY_ATTEMPTS:
            time.sleep(RETRY_BACKOFF_SECONDS * (2 ** attempt))

    if isinstance(last, urllib.error.HTTPError):
        raise SupabaseError(f"Supabase returned {last.code}") from last
    raise SupabaseError("Supabase unreachable") from last


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
        resource, slug_column = "v_driver_standings", "driver_slug"
    else:
        resource, slug_column = "v_constructor_standings", "constructor_slug"
    rows, _ = query(
        resource,
        filters={"season": f"eq.{season}"},
        # Trailing slug for a total order: two entities level on
        # points, wins, podiums AND name cannot happen, but two level
        # through podiums can, and locale vs byte collation on the name
        # alone put them in different orders on the two stores.
        order=f"points.desc,wins.desc,podiums.desc,{slug_column}.asc",
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


# Mirrors analytics._LEADERBOARD_SORTS fragment for fragment, including the
# trailing slug. These previously carried no tiebreak at all -- just
# "wins.desc" against SQLite's three levels -- so any two entities level on
# wins came back in an arbitrary and backend-specific order, and a listing
# paginated to a different set of drivers on Supabase than on SQLite.
_LEADERBOARD_SORTS = {
    "wins": "wins.desc,podiums.desc,entries.desc,{slug}.asc",
    "podiums": "podiums.desc,wins.desc,entries.desc,{slug}.asc",
    "entries": "entries.desc,wins.desc,{slug}.asc",
    "win_rate": "win_rate.desc,wins.desc,{slug}.asc",
    "podium_rate": "podium_rate.desc,podiums.desc,{slug}.asc",
    "avg_position": "avg_classified_position.asc,{slug}.asc",
    # sort_name is `display_name collate "C"` (migration 22): byte order, which
    # is what SQLite's default collation compares by.
    "name": "sort_name.asc,{slug}.asc",
    "points": "points.desc,{slug}.asc",
}


def leaderboard(
    entity: str = "driver",
    sort: str = "wins",
    limit: int = 50,
    offset: int = 0,
    min_entries: int = 1,
    exclude_hidden: bool = False,
    count_total: bool = True,
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
    slug_column = "driver_slug" if entity == "driver" else "constructor_slug"
    order = _LEADERBOARD_SORTS[sort].format(slug=slug_column)

    filters = {"entries": f"gte.{min_entries}"}
    if exclude_hidden and entity == "constructor":
        # The browsable index is the one place hidden constructors are
        # withheld. Their rows and every aggregate still count them --
        # mirrors analytics.HIDDEN_CONSTRUCTORS. Filtering here rather than in
        # the client keeps the pagination total honest.
        quoted = ",".join(f'"{name}"' for name in analytics.HIDDEN_CONSTRUCTORS)
        filters["constructor_name"] = f"not.in.({quoted})"

    return query(
        resource,
        filters=filters,
        order=order,
        limit=limit,
        offset=offset,
        # The count is a second scan and roughly doubles the cost. Callers
        # that only want the top row -- the records page runs seven of these
        # -- do not need it. Mirrors analytics.leaderboard(count_total=False).
        exact_count=count_total,
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
    """Which constructors a driver raced for, per season, with entry counts.

    Reads v_driver_constructor_seasons (migration 22). It previously read the
    raw `driver_constructor_seasons` table with select=constructor_id,
    season_id,race_count, which returned three columns where the contract
    specifies a full stat block -- and leaked `season_id`, a raw foreign key,
    in place of the season year. Nothing caught it because the payload parity
    suite was comparing Supabase against itself.

    A driver can appear for two constructors in one season (mid-season switch,
    reserve drive) -- two rows, never merged, same as analytics.
    """
    rows, _ = query(
        "v_driver_constructor_seasons",
        filters={"driver_slug": f"eq.{slug}"},
        order="season,entries.desc",
    )
    return [
        {
            "season": row["season"],
            "constructor_id": row["constructor_id"],
            "constructor_slug": row["constructor_slug"],
            "constructor_name": row["constructor_name"],
            **_stat_block(row),
        }
        for row in rows
    ]


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
            # Migration 22 added `entries` to both standings views. Before
            # that this was always None, so the UI rendered "unavailable" for
            # a count the other backend served as a number.
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
    exclude_hidden: bool = False,
    count_total: bool = True,
) -> dict:
    """A page of the ranking, shaped as analytics.leaderboard returns it."""
    rows, total = leaderboard(
        entity, sort, limit, offset, min_entries, exclude_hidden, count_total
    )
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
                "nationality": row.get("nationality"),
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
    """Cross-entity search, ranked and grouped the way SQLite ranks it.

    `v_search_index` is one row per findable entity, so PostgREST's inability
    to join across tables in one request is not a constraint here.

    Two things this got wrong before migration 22, both invisible while the
    parity suite compared Supabase against itself:

      * the index held drivers, constructors and circuits only. Races and
        seasons were absent entirely, so "ham" returned 3 results against
        SQLite's 11, and no race was ever findable on this backend.
      * ranking was one global sort truncated to `limit`, where SQLite takes
        up to `limit` of EACH kind and returns up to limit * 3. A single
        prominent constructor could therefore push every driver off the list
        -- "ham" returned Caterham above Lewis Hamilton.

    Ranking stays in Python because it depends on the search term (prefix
    matches first, then wins) and so cannot be baked into a view. Doing it
    here keeps it identical to the other backend rather than approximately
    similar.
    """
    text = (term or "").strip()
    if not text:
        return []

    lowered = text.lower()

    # A query like "2004 monza" carries two things: a season filter and a
    # name. Split them so races can use both, instead of failing to match
    # either half against a single column.
    year = re.search(r"\b(?:19|20)\d{2}\b", text)
    rest = (text[: year.start()] + text[year.end():]).strip() if year else text
    season = int(year.group(0)) if year else None

    # PostgREST's ilike wildcard is `*`, and `query` URL-encodes the value, so
    # no caller text reaches a SQL string.
    #
    # Two lookups, because the two halves of a query are matched differently.
    # Named entities are matched against the WHOLE string, exactly as SQLite
    # does. Races and seasons are matched against the non-year remainder and
    # filtered by the year -- searching races for the literal text "2004 monza"
    # matches nothing, which is why this returned zero results for it.
    named_rows, _ = query(
        "v_search_index",
        filters={"match_key": f"ilike.*{lowered}*", "kind": "in.(driver,constructor,circuit)"},
        limit=500,
    )

    def prefix_rank(row: dict) -> int:
        position = (row["search_key"] or "").find(lowered)
        # Not found sorts LAST. A circuit can match on its country while its
        # name contains nothing of the term -- "spa" matches Spain -- and
        # ranking those first put Barcelona and Valencia above Spa itself.
        return position if position >= 0 else 999

    def named(row: dict) -> tuple:
        return (prefix_rank(row), -(row["wins"] or 0))

    out: list[dict] = []
    for kind in ("driver", "constructor"):
        hits = sorted((r for r in named_rows if r["kind"] == kind), key=named)[:limit]
        out += [
            {"kind": kind, "id": r["id"], "slug": r["slug"], "label": r["label"],
             "sublabel": f"{r['wins'] or 0} wins"}
            for r in hits
        ]

    circuit_hits = sorted(
        (r for r in named_rows if r["kind"] == "circuit"),
        key=lambda r: (prefix_rank(r), r["label"]),
    )[:limit]
    out += [
        {"kind": "circuit", "id": r["id"], "slug": r["slug"], "label": r["label"],
         "sublabel": r["sublabel"]}
        for r in circuit_hits
    ]

    if rest or season is not None:
        race_filters = {"kind": "eq.race"}
        if rest:
            race_filters["match_key"] = f"ilike.*{rest.lower()}*"
        if season is not None:
            race_filters["season"] = f"eq.{season}"
        race_rows, _ = query(
            "v_search_index", filters=race_filters, order="season.desc,round.asc", limit=limit
        )
        out += [
            {"kind": "race", "id": r["id"], "label": r["label"], "sublabel": r["sublabel"]}
            for r in race_rows
        ]

    if text.isdigit() or season is not None:
        prefix = text if text.isdigit() else str(season)
        season_rows, _ = query(
            "v_search_index",
            filters={"kind": "eq.season", "label": f"like.{prefix}*"},
            order="season.asc",
            limit=limit,
        )
        out += [
            {"kind": "season", "id": r["season"], "label": r["label"], "sublabel": r["sublabel"]}
            for r in season_rows
        ]

    return out[: limit * 3]


def season_dominance(season_year: int) -> dict | None:
    """How concentrated one season was.

    win_share and points_share are NOT comparable with each other -- every
    scoring finisher dilutes points_share, so it is bounded far below 1.0
    however dominant the leader was. Both are returned; neither is a
    refinement of the other.

    Before migration 22 this returned five keys against the contract's eleven:
    the whole constructor half, both entity lists and `basis` were simply
    absent, so the season page's constructor charts had nothing to draw.
    v_season_dominance now carries the constructor scalars, and the two
    v_season_dominance_* views carry the rows.
    """
    row = _one("v_season_dominance", {"season": f"eq.{season_year}"})
    if row is None:
        return None

    def leaders(resource: str) -> list[dict]:
        rows, _ = query(
            resource,
            filters={"season": f"eq.{season_year}"},
            # Same order as advanced.season_dominance: most wins, then
            # podiums, then the better average finish.
            order="wins.desc,podiums.desc,avg_classified_position.asc",
        )
        return [
            {
                "id": entry["id"],
                "name": entry["name"],
                "wins": entry["wins"],
                "podiums": entry["podiums"],
                "entries": entry["entries"],
                "avg_classified_position": _number(entry["avg_classified_position"]),
                "win_share": _number(entry["win_share"]),
                "points": _round_half_up(_number(entry["points"]), 2),
            }
            for entry in rows
        ]

    return {
        "season": row["season"],
        "races": row["races"],
        "distinct_driver_winners": row["distinct_driver_winners"],
        "distinct_constructor_winners": row["distinct_constructor_winners"],
        "top_driver_win_share": _number(row["top_driver_win_share"]),
        "top_constructor_win_share": _number(row["top_constructor_win_share"]),
        "top_driver_points_share": _number(row["top_driver_points_share"]),
        "top_constructor_points_share": _number(row["top_constructor_points_share"]),
        "drivers": leaders("v_season_dominance_drivers")[:10],
        "constructors": leaders("v_season_dominance_constructors")[:10],
        # Verbatim from advanced.season_dominance. The string is the metric's
        # definition, so it must not drift between the two backends.
        "basis": advanced.SEASON_DOMINANCE_BASIS,
    }


def _uncached_era_summary() -> list[dict]:
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
            # No `slug`: the SQLite payload has no such key, and an extra
            # field is still a contract difference between backends.
            {"name": winner["name"], "wins": winner["wins"]}
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
    ("P2–P3", "p2_p3"),
    ("P4–P5", "p4_p5"),
    ("P6–P10", "p6_p10"),
    ("P11–P15", "p11_p15"),
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
    left_block, right_block = _stat_block(left), _stat_block(right)
    result = {
        "left": left_block,
        "right": right_block,
        "shared_seasons": shared,
        # Matches analytics.compare: overlapping seasons are necessary but not
        # sufficient. Two drivers who shared a season while one of them started
        # twice are not comparable, and this used to claim they were.
        "comparable": bool(shared) and left_block["rates_reliable"] and right_block["rates_reliable"],
    }
    if shared:
        window = (min(shared), max(shared))
        result["left_shared"] = _window_stats(entity, left_slug, *window)
        result["right_shared"] = _window_stats(entity, right_slug, *window)
    return result


def _window_stats(entity: str, slug: str, season_from: int, season_to: int) -> dict:
    """One entity's stat block over a season window, via f_entity_window_stats.

    A PostgREST RPC rather than a view because the window is an argument, and
    rather than a sum over the per-season view because avg_grid and
    avg_positions_gained are means over results -- a mean of means is only the
    mean when every season has the same entry count.
    """
    rows, _ = query(
        "rpc/f_entity_window_stats",
        filters={
            "p_entity": entity,
            "p_slug": slug,
            "p_from": str(season_from),
            "p_to": str(season_to),
        },
    )
    return _stat_block(rows[0] if rows else None)


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


# ---------------------------------------------------------------------------
# Route adapters added when the remaining routes were wired through
# `backends.serve` (migration 23).
#
# Until then roughly two thirds of the API read SQLite whatever F1_BACKEND
# said. `SUPABASE_CAPABILITIES` listed several of these as supported, which
# measured what this module could do rather than what any route called -- so
# the payload-parity suite passed on them by comparing SQLite against itself,
# the same vacuity as the fixture bug it was written to catch.
#
# Each function below returns the route's contract shape, not the view's, for
# the reason the shape-adapter section above gives.
# ---------------------------------------------------------------------------

def _uncached_records_list() -> list[dict]:
    """Dataset-wide records, built from analytics.RECORD_SPECS.

    Not read from `v_records`. That view was an independently authored record
    set -- different labels, different methodology wording, values rounded to
    four places and one record missing -- and nothing caught the divergence
    because /api/records never reached backends.serve. Building both backends
    from the same specs is what stops the list being defined twice.
    """
    span = coverage_span()
    out: list[dict] = []
    for label, entity, sort, min_entries, field, note in analytics.RECORD_SPECS:
        page = leaderboard_page(
            entity, sort=sort, limit=1, min_entries=min_entries, count_total=False
        )
        items = page["items"]
        if not items:
            continue
        out.append({
            "record": label,
            "entity": items[0]["name"],
            "value": items[0][field],
            "methodology": note.format(span=span),
        })

    best_season, _ = query(
        "v_driver_season_stats",
        select="display_name,season,wins",
        filters={"wins": "gt.0"},
        order="wins.desc,season.asc",
        limit=1,
    )
    if best_season:
        out.append({
            "record": analytics.BEST_SEASON_RECORD[0],
            "entity": best_season[0]["display_name"],
            "value": best_season[0]["wins"],
            "context": str(best_season[0]["season"]),
            "methodology": analytics.BEST_SEASON_RECORD[1],
        })

    circuit_king, _ = query(
        "v_driver_circuit_stats",
        select="display_name,circuit_name,wins",
        filters={"wins": "gt.0"},
        order="wins.desc,display_name.asc",
        limit=1,
    )
    if circuit_king:
        out.append({
            "record": analytics.CIRCUIT_KING_RECORD[0],
            "entity": circuit_king[0]["display_name"],
            "value": circuit_king[0]["wins"],
            "context": circuit_king[0]["circuit_name"],
            "methodology": analytics.CIRCUIT_KING_RECORD[1].format(span=span),
        })
    return out


def teammates_payload(slug: str) -> dict:
    """Head-to-head against every teammate, grouped by constructor spell.

    `seasons` comes from the view as an array (migration 23) rather than being
    inferred from first/last season, which cannot express a spell with a gap
    in it -- a driver who left a team and returned.
    """
    rows, _ = query(
        "v_teammate_comparisons",
        filters={"driver_slug": f"eq.{slug}"},
        order="shared_races.desc",
    )
    spells = [
        {
            "teammate_id": row["teammate_id"],
            "teammate_slug": row["teammate_slug"],
            "teammate_name": row["teammate_name"],
            "constructor_id": row["constructor_id"],
            "constructor_slug": row["constructor_slug"],
            "constructor_name": row["constructor_name"],
            "seasons": row["seasons"],
            "shared_races": row["shared_races"],
            "ahead": row["ahead"],
            "behind": row["behind"],
            "h2h_rate": _number(row["h2h_rate"]),
            "avg_position_delta": _number(row["avg_position_delta"]),
            "my_avg_position": _number(row["my_avg_position"]),
            "teammate_avg_position": _number(row["teammate_avg_position"]),
            "comparable": row["comparable"],
        }
        for row in rows
    ]
    return {
        "summary": _teammate_summary(spells),
        "spells": spells,
        "methodology": advanced.METRICS_BY_KEY["teammate_h2h"],
    }


def _teammate_summary(spells: list[dict]) -> dict:
    """Career totals across spells that clear the threshold.

    Mirrors advanced.teammate_summary exactly, including that short spells are
    excluded from the totals rather than diluted into them, and counted
    separately so the exclusion is visible.
    """
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
        "avg_position_delta": _round_half_up(
            sum(s["avg_position_delta"] * s["shared_races"] for s in counted) / shared, 3
        ),
        "teammates": len(counted),
        "excluded_short_spells": len(spells) - len(counted),
    }


def driver_circuit_profile(slug: str, min_appearances: int) -> list[dict]:
    """Per-circuit record, each compared with the driver's own career average."""
    rows, _ = query(
        "v_driver_circuit_stats",
        filters={"driver_slug": f"eq.{slug}"},
        order="appearances.desc,circuit_name.asc",
    )
    return [
        {
            "circuit_id": row["circuit_id"],
            "circuit_name": row["circuit_name"],
            "slug": row["circuit_slug"],
            "appearances": row["appearances"],
            "wins": row["wins"],
            "podiums": row["podiums"],
            "avg_classified_position": _number(row["avg_classified_position"]),
            "best_classified_position": row["best_classified_position"],
            "delta_vs_career": _number(row["delta_vs_career"]),
            # Computed here, not read: the view's own flag is fixed at five,
            # while the endpoint takes the threshold as a parameter.
            "meets_threshold": row["appearances"] >= min_appearances,
        }
        for row in rows
    ]


def circuit_specialists_list(circuit_slug: str, min_appearances: int) -> list[dict]:
    """Drivers who outperformed their own career norm at one circuit."""
    rows, _ = query(
        "v_driver_circuit_stats",
        filters={"circuit_slug": f"eq.{circuit_slug}"},
    )
    out = [
        {
            "driver_id": row["driver_id"],
            "driver_slug": row["driver_slug"],
            "driver_name": row["display_name"],
            "appearances": row["appearances"],
            "wins": row["wins"],
            "podiums": row["podiums"],
            "avg_here": _number(row["avg_classified_position"]),
            "avg_career": _number(row["career_avg_classified_position"]),
            "delta_vs_career": _number(row["delta_vs_career"]),
        }
        for row in rows
        if row["appearances"] >= min_appearances
    ]
    # Ranked by the delta, not raw results, so a midfield driver who reliably
    # over-delivered here is not buried under front-runners.
    out.sort(key=lambda r: -r["delta_vs_career"])
    return out


def constructor_distribution(slug: str) -> dict:
    """Finishing distribution for a constructor. Mirrors distribution()."""
    row = _one("v_constructor_position_distribution", {"constructor_slug": f"eq.{slug}"})
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


def _uncached_seasons_index() -> list[dict]:
    """One row per season, most recent first, as /api/seasons returns it."""
    rows, _ = query("v_season_index", order="season.desc")
    return [
        {
            "season": row["season"],
            "races": row["races"],
            "entries": row["entries"],
            "drivers": row["drivers"],
            "constructors": row["constructors"],
        }
        for row in rows
    ]


def _season_table(entity: str, season_year: int) -> list[dict]:
    """Wins-ordered per-season table, matching leaderboard(sort="wins")."""
    if entity == "driver":
        resource, id_key, slug_key, name_key = (
            "v_driver_season_stats", "driver_id", "driver_slug", "display_name")
    else:
        resource, id_key, slug_key, name_key = (
            "v_constructor_season_stats", "constructor_id", "constructor_slug", "constructor_name")
    rows, _ = query(
        resource,
        filters={"season": f"eq.{season_year}"},
        order=f"wins.desc,podiums.desc,entries.desc,{slug_key}.asc",
        limit=1000,
    )
    by_driver, by_constructor = _nationalities()
    lookup = by_driver if entity == "driver" else by_constructor
    return [
        {
            "id": row[id_key], "slug": row[slug_key], "name": row[name_key],
            "nationality": lookup.get(row[id_key]),
            **_stat_block(row),
        }
        for row in rows
    ]


def season_summary_payload(season_year: int) -> dict | None:
    """Season detail: standings, the wins-ordered tables, and the race list.

    `standings` is the championship. `drivers`/`constructors` are ordered by
    wins and `ranking_basis` says so -- they answer a different question, and
    a driver can top that table without winning the title.
    """
    row = _one("v_season_index", {"season": f"eq.{season_year}"})
    if row is None or not row["races"]:
        return None
    return {
        "season": season_year,
        "races": row["races"],
        "entries": row["entries"],
        "ranking_basis": "wins",
        "drivers": _season_table("driver", season_year),
        "constructors": _season_table("constructor", season_year),
        "standings": {
            "drivers": standings_detail(season_year, "driver"),
            "constructors": standings_detail(season_year, "constructor"),
            "basis": "points",
            "includes_sprint_points": True,
            "caveat": (
                "Ties are broken by wins, then podiums. The official rule is a "
                "countback and is not implemented, so an exact points tie may "
                "order differently from the official classification."
            ),
        },
        "races_list": race_summaries(season_year=season_year, limit=1000),
    }


def race_summaries(
    season_year: int | None = None,
    circuit_slug: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Race rows with their winner, as /api/races returns them.

    Filtered on `circuit_slug`, never on a circuit id: ids come from a
    different sequence in each store, so an id would select a different
    circuit here than it does in SQLite.
    """
    filters: dict[str, str] = {}
    if season_year is not None:
        filters["season"] = f"eq.{season_year}"
    if circuit_slug is not None:
        filters["circuit_slug"] = f"eq.{circuit_slug}"
    rows, _ = query(
        "v_race_summary",
        filters=filters,
        order="season.desc,round.asc",
        limit=limit,
        offset=offset,
    )
    return [
        {
            "id": row["id"], "season": row["season"], "round": row["round"],
            "name": row["name"], "date": row["date"],
            "circuit_id": row["circuit_id"], "circuit_name": row["circuit_name"],
            "circuit_slug": row["circuit_slug"],
            "winner_driver_id": row["winner_driver_id"],
            "winner_driver_slug": row["winner_driver_slug"],
            "winner_driver": row["winner_driver"],
            "winner_constructor_id": row["winner_constructor_id"],
            "winner_constructor_slug": row["winner_constructor_slug"],
            "winner_constructor": row["winner_constructor"],
            "winner_grid": row["winner_grid"],
            "winner_status": row["winner_status"],
            "qualifying_first": row["qualifying_first"],
            "qualifying_first_slug": row["qualifying_first_slug"],
        }
        for row in rows
    ]


def season_races_list(season_year: int) -> list[dict]:
    """The season's races in calendar order."""
    rows = race_summaries(season_year=season_year, limit=1000)
    return sorted(rows, key=lambda r: r["round"])


def season_rounds_payload(season_year: int) -> list[dict]:
    """Calendar order with each round's winner."""
    return [
        {
            "race_id": row["id"], "round": row["round"], "race_name": row["name"],
            "date": row["date"],
            "circuit_name": row["circuit_name"], "circuit_slug": row["circuit_slug"],
            "winner_driver_id": row["winner_driver_id"],
            "winner_driver_slug": row["winner_driver_slug"],
            "winner_driver": row["winner_driver"],
            "winner_constructor_id": row["winner_constructor_id"],
            "winner_constructor_slug": row["winner_constructor_slug"],
            "winner_constructor": row["winner_constructor"],
            "winner_grid": row["winner_grid"],
            "winner_status": row["winner_status"],
            "qualifying_first": row["qualifying_first"],
            "qualifying_first_slug": row["qualifying_first_slug"],
        }
        for row in season_races_list(season_year)
    ]


def _uncached_circuits_list() -> list[dict]:
    """Circuit index with race count and leading winner."""
    rows, _ = query("v_circuit_stats", order="sort_name")
    return [
        {
            "id": row["circuit_id"],
            "slug": row["circuit_key"],
            "name": row["circuit_name"],
            "country": row["country"],
            "has_map": row["has_map"],
            "races": row["races"],
            "top_winner": row["top_winner"],
            "top_winner_wins": row["top_winner_wins"],
        }
        for row in rows
    ]


def _circuit_leaderboard(resource: str, circuit_id: int, limit: int) -> list[dict]:
    rows, _ = query(
        resource,
        filters={"circuit_id": f"eq.{circuit_id}"},
        order="wins.desc,podiums.desc,entries.desc,slug.asc",
        limit=limit,
    )
    by_driver, by_constructor = _nationalities()
    lookup = by_driver if "driver" in resource else by_constructor
    return [
        {
            "id": row["id"], "slug": row["slug"], "name": row["name"],
            "nationality": lookup.get(row["id"]),
            **_stat_block(row),
        }
        for row in rows
    ]


def circuit_detail(slug: str) -> dict | None:
    """One circuit: descriptors, stat block, winners and per-circuit rankings."""
    row = _one("v_circuit_stats", {"circuit_key": f"eq.{slug}"})
    if row is None:
        return None
    descriptors, _ = query(
        "circuits",
        select="official_name,locality,latitude,longitude,source_url",
        filters={"circuit_key": f"eq.{slug}"},
        limit=1,
    )
    d = descriptors[0] if descriptors else {}
    circuit_id = row["circuit_id"]
    winners, _ = query(
        "v_circuit_winners",
        filters={"circuit_id": f"eq.{circuit_id}", "driver_id": "not.is.null"},
        order="season.desc,race_id.desc",
    )
    return {
        "id": circuit_id,
        "slug": row["circuit_key"],
        "name": row["circuit_name"],
        "country": row["country"],
        "official_name": d.get("official_name"),
        "locality": d.get("locality"),
        "latitude": _number(d.get("latitude")),
        "longitude": _number(d.get("longitude")),
        "source_url": d.get("source_url"),
        # No `svg_asset`: the SQLite circuits table has no such column, and an
        # extra key is still a contract difference. `has_map` is the fact the
        # payload carries.
        "has_map": row["has_map"],
        "races": row["races"],
        "stats": _stat_block(row),
        "winners": [
            {
                "season": w["season"], "race_id": w["race_id"], "race_name": w["race_name"],
                "driver_id": w["driver_id"], "driver_slug": w["driver_slug"],
                "driver_name": w["driver_name"],
                "constructor_id": w["constructor_id"],
                "constructor_slug": w["constructor_slug"],
                "constructor_name": w["constructor_name"],
            }
            for w in winners
        ],
        "top_drivers": _circuit_leaderboard("v_circuit_driver_leaderboard", circuit_id, 10),
        "top_constructors": _circuit_leaderboard("v_circuit_constructor_leaderboard", circuit_id, 10),
    }


def _uncached_dominance_timeline() -> list[dict]:
    """Per-season concentration across the dataset."""
    rows, _ = query("v_season_dominance", order="season")
    return [
        {
            "season": row["season"],
            "races": row["races"],
            "driver_winners": row["distinct_driver_winners"],
            "constructor_winners": row["distinct_constructor_winners"],
            "top_driver_win_share": _number(row["top_driver_win_share"]),
            "top_constructor_win_share": _number(row["top_constructor_win_share"]),
        }
        for row in rows
    ]


def qualifying_coverage_from() -> int | None:
    """First season where qualifying is essentially complete.

    Measured by the view, never a literal year -- see v_qualifying_coverage.
    """
    def produce():
        row = _one("v_qualifying_coverage", {})
        return row["coverage_from"] if row else None

    return _cached("qualifying_coverage", produce)


def driver_qualifying_payload(slug: str) -> dict:
    """Career qualifying record, shaped as analytics.driver_qualifying_stats.

    Zero entries returns None for every figure, not 0: the driver may well
    have qualified, the source simply does not say.
    """
    row = driver_qualifying(slug)
    entries = (row or {}).get("qualifying_entries") or 0
    if not entries:
        return {
            "entries": 0, "qualifying_p1": None,
            "avg_qualifying_position": None, "best_qualifying_position": None,
            "coverage_from": qualifying_coverage_from(),
        }
    return {
        "entries": entries,
        "qualifying_p1": row["qualifying_p1"],
        "avg_qualifying_position": _number(row["avg_qualifying_position"]),
        "best_qualifying_position": row["best_qualifying_position"],
        "coverage_from": qualifying_coverage_from(),
    }


def constructor_driver_contribution(slug: str) -> list[dict]:
    """Each driver's share of a constructor's entries, wins and podiums.

    Shares are of THIS constructor's totals, so entry_share sums to 1.0 across
    its drivers. Share of points is deliberately not offered.
    """
    rows, _ = query(
        "v_constructor_driver_stats",
        filters={"constructor_slug": f"eq.{slug}"},
        order="wins.desc,entries.desc,driver_slug.asc",
    )
    return [
        {
            "driver_id": row["driver_id"],
            "driver_slug": row["driver_slug"],
            "driver_name": row["driver_name"],
            **_stat_block(row),
            "entry_share": _number(row["entry_share"]),
            "win_share": _number(row["win_share"]),
            "podium_share": _number(row["podium_share"]),
        }
        for row in rows
    ]


def coverage_span() -> str:
    """The dataset's season range, read from the data, never a literal.

    A hardcoded span is correct only until the next ingestion, and a scope
    string that quietly describes the wrong window is worse than none.
    """
    def produce():
        rows, _ = query("v_season_index", select="season", order="season.asc", limit=1000)
        return f"{rows[0]['season']}-{rows[-1]['season']}" if rows else ""

    # One request, not two, and cached: the covered window changes only when
    # a season is ingested.
    return _cached("coverage_span", produce)


def _name_maps() -> tuple[dict, dict]:
    """driver_id -> (slug, name) and constructor_id -> (slug, name).

    Two requests for the whole dataset rather than an embedded join per
    session block: a race weekend touches five tables, and PostgREST cannot
    join them in one request. 129 drivers and 38 constructors is small enough
    that fetching both beats five embedded selects.
    """
    def produce():
        drivers, _ = query("drivers", select="id,slug,display_name", limit=1000)
        constructors, _ = query("constructors", select="id,slug,constructor_name", limit=1000)
        return (
            {d["id"]: (d["slug"], d["display_name"]) for d in drivers},
            {c["id"]: (c["slug"], c["constructor_name"]) for c in constructors},
        )

    # Identity only -- names and slugs change when the ETL runs, not between
    # two reads. This was two full-table round trips on every race request.
    return _cached("name_maps", produce)


def race_detail(season_year: int, round_: int) -> dict | None:
    """Full race weekend, addressed by its natural key.

    (season, round) rather than a race id, for the same reason entities use
    slugs: race ids are store-local, so an id would address a different race
    here than it does in SQLite.

    Each session block reports its own availability rather than returning a
    bare empty list -- "no qualifying recorded for this race" and "nobody
    qualified" look identical in JSON otherwise, and only one of them is true.
    """
    header = _one(
        "v_race_summary",
        {"season": f"eq.{season_year}", "round": f"eq.{round_}"},
    )
    if header is None:
        return None

    race_id = header["id"]
    drivers, constructors = _name_maps()

    def driver(did):
        return drivers.get(did, (None, None))

    def team(cid):
        return constructors.get(cid, (None, None))

    results, _ = query(
        "results",
        select="position,driver_id,constructor_id,grid,laps,points,status,classification,"
               "position_text,fastest_lap_rank,fastest_lap_number,fastest_lap_time,fastest_lap_speed",
        filters={"race_id": f"eq.{race_id}"},
        order="position",
        limit=1000,
    )
    grid_by_driver = {r["driver_id"]: r["grid"] for r in results}
    race_results = [
        {
            "position": r["position"],
            "driver_id": r["driver_id"],
            "driver_slug": driver(r["driver_id"])[0],
            "driver_name": driver(r["driver_id"])[1],
            "constructor_id": r["constructor_id"],
            "constructor_slug": team(r["constructor_id"])[0],
            "constructor_name": team(r["constructor_id"])[1],
            "grid": r["grid"],
            "laps": r["laps"],
            "points": _number(r["points"]),
            "status": r["status"],
            "classification": r["classification"],
            "position_text": r["position_text"],
            "fastest_lap_rank": r["fastest_lap_rank"],
            "fastest_lap_number": r["fastest_lap_number"],
            "fastest_lap_time": r["fastest_lap_time"],
        }
        for r in results
    ]

    qualifying_rows, _ = query(
        "qualifying_results",
        select="position,q1,q2,q3,driver_id,constructor_id",
        filters={"race_id": f"eq.{race_id}"},
        order="position",
        limit=1000,
    )
    qualifying = [
        {
            "position": q["position"],
            "q1": q["q1"], "q2": q["q2"], "q3": q["q3"],
            "driver_id": q["driver_id"],
            "driver_name": driver(q["driver_id"])[1],
            "constructor_id": q["constructor_id"],
            "constructor_name": team(q["constructor_id"])[1],
            "race_grid": grid_by_driver.get(q["driver_id"]),
        }
        for q in qualifying_rows
    ]

    sprint_rows, _ = query(
        "sprint_results",
        select="position,classification,status,points,grid,laps,driver_id,constructor_id",
        filters={"race_id": f"eq.{race_id}"},
        order="position",
        limit=1000,
    )
    sprint = [
        {
            "position": s["position"],
            "classification": s["classification"],
            "status": s["status"],
            "points": _number(s["points"]),
            "grid": s["grid"],
            "laps": s["laps"],
            "driver_id": s["driver_id"],
            "driver_name": driver(s["driver_id"])[1],
            "constructor_id": s["constructor_id"],
            "constructor_name": team(s["constructor_id"])[1],
        }
        for s in sprint_rows
    ]

    stop_rows, _ = query(
        "pit_stops",
        select="lap,stop,duration,time_of_day,driver_id",
        filters={"race_id": f"eq.{race_id}"},
        order="lap,stop",
        limit=1000,
    )
    stops = sorted(
        (
            {
                "lap": s["lap"], "stop": s["stop"],
                "duration": s["duration"], "time_of_day": s["time_of_day"],
                "driver_id": s["driver_id"],
                "driver_name": driver(s["driver_id"])[1],
            }
            for s in stop_rows
        ),
        # Sorted here rather than by the query: the final tiebreak is the
        # driver SLUG, and PostgREST can only order by the table's own
        # columns, where the driver is a store-local id.
        key=lambda s: (s["lap"], s["stop"], driver(s["driver_id"])[0] or ""),
    )

    quickest = _fastest_lap(race_id, drivers)
    award = _fastest_lap_award(race_id, results, drivers, constructors)
    practice_codes = _practice_sessions_available(race_id)

    return {
        "id": race_id,
        "season": header["season"],
        "round": header["round"],
        "name": header["name"],
        "date": header["date"],
        "circuit_id": header["circuit_id"],
        "circuit_name": header["circuit_name"],
        "circuit_slug": header["circuit_slug"],
        "winner_driver_id": header["winner_driver_id"],
        "winner_driver_slug": header["winner_driver_slug"],
        "winner_driver": header["winner_driver"],
        "winner_constructor_id": header["winner_constructor_id"],
        "winner_constructor_slug": header["winner_constructor_slug"],
        "winner_constructor": header["winner_constructor"],
        "winner_grid": header["winner_grid"],
        "winner_status": header["winner_status"],
        "qualifying_first": header["qualifying_first"],
        "qualifying_first_slug": header["qualifying_first_slug"],
        "results": race_results,
        "qualifying": {
            "available": bool(qualifying),
            "unavailable_reason": None if qualifying else
                "The source carries no qualifying for this race.",
            "items": qualifying,
        },
        "sprint": {
            "available": bool(sprint),
            "unavailable_reason": None if sprint else
                "No sprint was held at this event.",
            "items": sprint,
        },
        "pit_stops": {
            "available": bool(stops),
            "unavailable_reason": None if stops else
                "Pit stop data begins in 2011; none is recorded for this race.",
            "items": stops,
        },
        "practice": {
            "available": bool(practice_codes),
            "unavailable_reason": None if practice_codes else (
                "Practice timing begins in 2018; none exists for this race."
                if header["season"] < 2018
                else "Practice timing has not been ingested for this race."
            ),
            "source": "FastF1 / F1 live timing",
            "sessions": {
                code: _practice_results(race_id, code, drivers, constructors)
                for code in practice_codes
            },
        },
        # TWO DIFFERENT THINGS, deliberately side by side. The award is what
        # the sport gave, with its eligibility rules; `fastest_lap` is the
        # quickest time anyone recorded. They can name different drivers.
        "fastest_lap_award": {
            "available": award is not None,
            "unavailable_reason": None if award else (
                "The source publishes no fastest lap before 2004."
                if header["season"] < 2004
                else "No fastest-lap award recorded for this race."
            ),
            "basis": "as awarded by the sport, including eligibility rules",
            "item": award,
        },
        "fastest_lap": {
            "available": quickest is not None,
            "unavailable_reason": None if quickest else
                "Lap timings have not been ingested for this race.",
            "basis": "minimum lap time recorded; not the official award",
            "item": quickest,
        },
    }


def _fastest_lap(race_id: int, drivers: dict) -> dict | None:
    """Quickest lap anyone actually recorded, from the lap timings.

    Deliberately NOT the fastest-lap award: the award applies eligibility
    rules a raw minimum does not, so the two can name different drivers.
    """
    rows, _ = query(
        "lap_times",
        select="lap,time_text,time_ms,driver_id",
        filters={"race_id": f"eq.{race_id}", "time_ms": "not.is.null"},
        order="time_ms.asc",
        limit=1,
    )
    if not rows:
        return None
    row = rows[0]
    slug, name = drivers.get(row["driver_id"], (None, None))
    return {
        "lap": row["lap"],
        "time_text": row["time_text"],
        "time_ms": row["time_ms"],
        "driver_id": row["driver_id"],
        "driver_slug": slug,
        "driver_name": name,
    }


def _fastest_lap_award(race_id: int, results: list[dict], drivers: dict, constructors: dict) -> dict | None:
    """The fastest lap as the sport awarded it -- rank 1 in the enrichment."""
    for row in results:
        if row.get("fastest_lap_rank") == 1:
            dslug, dname = drivers.get(row["driver_id"], (None, None))
            cslug, cname = constructors.get(row["constructor_id"], (None, None))
            return {
                "driver_id": row["driver_id"],
                "driver_slug": dslug,
                "driver_name": dname,
                "constructor_id": row["constructor_id"],
                "constructor_slug": cslug,
                "constructor_name": cname,
                "lap": row["fastest_lap_number"],
                "time_text": row["fastest_lap_time"],
                # Read, not None: migration 24 added the column and the
                # backfill loaded it. It is NULL for 487 of the 8,725 enriched
                # rows, where the source omits it -- never estimated from the
                # lap time.
                "average_speed_kph": _number(row["fastest_lap_speed"]),
                "finish_position": row["position"],
            }
    return None


def _practice_sessions_available(race_id: int) -> list[str]:
    rows, _ = query(
        "practice_laps",
        select="session",
        filters={"race_id": f"eq.{race_id}"},
        limit=100000,
    )
    return sorted({r["session"] for r in rows})


def _practice_results(race_id: int, code: str, drivers: dict, constructors: dict) -> list[dict]:
    """One practice session, fastest first.

    `position` and `gap_to_leader` are assigned here rather than read: the
    view holds each driver's best lap, and the ordering that turns those into
    a classification is the session's, not a stored fact. `race_id` and
    `session` are dropped -- the caller already keys on both, and the SQLite
    payload does not repeat them per row.
    """
    rows, _ = query(
        "v_practice_results",
        filters={"race_id": f"eq.{race_id}", "session": f"eq.{code}"},
        order="best_lap.asc,driver_slug.asc",
        limit=1000,
    )
    leader = _number(rows[0]["best_lap"]) if rows else None
    return [
        {
            "position": index,
            "driver_id": row["driver_id"],
            "driver_slug": row["driver_slug"],
            "driver_name": row["driver_name"],
            "best_lap": _number(row["best_lap"]),
            "gap_to_leader": _round_half_up(_number(row["best_lap"]) - leader, 3),
            "laps": row["laps"],
            "deleted_laps": row["deleted_laps"],
        }
        for index, row in enumerate(rows, start=1)
    ]


# ---------------------------------------------------------------------------
# Dataset-wide aggregates, cached.
#
# Each of these summarises the WHOLE build: the record list, the circuit
# index, the season index, the era table, the dominance timeline. None of them
# can change without an ETL run, and each cost between two and nine PostgREST
# round trips to assemble -- /api/records was nine requests and 2.6 seconds.
#
# Nothing season-scoped or entity-scoped is cached here. A standings table or
# a race classification is exactly the kind of value that must not be served
# stale, and the current season is the part a reader is most likely to be
# looking at.
# ---------------------------------------------------------------------------

def records_list() -> list[dict]:
    return _cached("records", _uncached_records_list)


def circuits_list() -> list[dict]:
    return _cached("circuits_list", _uncached_circuits_list)


def seasons_index() -> list[dict]:
    return _cached("seasons_index", _uncached_seasons_index)


def dominance_timeline() -> list[dict]:
    return _cached("dominance_timeline", _uncached_dominance_timeline)


def era_summary() -> list[dict]:
    return _cached("era_summary", _uncached_era_summary)


def _nationalities() -> tuple[dict, dict]:
    """driver_id -> nationality and constructor_id -> nationality.

    Cached like the name maps, and for the same reason: nationality is entity
    identity, not a measurement, so it changes only when the ETL runs. Used by
    the nested rankings (a circuit's top drivers, a season's table), which are
    built from views that carry the stat block but not the descriptor.
    """
    def produce():
        drivers, _ = query("drivers", select="id,nationality", limit=1000)
        constructors, _ = query("constructors", select="id,nationality", limit=1000)
        return (
            {d["id"]: d["nationality"] for d in drivers},
            {c["id"]: c["nationality"] for c in constructors},
        )

    return _cached("nationalities", produce)
