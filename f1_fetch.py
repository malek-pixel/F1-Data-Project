import requests

def get_race_results(season, round_num):
    url = f"https://api.jolpi.ca/ergast/f1/{season}/{round_num}/results/"
    response = requests.get(url)
    data = response.json()

    race = data["MRData"]["RaceTable"]["Races"][0]
    print(f"\n{race['raceName']} — {race['date']}\n")

    for result in race["Results"]:
        pos = result["position"]
        driver = f"{result['Driver']['givenName']} {result['Driver']['familyName']}"
        team = result["Constructor"]["name"]
        print(f"P{pos}: {driver} ({team})")

get_race_results(2024, 1)
