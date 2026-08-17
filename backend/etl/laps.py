"""Fetch per-lap timings from Jolpica-F1. Resumable by construction.

WHY THIS IS ITS OWN MODULE
--------------------------
Every other dataset in this project is a season-at-a-time fetch that finishes
in minutes. Lap times are not: the API caps a page at 100 rows *server-side*
(asking for 1000 returns 100), and a single race carries north of a thousand
timings, so one race is ~11 requests and the full 2000-2025 window is roughly
5,500. Throttled, that is hours of wall clock.

A multi-hour fetch that cannot be interrupted is a fetch that never completes.
So the unit of work here is one race, cached as one file, and the driver loop
skips any race already on disk. Kill it and rerun it; it picks up where it
stopped and re-requests nothing.

COVERAGE IS RECORDED, NOT ASSUMED
---------------------------------
Ergast-derived lap timing does not exist for every race in the window. A race
that legitimately returns zero laps is cached as an empty list -- that is a
finding, and caching it stops the next run from asking again forever. A race
that *fails* is written to the failure manifest instead and is retried on the
next run. The two are never conflated: "no laps recorded" and "we could not
ask" are different facts, and only one of them is about the data.

Run:  python -m backend.etl.laps              # every season in the DB
      python -m backend.etl.laps 2023 2024    # named seasons only
      python -m backend.etl.laps --status     # report coverage, fetch nothing
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

from backend.etl.jolpica import CACHE, PAGE, PAUSE_SECONDS, _get

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data" / "f1.db"
FAILURES = CACHE / "laps_failures.json"


def cache_path(season: int, round_: int) -> Path:
    return CACHE / f"jolpica_{season}_{round_}_laps.json"


def race_index(seasons: list[int] | None = None) -> list[tuple[int, int]]:
    """(season, round) for every race in the built database.

    Driven by the database rather than by a hardcoded range so the fetch
    covers exactly the races the project actually has, and automatically
    extends when the build does.
    """
    if not DB_PATH.exists():
        raise SystemExit(f"{DB_PATH} not found. Run: python -m backend.etl.build")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT season, round FROM races ORDER BY season, round").fetchall()
    finally:
        conn.close()
    if seasons:
        wanted = set(seasons)
        rows = [r for r in rows if r[0] in wanted]
    return [(int(s), int(r)) for s, r in rows]


def fetch_race_laps(season: int, round_: int, refresh: bool = False) -> list[dict]:
    """Every lap timing for one race, flattened to one row per driver-lap.

    Values stay as the source wrote them -- lap and position as text, time as
    the raw "1:39.019" string. Parsing to milliseconds happens at load, where
    a failure is attributable to a specific row rather than lost in the fetch.
    """
    path = cache_path(season, round_)
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))

    CACHE.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    offset = 0
    while True:
        data = _get(f"{season}/{round_}/laps.json", offset)
        races = data["RaceTable"]["Races"]
        for race in races:
            for lap in race.get("Laps", []):
                for timing in lap.get("Timings", []):
                    rows.append({
                        "season": season,
                        "round": round_,
                        "lap": int(lap["number"]),
                        "driver_id": timing["driverId"],
                        "position": timing.get("position"),
                        "time": timing.get("time") or "",
                    })

        total = int(data["total"])
        offset += PAGE
        if offset >= total or not races:
            break
        time.sleep(PAUSE_SECONDS)

    # An empty result is written too: a race with no recorded laps is a fact
    # about the source, and caching it prevents an unbounded retry loop.
    path.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    time.sleep(PAUSE_SECONDS)
    return rows


def _read_failures() -> dict[str, str]:
    if FAILURES.exists():
        return json.loads(FAILURES.read_text(encoding="utf-8"))
    return {}


def _write_failures(failures: dict[str, str]) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    FAILURES.write_text(json.dumps(failures, indent=1, sort_keys=True), encoding="utf-8")


def status(seasons: list[int] | None = None) -> dict:
    """Coverage of the on-disk cache. Reads nothing from the network."""
    races = race_index(seasons)
    cached = [(s, r) for s, r in races if cache_path(s, r).exists()]
    empty = [(s, r) for s, r in cached if not json.loads(cache_path(s, r).read_text(encoding="utf-8"))]
    return {
        "races": len(races),
        "cached": len(cached),
        "remaining": len(races) - len(cached),
        "empty": len(empty),
        "failures": len(_read_failures()),
    }


def run(seasons: list[int] | None = None, refresh: bool = False) -> int:
    races = race_index(seasons)
    failures = _read_failures()
    done = fetched = 0

    for season, round_ in races:
        key = f"{season}-{round_}"
        if cache_path(season, round_).exists() and not refresh:
            done += 1
            continue
        try:
            rows = fetch_race_laps(season, round_, refresh)
        except Exception as error:  # noqa: BLE001 - recorded, not swallowed
            # Recorded and skipped rather than aborting: one unreachable race
            # must not discard hours of completed work. The manifest is what
            # makes the next run retry exactly these.
            failures[key] = f"{type(error).__name__}: {error}"
            _write_failures(failures)
            print(f"  {key:>10}  FAILED  {error}", flush=True)
            continue

        failures.pop(key, None)
        _write_failures(failures)
        fetched += 1
        done += 1
        print(f"  {key:>10}  {len(rows):>5} timings   ({done}/{len(races)})", flush=True)

    report = status(seasons)
    print(
        f"\nlap cache: {report['cached']}/{report['races']} races "
        f"({fetched} fetched this run, {report['empty']} with no laps recorded, "
        f"{report['failures']} failed)",
        flush=True,
    )
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    refresh = "--refresh" in argv
    only_status = "--status" in argv
    seasons = [int(a) for a in argv if a.isdigit()] or None
    if only_status:
        print(json.dumps(status(seasons), indent=1))
        return 0
    return run(seasons, refresh)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
