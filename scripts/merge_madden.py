import json
import os
import re

# Map full team names to our abbreviations
TEAM_MAP = {
    "Arizona Cardinals": "ARI",
    "Atlanta Falcons": "ATL",
    "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF",
    "Carolina Panthers": "CAR",
    "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN",
    "Cleveland Browns": "CLE",
    "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN",
    "Detroit Lions": "DET",
    "Green Bay Packers": "GB",
    "Houston Texans": "HOU",
    "Indianapolis Colts": "IND",
    "Jacksonville Jaguars": "JAC",
    "Kansas City Chiefs": "KC",
    "Las Vegas Raiders": "LV",
    "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LAR",
    "Miami Dolphins": "MIA",
    "Minnesota Vikings": "MIN",
    "New England Patriots": "NE",
    "New Orleans Saints": "NO",
    "New York Giants": "NYG",
    "New York Jets": "NYJ",
    "Philadelphia Eagles": "PHI",
    "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF",
    "Seattle Seahawks": "SEA",
    "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN",
    "Washington Commanders": "WAS",
}

def normalize(name):
    """Lowercase, remove punctuation, strip whitespace for fuzzy matching."""
    name = name.lower()
    # Remove suffixes for matching
    name = re.sub(r'\b(jr|sr|ii|iii|iv)\b\.?', '', name)
    # Remove all punctuation
    name = re.sub(r"[^a-z ]", "", name)
    return re.sub(r'\s+', ' ', name).strip()

def load_madden(path):
    with open(path) as f:
        players = json.load(f)
    
    # Build lookup: abbr -> list of player dicts
    by_team = {}
    for p in players:
        team_label = p.get("team", {}).get("label", "")
        abbr = TEAM_MAP.get(team_label)
        if not abbr:
            continue
        if abbr not in by_team:
            by_team[abbr] = []
        by_team[abbr].append({
            "full_name": f"{p['firstName']} {p['lastName']}",
            "normalized": normalize(f"{p['firstName']} {p['lastName']}"),
            "overall": p["overallRating"],
            "jersey": p.get("jerseyNum"),
            "age": p.get("age"),
            "years_pro": p.get("yearsPro"),
            "position": p.get("position", {}).get("shortLabel", ""),
        })
    return by_team

def find_madden_player(name, madden_team_players):
    """Try to match OurLads name to a Madden player on the same team."""
    target = normalize(name)
    
    # Exact match first
    for mp in madden_team_players:
        if mp["normalized"] == target:
            return mp
    
    # Partial match — all words in OurLads name appear in Madden name
    target_words = set(target.split())
    for mp in madden_team_players:
        madden_words = set(mp["normalized"].split())
        if target_words and target_words.issubset(madden_words):
            return mp

    return None

def merge():
    madden_by_team = load_madden("data/madden.json")
    matched = 0
    unmatched = 0

    for abbr in TEAM_MAP.values():
        filepath = f"data/{abbr.lower()}.json"
        if not os.path.exists(filepath):
            continue

        with open(filepath) as f:
            team_data = json.load(f)

        madden_players = madden_by_team.get(abbr, [])
        all_madden_players = [p for players in madden_by_team.values() for p in players]

        for pos, players in team_data["depth_chart"].items():
            for player in players:
                mp = find_madden_player(player["name"], all_madden_players)
                if mp:
                    player["madden"] = mp["overall"]
                    player["jersey"] = mp["jersey"]
                    player["age"] = mp["age"]
                    player["years_pro"] = mp["years_pro"]
                    matched += 1
                else:
                    player["madden"] = None
                    player["jersey"] = None
                    unmatched += 1

        with open(filepath, "w") as f:
            json.dump(team_data, f, indent=2)

    print(f"\nDone — {matched} matched, {unmatched} unmatched")

def diagnose(abbr="BUF"):
    madden_by_team = load_madden("data/madden.json")
    filepath = f"data/{abbr.lower()}.json"
    with open(filepath) as f:
        team_data = json.load(f)

    madden_players = madden_by_team.get(abbr, [])
    print(f"\nMadden players on {abbr}:")
    for mp in madden_players:
        print(f"  {mp['full_name']}")

    print(f"\nOurLads players on {abbr}:")
    for pos, players in team_data["depth_chart"].items():
        for p in players:
            print(f"  {p['name']}")

if __name__ == "__main__":
    diagnose("BUF")
    # merge()