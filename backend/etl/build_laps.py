"""Turn the cached per-race lap JSON into one committed CSV.

Every other dataset in this project is committed as a CSV so a fresh clone
rebuilds the identical database offline, with a SHA-256 recorded for what was
loaded. Lap times are no different in principle, only in size: roughly half a
million rows across the covered seasons.

The per-race JSON under `data/cache/` is deliberately untracked -- it is a
network artefact, one file per race, shaped for resumability rather than for
review. This module is the boundary between that and the tracked artefact.

Times are parsed here rather than at load. "1:39.019" is the source's own
string and is kept verbatim, but sorting on it is wrong (it is text), so the
millisecond value is derived once, in one place, and a string that will not
parse is reported rather than coerced.

Run:  python -m backend.etl.build_laps
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from pathlib import Path

from backend.etl.laps import cache_path, race_index

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_CSV = REPO_ROOT / "data" / "jolpica_laptimes.csv"

FIELDS = ["season", "round", "driver_id", "lap", "position", "time", "time_ms"]

# m:ss.mmm is the only shape lap timings take in this source. h:mm:ss.mmm is
# not matched on purpose: a lap that long does not exist, so a string of that
# shape means something is wrong and should be reported, not parsed.
_LAP_TIME = re.compile(r"^(?:(\d+):)?(\d{1,2})\.(\d{1,3})$")


def parse_lap_time(value: str) -> int | None:
    """"1:39.019" -> 99019 milliseconds. None when it does not parse.

    None is a finding, not a default. A lap time that silently became 0 would
    be the fastest lap in every query that touched it.
    """
    match = _LAP_TIME.match((value or "").strip())
    if not match:
        return None
    minutes, seconds, millis = match.groups()
    return (
        int(minutes or 0) * 60_000
        + int(seconds) * 1_000
        + int(millis.ljust(3, "0"))
    )


def collect(seasons: list[int] | None = None) -> tuple[list[dict], list[str]]:
    """All cached lap rows, plus a list of problems worth reporting."""
    problems: list[str] = []
    rows: list[dict] = []
    missing = 0

    for season, round_ in race_index(seasons):
        path = cache_path(season, round_)
        if not path.exists():
            missing += 1
            continue
        for row in json.loads(path.read_text(encoding="utf-8")):
            millis = parse_lap_time(row["time"])
            if millis is None:
                problems.append(
                    f"{season} R{round_} {row['driver_id']} lap {row['lap']}: "
                    f"unparseable time {row['time']!r}"
                )
            rows.append({
                "season": season,
                "round": round_,
                "driver_id": row["driver_id"],
                "lap": row["lap"],
                "position": row.get("position") or "",
                "time": row["time"],
                "time_ms": "" if millis is None else millis,
            })

    if missing:
        # Stated, not hidden: a partial cache produces a partial CSV, and the
        # difference between "these races have no laps" and "these races were
        # never fetched" must survive into the report.
        problems.append(f"{missing} races have no cached lap file (fetch incomplete)")
    return rows, problems


def main(argv: list[str]) -> int:
    seasons = [int(a) for a in argv if a.isdigit()] or None
    rows, problems = collect(seasons)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    digest = hashlib.sha256(OUT_CSV.read_bytes()).hexdigest()
    races = len({(r["season"], r["round"]) for r in rows})
    print(f"  {OUT_CSV.name:<28} {len(rows):>7,} rows  {races} races  sha256 {digest[:16]}")

    unparseable = [p for p in problems if "unparseable" in p]
    for problem in problems[:10]:
        print(f"  [WARNING] {problem}")
    if len(problems) > 10:
        print(f"  ... and {len(problems) - 10} more")
    # Unparseable times are a data problem and fail the step; an incomplete
    # cache is expected mid-fetch and is only reported.
    return 1 if unparseable else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
