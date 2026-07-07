import csv
from collections import defaultdict

wins = defaultdict(lambda: defaultdict(int))        # wins[decade][constructor] = count
seasons_in_decade = defaultdict(set)                 # decade -> set of seasons present
races_per_season = defaultdict(int)                  # season -> max round number seen

with open("results.csv", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        season = int(row["season"])
        rnd = int(row["round"])
        decade = (season // 10) * 10
        seasons_in_decade[decade].add(season)
        races_per_season[season] = max(races_per_season[season], rnd)
        if row["position"] != "1":
            continue
        wins[decade][row["constructor"]] += 1

total_races_by_decade = {
    decade: sum(races_per_season[s] for s in seasons)
    for decade, seasons in seasons_in_decade.items()
}

for decade in sorted(wins.keys()):
    num_seasons = len(seasons_in_decade[decade])
    total_races = total_races_by_decade[decade]
    print(f"\n{decade}s  ({num_seasons} seasons, {total_races} races total)")
    ranked = sorted(wins[decade].items(), key=lambda x: -x[1])
    for constructor, count in ranked:
        per_season = count / num_seasons
        win_rate = 100 * count / total_races
        print(f"  {count:3d} wins  ({per_season:4.1f}/season)  ({win_rate:4.1f}% of races)  {constructor}")
