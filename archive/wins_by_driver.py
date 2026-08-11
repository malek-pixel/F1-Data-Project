"""Print driver wins bucketed by decade.

SUPERSEDED by the web application. Kept because it produced the committed
charts in output/ and documents the project's origin as a set of analysis
scripts.

TERMINOLOGY: this computes *win share* -- wins / races held -- which is the
same quantity `backend/app/advanced.py` names `win_share`. It is NOT the
application's `win_rate`, which is wins / driver entries. The two denominators
answer different questions and are named differently on purpose.
"""

import os
import matplotlib.pyplot as plt

from f1_utils import OUTPUT_DIR, load_results, bucket_by_decade



def plot_top_drivers_for_decade(decade_wins, seasons_in_decade, decade, top_n=5):
    ranked = sorted(decade_wins[decade].items(), key=lambda x: -x[1])[:top_n]
    drivers = [d for d, _ in ranked]
    counts = [n for _, n in ranked]

    plt.figure(figsize=(8, 5))
    plt.barh(drivers[::-1], counts[::-1], color="#c8102e")
    plt.title(f"Top Drivers by Wins - {decade}s ({len(seasons_in_decade[decade])} seasons)")
    plt.xlabel("Race wins")
    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, f"top_drivers_{decade}s.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"Saved {path}")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    wins, races_per_season = load_results(by="driver")
    decade_wins, seasons_in_decade, total_races_by_decade = bucket_by_decade(wins, races_per_season)

    for decade in sorted(decade_wins.keys()):
        num_seasons = len(seasons_in_decade[decade])
        total_races = total_races_by_decade[decade]
        print(f"\n{decade}s  ({num_seasons} seasons, {total_races} races total)")
        ranked = sorted(decade_wins[decade].items(), key=lambda x: -x[1])[:15]
        for driver, count in ranked:
            per_season = count / num_seasons
            win_share = 100 * count / total_races
            print(f"  {count:3d} wins  ({per_season:4.1f}/season)  ({win_share:4.1f}% of races)  {driver}")
        plot_top_drivers_for_decade(decade_wins, seasons_in_decade, decade)


if __name__ == "__main__":
    main()