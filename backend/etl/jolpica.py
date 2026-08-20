"""Fetch full race results from Jolpica-F1, with an on-disk cache.

Jolpica is the maintained successor to the retired Ergast API. It carries the
fields this project's source CSV lacks -- finishing status, championship
points, grid position, laps completed -- plus driver and constructor
descriptive data.

Nothing here writes to a database. Fetching, caching and shaping only, so the
network layer can be exercised and inspected on its own.

Paging: the API caps a page at 100 rows, so a season is several requests. Each
season is cached as one JSON file under `data/cache/`; delete it to refetch.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

API = "https://api.jolpi.ca/ergast/f1"
CACHE = Path(__file__).resolve().parents[2] / "data" / "cache"

PAGE = 100
PAUSE_SECONDS = 0.3
TIMEOUT_SECONDS = 60
USER_AGENT = "f1-data-project/ingest"

# There is NO API KEY. This is checked, not assumed.
#
# An earlier version of this file read JOLPICA_API_KEY and, when set, paced
# requests at 10,000/hour. That number was invented. Jolpica's own rate-limit
# documentation says token authentication is "currently being implemented"
# and publishes no authenticated figure at all.
#
# The bug was worse than the wrong docs: setting the variable to any value
# would have paced the fetcher twenty times too fast, so every request past
# the first 500 in an hour would fail. An unavailable feature that breaks
# ingestion when someone tries to use it is worse than no feature.
#
# If tokens do ship, the change is a higher HOURLY_BUDGET and an auth header
# -- but only once the real published limit is known.

# Sustained request budget per hour, and the minimum spacing that respects it.
#
# WHY PACING RATHER THAN RETRYING
# -------------------------------
# Jolpica returns a bare `429 {"detail": "Request was throttled."}` with no
# Retry-After header once the hourly quota is gone. Retrying then cannot
# succeed however patient the backoff is -- the quota refills on a clock, not
# in response to waiting politely -- so a lap sweep that fired as fast as it
# could spent its first minutes filling the budget and every minute after that
# failing.
#
# Spacing requests to stay just inside the budget is slower per request and
# far faster overall, because none of them are wasted. A full lap sweep is
# ~4,600 requests against 500/hour, so it is genuinely an overnight job and
# there is no way to shorten it: the limit is the source's, not ours.
# Jolpica's published sustained limit: 500 requests/hour, plus a 4/second
# burst cap. The documentation also warns these "will decrease in the future",
# so this is a ceiling to stay under, not a target to saturate.
HOURLY_BUDGET = 500
# 2% headroom: landing exactly on the limit is landing over it.
MIN_REQUEST_INTERVAL = 3600.0 / (HOURLY_BUDGET * 0.98)

# Once this many calls in a row come back 429, stop probing and wait out the
# window properly.
#
# WHY A COOL-OFF AND NOT JUST BACKOFF
# -----------------------------------
# Per-request backoff resets on every new request, so a paced loop that keeps
# asking will consume each refill the instant it appears and see 429 again --
# the bucket never gets a chance to fill. Observed directly: a paced run sat
# at zero progress for over an hour while making a full budget's worth of
# failed requests.
#
# Sleeping for a solid block instead lets the window actually reopen. It looks
# idle, and that is the point.
CONSECUTIVE_429_BEFORE_COOLOFF = 3
COOLOFF_SECONDS = 15 * 60

_last_request_at = 0.0
_consecutive_429 = 0


def _throttle() -> None:
    """Sleep just long enough to stay inside the sustained request budget."""
    global _last_request_at
    wait = MIN_REQUEST_INTERVAL - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def _note_throttled() -> None:
    """Record a 429 and, if they are piling up, wait out the whole window."""
    global _consecutive_429
    _consecutive_429 += 1
    if _consecutive_429 >= CONSECUTIVE_429_BEFORE_COOLOFF:
        print(
            f"  rate limit persists after {_consecutive_429} calls; "
            f"cooling off for {COOLOFF_SECONDS // 60} minutes",
            flush=True,
        )
        time.sleep(COOLOFF_SECONDS)
        _consecutive_429 = 0


def _note_success() -> None:
    global _consecutive_429
    _consecutive_429 = 0


# Raised from 6 after a full-calendar lap sweep. Six attempts with the backoff
# below tops out at roughly two minutes of waiting, and Jolpica's sustained
# limit is tighter than that over a run of thousands of requests -- races were
# being recorded as failures purely for being asked about during a long
# throttle. Giving up early does not save the rate budget, it just means the
# same request is made again on the next run.
MAX_RETRIES = 10


def _get(path: str, offset: int) -> dict:
    """One paced API call, retrying on rate limits.

    Every call goes through `_throttle` first, so the caller cannot outrun the
    hourly budget however tight its loop is. That pacing is what prevents the
    429s rather than the retry logic below, which only handles the case where
    the budget is already spent -- from an earlier run, say.

    A 429 is not an error to surface, it is a "wait" to obey. Everything else
    still raises: a 400 or 404 means the query is wrong, and retrying it would
    burn budget that buys nothing.
    """
    delay = 2.0
    headers = {"User-Agent": USER_AGENT}

    for attempt in range(MAX_RETRIES):
        _throttle()
        response = requests.get(
            f"{API}/{path}",
            params={"limit": PAGE, "offset": offset},
            timeout=TIMEOUT_SECONDS,
            headers=headers,
        )
        if response.status_code != 429:
            response.raise_for_status()
            _note_success()
            return response.json()["MRData"]

        _note_throttled()

        # Jolpica sends no Retry-After, so `delay` is the fallback in
        # practice. The ceiling is high because an exhausted hourly quota is
        # refilled by the clock, not by the request rate: waiting minutes is
        # the only thing that helps, and giving up early just means the same
        # request is reissued on the next run.
        wait = float(response.headers.get("Retry-After", delay))
        time.sleep(wait)
        delay = min(delay * 2, 300)

    raise RuntimeError(f"rate limited after {MAX_RETRIES} attempts: {path}")


def fetch_season_results(season: int, refresh: bool = False) -> list[dict]:
    """Every result row for `season`, flattened. Cached on disk.

    Values are kept as the source wrote them -- strings, including "" and
    absent keys -- and are converted at the point of use. Coercing here would
    hide which fields the source actually omitted.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"jolpica_{season}_results.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))

    rows: list[dict] = []
    offset = 0
    while True:
        data = _get(f"{season}/results.json", offset)
        races = data["RaceTable"]["Races"]
        for race in races:
            for result in race.get("Results", []):
                driver = result["Driver"]
                rows.append({
                    "season": int(race["season"]),
                    "round": int(race["round"]),
                    "race_name": race["raceName"],
                    "date": race["date"],
                    "position": int(result["position"]),
                    "position_text": result.get("positionText"),
                    "driver": f"{driver['givenName']} {driver['familyName']}",
                    "driver_id": driver.get("driverId"),
                    "driver_nationality": driver.get("nationality"),
                    "driver_dob": driver.get("dateOfBirth"),
                    "driver_code": driver.get("code"),
                    "permanent_number": driver.get("permanentNumber"),
                    "constructor": result["Constructor"]["name"],
                    "constructor_id": result["Constructor"].get("constructorId"),
                    "constructor_nationality": result["Constructor"].get("nationality"),
                    "points": result.get("points"),
                    "grid": result.get("grid"),
                    "laps": result.get("laps"),
                    "status": result.get("status"),
                    # The official fastest-lap AWARD, which this fetcher used
                    # to discard. `rank` 1 is the driver credited with it --
                    # which is NOT simply the quickest time, because
                    # eligibility rules apply. Absent before 2004, and absent
                    # for any driver who set no timed lap.
                    "fastest_lap_rank": (result.get("FastestLap") or {}).get("rank"),
                    "fastest_lap_number": (result.get("FastestLap") or {}).get("lap"),
                    "fastest_lap_time": (
                        ((result.get("FastestLap") or {}).get("Time") or {}).get("time")
                    ),
                    "fastest_lap_speed": (
                        ((result.get("FastestLap") or {}).get("AverageSpeed") or {}).get("speed")
                    ),
                })

        total = int(data["total"])
        offset += PAGE
        if offset >= total or not races:
            break
        time.sleep(PAUSE_SECONDS)

    path.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    return rows


