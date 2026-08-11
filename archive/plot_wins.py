"""Generate chart images from the win data.

SUPERSEDED by the web application. Kept because it produced the committed
charts in output/ and documents the project's origin as a set of analysis
scripts.

TERMINOLOGY: this computes *win share* -- wins / races held that season --
which is the same quantity `backend/app/advanced.py` names `win_share`. It is
NOT the application's `win_rate`, which is wins / driver entries. The two
denominators answer different questions and are named differently on purpose.
"""

import os
import matplotlib.pyplot as plt

from f1_utils import OUTPUT_DIR, load_results, bucket_by_decade



def plot_leader_win_share_by_year(wins, races_per_season):
    seasons = sorted(wins.keys())
    shares = []
    for season in seasons:
        total = races_per_season[season]
        top_wins = max(wins[season].values())
        shares.append(100 * top_wins / total)

    plt.figure(figsize=(12, 6))
    plt.plot(seasons, shares, marker="o", linewidth=1.5, markersize=3)
    plt.title("Leading Constructor's Share of Races Won by Season (2000-2025)")
    plt.xlabel("Season")
    plt.ylabel("Share of season's races won by top constructor (%)")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, "leader_win_share_by_year.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"Saved {path}")


def plot_top_constructors_for_decade(decade_wins, seasons_in_decade, decade, top_n=5):
    ranked = sorted(decade_wins[decade].items(), key=lambda x: -x[1])[:top_n]
    constructors = [c for c, _ in ranked]
    counts = [n for _, n in ranked]

    plt.figure(figsize=(8, 5))
    plt.barh(constructors[::-1], counts[::-1], color="#c8102e")
    plt.title(f"Top Constructors by Wins - {decade}s ({len(seasons_in_decade[decade])} seasons)")
    plt.xlabel("Race wins")
    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, f"top_constructors_{decade}s.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"Saved {path}")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    wins, races_per_season = load_results()
    decade_wins, seasons_in_decade, _ = bucket_by_decade(wins, races_per_season)

    plot_leader_win_share_by_year(wins, races_per_season)

    for decade in sorted(decade_wins.keys()):
        plot_top_constructors_for_decade(decade_wins, seasons_in_decade, decade)


if __name__ == "__main__":
    main()
