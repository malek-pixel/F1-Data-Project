from f1_utils import load_results

wins, races_per_season = load_results()

for season in sorted(wins.keys()):
    total = races_per_season[season]
    ranked = sorted(wins[season].items(), key=lambda x: -x[1])
    top_constructor, top_wins = ranked[0]
    win_rate = 100 * top_wins / total
    print(f"{season}  ({total:2d} races)  leader: {top_constructor:<16s} {top_wins:2d} wins  ({win_rate:5.1f}%)")
