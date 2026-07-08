from f1_utils import load_results, bucket_by_decade

wins, races_per_season = load_results(by="driver")
decade_wins, seasons_in_decade, total_races_by_decade = bucket_by_decade(wins, races_per_season)

for decade in sorted(decade_wins.keys()):
    num_seasons = len(seasons_in_decade[decade])
    total_races = total_races_by_decade[decade]
    print(f"\n{decade}s  ({num_seasons} seasons, {total_races} races total)")
    ranked = sorted(decade_wins[decade].items(), key=lambda x: -x[1])[:15]
    for driver, count in ranked:
        per_season = count / num_seasons
        win_rate = 100 * count / total_races
        print(f"  {count:3d} wins  ({per_season:4.1f}/season)  ({win_rate:4.1f}% of races)  {driver}")