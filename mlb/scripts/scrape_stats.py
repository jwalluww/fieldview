"""
mlb/scripts/scrape_stats.py

Pulls full-league season hitting/pitching stats via /v1/stats with
playerPool=all (confirmed via probe_stats.py: 702 hitters, 799 pitchers
in two calls total, vs. ~780 individual per-player hydrate calls).
Loads each group into its own raw DuckDB table.

Note: this population is NOT the same set as statsapi_roster -- see
scrape_roster.py's neighboring tables. Season stats include anyone who
played in 2026, roster reflects today's snapshot only. Expect a
partial, not 1:1, overlap -- handle at match time, not here.
"""
import duckdb
import pandas as pd
from datetime import datetime, timezone
from statsapi_utils import fetch_with_retry

DB_PATH = "mlb/data/fieldview.duckdb"
BASE_URL = "https://statsapi.mlb.com/api/v1"
SEASON = 2026


def fetch_stats(group):
    resp = fetch_with_retry(f"{BASE_URL}/stats", params={
        "stats": "season",
        "group": group,
        "sportIds": 1,
        "season": SEASON,
        "limit": 2000,
        "playerPool": "all",
    })
    loaded_at = datetime.now(timezone.utc).isoformat()
    splits = resp.json().get("stats", [{}])[0].get("splits", [])
    rows = []
    for s in splits:
        player = s.get("player", {})
        team = s.get("team", {})
        stat = s.get("stat", {})
        row = {
            "row_id": f"{group}_{player.get('id')}",
            "person_id": player.get("id"),
            "full_name": player.get("fullName"),
            "team_id": team.get("id"),
            "team_abbr": team.get("abbreviation"),
            "group": group,
            "loaded_at": loaded_at,
        }
        row.update(stat)
        rows.append(row)
    return rows


if __name__ == "__main__":
    conn = duckdb.connect(DB_PATH)

    hitting_df = pd.DataFrame(fetch_stats("hitting"))
    conn.execute("CREATE OR REPLACE TABLE statsapi_stats_hitting AS SELECT * FROM hitting_df")
    print(f"statsapi_stats_hitting: {len(hitting_df)} rows loaded")

    pitching_df = pd.DataFrame(fetch_stats("pitching"))
    conn.execute("CREATE OR REPLACE TABLE statsapi_stats_pitching AS SELECT * FROM pitching_df")
    print(f"statsapi_stats_pitching: {len(pitching_df)} rows loaded")

    conn.close()
