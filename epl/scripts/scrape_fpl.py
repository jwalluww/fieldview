"""epl/scripts/scrape_fpl.py

Phase 1 (EPL): pulls fantasy.premierleague.com/api/bootstrap-static/, a
real live API confirmed live (no auth, no key, no rate limiting observed
across 10 rapid full pulls) -- writes epl/data/epl_players.json.

Real field names confirmed against the live 2026-08-22 response before
writing this mapping, not assumed from prior recon notes:
  - elements[].element_type is a FK into element_types[] (ids 1-4:
    GKP/DEF/MID/FWD) -- coarse only, no winger/fullback/fullback-side
    granularity. sofifa fills that gap (shared/scripts/scrape_sofifa.py),
    joined downstream in build_epl_match.py -- this script does not
    attempt to resolve a granular position.
  - elements[].team is a FK into teams[].id (20 teams) -- resolved here
    to team name/short_name so epl_players.json is self-contained, same
    convention as NBA's fetch_stats.py resolving TEAM_ABBREVIATION.
  - elements[].code is FPL's own numeric player id (also the photo
    filename prefix). elements[].opta_code (e.g. "p223094" for Haaland)
    is a real Opta player id, confirmed live NOT to share an ID space
    with sofifa's player id (recon cross-checked several real players) --
    not usable as a sofifa join key, kept anyway since it's real data a
    future source might key off of.
  - No height/weight anywhere in this response. FPL is a fantasy-stats
    API, not a bio source -- confirmed absent, not defaulted/guessed.
    sofifa's player-listing table doesn't carry them either (only on
    individual player detail pages, not pulled by scrape_sofifa.py), so
    epl_players_master.json will have no height/weight field at all.
    Known gap, not a bug.

elements[].history / history_past (per-gameweek log + season-by-season
totals) live at a SEPARATE endpoint, element-summary/{id}/ -- one call
per player (604 as of this run), not part of bootstrap-static and NOT
pulled by this script. Confirmed live: as of 2026-08-22 (the day before
Gameweek 1 kicks off), a real player's `history` is a single all-zero
row and `history_past` already holds real season totals back to 2022/23.
Worth a follow-up per-player pull once there's an actual in-season shape
to build against -- not forced into this script now.

Dropped fields are pure FPL-game mechanics with no football-stats meaning
(price-change tracking, dream-team voting, scout-risk links, set-piece
taker order/text, transfer counts, the *_rank/*_rank_type family) --
everything else is kept under its real API field name, unmodified, same
passthrough convention as MLB's statsapi ingestion.

Run from the repo root: python epl/scripts/scrape_fpl.py
"""
import json
import os
from datetime import datetime, timezone

import requests

BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
OUT_PATH = os.path.join("epl", "data", "epl_players.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

# Real football stats + identity/bio fields, kept under their real FPL
# field names. Excludes pure FPL-game-mechanics fields (price-change
# tracking, dreamteam voting, scout-risk links, set-piece order/text,
# transfer counts, *_rank / *_rank_type) -- see module docstring.
KEEP_FIELDS = [
    # identity / bio
    "id", "code", "opta_code", "photo", "first_name", "second_name",
    "web_name", "known_name", "birth_date", "team_code", "team_join_date",
    "status", "news", "news_added", "chance_of_playing_this_round",
    "chance_of_playing_next_round", "squad_number",
    # fantasy context worth keeping (not a game mechanic -- a real
    # popularity/price signal)
    "now_cost", "selected_by_percent",
    # season-to-date stats
    "minutes", "starts", "starts_per_90", "goals_scored", "assists",
    "clean_sheets", "clean_sheets_per_90", "goals_conceded",
    "goals_conceded_per_90", "own_goals", "penalties_saved",
    "penalties_missed", "yellow_cards", "red_cards", "saves",
    "saves_per_90", "bonus", "bps", "influence", "creativity", "threat",
    "ict_index", "expected_goals", "expected_assists",
    "expected_goal_involvements", "expected_goals_conceded",
    "expected_goals_per_90", "expected_assists_per_90",
    "expected_goal_involvements_per_90", "expected_goals_conceded_per_90",
    "defensive_contribution", "defensive_contribution_per_90",
    "clearances_blocks_interceptions", "recoveries", "tackles",
    "total_points", "event_points", "points_per_game", "form",
]


def fetch_bootstrap():
    resp = requests.get(BOOTSTRAP_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def build_players(data):
    teams_by_id = {t["id"]: t for t in data["teams"]}
    positions_by_id = {et["id"]: et for et in data["element_types"]}
    loaded_at = datetime.now(timezone.utc).isoformat()

    players = {}
    for e in data["elements"]:
        team = teams_by_id.get(e["team"], {})
        position = positions_by_id.get(e["element_type"], {})

        entry = {k: e.get(k) for k in KEEP_FIELDS}
        entry["team_name"] = team.get("name")
        entry["team_short_name"] = team.get("short_name")
        entry["position"] = position.get("singular_name")
        entry["position_short"] = position.get("singular_name_short")
        entry["loaded_at"] = loaded_at

        players[str(e["id"])] = entry

    return players


def main():
    print(f"Fetching {BOOTSTRAP_URL} ...")
    data = fetch_bootstrap()
    print(f"  {len(data['elements'])} players, {len(data['teams'])} teams, "
          f"{len(data['element_types'])} position groups")

    players = build_players(data)

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(players, f, indent=2, ensure_ascii=False)

    print(f"Wrote {OUT_PATH}: {len(players)} players")


if __name__ == "__main__":
    main()
