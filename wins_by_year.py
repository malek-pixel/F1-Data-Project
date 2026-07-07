import csv
from collections import defaultdict

wins = defaultdict(lambda: defaultdict(int))   # wins[season][constructor] = count
races_per_season = defaultdict(int)

with open("results.csv", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        season = int(row["season"])
        rnd = int(row["round"])
        races_per_season[season] = max(races_per_season[season], rnd)
        if row["position"] != "1":
            continue
        wins[season][row["constructor"]] += 1

for season in sorted(wins.keys()):
    total = races_per_season[season]
    ranked = sorted(wins[season].items(), key=lambda x: -x[1])
    top_constructor, top_wins = ranked[0]
    win_rate = 100 * top_wins / total
    print(f"{season}  ({total:2d} races)  leader: {top_constructor:<16s} {top_wins:2d} wins  ({win_rate:5.1f}%)")
