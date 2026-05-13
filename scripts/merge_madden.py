import json
import os
import re

TEAM_MAP = {
    "Arizona Cardinals": "ARZ",
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
    "Jacksonville Jaguars": "JAX",
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
    name = name.lower()
    name = re.sub(r'\b(jr|sr|ii|iii|iv)\b\.?', '', name)
    name = re.sub(r"[^a-z ]", "", name)
    return re.sub(r'\s+', ' ', name).strip()

def load_madden(path):
    with open(path) as f:
        players = json.load(f)
    by_team = {}
    for p in players:
        team_label = p.get("team", {}).get("label", "")
        abbr = TEAM_MAP.get(team_label)
        if not abbr:
            continue
        by_team.setdefault(abbr, []).append({
            "full_name": f"{p['firstName']} {p['lastName']}",
            "normalized": normalize(f"{p['firstName']} {p['lastName']}"),
            "overall": p["overallRating"],
            "jersey": p.get("jerseyNum"),
            "age": p.get("age"),
            "years_pro": p.get("yearsPro"),
            "position": p.get("position", {}).get("shortLabel", ""),
        })
    return by_team

def build_pos_ranks(madden_by_team):
    all_players = [p for players in madden_by_team.values() for p in players]
    by_position = {}
    for p in all_players:
        by_position.setdefault(p["position"], []).append(p)
    pos_ranks = {}
    for pos, players in by_position.items():
        sorted_players = sorted(players, key=lambda x: x["overall"], reverse=True)
        for rank, player in enumerate(sorted_players, 1):
            pos_ranks[player["normalized"]] = {
                "rank": rank,
                "total": len(sorted_players),
                "pos": pos
            }
    return pos_ranks

def find_madden_player(name, all_madden_players):
    target = normalize(name)
    for mp in all_madden_players:
        if mp["normalized"] == target:
            return mp
    target_words = set(target.split())
    for mp in all_madden_players:
        if target_words and target_words.issubset(set(mp["normalized"].split())):
            return mp
    return None

def merge():
    madden_by_team = load_madden("data/madden.json")
    pos_ranks = build_pos_ranks(madden_by_team)
    all_madden_players = [p for players in madden_by_team.values() for p in players]

    matched = 0
    unmatched = 0

    for abbr in TEAM_MAP.values():
        filepath = f"data/{abbr.lower()}.json"
        if not os.path.exists(filepath):
            continue

        with open(filepath) as f:
            team_data = json.load(f)

        for pos, players in team_data["depth_chart"].items():
            for player in players:
                mp = find_madden_player(player["name"], all_madden_players)
                if mp:
                    player["madden"] = mp["overall"]
                    player["jersey"] = mp["jersey"]
                    player["age"] = mp["age"]
                    player["years_pro"] = mp["years_pro"]
                    rank_info = pos_ranks.get(mp["normalized"])
                    player["madden_rank"] = rank_info["rank"] if rank_info else None
                    player["madden_rank_total"] = rank_info["total"] if rank_info else None
                    player["madden_pos_label"] = rank_info["pos"] if rank_info else None
                    matched += 1
                else:
                    player["madden"] = None
                    player["jersey"] = None
                    player["madden_rank"] = None
                    player["madden_rank_total"] = None
                    player["madden_pos_label"] = None
                    unmatched += 1

        with open(filepath, "w") as f:
            json.dump(team_data, f, indent=2)

    print(f"\nDone — {matched} matched, {unmatched} unmatched")

if __name__ == "__main__":
    merge()