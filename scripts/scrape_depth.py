import requests
from bs4 import BeautifulSoup
import json
import os
import re

TEAMS = [
    {"name": "Arizona Cardinals",   "abbr": "ARZ"},
    {"name": "Atlanta Falcons",     "abbr": "ATL"},
    {"name": "Baltimore Ravens",    "abbr": "BAL"},
    {"name": "Buffalo Bills",       "abbr": "BUF"},
    {"name": "Carolina Panthers",   "abbr": "CAR"},
    {"name": "Chicago Bears",       "abbr": "CHI"},
    {"name": "Cincinnati Bengals",  "abbr": "CIN"},
    {"name": "Cleveland Browns",    "abbr": "CLE"},
    {"name": "Dallas Cowboys",      "abbr": "DAL"},
    {"name": "Denver Broncos",      "abbr": "DEN"},
    {"name": "Detroit Lions",       "abbr": "DET"},
    {"name": "Green Bay Packers",   "abbr": "GB"},
    {"name": "Houston Texans",      "abbr": "HOU"},
    {"name": "Indianapolis Colts",  "abbr": "IND"},
    {"name": "Jacksonville Jaguars","abbr": "JAX"},
    {"name": "Kansas City Chiefs",  "abbr": "KC"},
    {"name": "Las Vegas Raiders",   "abbr": "LV"},
    {"name": "Los Angeles Chargers","abbr": "LAC"},
    {"name": "Los Angeles Rams",    "abbr": "LAR"},
    {"name": "Miami Dolphins",      "abbr": "MIA"},
    {"name": "Minnesota Vikings",   "abbr": "MIN"},
    {"name": "New England Patriots","abbr": "NE"},
    {"name": "New Orleans Saints",  "abbr": "NO"},
    {"name": "New York Giants",     "abbr": "NYG"},
    {"name": "New York Jets",       "abbr": "NYJ"},
    {"name": "Philadelphia Eagles", "abbr": "PHI"},
    {"name": "Pittsburgh Steelers", "abbr": "PIT"},
    {"name": "San Francisco 49ers", "abbr": "SF"},
    {"name": "Seattle Seahawks",    "abbr": "SEA"},
    {"name": "Tampa Bay Buccaneers","abbr": "TB"},
    {"name": "Tennessee Titans",    "abbr": "TEN"},
    {"name": "Washington Commanders","abbr": "WAS"},
]

def clean_name(name):
    name = re.sub(r'\s+\S*[\d/]\S*$', '', name).strip()
    if ',' in name:
        parts = name.split(',', 1)
        name = parts[1].strip() + ' ' + parts[0].strip()
    return name

def scrape_depth_chart(team):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    print(f"Fetching {team['name']} depth chart from OurLads...")
    url = f"https://www.ourlads.com/nfldepthcharts/depthchart/{team['abbr']}"
    try:
        response = requests.get(url, headers=headers, timeout=10)
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Network error — {e}")
        return None

    if response.status_code != 200:
        print(f"ERROR: Got status code {response.status_code}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    # OurLads depth chart table
    rows = soup.select("tr.row-dc-wht, tr.row-dc-grey")

    if not rows:
        print("ERROR: No depth chart rows found — OurLads may have changed their HTML structure")
        print("Tip: Open the URL in your browser and inspect the table element")
        return None

    depth_chart = {}

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 2:
            continue

        position = cols[0].get_text(strip=True)
        if not position:
            continue

        players = []
        for col in cols[2::2]:  # start at index 2, skip every other td
            player_tag = col.find("a")
            if player_tag:
                player_name = player_tag.get_text(strip=True)
                if player_name:
                    players.append({
                        "name": clean_name(player_name),
                        "depth": len(players) + 1
                    })

        if players:
            depth_chart[position] = players

    return {
        "team": team["name"],
        "abbr": team["abbr"],
        "source": "OurLads",
        "depth_chart": depth_chart
    }


def save_json(data, abbr):
    os.makedirs("data", exist_ok=True)
    filepath = f"data/{abbr.lower()}.json"
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved to {filepath}")


if __name__ == "__main__":
    import time
    for team in TEAMS:
        result = scrape_depth_chart(team)
        if result:
            save_json(result, team["abbr"])
            print(f"Success: {team['name']} — {len(result['depth_chart'])} positions\n")
        else:
            print(f"FAILED: {team['name']}\n")
        time.sleep(5)  # be polite to OurLads, don't hammer them