def fetch_season_sprints(season: int, refresh: bool = False) -> list[dict]:
    """Every sprint result for `season`. Empty before 2021.

    Sprints are a separate event from the Grand Prix, so they are fetched and
    stored separately rather than folded into race results. They share the
    weekend's `round`, which is how they join back to a race.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"jolpica_{season}_sprints.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))

    rows: list[dict] = []
    offset = 0
    while True:
        data = _get(f"{season}/sprint.json", offset)
        races = data["RaceTable"]["Races"]
        for race in races:
            for result in race.get("SprintResults", []):
                driver = result["Driver"]
                rows.append({
                    "season": int(race["season"]),
                    "round": int(race["round"]),
                    "race_name": race["raceName"],
                    "position": int(result["position"]),
                    "position_text": result.get("positionText"),
                    "driver": f"{driver['givenName']} {driver['familyName']}",
                    "constructor": result["Constructor"]["name"],
                    "points": result.get("points"),
                    "grid": result.get("grid"),
                    "laps": result.get("laps"),
                    "status": result.get("status"),
                })

        total = int(data["total"])
        offset += PAGE
        if offset >= total or not races:
            break
        time.sleep(PAUSE_SECONDS)

    path.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    return rows


def fetch_season_qualifying(season: int, refresh: bool = False) -> list[dict]:
    """Every qualifying result for `season`.

    Coverage is genuinely partial: the source has little qualifying before
    2003, and Q1/Q2/Q3 only exist from 2006 -- earlier eras used one- or
    two-lap formats with a single time. Missing sessions stay absent rather
    than being filled with a duplicated time.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"jolpica_{season}_qualifying.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))

    rows: list[dict] = []
    offset = 0
    while True:
        data = _get(f"{season}/qualifying.json", offset)
        races = data["RaceTable"]["Races"]
        for race in races:
            for result in race.get("QualifyingResults", []):
                driver = result["Driver"]
                rows.append({
                    "season": int(race["season"]),
                    "round": int(race["round"]),
                    "position": int(result["position"]),
                    "driver": f"{driver['givenName']} {driver['familyName']}",
                    "constructor": result["Constructor"]["name"],
                    "q1": result.get("Q1") or "",
                    "q2": result.get("Q2") or "",
                    "q3": result.get("Q3") or "",
                })
        total = int(data["total"])
        offset += PAGE
        if offset >= total or not races:
            break
        time.sleep(PAUSE_SECONDS)

    path.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    return rows


