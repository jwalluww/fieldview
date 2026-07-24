import requests
from bs4 import BeautifulSoup
import json
import os
import re
import time

TEAMS = [
    {"name": "Arizona Cardinals",    "abbr": "ARZ", "slug": "arizona-cardinals"},
    {"name": "Atlanta Falcons",      "abbr": "ATL", "slug": "atlanta-falcons"},
    {"name": "Baltimore Ravens",     "abbr": "BAL", "slug": "baltimore-ravens"},
    {"name": "Buffalo Bills",        "abbr": "BUF", "slug": "buffalo-bills"},
    {"name": "Carolina Panthers",    "abbr": "CAR", "slug": "carolina-panthers"},
    {"name": "Chicago Bears",        "abbr": "CHI", "slug": "chicago-bears"},
    {"name": "Cincinnati Bengals",   "abbr": "CIN", "slug": "cincinnati-bengals"},
    {"name": "Cleveland Browns",     "abbr": "CLE", "slug": "cleveland-browns"},
    {"name": "Dallas Cowboys",       "abbr": "DAL", "slug": "dallas-cowboys"},
    {"name": "Denver Broncos",       "abbr": "DEN", "slug": "denver-broncos"},
    {"name": "Detroit Lions",        "abbr": "DET", "slug": "detroit-lions"},
    {"name": "Green Bay Packers",    "abbr": "GB",  "slug": "green-bay-packers"},
    {"name": "Houston Texans",       "abbr": "HOU", "slug": "houston-texans"},
    {"name": "Indianapolis Colts",   "abbr": "IND", "slug": "indianapolis-colts"},
    {"name": "Jacksonville Jaguars", "abbr": "JAX", "slug": "jacksonville-jaguars"},
    {"name": "Kansas City Chiefs",   "abbr": "KC",  "slug": "kansas-city-chiefs"},
    {"name": "Las Vegas Raiders",    "abbr": "LV",  "slug": "las-vegas-raiders"},
    {"name": "Los Angeles Chargers", "abbr": "LAC", "slug": "los-angeles-chargers"},
    {"name": "Los Angeles Rams",     "abbr": "LAR", "slug": "los-angeles-rams"},
    {"name": "Miami Dolphins",       "abbr": "MIA", "slug": "miami-dolphins"},
    {"name": "Minnesota Vikings",    "abbr": "MIN", "slug": "minnesota-vikings"},
    {"name": "New England Patriots", "abbr": "NE",  "slug": "new-england-patriots"},
    {"name": "New Orleans Saints",   "abbr": "NO",  "slug": "new-orleans-saints"},
    {"name": "New York Giants",      "abbr": "NYG", "slug": "new-york-giants"},
    {"name": "New York Jets",        "abbr": "NYJ", "slug": "new-york-jets"},
    {"name": "Philadelphia Eagles",  "abbr": "PHI", "slug": "philadelphia-eagles"},
    {"name": "Pittsburgh Steelers",  "abbr": "PIT", "slug": "pittsburgh-steelers"},
    {"name": "San Francisco 49ers",  "abbr": "SF",  "slug": "san-francisco-49ers"},
    {"name": "Seattle Seahawks",     "abbr": "SEA", "slug": "seattle-seahawks"},
    {"name": "Tampa Bay Buccaneers", "abbr": "TB",  "slug": "tampa-bay-buccaneers"},
    {"name": "Tennessee Titans",     "abbr": "TEN", "slug": "tennessee-titans"},
    {"name": "Washington Commanders","abbr": "WAS", "slug": "washington-commanders"},
]

def scrape_otc(team):
    url = f"https://overthecap.com/salary-cap/{team['slug']}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    print(f"Fetching {team['name']}...")
    try:
        response = requests.get(url, headers=headers, timeout=10)
    except requests.exceptions.RequestException as e:
        print(f"  ERROR: {e}")
        return None

    if response.status_code != 200:
        print(f"  ERROR: Status {response.status_code}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    # Only grab the current year table (first contracted-players table)
    table = soup.select_one("table.contracted-players")
    if not table:
        print(f"  ERROR: No contract table found")
        return None

    contracts = {}
    for row in table.select("tbody tr"):
        name_tag = row.select_one("td.player-information div.name a")
        cap_td = row.select("td")

        if not name_tag:
            continue

        name = name_tag.get_text(strip=True)

        # Cap number is the last non-spacer td before the dead money columns
        # It's the td with class="" (no mobile_drop, no spacer) — simplest: grab all tds, cap number is index 11
        tds = row.find_all("td", recursive=False)
        cap_number = None
        for td in tds:
            classes = td.get("class", [])
            if "spacer" not in classes and "mobile_drop" not in classes and "player-information" not in classes:
                text = td.get_text(strip=True)
                if text.startswith("$"):
                    cap_number = text
                    break

        if name and cap_number:
            contracts[name] = {"cap_number": cap_number}

    return contracts

def normalize(name):
    name = re.sub(r'\b(jr|sr|ii|iii|iv)\b\.?', '', name.lower())
    name = re.sub(r"[^a-z ]", "", name)
    return re.sub(r'\s+', ' ', name).strip()

def merge_into_team(abbr, contracts):
    filepath = f"nfl/data/{abbr.lower()}.json"
    if not os.path.exists(filepath):
        return

    with open(filepath) as f:
        team_data = json.load(f)

    # Build normalized lookup
    lookup = {normalize(k): v for k, v in contracts.items()}

    matched = 0
    for pos, players in team_data["depth_chart"].items():
        for player in players:
            key = normalize(player["name"])
            if key in lookup:
                player["cap_number"] = lookup[key]["cap_number"]
                matched += 1
            else:
                player.setdefault("cap_number", None)

    with open(filepath, "w") as f:
        json.dump(team_data, f, indent=2)

    print(f"  Merged {matched} contracts into {abbr}")

if __name__ == "__main__":
    for team in TEAMS:
        contracts = scrape_otc(team)
        if contracts:
            merge_into_team(team["abbr"], contracts)
        time.sleep(3)