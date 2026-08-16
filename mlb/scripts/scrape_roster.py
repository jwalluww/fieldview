"""
mlb/scripts/scrape_roster.py

Pulls team list, one team's roster, and that roster's player bio data
from statsapi.mlb.com, loads each straight into mlb/data/fieldview.duckdb
as raw unmodified tables (row_id + loaded_at) -- same convention as
build_db.py's raw ingestion, applied to the live-pull pattern it already
uses for the GSIS crosswalk / nflreadpy sources.

TEST MODE: only pulls one team (NYY) to confirm the real response shape
before scaling to all 30. Team ID comes from the live /teams call, not
hardcoded, so we're not trusting anyone's memory of MLB's numeric team IDs.
"""
import duckdb
import pandas as pd
import time
from datetime import datetime, timezone
from statsapi_utils import fetch_with_retry

DB_PATH = "mlb/data/fieldview.duckdb"
BASE_URL = "https://statsapi.mlb.com/api/v1"
TEST_ABBR = "NYY"  # swap or remove once the shape is confirmed


def chunk_list(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def fetch_teams():
    resp = fetch_with_retry(f"{BASE_URL}/teams", params={"sportId": 1})
    resp.raise_for_status()
    return resp.json()["teams"]


def fetch_roster(team_id, team_abbr):
    resp = fetch_with_retry(f"{BASE_URL}/teams/{team_id}/roster",
                             params={"rosterType": "active"})
    resp.raise_for_status()
    loaded_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for entry in resp.json()["roster"]:
        person = entry["person"]
        position = entry.get("position", {})
        status = entry.get("status", {})
        rows.append({
            "row_id": f"{team_id}_{person['id']}",
            "team_id": team_id,
            "team_abbr": team_abbr,
            "person_id": person["id"],
            "full_name": person.get("fullName"),
            "jersey_number": entry.get("jerseyNumber"),
            "position_code": position.get("code"),
            "position_abbreviation": position.get("abbreviation"),
            "position_name": position.get("name"),
            "position_type": position.get("type"),
            "status_code": status.get("code"),
            "status_description": status.get("description"),
            "loaded_at": loaded_at,
        })
    return rows


def fetch_people(person_ids):
    ids_str = ",".join(str(i) for i in person_ids)
    resp = fetch_with_retry(f"{BASE_URL}/people", params={"personIds": ids_str})
    resp.raise_for_status()
    loaded_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for p in resp.json()["people"]:
        rows.append({
            "row_id": p["id"],
            "person_id": p["id"],
            "full_name": p.get("fullName"),
            "birth_date": p.get("birthDate"),
            "height": p.get("height"),
            "weight": p.get("weight"),
            "bat_side": p.get("batSide", {}).get("code"),
            "pitch_hand": p.get("pitchHand", {}).get("code"),
            "primary_position_abbr": p.get("primaryPosition", {}).get("abbreviation"),
            "loaded_at": loaded_at,
        })
    return rows


if __name__ == "__main__":
    conn = duckdb.connect(DB_PATH)

    teams = fetch_teams()
    teams_df = pd.DataFrame(teams)
    conn.execute("CREATE OR REPLACE TABLE statsapi_teams AS SELECT * FROM teams_df")
    print(f"statsapi_teams: {len(teams_df)} rows loaded")

    all_roster_rows = []
    for team in teams:
        rows = fetch_roster(team["id"], team.get("abbreviation"))
        all_roster_rows.extend(rows)
        print(f"  {team.get('abbreviation')}: {len(rows)} roster rows")
        time.sleep(0.3)

    roster_df = pd.DataFrame(all_roster_rows)
    conn.execute("CREATE OR REPLACE TABLE statsapi_roster AS SELECT * FROM roster_df")
    print(f"statsapi_roster: {len(roster_df)} rows loaded (30 teams)")

    all_person_ids = [r["person_id"] for r in all_roster_rows]
    all_people_rows = []
    for batch in chunk_list(all_person_ids, 100):
        all_people_rows.extend(fetch_people(batch))
        time.sleep(0.3)

    people_df = pd.DataFrame(all_people_rows)
    conn.execute("CREATE OR REPLACE TABLE statsapi_people AS SELECT * FROM people_df")
    print(f"statsapi_people: {len(people_df)} rows loaded")

    conn.close()
