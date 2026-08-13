"""Write descriptive driver, constructor and circuit data to committed CSVs.

The dimension tables were created with columns a future source would fill --
`drivers.nationality`, `drivers.date_of_birth`, `circuits.latitude` -- and left
NULL, honestly meaning "not yet known". Jolpica-F1 is that source.

Three files, each a checksummed artefact like the results enrichment:

    data/jolpica_drivers.csv       nationality, date of birth, code, number
    data/jolpica_constructors.csv  nationality
    data/jolpica_circuits.csv      official name, locality, country, lat/long

CIRCUIT MATCHING IS DERIVED, NOT GUESSED
----------------------------------------
This project's circuit slugs come from a curated `circuit_map.csv`; Jolpica has
its own `circuitId`. Matching them by name would be a guess, and the names
differ ("Autodromo Enzo e Dino Ferrari" vs "Imola").

Instead the mapping is derived from race associations: for every (season,
round) both sides already agree on -- verified across all 503 races -- take
this project's circuit and Jolpica's circuit for that race. If the resulting
relation is not one-to-one, the build FAILS rather than picking a winner.

Still not available anywhere in this source, and therefore still NULL:
circuit length, number of corners, and lap records.

Run:  python -m backend.etl.build_dimensions
"""

from __future__ import annotations

import csv
import hashlib
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import requests

from backend.etl.jolpica import CACHE, PAUSE_SECONDS, TIMEOUT_SECONDS, USER_AGENT, fetch_all

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA = REPO_ROOT / "data"
SEASONS = list(range(2000, 2026))


def _write(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f"  {path.name:<32} {len(rows):>4} rows  sha256 {digest[:16]}")


def build_drivers(rows: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for row in rows:
        seen.setdefault(row["driver"], row)
    out = [
        {
            "driver": name,
            # The source's own stable id. Committed here because pit stops
            # (and any future per-driver endpoint) key on it, and resolving it
            # from the network cache at load time would make ingestion depend
            # on a cache that is deliberately not tracked.
            "jolpica_driver_id": row["driver_id"] or "",
            "nationality": row["driver_nationality"] or "",
            "date_of_birth": row["driver_dob"] or "",
            # Absent for drivers who raced before three-letter codes and
            # permanent numbers existed. Empty here becomes NULL on load --
            # genuinely unknown, not a blank string.
            "abbreviation": row["driver_code"] or "",
            "permanent_number": row["permanent_number"] or "",
        }
        for name, row in sorted(seen.items())
    ]
    return out


def build_constructors(rows: list[dict]) -> list[dict]:
    seen: dict[str, str] = {}
    for row in rows:
        seen.setdefault(row["constructor"], row["constructor_nationality"] or "")
    return [{"constructor": k, "nationality": v} for k, v in sorted(seen.items())]


def fetch_race_circuits(season: int) -> dict[int, dict]:
    """(round -> circuit) for one season, from the schedule endpoint."""
    import json
    import time

    path = CACHE / f"jolpica_{season}_schedule.json"
    if path.exists():
        races = json.loads(path.read_text(encoding="utf-8"))
    else:
        response = requests.get(
            f"https://api.jolpi.ca/ergast/f1/{season}.json",
            params={"limit": 100},
            timeout=TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
        races = response.json()["MRData"]["RaceTable"]["Races"]
        path.write_text(json.dumps(races, indent=1, ensure_ascii=False), encoding="utf-8")
        time.sleep(PAUSE_SECONDS)
    return {int(r["round"]): r["Circuit"] for r in races}


def build_circuits(db: Path) -> list[dict]:
    """Map this project's circuit slugs to Jolpica circuits via shared races."""
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    local = conn.execute(
        "SELECT ra.season, ra.round, c.slug FROM races ra JOIN circuits c ON c.id = ra.circuit_id"
    ).fetchall()
    conn.close()

    pairs: dict[str, set[str]] = defaultdict(set)
    circuits: dict[str, dict] = {}
    for season in SEASONS:
        schedule = fetch_race_circuits(season)
        for row in local:
            if row["season"] != season:
                continue
            circuit = schedule.get(row["round"])
            if circuit is None:
                continue
            pairs[row["slug"]].add(circuit["circuitId"])
            circuits[circuit["circuitId"]] = circuit

    ambiguous = {slug: ids for slug, ids in pairs.items() if len(ids) != 1}
    if ambiguous:
        raise SystemExit(
            "circuit mapping is not one-to-one; refusing to guess:\n"
            + "\n".join(f"  {slug} -> {sorted(ids)}" for slug, ids in ambiguous.items())
        )

    out = []
    for slug, ids in sorted(pairs.items()):
        circuit = circuits[next(iter(ids))]
        location = circuit["Location"]
        out.append({
            "circuit_key": slug,
            "jolpica_circuit_id": circuit["circuitId"],
            "official_name": circuit["circuitName"],
            "locality": location.get("locality", ""),
            "country": location.get("country", ""),
            "latitude": location.get("lat", ""),
            "longitude": location.get("long", ""),
            "source_url": circuit.get("url", ""),
        })
    return out


def main() -> int:
    print("building dimension enrichment...")
    rows = fetch_all(SEASONS, progress=False)

    _write(DATA / "jolpica_drivers.csv", build_drivers(rows),
           ["driver", "jolpica_driver_id", "nationality", "date_of_birth",
            "abbreviation", "permanent_number"])
    _write(DATA / "jolpica_constructors.csv", build_constructors(rows),
           ["constructor", "nationality"])

    db = REPO_ROOT / "data" / "f1.db"
    if not db.exists():
        print("  skipping circuits: data/f1.db not built")
        return 1
    _write(DATA / "jolpica_circuits.csv", build_circuits(db),
           ["circuit_key", "jolpica_circuit_id", "official_name", "locality",
            "country", "latitude", "longitude", "source_url"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
