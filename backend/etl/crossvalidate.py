"""Cross-validate the local dataset against an independent authoritative source.

WHY THIS EXISTS
---------------
Every other check in this project proves the database faithfully matches
`results.csv`. None of them prove `results.csv` matches Formula 1. If the CSV
recorded the wrong winner for a race, all 156 tests would still pass.

This module closes that gap for the facts that matter most and are cheapest to
verify. For every race: the **winner**, the **winning constructor**, the
**date** and the **race name**. Then two datasets the integrity audit can only
check structurally, because nothing local can prove them right:

  * **Qualifying P1** -- the pole-sitter of every round, compared driver by
    driver. The audit can prove no race has two qualifying P1s; it cannot
    prove the one it has is the right driver.

  * **Circuit identity** -- checked as a BIJECTION over the whole dataset
    rather than by name, because names legitimately differ between sources
    ("Albert Park Circuit" vs "Albert Park Grand Prix Circuit", "Autodromo
    Nazionale Monza" vs "Autodromo Nazionale di Monza") without being a
    disagreement about which corner of the world the race was held at. What
    must hold is that each source circuit maps to exactly one local circuit
    and back. That is the failure mode `circuit_map.csv` can actually produce
    -- two venues collapsed into one entry, or one venue split across two --
    and it is invisible to a name comparison.

WHAT THIS DOES AND DOES NOT PROVE
---------------------------------
Jolpica is independent of this project's PIPELINE, not of this project's
PROVIDER: the enrichment extracts were fetched from Jolpica in the first
place. So a green run proves that fetching, folding, joining, mapping and
storing did not corrupt anything between the source and the database. It does
not independently confirm Formula 1's own record. That is a real limit and is
stated rather than glossed, because "cross-validated" reads stronger than what
is actually being measured.

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
Three requests per season (78 total), not one per race. `/f1/{year}/results/1`,
`/f1/{year}/qualifying/1` and `/f1/{year}/races` each return every round of a
season in a single response.

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
from backend.etl import build_sessions

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


def say(line: str) -> None:
    """print(), but never crashes on a name it cannot encode.

    Discrepancy lines carry driver and circuit names verbatim, and a Windows
    console running a legacy code page raises UnicodeEncodeError on the first
    accented character -- turning "here is the disagreement I found" into a
    traceback, losing the finding at the exact moment it matters.
    """
    try:
        print(line)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "ascii"
        print(line.encode(encoding, "replace").decode(encoding))


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


def _fetch_season(season: int, resource: str) -> list[dict]:
    """One season of `resource` from the API. The network layer only.

    Deliberately does NOT cache: each caller caches its own SHAPED rows, and
    caching here as well would write two files per season holding the same
    facts, one of which nothing reads. The request settings — timeout, pause,
    User-Agent — live here so the three callers cannot drift apart on them.
    """
    response = requests.get(
        f"{API}/{season}/{resource}.json",
        params={"limit": 100},
        timeout=TIMEOUT_SECONDS,
        headers={"User-Agent": "f1-data-project/crossvalidate"},
    )
    response.raise_for_status()
    races = response.json()["MRData"]["RaceTable"]["Races"]
    time.sleep(PAUSE_SECONDS)
    return races


def fetch_season_poles(season: int, refresh: bool = False) -> list[dict]:
    """Qualifying P1 for every round in `season`. Cached on disk.

    Seasons before 2003 return partial data upstream, and rounds simply
    missing from the response are not treated as a disagreement -- the local
    dataset documents the same gap.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"jolpica_{season}_poles.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))

    races = _fetch_season(season, "qualifying/1")
    rows = [
        {
            "round": int(race["round"]),
            "pole": f"{race['QualifyingResults'][0]['Driver']['givenName']} "
                    f"{race['QualifyingResults'][0]['Driver']['familyName']}",
        }
        for race in races
        if race.get("QualifyingResults")
    ]
    path.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    return rows


def fetch_season_circuits(season: int, refresh: bool = False) -> list[dict]:
    """The circuit each round of `season` was held at. Cached on disk."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"jolpica_{season}_circuits.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))

    races = _fetch_season(season, "races")
    rows = [
        {"round": int(race["round"]), "circuit_id": race["Circuit"]["circuitId"]}
        for race in races
        if race.get("Circuit")
    ]
    path.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    return rows


def fetch_season_sessions(season: int, refresh: bool = False) -> list[dict]:
    """The weekend timetable of every round in `season`. Cached on disk.

    Free, in network terms: the session blocks ride along in the same /races
    response the circuit check already fetches, so this closes a whole
    dataset's verification gap for no extra request.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"jolpica_{season}_sessions.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))

    races = _fetch_season(season, "races")
    rows = []
    for race in races:
        for source_key, code in build_sessions.SESSION_KEYS.items():
            block = race.get(source_key)
            if not block or not block.get("date"):
                continue
            rows.append(
                {
                    "round": int(race["round"]),
                    "session": code,
                    "date": block["date"],
                    "time": block.get("time") or "",
                }
            )
    path.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    return rows


