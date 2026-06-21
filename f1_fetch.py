import requests
import csv
import time
import os

def get_round_count(season):
    url = f"https://api.jolpi.ca/ergast/f1/{season}.json"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200 or not response.text.strip():
            print(f"  Skipping season {season} — empty response")
            return 0
        data = response.json()
        return int(data["MRData"]["total"])
    except Exception as e:
        print(f"  Error fetching round count for {season}: {e}")
        return 0

def get_race_results(season, round_num):
    url = f"https://api.jolpi.ca/ergast/f1/{season}/{round_num}/results.json"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200 or not response.text.strip():
            print(f"  Skipping {season} R{round_num} — empty response")
            return []
        data = response.json()
        races = data["MRData"]["RaceTable"]["Races"]
        if not races:
            return []
        race = races[0]
        results = []
        for result in race["Results"]:
            results.append({
                "season": season,
                "round": round_num,
                "race_name": race["raceName"],
                "date": race["date"],
                "position": result["position"],
                "driver": f"{result['Driver']['givenName']} {result['Driver']['familyName']}",
                "constructor": result["Constructor"]["name"]
            })
        return results
    except Exception as e:
        print(f"  Error {season} R{round_num}: {e}")
        return []

completed_seasons = set()
if os.path.exists("results.csv"):
    with open("results.csv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            completed_seasons.add(int(row["season"]))

with open("results.csv", "a", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["season","round","race_name","date","position","driver","constructor"])
    if not os.path.exists("results.csv") or os.path.getsize("results.csv") == 0:
        writer.writeheader()
    for season in range(2000, 2026):
        if season in completed_seasons:
            print(f"Season {season}: already fetched, skipping")
            continue
        rounds = get_round_count(season)
        print(f"Season {season}: {rounds} rounds")
        for round_num in range(1, rounds + 1):
            rows = get_race_results(season, round_num)
            writer.writerows(rows)
            time.sleep(0.3)

print("Done. results.csv saved.")