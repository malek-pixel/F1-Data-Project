"""Turn cached practice-session JSON into one committed CSV.

Same boundary as build_laps: the per-session files under `data/cache/practice`
are untracked network artefacts, and this produces the tracked, checksummed
artefact the build actually loads.

DRIVER IDENTITY
---------------
FastF1 identifies a driver by three-letter code ("VER"), which this project's
`drivers` table also carries. Every driver who raced from 2018 has one and
they are unique across that window, so the mapping is exact -- verified before
this was written rather than assumed.

A code that does not resolve is reported, never guessed. Test drivers appear
in practice who never start a race, so they have no row in `drivers` at all;
those laps are counted and excluded rather than silently attached to whoever
happens to share a code.

Run:  python -m backend.etl.build_practice
"""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from backend.etl.practice import SESSIONS, cache_path, race_index

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data" / "f1.db"
OUT_CSV = REPO_ROOT / "data" / "fastf1_practice_laps.csv"

FIELDS = [
    "season", "round", "session", "driver_slug", "lap", "stint",
    "lap_time", "sector1", "sector2", "sector3",
    "compound", "tyre_life", "fresh_tyre", "speed_trap",
    "is_personal_best", "deleted", "is_accurate",
]


def driver_codes() -> dict[str, str]:
    """three-letter code -> driver slug, for drivers who raced from 2018."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT d.abbreviation, d.slug
            FROM drivers d
            JOIN results r ON r.driver_id = d.id
            JOIN races ra  ON ra.id = r.race_id
            WHERE ra.season >= 2018 AND d.abbreviation IS NOT NULL
            """
        ).fetchall()
    finally:
        conn.close()
    return {code: slug for code, slug in rows}


def collect(seasons: list[int] | None = None) -> tuple[list[dict], list[str], Counter]:
    codes = driver_codes()
    rows: list[dict] = []
    problems: list[str] = []
    unresolved: Counter = Counter()
    missing_sessions = 0

    for season, round_, _ in race_index(seasons):
        for code in SESSIONS:
            path = cache_path(season, round_, code)
            if not path.exists():
                missing_sessions += 1
                continue
            for lap in json.loads(path.read_text(encoding="utf-8")):
                slug = codes.get(lap["driver_code"])
                if slug is None:
                    # A practice-only driver. Real, and deliberately not
                    # invented into the drivers table: this database's drivers
                    # are people who started a race.
                    unresolved[lap["driver_code"]] += 1
                    continue
                rows.append({
                    "season": lap["season"],
                    "round": lap["round"],
                    "session": lap["session"],
                    "driver_slug": slug,
                    "lap": lap["lap"] or "",
                    "stint": lap["stint"] or "",
                    "lap_time": lap["lap_time"] or "",
                    "sector1": lap["sector1"] or "",
                    "sector2": lap["sector2"] or "",
                    "sector3": lap["sector3"] or "",
                    "compound": lap["compound"] or "",
                    "tyre_life": "" if lap["tyre_life"] is None else lap["tyre_life"],
                    "fresh_tyre": "" if lap["fresh_tyre"] is None else int(lap["fresh_tyre"]),
                    "speed_trap": lap["speed_trap"] or "",
                    "is_personal_best": "" if lap["is_personal_best"] is None else int(lap["is_personal_best"]),
                    "deleted": int(lap["deleted"]),
                    "is_accurate": int(lap.get("is_accurate", 0)),
                })

    if missing_sessions:
        problems.append(f"{missing_sessions} sessions not cached (fetch incomplete)")
    return rows, problems, unresolved


def main(argv: list[str]) -> int:
    seasons = [int(a) for a in argv if a.isdigit()] or None
    rows, problems, unresolved = collect(seasons)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    digest = hashlib.sha256(OUT_CSV.read_bytes()).hexdigest()
    sessions = len({(r["season"], r["round"], r["session"]) for r in rows})
    print(f"  {OUT_CSV.name:<30} {len(rows):>7,} laps  {sessions} sessions  sha256 {digest[:16]}")

    for problem in problems:
        print(f"  [WARNING] {problem}")
    if unresolved:
        # Named, not hidden. These are practice-only participants -- reserve
        # and test drivers who never started a race -- and the count is the
        # evidence that the exclusion is small and explicable rather than a
        # broken mapping.
        total = sum(unresolved.values())
        top = ", ".join(f"{code} ({n})" for code, n in unresolved.most_common(6))
        print(f"  [WARNING] {total:,} laps by {len(unresolved)} drivers with no race entry: {top}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
