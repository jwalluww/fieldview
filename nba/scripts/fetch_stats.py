import json
import os
import random
import time
from datetime import date

from nba_api.stats.endpoints import commonteamroster, leaguedashplayerstats
from nba_api.stats.static import teams

# stats.nba.com's bot detection fingerprints on header *completeness*, not
# just User-Agent -- a thin/hand-rolled header set (missing Sec-Ch-Ua,
# Accept-Encoding, etc.) gets the connection dropped outright even with a
# convincing User-Agent. This set was verified against a live pull.
HEADERS = {
    "Host": "stats.nba.com",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
    "Sec-Ch-Ua": '"Not:A-Brand";v="99", "Google Chrome";v="124", "Chromium";v="124"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Fetch-Dest": "empty",
}

OUT_PATH = os.path.join("nba", "data", "nba_stats.json")

# Starting guess, not a settled rule -- flagged for Justin to revisit once
# real usage patterns are known. games_started isn't available from any
# bulk NBA stats endpoint (only playercareerstats, one call per player),
# so rotation_status is derived from minutes per game alone.
STARTER_MPG = 24
ROTATION_MPG = 15


def get_current_nba_season():
    """NBA season is named by the year it starts (Oct-June).
    Before October, the most recently completed season is the prior year's."""
    today = date.today()
    start_year = today.year if today.month >= 10 else today.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def fetch_with_retry(fn, *args, max_retries=6, base_delay=2.0, **kwargs):
    """Call an nba_api endpoint with exponential backoff on transient
    failures. stats.nba.com throttles/blocks aggressively -- budget for
    retries, not a single clean pull.

    max_retries bumped 4 -> 6 after a real GitHub Actions run
    (scrape-nba job) exhausted all 4 attempts on ReadTimeout, every one
    stalling the full per-request timeout before failing -- a pattern
    that looks more like persistent throttling of the runner's IP than
    one-off network flakiness, so this alone may not fully fix it, but
    it's the cheap first thing to try."""
    for attempt in range(1, max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if attempt == max_retries:
                raise
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1)
            print(f"  retry {attempt}/{max_retries} after error ({e}); sleeping {delay:.1f}s")
            time.sleep(delay)


def clean_str(val):
    """NaN-safe passthrough for string bio fields -- pandas represents a
    handful of missing NUM values as float NaN rather than "", and json.dump
    would otherwise emit a bare NaN token that browsers can't JSON.parse."""
    if val is None:
        return None
    try:
        if val != val:  # NaN check without importing pandas/numpy here
            return None
    except TypeError:
        pass
    return val or None


def clean_num(val):
    """Coerce a pandas scalar (numpy dtype, possibly NaN) to a plain
    JSON-safe Python number, or None."""
    if val is None:
        return None
    try:
        if val != val:  # NaN check without importing pandas/numpy here
            return None
    except TypeError:
        pass
    if isinstance(val, float):
        return round(float(val), 1)
    return int(val)


def fetch_season_averages(season):
    print(f"Fetching league-wide season averages for {season}...")
    resp = fetch_with_retry(
        leaguedashplayerstats.LeagueDashPlayerStats,
        season=season,
        per_mode_detailed="PerGame",
        headers=HEADERS,
        timeout=60,
    )
    df = resp.get_data_frames()[0]
    print(f"  {len(df)} players")

    stats_by_id = {}
    for row in df.to_dict("records"):
        pid = int(row["PLAYER_ID"])
        stats_by_id[pid] = {
            "player_id": pid,
            "name": row["PLAYER_NAME"],
            "team": row["TEAM_ABBREVIATION"],
            "ppg": clean_num(row["PTS"]),
            "rpg": clean_num(row["REB"]),
            "apg": clean_num(row["AST"]),
            "mpg": clean_num(row["MIN"]),
            "games_played": clean_num(row["GP"]),
            "games_started": None,
        }
    return stats_by_id


def fetch_rosters(season):
    print(f"Fetching team rosters for {season}...")
    roster_by_id = {}
    all_teams = teams.get_teams()
    for i, team in enumerate(all_teams, 1):
        print(f"  [{i}/{len(all_teams)}] {team['abbreviation']}")
        resp = fetch_with_retry(
            commonteamroster.CommonTeamRoster,
            team_id=team["id"],
            season=season,
            headers=HEADERS,
            timeout=60,
        )
        df = resp.get_data_frames()[0]
        for row in df.to_dict("records"):
            pid = int(row["PLAYER_ID"])
            roster_by_id[pid] = {
                "name": row["PLAYER"] or None,
                "team": team["abbreviation"],
                "jersey_number": clean_str(row["NUM"]),
                "position": clean_str(row["POSITION"]),
                "height": clean_str(row["HEIGHT"]),
                "weight": clean_num(row["WEIGHT"]) if row["WEIGHT"] not in (None, "") else None,
            }
        # be polite -- stats.nba.com throttles/blocks aggressively without delay
        time.sleep(1.0 + random.uniform(0, 0.5))
    return roster_by_id


def derive_rotation_status(mpg):
    if mpg is None:
        return "bench"
    if mpg >= STARTER_MPG:
        return "starter"
    if mpg >= ROTATION_MPG:
        return "rotation"
    return "bench"


def main():
    season = get_current_nba_season()
    stats_by_id = fetch_season_averages(season)
    roster_by_id = fetch_rosters(season)

    # Full outer join on player_id: keep every rostered player (even 0-game
    # guys leaguedashplayerstats drops) plus any stats-only stragglers
    # (e.g. traded players no longer on a current roster snapshot).
    output = {}
    for pid in set(roster_by_id) | set(stats_by_id):
        bio = roster_by_id.get(pid, {})
        entry = stats_by_id.get(pid)
        if entry is None:
            entry = {
                "player_id": pid,
                "name": bio.get("name"),
                "team": bio.get("team"),
                "ppg": None,
                "rpg": None,
                "apg": None,
                "mpg": None,
                "games_played": 0,
                "games_started": None,
            }
        entry["position"] = bio.get("position")
        entry["jersey_number"] = bio.get("jersey_number")
        entry["height"] = bio.get("height")
        entry["weight"] = bio.get("weight")
        entry["rotation_status"] = derive_rotation_status(entry["mpg"])
        output[str(pid)] = entry

    os.makedirs(os.path.join("nba", "data"), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    matched_bio = sum(1 for p in output.values() if p.get("position"))
    status_counts = {}
    for p in output.values():
        status_counts[p["rotation_status"]] = status_counts.get(p["rotation_status"], 0) + 1

    print(f"\nWrote {len(output)} players to {OUT_PATH}")
    print(f"Matched roster bio (jersey/position/height/weight): {matched_bio} / {len(output)}")
    print(f"Rotation status breakdown: {status_counts}")
    print("\nNOTE: rotation_status thresholds (starter >= 24 mpg, rotation >= 15 mpg) "
          "are a starting guess -- flag to Justin before treating as settled.")


if __name__ == "__main__":
    main()
