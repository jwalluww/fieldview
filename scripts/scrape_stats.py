import nflreadpy as nfl
import json
import os

SEASON = 2025

# OurLads team abbr -> nflreadpy team abbr
TEAM_MAP = {
    "ARZ": "ARI", "ATL": "ATL", "BAL": "BAL", "BUF": "BUF",
    "CAR": "CAR", "CHI": "CHI", "CIN": "CIN", "CLE": "CLE",
    "DAL": "DAL", "DEN": "DEN", "DET": "DET", "GB":  "GB",
    "HOU": "HOU", "IND": "IND", "JAX": "JAX", "KC":  "KC",
    "LAC": "LAC", "LAR": "LA",  "LV":  "LV",  "MIA": "MIA",
    "MIN": "MIN", "NE":  "NE",  "NO":  "NO",  "NYG": "NYG",
    "NYJ": "NYJ", "PHI": "PHI", "PIT": "PIT", "SF":  "SF",
    "SEA": "SEA", "TB":  "TB",  "TEN": "TEN", "WAS": "WAS",
}

# Fields to sum across weeks
SUM_FIELDS = [
    "completions", "attempts", "passing_yards", "passing_tds",
    "passing_interceptions", "sacks_suffered",
    "carries", "rushing_yards", "rushing_tds",
    "receptions", "targets", "receiving_yards", "receiving_tds",
    "receiving_yards_after_catch",
    "def_tackles_solo", "def_tackles_with_assist", "def_sacks",
    "def_interceptions", "def_pass_defended", "def_qb_hits",
    "def_tackles_for_loss",
    "fg_made", "fg_att", "fg_long",
    "pat_made", "pat_att",
]

import re

def normalize(name):
    name = name.lower()
    name = re.sub(r'\b(jr|sr|ii|iii|iv)\b\.?', '', name)
    name = re.sub(r"[^a-z ]", "", name)
    return re.sub(r'\s+', ' ', name).strip()

def build_stat_summary(row, position_group):
    pos = position_group.upper() if position_group else ""
    stats = {}

    if pos == "QB":
        stats = {
            "CMP":  row.get("completions", 0),
            "ATT":  row.get("attempts", 0),
            "YDS":  row.get("passing_yards", 0),
            "TDs":  row.get("passing_tds", 0),
            "INTs": row.get("passing_interceptions", 0),
            "SACKS":row.get("sacks_suffered", 0),
            "RU YDS": row.get("rushing_yards", 0),
        }
    elif pos in ("RB", "FB"):
        stats = {
            "CAR":    row.get("carries", 0),
            "RU YDS": row.get("rushing_yards", 0),
            "RU TDs": row.get("rushing_tds", 0),
            "REC":    row.get("receptions", 0),
            "RE YDS": row.get("receiving_yards", 0),
            "TGT":    row.get("targets", 0),
        }
    elif pos in ("WR", "TE"):
        stats = {
            "TGT":  row.get("targets", 0),
            "REC":  row.get("receptions", 0),
            "YDS":  row.get("receiving_yards", 0),
            "TDs":  row.get("receiving_tds", 0),
            "YAC":  row.get("receiving_yards_after_catch", 0),
            "CAR":  row.get("carries", 0),
        }
    elif pos == "DB" or pos in ("CB", "S", "LB"):
        stats = {
            "TKL":  (row.get("def_tackles_solo", 0) or 0) + (row.get("def_tackles_with_assist", 0) or 0),
            "SACKS":row.get("def_sacks", 0),
            "INTs": row.get("def_interceptions", 0),
            "PD":   row.get("def_pass_defended", 0),
            "TFL":  row.get("def_tackles_for_loss", 0),
            "QB HIT": row.get("def_qb_hits", 0),
        }
    elif pos == "DL":
        stats = {
            "TKL":    (row.get("def_tackles_solo", 0) or 0) + (row.get("def_tackles_with_assist", 0) or 0),
            "SACKS":  row.get("def_sacks", 0),
            "TFL":    row.get("def_tackles_for_loss", 0),
            "QB HIT": row.get("def_qb_hits", 0),
            "FF":     row.get("def_fumbles_forced", 0),
        }
    elif pos == "SPEC":
        fg_made = row.get("fg_made", 0) or 0
        fg_att  = row.get("fg_att", 0) or 0
        stats = {
            "FG":    f"{fg_made}/{fg_att}",
            "FG%":   f"{round(fg_made/fg_att*100)}%" if fg_att else "—",
            "LONG":  row.get("fg_long", 0),
            "PAT":   f"{row.get('pat_made',0)}/{row.get('pat_att',0)}",
        }

    # Remove zero/null values to keep hover cards clean
    return {k: v for k, v in stats.items() if v not in (0, None, "0/0")}

def main():
    print(f"Loading {SEASON} weekly data...")
    weekly = nfl.load_player_stats([SEASON], 'reg')
    print(f"  {len(weekly)} rows loaded")

    # Aggregate to season totals per player
    agg = {}
    for row in weekly.to_dicts():
        if row["player_id"] != None:
            pid = row["player_id"]
            if pid not in agg:
                agg[pid] = {
                    "player_id": pid,
                    "player_name": row["player_name"],
                    "player_display_name": row["player_display_name"],
                    "position": row["position"],
                    "position_group": row["position_group"],
                    "team": row["recent_team"],
                }
                for f in SUM_FIELDS:
                    agg[pid][f] = 0
            for f in SUM_FIELDS:
                val = row.get(f) or 0
                agg[pid][f] = (agg[pid][f] or 0) + (val or 0)
            # Keep latest team
            agg[pid]["team"] = row["recent_team"]

    players = list(agg.values())

    # Build normalized name lookup
    name_lookup = {}
    for p in players:
        key = normalize(p["player_display_name"])
        name_lookup[key] = p
        # Also index by short name (A.Rodgers style)
        key2 = normalize(p["player_name"])
        name_lookup[key2] = p

    print(f"  {len(players)} unique players aggregated")

    # Merge into team JSONs
    matched = 0
    unmatched = 0

    for our_abbr, nfl_abbr in TEAM_MAP.items():
        filepath = f"data/{our_abbr.lower()}.json"
        if not os.path.exists(filepath):
            continue

        with open(filepath) as f:
            team_data = json.load(f)

        for pos, depth_players in team_data["depth_chart"].items():
            for player in depth_players:
                key = normalize(player["name"])
                sp = name_lookup.get(key)

                # Fallback: match on last name only within same team
                if not sp:
                    last = key.split()[-1] if key.split() else ""
                    for k, v in name_lookup.items():
                        if k.endswith(last) and v.get("team") == nfl_abbr:
                            sp = v
                            break

                if sp:
                    player["stats"] = build_stat_summary(sp, sp.get("position_group", ""))
                    player["stats_season"] = SEASON
                    matched += 1
                else:
                    player["stats"] = {}
                    player["stats_season"] = None
                    unmatched += 1

        with open(filepath, "w") as f:
            json.dump(team_data, f, indent=2)

    print(f"\nDone — {matched} matched, {unmatched} unmatched")

if __name__ == "__main__":
    main()