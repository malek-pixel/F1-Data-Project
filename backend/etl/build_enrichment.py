"""Write the Jolpica enrichment to a committed, checksummed CSV.

WHY A FILE, NOT A DIRECT LOAD
-----------------------------
`results.csv` is this project's pinned source of truth and its SHA-256 is
recorded as provenance. Adding columns to it would change those bytes and
break that chain.

So the enrichment becomes a *second* source artefact with its own checksum,
joined to the original on `(season, round, position)` -- a key verified to
align across all 10,550 rows with zero mismatches before this file was ever
written. Both the SQLite build and the Supabase import read it, so the two
stores stay materialisations of the same bytes rather than of two separate
network fetches that could drift.

It is written from the on-disk cache under `data/cache/`, so regenerating it
does not re-hit the network unless the cache is cleared.

Columns
-------
season, round, position    join key into results.csv
position_text              R / W / D / a number. THE classification signal.
classification             derived from position_text, by the documented rule
status                     raw source text, 104 distinct values, never collapsed
points                     championship points awarded for this result
grid                       starting position; 0 means PIT LANE START, not unknown
laps                       laps completed

Run:  python -m backend.etl.build_enrichment
"""

from __future__ import annotations

import csv
import hashlib
import sys
from pathlib import Path

from backend.etl.jolpica import fetch_all

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "data" / "jolpica_results.csv"

SEASONS = list(range(2000, 2026))

FIELDS = [
    "season", "round", "position", "position_text", "classification",
    "status", "points", "grid", "laps",
]


def classify(position_text: str) -> str:
    """Map the source's positionText to a classification category.

    This is the one transformation in the enrichment, so it is spelled out
    rather than buried:

        a number -> "classified"     the driver was classified at that position
        "R"      -> "retired"        did not finish and was not classified
        "D"      -> "disqualified"   excluded from the results
        "W"      -> "withdrawn"      entered but did not take part

    Note that "classified" is NOT the same as "finished": a driver several laps
    down is classified. Whether they saw the flag is in `status`, which is kept
    raw precisely so this distinction is never lost.
    """
    if position_text.isdigit():
        return "classified"
    return {"R": "retired", "D": "disqualified", "W": "withdrawn"}[position_text]


def build() -> list[dict]:
    rows = fetch_all(SEASONS, progress=False)
    out = []
    for row in rows:
        out.append({
            "season": row["season"],
            "round": row["round"],
            "position": row["position"],
            "position_text": row["position_text"],
            "classification": classify(row["position_text"]),
            "status": row["status"],
            "points": row["points"],
            "grid": row["grid"],
            "laps": row["laps"],
        })
    out.sort(key=lambda r: (r["season"], r["round"], r["position"]))
    return out


def main() -> int:
    rows = build()

    # newline="" + \n keeps the file byte-identical on Windows and POSIX, so
    # the checksum below means the same thing on both.
    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    digest = hashlib.sha256(OUT.read_bytes()).hexdigest()
    print(f"wrote {len(rows):,} rows -> {OUT}")
    print(f"sha256 {digest}")

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["classification"]] = counts.get(row["classification"], 0) + 1
    for name, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {name:<14}{count:>6}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
