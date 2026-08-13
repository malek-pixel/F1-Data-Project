"""Cross-validate the local dataset against an independent authoritative source.

WHY THIS EXISTS
---------------
Every other check in this project proves the database faithfully matches
`results.csv`. None of them prove `results.csv` matches Formula 1. If the CSV
recorded the wrong winner for a race, all 156 tests would still pass.

This module closes that gap for the facts that matter most and are cheapest to
verify: for every race, the **winner**, the **winning constructor**, the
**date** and the **race name**.

SOURCE
------
Jolpica-F1 (`api.jolpi.ca`), the maintained successor to the retired Ergast
API. It is an independent materialisation of the historical record, so
agreement is genuine corroboration rather than a file compared with itself.

It is *not* infallible and is not treated as such: a disagreement is reported
as a **discrepancy to investigate**, never auto-applied. Deciding which side is
right is a human judgement that needs evidence, per the project's rule that
conflicts are investigated and documented rather than silently resolved.

COST
----
One request per season (26 total), not one per race. `/f1/{year}/results/1`
returns every round's winner for that season in a single response.

Responses are cached under `data/cache/` so re-runs are free and reproducible.
Delete that directory to force a refetch.

Run:  python -m backend.etl.crossvalidate            (all seasons)
      python -m backend.etl.crossvalidate --season 2008
      python -m backend.etl.crossvalidate --refresh  (ignore cache)
Exit: 0 when no discrepancy is found, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import requests

from backend.app.db import DB_PATH, connect

API = "https://api.jolpi.ca/ergast/f1"
CACHE = Path(__file__).resolve().parents[2] / "data" / "cache"

# Jolpica asks for <=4 requests/second unauthenticated. One season per request
# and a deliberate pause keeps this well inside that, and well inside the
# hourly budget.
PAUSE_SECONDS = 0.35
TIMEOUT_SECONDS = 30


@dataclass
class Discrepancy:
    season: int
    round_: int
    field: str
    local: str
    remote: str

    def __str__(self) -> str:
        return (
            f"  {self.season} R{self.round_:<2} {self.field:<12} "
            f"local={self.local!r}  source={self.remote!r}"
        )


def fold(name: str) -> str:
    """Normalise a name for comparison only -- never for storage.

    Accents and case differ between sources ("Antonio" vs "Antônio") without
    being a factual disagreement. Comparison folds them; the stored value is
    left exactly as the source wrote it.
    """
    stripped = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in stripped if not unicodedata.combining(c))
    return " ".join(stripped.lower().replace("-", " ").split())


def fetch_season_winners(season: int, refresh: bool = False) -> list[dict]:
    """Winner of every round in `season`, from the source. Cached on disk."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"jolpica_{season}_winners.json"

    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))

    response = requests.get(
        f"{API}/{season}/results/1.json",
        params={"limit": 100},
        timeout=TIMEOUT_SECONDS,
        headers={"User-Agent": "f1-data-project/crossvalidate"},
    )
    response.raise_for_status()
    races = response.json()["MRData"]["RaceTable"]["Races"]

    rows = [
        {
            "round": int(race["round"]),
            "race_name": race["raceName"],
            "date": race["date"],
            "winner": f"{race['Results'][0]['Driver']['givenName']} "
                      f"{race['Results'][0]['Driver']['familyName']}",
            "constructor": race["Results"][0]["Constructor"]["name"],
        }
        for race in races
        if race.get("Results")
    ]
    path.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    time.sleep(PAUSE_SECONDS)
    return rows


def local_winners(conn, season: int) -> dict[int, dict]:
    rows = conn.execute(
        """
        SELECT ra.round, ra.name AS race_name, ra.date,
               d.name AS winner, c.name AS constructor
        FROM results r
        JOIN races ra        ON ra.id = r.race_id
        JOIN drivers d       ON d.id  = r.driver_id
        JOIN constructors c  ON c.id  = r.constructor_id
        WHERE ra.season = ? AND r.position = 1
        ORDER BY ra.round
        """,
        [season],
    ).fetchall()
    return {row["round"]: dict(row) for row in rows}


def compare_season(conn, season: int, refresh: bool = False) -> tuple[list[Discrepancy], int]:
    """Returns (discrepancies, races_compared)."""
    remote = {row["round"]: row for row in fetch_season_winners(season, refresh)}
    local = local_winners(conn, season)

    found: list[Discrepancy] = []

    for round_ in sorted(set(local) | set(remote)):
        if round_ not in local:
            r = remote[round_]
            found.append(Discrepancy(season, round_, "race missing", "--", r["race_name"]))
            continue
        if round_ not in remote:
            found.append(Discrepancy(season, round_, "extra race", local[round_]["race_name"], "--"))
            continue

        a, b = local[round_], remote[round_]

        # Winner and constructor are compared folded: an accent difference is
        # not a factual disagreement.
        if fold(a["winner"]) != fold(b["winner"]):
            found.append(Discrepancy(season, round_, "winner", a["winner"], b["winner"]))
        if fold(a["constructor"]) != fold(b["constructor"]):
            found.append(
                Discrepancy(season, round_, "constructor", a["constructor"], b["constructor"])
            )
        # Dates are compared exactly. A one-day difference is a real conflict
        # worth seeing, not noise to absorb.
        if a["date"] != b["date"]:
            found.append(Discrepancy(season, round_, "date", a["date"], b["date"]))
        if fold(a["race_name"]) != fold(b["race_name"]):
            found.append(
                Discrepancy(season, round_, "race name", a["race_name"], b["race_name"])
            )

    return found, len(set(local) & set(remote))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, help="check one season only")
    parser.add_argument("--refresh", action="store_true", help="ignore the cache")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}. Run: python -m backend.etl.build")
        return 1

    conn = connect()
    try:
        if args.season:
            seasons = [args.season]
        else:
            seasons = [r[0] for r in conn.execute("SELECT DISTINCT season FROM races ORDER BY season")]

        all_found: list[Discrepancy] = []
        compared = 0

        for season in seasons:
            found, n = compare_season(conn, season, args.refresh)
            compared += n
            all_found.extend(found)
            flag = "FAIL" if found else "ok  "
            print(f"{flag}  {season}  {n:>2} races  {len(found)} discrepancies")
    finally:
        conn.close()

    print()
    print(f"{compared} races cross-validated against Jolpica-F1 "
          f"(winner, constructor, date, race name).")

    if all_found:
        print(f"\n{len(all_found)} DISCREPANCIES -- investigate, do not auto-apply:\n")
        for d in all_found:
            print(d)
        return 1

    print("0 discrepancies.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