def local_sessions(conn, season: int) -> dict[tuple[int, str], tuple[str, str]]:
    rows = conn.execute(
        """
        SELECT ra.round, s.session, s.date, s.time
        FROM sessions s
        JOIN races ra ON ra.id = s.race_id
        WHERE ra.season = ?
        """,
        [season],
    ).fetchall()
    return {(row["round"], row["session"]): (row["date"], row["time"] or "") for row in rows}


def compare_sessions(conn, season: int, refresh: bool = False) -> tuple[list[Discrepancy], int]:
    """Weekend timetable agreement. Returns (discrepancies, sessions compared).

    Compared exactly, date and start time both. A session listed by the source
    and absent locally is reported: the timetable drives every "when did this
    run" answer in the app, and a missing FP3 is not visible anywhere else --
    the audit can only check that the sessions present point at real races.

    The reverse -- local sessions the source no longer lists -- is also
    reported, because the only way to acquire one is an ingestion bug.

    ONE CAVEAT, stated because it is easy to miss: this reuses
    `build_sessions.SESSION_KEYS`, the same source-key -> session-code mapping
    the ingestion used. So the DATES and TIMES are independently corroborated,
    and the count is complete, but a bug in that seven-entry mapping -- FP2
    stored as FP3, say -- would be invisible here, because both sides would
    make the same substitution. The mapping is short enough to verify by
    reading, which is the only check it gets.
    """
    remote = {
        (row["round"], row["session"]): (row["date"], row["time"])
        for row in fetch_season_sessions(season, refresh)
    }
    local = local_sessions(conn, season)

    found: list[Discrepancy] = []
    for key in sorted(set(remote) | set(local)):
        round_, code = key
        if key not in local:
            found.append(Discrepancy(season, round_, f"{code} missing", "--", remote[key][0]))
            continue
        if key not in remote:
            found.append(Discrepancy(season, round_, f"{code} extra", local[key][0], "--"))
            continue
        if local[key] != remote[key]:
            found.append(
                Discrepancy(
                    season, round_, code,
                    " ".join(local[key]).strip(), " ".join(remote[key]).strip(),
                )
            )
    return found, len(set(remote) & set(local))


def local_poles(conn, season: int) -> dict[int, str]:
    rows = conn.execute(
        """
        SELECT ra.round, d.name AS pole
        FROM qualifying_results q
        JOIN races ra   ON ra.id = q.race_id
        JOIN drivers d  ON d.id  = q.driver_id
        WHERE ra.season = ? AND q.position = 1
        ORDER BY ra.round
        """,
        [season],
    ).fetchall()
    return {row["round"]: row["pole"] for row in rows}


def local_circuits(conn, season: int) -> dict[int, str]:
    rows = conn.execute(
        """
        SELECT ra.round, ci.slug
        FROM races ra
        JOIN circuits ci ON ci.id = ra.circuit_id
        WHERE ra.season = ?
        ORDER BY ra.round
        """,
        [season],
    ).fetchall()
    return {row["round"]: row["slug"] for row in rows}


def compare_poles(conn, season: int, refresh: bool = False) -> tuple[list[Discrepancy], int]:
    """Pole-sitter agreement for one season. Returns (discrepancies, compared).

    A round the SOURCE does not carry is skipped, not failed: qualifying is
    genuinely partial upstream before 2003. A round the source carries and the
    LOCAL dataset does not is a real gap and is reported, because that is data
    the ingestion should have picked up.
    """
    remote = {row["round"]: row["pole"] for row in fetch_season_poles(season, refresh)}
    local = local_poles(conn, season)

    found: list[Discrepancy] = []
    compared = 0
    for round_, pole in sorted(remote.items()):
        if round_ not in local:
            found.append(Discrepancy(season, round_, "pole missing", "--", pole))
            continue
        compared += 1
        if fold(local[round_]) != fold(pole):
            found.append(Discrepancy(season, round_, "pole", local[round_], pole))
    return found, compared


