"""Shared data-loading logic for the F1 win-rate analysis scripts."""

import csv
from collections import defaultdict


def load_results(path="results.csv"):
    """Parse results.csv once and return the two structures every analysis
    script needs:

    wins[season][constructor]   -> number of race wins
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
            wins[season][row["constructor"]] += 1

    return wins, races_per_season


def bucket_by_decade(wins, races_per_season):
    """Roll season-level wins/races up into decade-level totals."""
    decade_wins = defaultdict(lambda: defaultdict(int))
    seasons_in_decade = defaultdict(set)

    for season, constructor_wins in wins.items():
        decade = (season // 10) * 10
        seasons_in_decade[decade].add(season)
        for constructor, count in constructor_wins.items():
            decade_wins[decade][constructor] += count

    total_races_by_decade = {
        decade: sum(races_per_season[s] for s in seasons)
        for decade, seasons in seasons_in_decade.items()
    }

    return decade_wins, seasons_in_decade, total_races_by_decade
