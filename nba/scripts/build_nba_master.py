import json
import os

STATS_PATH = os.path.join("nba", "data", "nba_stats.json")
CONTRACTS_PATH = os.path.join("nba", "data", "contracts_nba.json")
RATINGS_PATH = os.path.join("nba", "data", "nba_ratings_2k.json")
OUT_PATH = os.path.join("nba", "data", "nba_players_master.json")


GRANULAR_POSITIONS = {"PG", "SG", "SF", "PF", "C"}

# nba_api's roster endpoint only reports coarse groups (G/F/C, plus
# hybrids). formation.html's court view needs a specific slot per player,
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


def main():
    stats_by_id = load_json(STATS_PATH)
    contracts_by_id = {
        c["player_id"]: c for c in load_json(CONTRACTS_PATH)["contracts"]
    }
    ratings_by_id = {
        r["player_id"]: r for r in load_json(RATINGS_PATH)["ratings"]
    }

    output = {}
    for pid_str, p in stats_by_id.items():
        pid = p["player_id"]
        contract = contracts_by_id.get(pid)
        rating = ratings_by_id.get(pid)

        output[pid_str] = {
            "player_id": pid,
            "name": p.get("name"),
            "team": p.get("team"),
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
            "rotation_status": p.get("rotation_status"),
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

    print(f"Wrote {len(output)} players to {OUT_PATH}")
    print(f"Matched contracts: {matched_contract} / {len(output)}")
    print(f"Matched 2k ratings: {matched_rating} / {len(output)}")
    print(f"Granular position (Spotrac or resolved fallback): {granular_pos} / {len(output)}")
    print(f"No position at all: {no_pos} / {len(output)}")


if __name__ == "__main__":
    main()
