"""mls/scripts/fetch_asa_stats.py

Phase 1b (MLS): pulls American Soccer Analysis's advanced-metrics stats
via their official `itscalledsoccer` package (PyPI, MIT, maintained by
ASA themselves) rather than hitting the raw HTTP API directly -- it's a
thin, faithful wrapper (same BASE_URL) that adds real retry/backoff
(429/500/502/503/504), a day-long response cache, and pandas DataFrame
returns, for free. Confirmed no auth/key needed (empty securitySchemes
in ASA's own OpenAPI spec, and this script runs with none).

Real column names confirmed live via the actual installed package before
writing this mapping, not assumed from the earlier recon session's raw
`requests.get()` probe:
    client.get_player_xgoals(leagues="mls", season_name="2026")
returns a DataFrame with columns: player_id, team_id, general_position,
minutes_played, shots, shots_on_target, goals, xgoals, xplace,
goals_minus_xgoals, key_passes, primary_assists, xassists,
primary_assists_minus_xassists, goals_plus_primary_assists,
xgoals_plus_xassists, points_added, xpoints_added -- 797 rows for the
2026 season (confirmed live, matches the raw-API recon count exactly).

get_player_xgoals has NO player name -- only ASA's own opaque player_id
(e.g. "0Oq624oPq6"). This script also pulls client.get_players(leagues=
"mls") (3566 rows, ALL-TIME ASA history, not season-filtered -- there is
no season param on this endpoint) to resolve player_id -> player_name/
position/bio, and left-joins it onto the xgoals rows here so
mls_asa_stats.json is self-contained. Matching this data against the
ESPN roster by name happens downstream in build_mls_match.py, not here.

client.get_teams(leagues="mls") returns 31 rows, not the 32 ESPN has --
confirmed by hand this is NOT a missing-current-club problem: ASA's 31
includes one real defunct historical club (Chivas USA, folded 2014) that
was never filtered out, while the 30 real *current* clubs match ESPN's
roster exactly. ESPN's 32 is 2 higher because it includes two exhibition
entries ("MLS All-Stars", "Liga MX All-Stars") that aren't real clubs at
all. Full detail and the team-name alias map live in
build_mls_match.py, not here -- this script just writes ASA's raw team
list unmodified alongside the stats.

Run from the repo root: python mls/scripts/fetch_asa_stats.py
"""
import json
import os
from datetime import datetime, timezone

from itscalledsoccer.client import AmericanSoccerAnalysis

OUT_PATH = os.path.join("mls", "data", "mls_asa_stats.json")
SEASON = "2026"


def df_records(df):
    # ASA's season_name column can hold a list (per get_players) -- plain
    # to_dict("records") handles that fine, no special casing needed.
    return json.loads(df.to_json(orient="records"))


def main():
    client = AmericanSoccerAnalysis()

    print(f"Fetching get_player_xgoals(leagues='mls', season_name='{SEASON}') ...")
    xgoals = client.get_player_xgoals(leagues="mls", season_name=SEASON)
    print(f"  {len(xgoals)} rows, columns: {list(xgoals.columns)}")

    print("Fetching get_players(leagues='mls') ...")
    players = client.get_players(leagues="mls")
    print(f"  {len(players)} rows (all-time ASA history, not season-filtered)")

    print("Fetching get_teams(leagues='mls') ...")
    teams = client.get_teams(leagues="mls")
    print(f"  {len(teams)} rows")

    bio_by_id = {r["player_id"]: r for r in df_records(players)}

    stats = []
    for row in df_records(xgoals):
        bio = bio_by_id.get(row["player_id"], {})
        stats.append({
            **row,
            "player_name": bio.get("player_name"),
            "primary_broad_position": bio.get("primary_broad_position"),
            "primary_general_position": bio.get("primary_general_position"),
            "nationality": bio.get("nationality"),
            "birth_date": bio.get("birth_date"),
        })

    output = {
        "season_name": SEASON,
        "loaded_at": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
        "teams": df_records(teams),
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    unresolved = sum(1 for s in stats if s["player_name"] is None)
    print(f"\nWrote {OUT_PATH}: {len(stats)} stat rows "
          f"({unresolved} with no matching bio row in get_players)")


if __name__ == "__main__":
    main()
