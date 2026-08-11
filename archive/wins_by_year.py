"""Print the leading constructor of each season.

SUPERSEDED by the web application. Kept because it produced the committed
charts in output/ and documents the project's origin as a set of analysis
scripts.

TERMINOLOGY: this computes *win share* -- wins / races held that season --
which is the same quantity `backend/app/advanced.py` names `win_share`. It is
NOT the application's `win_rate`, which is wins / driver entries. The two
denominators answer different questions and are named differently on purpose.
"""

from f1_utils import load_results

wins, races_per_season = load_results()

for season in sorted(wins.keys()):
    total = races_per_season[season]
    ranked = sorted(wins[season].items(), key=lambda x: -x[1])
    top_constructor, top_wins = ranked[0]
    win_share = 100 * top_wins / total
    print(f"{season}  ({total:2d} races)  leader: {top_constructor:<16s} {top_wins:2d} wins  ({win_share:5.1f}%)")
