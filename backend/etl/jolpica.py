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
import time
from pathlib import Path

import requests

API = "https://api.jolpi.ca/ergast/f1"
CACHE = Path(__file__).resolve().parents[2] / "data" / "cache"

PAGE = 100
PAUSE_SECONDS = 0.3
TIMEOUT_SECONDS = 60
USER_AGENT = "f1-data-project/ingest"


def _get(path: str, offset: int) -> dict:
    response = requests.get(
        f"{API}/{path}",
        params={"limit": PAGE, "offset": offset},
        timeout=TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    return response.json()["MRData"]


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
