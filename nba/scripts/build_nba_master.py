import json
import os

STATS_PATH = os.path.join("nba", "data", "nba_stats.json")
CONTRACTS_PATH = os.path.join("nba", "data", "contracts_nba.json")
RATINGS_PATH = os.path.join("nba", "data", "nba_ratings_2k.json")
DEPTH_CHART_PATH = os.path.join("nba", "data", "nba_depth_chart.json")
OUT_PATH = os.path.join("nba", "data", "nba_players_master.json")

# nbadepthcharts.com's own STARTERS/2ND STRING/3RD STRING/OTHER tiers,
# mapped onto the existing 3-value rotation_status enum the frontend
# already renders (court-view.html/player-table.html STATUS_LABEL).
DEPTH_RANK_TO_STATUS = {
    1: "starter",
    2: "rotation",
    3: "bench",
    4: "bench",
}


GRANULAR_POSITIONS = {"PG", "SG", "SF", "PF", "C"}

# nba_api's roster endpoint only reports coarse groups (G/F/C, plus
# hybrids). court-view.html's court needs a specific slot per player,
# so this is the last-resort guess when neither nba_stats nor Spotrac has
# a granular position -- not a real position determination.
COARSE_POSITION_FALLBACK = {
    "G": "PG",
    "F": "SF",
    "C": "C",
    "G-F": "SG",
    "F-G": "SF",
    "F-C": "PF",
    "C-F": "PF",
}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def resolve_position(nba_pos, contract_pos):
    """Prefer Spotrac's granular pos (PG/SG/SF/PF/C); fall back to a
    coarse-group guess from whichever source has a coarse label."""
    if contract_pos in GRANULAR_POSITIONS:
        return contract_pos
    if nba_pos:
        return COARSE_POSITION_FALLBACK.get(nba_pos, nba_pos)
    if contract_pos:
        return COARSE_POSITION_FALLBACK.get(contract_pos, contract_pos)
    return None


def format_salary(cash_total_remaining, length_remaining):
    if not cash_total_remaining or not length_remaining:
        return None
    avg_annual = round(cash_total_remaining / length_remaining)
    return f"${avg_annual:,}"


def resolve_rotation(pid, mpg_derived_status, depth_by_id):
    """nbadepthcharts.com is the primary source for rotation_status; the
    existing MPG-derived logic (already computed onto nba_stats.json by
    fetch_stats.py) is only a fallback for players the depth chart
    doesn't cover -- not a flat replacement, both tiers coexist."""
    entry = depth_by_id.get(pid)
    if entry:
        return {
            "rotation_status": DEPTH_RANK_TO_STATUS.get(entry["depth_rank"], "bench"),
            "rotation_source": "nbadepthchart.com",
            "depth_rank": entry["depth_rank"],
        }
    return {
        "rotation_status": mpg_derived_status,
        "rotation_source": "mpg_derived",
        "depth_rank": None,
    }


def resolve_team(pid, stats_team, depth_by_id):
    """Same layering as resolve_rotation: nbadepthcharts.com reflects
    trades faster than nba_stats.json's roster-snapshot team, so prefer
    it when the player is covered; otherwise keep the snapshot value."""
    entry = depth_by_id.get(pid)
    return entry["team"] if entry else stats_team


def main():
    stats_by_id = load_json(STATS_PATH)
    contracts_by_id = {
        c["player_id"]: c for c in load_json(CONTRACTS_PATH)["contracts"]
    }
    ratings_by_id = {
        r["player_id"]: r for r in load_json(RATINGS_PATH)["ratings"]
    }
    depth_by_id = {
        e["player_id"]: e for e in load_json(DEPTH_CHART_PATH)["depth_chart"]
        if e["player_id"] is not None
    }

    output = {}
    for pid_str, p in stats_by_id.items():
        pid = p["player_id"]
        contract = contracts_by_id.get(pid)
        rating = ratings_by_id.get(pid)
        rotation = resolve_rotation(pid, p.get("rotation_status"), depth_by_id)
        team = resolve_team(pid, p.get("team"), depth_by_id)

        output[pid_str] = {
            "player_id": pid,
            "name": p.get("name"),
            "team": team,
            "position": resolve_position(p.get("position"), contract["pos"] if contract else None),
            "jersey_number": p.get("jersey_number"),
            "height": p.get("height"),
            "weight": p.get("weight"),
            "ppg": p.get("ppg"),
            "rpg": p.get("rpg"),
            "apg": p.get("apg"),
            "mpg": p.get("mpg"),
            "games_played": p.get("games_played"),
            "games_started": p.get("games_started"),
            "rotation_status": rotation["rotation_status"],
            "rotation_source": rotation["rotation_source"],
            "depth_rank": rotation["depth_rank"],
            "overall_rating": rating["overall_rating"] if rating else None,
            "contract_salary": format_salary(
                contract["cash_total_remaining"], contract["length_remaining"]
            ) if contract else None,
            "contract_years_remaining": contract["length_remaining"] if contract else None,
        }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    matched_contract = sum(1 for p in output.values() if p["contract_salary"] is not None)
    matched_rating = sum(1 for p in output.values() if p["overall_rating"] is not None)
    granular_pos = sum(1 for p in output.values() if p["position"] in GRANULAR_POSITIONS)
    no_pos = sum(1 for p in output.values() if p["position"] is None)
    from_depth_chart = sum(1 for p in output.values() if p["rotation_source"] == "nbadepthchart.com")
    no_rotation_status = sum(1 for p in output.values() if p["rotation_status"] is None)
    team_overridden = sum(
        1 for pid_str, p in output.items()
        if p["rotation_source"] == "nbadepthchart.com" and p["team"] != stats_by_id[pid_str].get("team")
    )

    print(f"Wrote {len(output)} players to {OUT_PATH}")
    print(f"Matched contracts: {matched_contract} / {len(output)}")
    print(f"Matched 2k ratings: {matched_rating} / {len(output)}")
    print(f"Granular position (Spotrac or resolved fallback): {granular_pos} / {len(output)}")
    print(f"No position at all: {no_pos} / {len(output)}")
    print(f"rotation_status from nbadepthchart.com: {from_depth_chart} / {len(output)}")
    print(f"rotation_status from mpg_derived fallback: {len(output) - from_depth_chart} / {len(output)}")
    print(f"rotation_status still null: {no_rotation_status} / {len(output)}")
    print(f"team overridden by nbadepthchart.com (trade catch-up): {team_overridden} / {len(output)}")


if __name__ == "__main__":
    main()