def collect_circuit_pairs(conn, season: int, refresh: bool = False) -> tuple[list[Discrepancy], set]:
    """(source circuit, local circuit) for every round. Returns (gaps, pairs).

    The bijection is asserted across all seasons at once, so this only gathers
    pairs -- a venue used in several seasons must produce the same pair every
    time, and a set collapses that naturally.
    """
    remote = {row["round"]: row["circuit_id"] for row in fetch_season_circuits(season, refresh)}
    local = local_circuits(conn, season)

    found: list[Discrepancy] = []
    pairs: set = set()
    for round_, circuit_id in sorted(remote.items()):
        if round_ not in local:
            found.append(Discrepancy(season, round_, "circuit missing", "--", circuit_id))
            continue
        pairs.add((circuit_id, local[round_]))
    return found, pairs


# Splits where the LOCAL dataset is deliberately finer than the source.
#
# Jolpica identifies a circuit by venue. This project identifies it by
# CONFIGURATION, because a lap of one is not a lap of the other -- different
# length, different corner count, different lap record. Where the two models
# disagree and the local one is the more precise, the split is recorded here
# rather than flattened to make a check pass.
#
# Removing an entry must mean the split itself was wrong, never that the check
# was inconvenient.
KNOWN_CONFIGURATION_SPLITS: dict[str, set[str]] = {
    # The 2020 Sakhir Grand Prix ran on the Bahrain Outer Circuit: 3.543 km
    # against the full track's 5.412 km, and the shortest lap in modern F1.
    # Jolpica files both under circuitId 'bahrain'. Merging them here would
    # put both races on one circuit page and let a "record at this circuit"
    # compare lap times set on two different tracks.
    "bahrain": {"bahrain", "bahrain-outer"},
}


def circuit_bijection_failures(pairs: set) -> list[str]:
    """Every source circuit maps to one local circuit, and every local to one
    source circuit.

    Both directions matter and they fail differently. One source circuit
    reaching two local circuits means a venue was split -- its records are now
    divided across two profile pages. Two source circuits reaching one local
    circuit means distinct venues were merged, and a driver's "record at this
    circuit" silently spans both. `circuit_map.csv` is hand-written, so both
    are live possibilities every time a season is added.
    """
    forward: dict[str, set] = {}
    backward: dict[str, set] = {}
    for source, local in pairs:
        forward.setdefault(source, set()).add(local)
        backward.setdefault(local, set()).add(source)

    problems = []
    for source, locals_ in sorted(forward.items()):
        if len(locals_) > 1 and KNOWN_CONFIGURATION_SPLITS.get(source) == locals_:
            continue
        if len(locals_) > 1:
            problems.append(
                f"  source circuit {source!r} is split across local circuits "
                f"{sorted(locals_)}"
            )
    for local, sources in sorted(backward.items()):
        if len(sources) > 1:
            problems.append(
                f"  local circuit {local!r} merges source circuits {sorted(sources)}"
            )
    return problems


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
        say(f"Database not found at {DB_PATH}. Run: python -m backend.etl.build")
        return 1

    conn = connect()
    try:
        if args.season:
            seasons = [args.season]
        else:
            seasons = [r[0] for r in conn.execute("SELECT DISTINCT season FROM races ORDER BY season")]

        all_found: list[Discrepancy] = []
        compared = 0
        poles_compared = 0
        sessions_compared = 0
        circuit_pairs: set = set()

        for season in seasons:
            found, n = compare_season(conn, season, args.refresh)
            pole_found, pole_n = compare_poles(conn, season, args.refresh)
            circuit_found, pairs = collect_circuit_pairs(conn, season, args.refresh)
            session_found, session_n = compare_sessions(conn, season, args.refresh)

            compared += n
            poles_compared += pole_n
            sessions_compared += session_n
            circuit_pairs |= pairs
            season_found = found + pole_found + circuit_found + session_found
            all_found.extend(season_found)

            flag = "FAIL" if season_found else "ok  "
            say(f"{flag}  {season}  {n:>2} races  {pole_n:>2} poles  "
                f"{session_n:>3} sessions  {len(season_found)} discrepancies")
    finally:
        conn.close()

    # Asserted over the whole dataset, not per season: a venue is only split or
    # merged relative to the other seasons that used it.
    bijection = circuit_bijection_failures(circuit_pairs)

    say("")
    say(f"{compared} races cross-validated against Jolpica-F1 "
        f"(winner, constructor, date, race name).")
    say(f"{poles_compared} qualifying P1s cross-validated.")
    say(f"{sessions_compared} weekend sessions cross-validated (date and start time).")
    say(f"{len(circuit_pairs)} circuit assignments checked for a 1:1 mapping.")

    if all_found or bijection:
        say(f"\n{len(all_found) + len(bijection)} DISCREPANCIES -- "
            f"investigate, do not auto-apply:\n")
        for d in all_found:
            say(str(d))
        for problem in bijection:
            say(problem)
        return 1

    say("0 discrepancies.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
