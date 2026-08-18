"""
nhl/scripts/scrape_roster.py

Pulls all 32 teams' rosters from the NHL API (via nhl-api-py) and loads
them into nhl/data/fieldview.duckdb as a raw unmodified table (row_id +
loaded_at) -- same convention as mlb/scripts/scrape_roster.py.

Position grouping (forwards/defensemen/goalies) confirmed live against
the docstring's claim before this was scaled up from a single-team
(TOR) test. Team list comes from the live teams.teams() call rather
than a hardcoded abbreviation list -- confirmed it returns a clean 32
even with date="now" during NHL offseason, so no explicit date param
needed there (unlike team_roster's season, which does need explicit
resolution -- see season_utils.py).

Season: uses season_utils.resolve_seasons()'s roster_season, not the
stats_season -- confirmed live that during NHL offseason the *upcoming*
season id has the fuller/more current roster (free agency signings
already reflected), while the prior season id is already going stale
(departed UFAs still listed as absent). See season_utils.py docstring.
"""
import duckdb
import pandas as pd
import time
from datetime import datetime, timezone
from nhlpy import NHLClient
from season_utils import resolve_seasons

DB_PATH = "nhl/data/fieldview.duckdb"


def fetch_roster(client, team_abbr, season):
    raw = client.teams.team_roster(team_abbr=team_abbr, season=season)
    loaded_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for group, position_group in (
        ("forwards", "forward"),
        ("defensemen", "defenseman"),
        ("goalies", "goalie"),
    ):
        for p in raw.get(group, []):
            rows.append({
                "row_id": f"{team_abbr}_{p['id']}",
                "team_abbr": team_abbr,
                "season": season,
                "position_group": position_group,
                "player_id": p["id"],
                "first_name": p.get("firstName", {}).get("default"),
                "last_name": p.get("lastName", {}).get("default"),
                "sweater_number": p.get("sweaterNumber"),
                "position_code": p.get("positionCode"),
                "shoots_catches": p.get("shootsCatches"),
                "height_in_inches": p.get("heightInInches"),
                "weight_in_pounds": p.get("weightInPounds"),
                "birth_date": p.get("birthDate"),
                "birth_city": p.get("birthCity", {}).get("default"),
                "birth_country": p.get("birthCountry"),
                "birth_state_province": p.get("birthStateProvince", {}).get("default"),
                "loaded_at": loaded_at,
            })
    return rows


if __name__ == "__main__":
    client = NHLClient()
    roster_season, stats_season = resolve_seasons(client)
    print(f"roster_season={roster_season}  stats_season={stats_season}")

    teams = client.teams.teams()
    abbrs = sorted(t["abbr"] for t in teams)
    print(f"teams.teams(): {len(abbrs)} teams")

    all_rows = []
    for abbr in abbrs:
        rows = fetch_roster(client, abbr, roster_season)
        all_rows.extend(rows)
        print(f"  {abbr}: {len(rows)} roster rows")
        time.sleep(0.3)

    roster_df = pd.DataFrame(all_rows)

    conn = duckdb.connect(DB_PATH)
    conn.execute("CREATE OR REPLACE TABLE nhl_roster AS SELECT * FROM roster_df")
    conn.close()

    by_group = roster_df["position_group"].value_counts().to_dict()
    missing_sweater = roster_df["sweater_number"].isna().sum()
    print(f"nhl_roster: {len(roster_df)} rows loaded (32 teams, season {roster_season})")
    print(f"  by position_group: {by_group}")
    print(f"  missing sweater_number: {missing_sweater} / {len(roster_df)}")
