"""Write the race-weekend session timetable to a committed CSV.

WHAT THIS IS, AND WHAT IT IS NOT
--------------------------------
This is the *timetable*: when FP1, FP2, FP3, qualifying and the sprint were
scheduled. It is not practice results. Nothing in this file carries a
classification, a lap time or a driver -- because the source has none.

That distinction matters enough to state twice, because "practice sessions"
sounds like it means practice classifications. The Ergast-compatible API this
project ingests from has no practice results endpoint at all (`/practice`,
`/fp1` and `/sessions` return 400 or 404). Practice classifications exist only
in F1's live-timing feed, reachable through a different library with different
provenance and a 2018 start; adopting it is a separate decision, not something
to slip in behind a column named `practice`.

So this module ingests the part that genuinely exists, and the absence of the
rest stays visible rather than being papered over with an empty table that
looks like it should have rows.

COVERAGE
--------
Session times begin in 2006. Earlier seasons in the covered window carry a
race date and nothing else -- a real gap in the source, recorded as such.

Reads only `data/cache/*_schedule.json`, already fetched by
`build_dimensions`, so this needs no network.

Run:  python -m backend.etl.build_sessions
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE = REPO_ROOT / "data" / "cache"
OUT_CSV = REPO_ROOT / "data" / "jolpica_sessions.csv"

FIELDS = ["season", "round", "session", "date", "time"]

# The source's key -> this project's session code. Ordered as the weekend
# runs, which is the order the CSV is written in.
#
# `SprintShootout` (2023) and `SprintQualifying` (2024-) are the same session
# under two names: F1 renamed it. They are stored under one code so a query
# for the sprint's qualifying session does not have to know which season it is
# asking about -- and the rename is recorded here rather than in every caller.
SESSION_KEYS = {
    "FirstPractice": "fp1",
    "SecondPractice": "fp2",
    "ThirdPractice": "fp3",
    "SprintShootout": "sprint_qualifying",
    "SprintQualifying": "sprint_qualifying",
    "Sprint": "sprint",
    "Qualifying": "qualifying",
}

ORDER = ["fp1", "fp2", "fp3", "sprint_qualifying", "sprint", "qualifying"]


def collect() -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    problems: list[str] = []
    seen: set[tuple[int, int, str]] = set()

    for path in sorted(CACHE.glob("jolpica_*_schedule.json")):
        for race in json.loads(path.read_text(encoding="utf-8")):
            season, round_ = int(race["season"]), int(race["round"])
            for source_key, code in SESSION_KEYS.items():
                session = race.get(source_key)
                if not session or not session.get("date"):
                    continue
                key = (season, round_, code)
                if key in seen:
                    # Both names for the sprint's qualifying session appearing
                    # on one weekend would mean the rename assumption above is
                    # wrong. Report it rather than letting one overwrite the
                    # other.
                    problems.append(f"{season} R{round_}: duplicate session {code}")
                    continue
                seen.add(key)
                rows.append({
                    "season": season,
                    "round": round_,
                    "session": code,
                    "date": session["date"],
                    "time": session.get("time") or "",
                })

    rows.sort(key=lambda r: (r["season"], r["round"], ORDER.index(r["session"])))
    return rows, problems


def main() -> int:
    rows, problems = collect()
    if not rows:
        print("  no schedule cache found; run: python -m backend.etl.build_dimensions")
        return 1

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    digest = hashlib.sha256(OUT_CSV.read_bytes()).hexdigest()
    seasons = {r["season"] for r in rows}
    print(f"  {OUT_CSV.name:<28} {len(rows):>6,} rows  "
          f"{min(seasons)}-{max(seasons)}  sha256 {digest[:16]}")
    for problem in problems:
        print(f"  [WARNING] {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
