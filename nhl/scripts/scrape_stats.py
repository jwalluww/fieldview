"""
nhl/scripts/scrape_stats.py

Pulls league-wide skater and goalie season stats from the NHL API (via
nhl-api-py) and loads them into nhl/data/fieldview.duckdb as raw
unmodified tables (row_id + loaded_at) -- same convention as
mlb/scripts/scrape_stats.py.

Pagination, not limit: confirmed live that both skater_stats_summary
and goalie_stats_summary hard-cap each response at 100 rows server-side
regardless of how high `limit` is set (tried up to 100000 -- still 100
back). Full league coverage requires paging with `start` in increments
of 100 until an empty page comes back, not a bigger limit value. For
the 2025-26 season this came to 940 skaters (gamesPlayed>=1, the
library's own default filter) and 98 goalies (fit in a single page).

Season: uses season_utils.resolve_seasons()'s stats_season, not the
roster_season -- confirmed live that the upcoming season id returns
zero stat rows until the season actually starts playing games. See
season_utils.py docstring for the full roster-vs-stats split.
"""
import duckdb
import pandas as pd
from datetime import datetime, timezone
from nhlpy import NHLClient
from season_utils import resolve_seasons

DB_PATH = "nhl/data/fieldview.duckdb"
PAGE_SIZE = 100


def fetch_all_pages(fetch_fn, **kwargs):
    rows = []
    start = 0
    while True:
        page = fetch_fn(limit=PAGE_SIZE, start=start, **kwargs)
        if not page:
            break
        rows.extend(page)
        start += PAGE_SIZE
    return rows


def to_df(rows, id_key, prefix, loaded_at):
    for r in rows:
        r["row_id"] = f"{prefix}_{r[id_key]}"
        r["loaded_at"] = loaded_at
    return pd.DataFrame(rows)


if __name__ == "__main__":
    client = NHLClient()
    roster_season, stats_season = resolve_seasons(client)
    print(f"roster_season={roster_season}  stats_season={stats_season}")
    loaded_at = datetime.now(timezone.utc).isoformat()

    skater_rows = fetch_all_pages(
        client.stats.skater_stats_summary,
        start_season=stats_season, end_season=stats_season,
    )
    skaters_df = to_df(skater_rows, "playerId", "skater", loaded_at)

    goalie_rows = fetch_all_pages(
        client.stats.goalie_stats_summary,
        start_season=stats_season, end_season=stats_season,
    )
    goalies_df = to_df(goalie_rows, "playerId", "goalie", loaded_at)

    conn = duckdb.connect(DB_PATH)
    conn.execute("CREATE OR REPLACE TABLE nhl_stats_skaters AS SELECT * FROM skaters_df")
    conn.execute("CREATE OR REPLACE TABLE nhl_stats_goalies AS SELECT * FROM goalies_df")
    conn.close()

    print(f"nhl_stats_skaters: {len(skaters_df)} rows loaded (season {stats_season})")
    print(f"nhl_stats_goalies: {len(goalies_df)} rows loaded (season {stats_season})")
