"""Shared data-loading logic for the F1 win-rate analysis scripts."""
import csv
import os
from collections import defaultdict

# Anchored to this file, not the working directory: these scripts live in
# archive/ but read the CSV at the repo root, so they must run from anywhere.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_CSV = os.path.join(REPO_ROOT, "results.csv")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

def load_results(path=RESULTS_CSV, by="constructor"):
    """Parse results.csv once and return the two structures every analysis
    script needs:
    wins[season][<by>]          -> number of race wins, keyed by constructor or driver
    races_per_season[season]    -> total races run that season (max round number)
    """
    wins = defaultdict(lambda: defaultdict(int))
    races_per_season = defaultdict(int)
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            season = int(row["season"])
            rnd = int(row["round"])
            races_per_season[season] = max(races_per_season[season], rnd)
            if row["position"] != "1":
                continue
            wins[season][row[by]] += 1
    return wins, races_per_season

def bucket_by_decade(wins, races_per_season):
    """Roll season-level wins/races up into decade-level totals."""
    decade_wins = defaultdict(lambda: defaultdict(int))
    seasons_in_decade = defaultdict(set)
    for season, group_wins in wins.items():
        decade = (season // 10) * 10
        seasons_in_decade[decade].add(season)
        for key, count in group_wins.items():
            decade_wins[decade][key] += count
    total_races_by_decade = {
        decade: sum(races_per_season[s] for s in seasons)
        for decade, seasons in seasons_in_decade.items()
    }
    return decade_wins, seasons_in_decade, total_races_by_decade