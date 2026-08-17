"""Fetch practice-session timing from FastF1. Resumable, one session per file.

WHY A SECOND SOURCE AT ALL
--------------------------
Every other dataset here comes from Jolpica, which publishes no practice
results whatsoever -- its /practice, /fp1 and /sessions routes return 400 or
404. Practice classifications, tyre compounds and sector times therefore had
no source, and were reported as absent rather than invented.

FastF1 reads Formula 1's own live-timing service, which does carry them. That
is a genuinely different provenance from the rest of this database, and it is
recorded as such: a separate `data_source`, its own coverage window, and its
own tables. It is never silently blended into the Jolpica-derived rows.

COVERAGE STARTS IN 2018
-----------------------
Live timing does not exist before then. That is a real boundary, not a
fetching limit, so the window is stated rather than implied.

THE SESSION LIST COMES FROM OUR DATABASE, NOT FROM FASTF1
---------------------------------------------------------
This matters more than it looks. FastF1's default schedule backend returns a
PARTIAL 2024 -- rounds 10 to 24, silently omitting the first nine -- while its
ergast backend returns all 24. Driving ingestion from that schedule would have
produced a database missing nine race weekends with nothing anywhere saying
so.

Iterating our own `races` table instead makes coverage complete by
construction: every round we know about is asked for, and a session that
cannot be fetched becomes a recorded failure rather than an absence nobody
notices.

Run:  python -m backend.etl.practice            # every season from 2018
      python -m backend.etl.practice 2023       # one season
      python -m backend.etl.practice --status   # report, fetch nothing
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
import time
import warnings
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data" / "f1.db"
CACHE = REPO_ROOT / "data" / "cache" / "practice"
FASTF1_CACHE = REPO_ROOT / "data" / "cache" / "fastf1"

# Live timing begins here. Earlier seasons are a source boundary, not a gap.
FIRST_SEASON = 2018

# FastF1's names for the sessions we ingest. Qualifying and the race are
# already covered by Jolpica, so they are deliberately not fetched twice --
# two sources for one fact is how they start disagreeing.
SESSIONS = {
    "fp1": "Practice 1",
    "fp2": "Practice 2",
    "fp3": "Practice 3",
}

FAILURES = CACHE / "practice_failures.json"

# FastF1's event lookup shares the lap fetch's quota, so a sweep meets the
# same throttle. Waiting it out is the only thing that helps.
RATE_LIMIT_RETRIES = 6
RATE_LIMIT_BACKOFF_SECONDS = 120


def _fastf1():
    """Import and configure FastF1 lazily.

    Kept out of module scope so the rest of the ETL, and the test suite, do
    not require the dependency just to import this file.
    """
    warnings.filterwarnings("ignore")
    import fastf1

    # FastF1 installs its own handlers on import, so the level has to be set
    # afterwards -- and on every one of its child loggers, since it logs
    # through several ("req", "core", "api"). Without this a full sweep emits
    # ten lines per session and the actual progress is unreadable.
    fastf1.set_log_level("ERROR")
    for name in list(logging.root.manager.loggerDict):
        if name.startswith("fastf1") or name in {"req", "core", "api", "logger"}:
            logging.getLogger(name).setLevel(logging.ERROR)

    FASTF1_CACHE.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(FASTF1_CACHE))
    return fastf1


# One schedule lookup per SEASON, not per session.
#
# FastF1 resolves an event through its ergast backend, which is the same
# service the lap fetch uses -- so three lookups per race weekend were
# spending the shared Jolpica quota, and 309 sessions failed with
# RateLimitExceededError as a result. Timing data comes from F1 live timing
# and is genuinely independent; the event lookup is not, and assuming
# otherwise is what caused this.
_SCHEDULE_CACHE: dict[int, object] = {}


def _event_schedule(fastf1, season: int):
    if season not in _SCHEDULE_CACHE:
        # `ergast` is the only backend that returns every round -- the default
        # silently omits nine of 2024's.
        _SCHEDULE_CACHE[season] = fastf1.get_event_schedule(season, backend="ergast")
    return _SCHEDULE_CACHE[season]


def cache_path(season: int, round_: int, code: str) -> Path:
    return CACHE / f"ff1_{season}_{round_}_{code}.json"


def race_index(seasons: list[int] | None = None) -> list[tuple[int, int, str]]:
    """(season, round, race name) for every race in OUR database from 2018 on.

    Deliberately not FastF1's schedule -- see the module docstring. The name
    rides along because it is the fallback identifier when a round number
    fails to resolve.
    """
    if not DB_PATH.exists():
        raise SystemExit(f"{DB_PATH} not found. Run: python -m backend.etl.build")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT season, round, name FROM races WHERE season >= ? ORDER BY season, round",
            [FIRST_SEASON],
        ).fetchall()
    finally:
        conn.close()
    if seasons:
        wanted = set(seasons)
        rows = [r for r in rows if r[0] in wanted]
    return [(int(s), int(r), n) for s, r, n in rows]


def _seconds(value) -> float | None:
    """A pandas Timedelta as seconds. None stays None.

    Times are stored as seconds rather than the source's Timedelta so the
    value survives JSON and SQLite unchanged. NaT becomes None -- a missing
    sector is missing, never zero, which would be the fastest sector ever set.
    """
    if value is None:
        return None
    try:
        if value != value:  # NaT/NaN is the only value unequal to itself
            return None
        return round(value.total_seconds(), 3)
    except (AttributeError, TypeError):
        return None


def fetch_session(
    season: int, round_: int, code: str, refresh: bool = False, race_name: str | None = None
) -> list[dict]:
    """Every timed lap of one practice session, flattened.

    An empty list is cached too: a session that genuinely recorded no laps
    (a washed-out FP3) is a finding, and caching it stops the next run asking
    forever.
    """
    path = cache_path(season, round_, code)
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))

    fastf1 = _fastf1()
    from fastf1.ergast.interface import ErgastError  # noqa: F401  (import guard)

    for attempt in range(RATE_LIMIT_RETRIES):
        try:
            schedule = _event_schedule(fastf1, season)
            event = schedule[schedule["RoundNumber"] == round_]
            if event.empty:
                # Fall back to the name from our own races table rather than
                # guessing: FastF1 cannot resolve every round number, and 2018
                # round 1 raises where round 2 is fine.
                if not race_name:
                    raise ValueError(f"round {round_} not in the {season} schedule")
                session = fastf1.get_session(season, race_name, SESSIONS[code])
            else:
                session = event.iloc[0].get_session(SESSIONS[code])
            session.load(telemetry=False, weather=False, messages=False)
            break
        except Exception as error:
            # A rate limit is a wait, not an error. Everything else -- a
            # session that was never held, timing that does not exist -- is a
            # fact about the weekend and is raised for the caller to record.
            if type(error).__name__ != "RateLimitExceededError":
                raise
            if attempt == RATE_LIMIT_RETRIES - 1:
                raise
            wait = RATE_LIMIT_BACKOFF_SECONDS * (attempt + 1)
            print(f"    rate limited; waiting {wait}s", flush=True)
            time.sleep(wait)

    rows: list[dict] = []
    for lap in session.laps.itertuples():
        rows.append({
            "season": season,
            "round": round_,
            "session": code,
            # Three-letter code. Every driver who raced from 2018 has one, and
            # they are unique in that window, so this resolves to a slug.
            "driver_code": getattr(lap, "Driver", None),
            "lap": int(lap.LapNumber) if lap.LapNumber == lap.LapNumber else None,
            "stint": int(lap.Stint) if lap.Stint == lap.Stint else None,
            "lap_time": _seconds(lap.LapTime),
            "sector1": _seconds(lap.Sector1Time),
            "sector2": _seconds(lap.Sector2Time),
            "sector3": _seconds(lap.Sector3Time),
            "compound": _text(getattr(lap, "Compound", None)),
            "tyre_life": int(lap.TyreLife) if lap.TyreLife == lap.TyreLife else None,
            "fresh_tyre": bool(lap.FreshTyre) if lap.FreshTyre == lap.FreshTyre else None,
            "speed_trap": _number(getattr(lap, "SpeedST", None)),
            "is_personal_best": bool(lap.IsPersonalBest) if lap.IsPersonalBest == lap.IsPersonalBest else None,
            # A deleted lap is recorded and flagged, never dropped: it happened,
            # and a session's fastest lap depends on knowing which laps stood.
            "deleted": bool(lap.Deleted) if lap.Deleted == lap.Deleted else False,
            # The source's own judgement on whether this lap's timing hangs
            # together. Inaccurate laps are KEPT -- they were driven -- but
            # their sector times do not necessarily reconstruct the lap, so
            # anything asserting that invariant must filter on this.
            "is_accurate": bool(lap.IsAccurate) if lap.IsAccurate == lap.IsAccurate else False,
        })

    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    return rows


def _text(value) -> str | None:
    """A source string, or None.

    pandas hands back the STRINGS "None" and "nan" for missing categorical
    values, not the Python objects. `value or None` does not catch them --
    both are non-empty and therefore truthy -- so they were being stored as
    tyre compounds until a test noticed 'nan' among the compound names.
    """
    if value is None:
        return None
    text = str(value).strip()
    return None if text in {"", "None", "nan", "NaN", "NaT"} else text


def _number(value) -> float | None:
    if value is None:
        return None
    try:
        if value != value:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_failures() -> dict[str, str]:
    """Recorded failures, minus any whose data has since been fetched.

    A failure entry outlives the problem it describes: retry the session, or
    recover it another way, and the file still names it. Reporting three
    failures for sessions that are sitting in the cache is a false alarm, and
    a status that cannot be trusted is worse than none -- so the manifest is
    reconciled against what is actually on disk every time it is read.
    """
    if not FAILURES.exists():
        return {}
    recorded = json.loads(FAILURES.read_text(encoding="utf-8"))
    live = {}
    for key, reason in recorded.items():
        season, round_, code = key.rsplit("-", 2)
        if not cache_path(int(season), int(round_), code).exists():
            live[key] = reason
    return live


def _write_failures(failures: dict[str, str]) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    FAILURES.write_text(json.dumps(failures, indent=1, sort_keys=True), encoding="utf-8")


def status(seasons: list[int] | None = None) -> dict:
    """Cache coverage. Reads nothing from the network."""
    wanted = [
        (season, round_, code)
        for season, round_, _ in race_index(seasons)
        for code in SESSIONS
    ]
    cached = [w for w in wanted if cache_path(*w).exists()]
    empty = [
        w for w in cached
        if not json.loads(cache_path(*w).read_text(encoding="utf-8"))
    ]
    return {
        "sessions": len(wanted),
        "cached": len(cached),
        "remaining": len(wanted) - len(cached),
        "empty": len(empty),
        "failures": len(_read_failures()),
    }


def run(seasons: list[int] | None = None, refresh: bool = False) -> int:
    failures = _read_failures()
    wanted = [
        (season, round_, code, name)
        for season, round_, name in race_index(seasons)
        for code in SESSIONS
    ]
    done = fetched = 0

    for season, round_, code, race_name in wanted:
        key = f"{season}-{round_}-{code}"
        if cache_path(season, round_, code).exists() and not refresh:
            done += 1
            continue
        try:
            rows = fetch_session(season, round_, code, refresh, race_name)
        except Exception as error:  # noqa: BLE001 - recorded, not swallowed
            message = str(error)
            if "does not exist for this event" in message:
                # NOT a failure. Sprint weekends run one practice session
                # instead of three, so FP2 and FP3 genuinely did not happen.
                # Cached empty so it is never asked for again, and so the
                # report distinguishes "was not held" from "could not fetch" --
                # counting these as failures made 14 non-events look like
                # breakage.
                cache_path(season, round_, code).write_text("[]", encoding="utf-8")
                failures.pop(key, None)
                _write_failures(failures)
                print(f"  {key:>16}  not held this weekend", flush=True)
                done += 1
                continue
            failures[key] = f"{type(error).__name__}: {error}"
            _write_failures(failures)
            print(f"  {key:>16}  unavailable  {message[:60]}", flush=True)
            done += 1
            continue

        failures.pop(key, None)
        _write_failures(failures)
        fetched += 1
        done += 1
        print(f"  {key:>16}  {len(rows):>4} laps   ({done}/{len(wanted)})", flush=True)

    report = status(seasons)
    print(
        f"\npractice cache: {report['cached']}/{report['sessions']} sessions "
        f"({fetched} fetched this run, {report['empty']} with no laps, "
        f"{report['failures']} unavailable)",
        flush=True,
    )
    return 0


def main(argv: list[str]) -> int:
    if "--status" in argv:
        print(json.dumps(status([int(a) for a in argv if a.isdigit()] or None), indent=1))
        return 0
    seasons = [int(a) for a in argv if a.isdigit()] or None
    return run(seasons, refresh="--refresh" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