def fetch_race_pitstops(season: int, round_: int, refresh: bool = False) -> list[dict]:
    """Pit stops for one race.

    Per-race only: the API rejects a whole-season pit-stop query with 400, so
    this is one request per race (plus paging for races with over 100 stops).

    Coverage starts in 2011. Earlier seasons return zero rows -- a real absence
    in the source, not a fetch failure, and recorded as such rather than
    retried forever.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"jolpica_{season}_{round_}_pitstops.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))

    rows: list[dict] = []
    offset = 0
    while True:
        data = _get(f"{season}/{round_}/pitstops.json", offset)
        races = data["RaceTable"]["Races"]
        for race in races:
            for stop in race.get("PitStops", []):
                rows.append({
                    "season": season,
                    "round": round_,
                    "driver_id": stop["driverId"],
                    "lap": int(stop["lap"]),
                    "stop": int(stop["stop"]),
                    "time_of_day": stop.get("time") or "",
                    # Absent for a few early stops; "" becomes NULL on load.
                    "duration": stop.get("duration") or "",
                })
        total = int(data["total"])
        offset += PAGE
        if offset >= total or not races:
            break
        time.sleep(PAUSE_SECONDS)

    path.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    time.sleep(PAUSE_SECONDS)
    return rows


def fetch_all_qualifying(seasons: list[int], refresh: bool = False) -> list[dict]:
    out: list[dict] = []
    for season in seasons:
        out.extend(fetch_season_qualifying(season, refresh))
    return out


def fetch_all_sprints(seasons: list[int], refresh: bool = False) -> list[dict]:
    out: list[dict] = []
    for season in seasons:
        out.extend(fetch_season_sprints(season, refresh))
    return out


def fetch_all(seasons: list[int], refresh: bool = False, progress: bool = True) -> list[dict]:
    out: list[dict] = []
    for season in seasons:
        rows = fetch_season_results(season, refresh)
        out.extend(rows)
        if progress:
            print(f"  {season}: {len(rows):>4} rows")
    return out


if __name__ == "__main__":
    import sys

    seasons = [int(a) for a in sys.argv[1:]] or list(range(2000, 2026))
    rows = fetch_all(seasons)
    print(f"\n{len(rows):,} result rows cached under {CACHE}")
