"""Print constructor wins bucketed by decade.

SUPERSEDED by the web application. Kept because it produced the committed
charts in output/ and documents the project's origin as a set of analysis
scripts.

TERMINOLOGY: this computes *win share* -- wins / races held that season --
which is the same quantity `backend/app/advanced.py` names `win_share`. It is
NOT the application's `win_rate`, which is wins / driver entries. The two
denominators answer different questions and are named differently on purpose.
"""

from f1_utils import load_results, bucket_by_decade

wins, races_per_season = load_results()
decade_wins, seasons_in_decade, total_races_by_decade = bucket_by_decade(wins, races_per_season)

for decade in sorted(decade_wins.keys()):
    num_seasons = len(seasons_in_decade[decade])
    total_races = total_races_by_decade[decade]
    print(f"\n{decade}s  ({num_seasons} seasons, {total_races} races total)")
    ranked = sorted(decade_wins[decade].items(), key=lambda x: -x[1])
    for constructor, count in ranked:
        per_season = count / num_seasons
        win_share = 100 * count / total_races
        print(f"  {count:3d} wins  ({per_season:4.1f}/season)  ({win_share:4.1f}% of races)  {constructor}")
