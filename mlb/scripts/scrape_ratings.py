"""
mlb/scripts/scrape_ratings.py

Pulls MLB The Show 26 ratings (OVR/POT) from theshowratings.com's 30
team pages, loads into mlb/data/fieldview.duckdb as a raw show_ratings
table. Join key is the mlbam_id embedded in each player's photo URL
(pattern: .../{slug}-{mlbam_id}-80x80.png), confirmed to equal
statsapi_roster.person_id for all 3 spot-checked players (Ketel Marte
606466, Corbin Carroll 682998, Geraldo Perdomo 672695) before writing
any of this -- no fuzzy name matching needed, unlike NFL/NBA.

Uses curl_cffi's Chrome-120 TLS impersonation (same pattern proven in
probe_show_ratings_cffi.py) -- plain requests gets a Cloudflare 403 on
this host. Only jersey/team/position/bat-throw come from statsapi_roster
instead of being re-parsed here: that subtext line is bare text nodes
with no wrapping element per field, fragile to parse, and this project
already has all of it cleanly from statsapi.mlb.com.

Pacing: this site blocked after ~4 requests earlier in the same
session that discovered the curl_cffi fix -- more sensitive than
statsapi.mlb.com's 0.3s tolerance. 2.5s between team pages, and a
403 gets only 2 retries (not the general 3) so a block fails fast
instead of hammering an active cooldown, same fix already flagged as
still-needed for the open 2kratings.com NBA issue.
"""
import re
import time
from datetime import datetime, timezone

import duckdb
import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

DB_PATH = "mlb/data/fieldview.duckdb"

# Captured from the earlier nav-link probe (show_ratings_probe_cffi.html,
# saved during the session that found the curl_cffi fix) -- reused as-is,
# not re-derived with a fresh request.
TEAM_URLS = [
    ("Arizona Diamondbacks", "https://www.theshowratings.com/teams/arizona-diamondbacks"),
    ("Athletics", "https://www.theshowratings.com/teams/athletics"),
    ("Atlanta Braves", "https://www.theshowratings.com/teams/atlanta-braves"),
    ("Baltimore Orioles", "https://www.theshowratings.com/teams/baltimore-orioles"),
    ("Boston Red Sox", "https://www.theshowratings.com/teams/boston-red-sox"),
    ("Chicago Cubs", "https://www.theshowratings.com/teams/chicago-cubs"),
    ("Chicago White Sox", "https://www.theshowratings.com/teams/chicago-white-sox"),
    ("Cincinnati Reds", "https://www.theshowratings.com/teams/cincinnati-reds"),
    ("Cleveland Guardians", "https://www.theshowratings.com/teams/cleveland-guardians"),
    ("Colorado Rockies", "https://www.theshowratings.com/teams/colorado-rockies"),
    ("Detroit Tigers", "https://www.theshowratings.com/teams/detroit-tigers"),
    ("Houston Astros", "https://www.theshowratings.com/teams/houston-astros"),
    ("Kansas City Royals", "https://www.theshowratings.com/teams/kansas-city-royals"),
    ("Los Angeles Angels", "https://www.theshowratings.com/teams/los-angeles-angels"),
    ("Los Angeles Dodgers", "https://www.theshowratings.com/teams/los-angeles-dodgers"),
    ("Miami Marlins", "https://www.theshowratings.com/teams/miami-marlins"),
    ("Milwaukee Brewers", "https://www.theshowratings.com/teams/milwaukee-brewers"),
    ("Minnesota Twins", "https://www.theshowratings.com/teams/minnesota-twins"),
    ("New York Mets", "https://www.theshowratings.com/teams/new-york-mets"),
    ("New York Yankees", "https://www.theshowratings.com/teams/new-york-yankees"),
    ("Philadelphia Phillies", "https://www.theshowratings.com/teams/philadelphia-phillies"),
    ("Pittsburgh Pirates", "https://www.theshowratings.com/teams/pittsburgh-pirates"),
    ("San Diego Padres", "https://www.theshowratings.com/teams/san-diego-padres"),
    ("San Francisco Giants", "https://www.theshowratings.com/teams/san-francisco-giants"),
    ("Seattle Mariners", "https://www.theshowratings.com/teams/seattle-mariners"),
    ("St. Louis Cardinals", "https://www.theshowratings.com/teams/st-louis-cardinals"),
    ("Tampa Bay Rays", "https://www.theshowratings.com/teams/tampa-bay-rays"),
    ("Texas Rangers", "https://www.theshowratings.com/teams/texas-rangers"),
    ("Toronto Blue Jays", "https://www.theshowratings.com/teams/toronto-blue-jays"),
    ("Washington Nationals", "https://www.theshowratings.com/teams/washington-nationals"),
]

# Captures the numeric id immediately before "-80x80.png", regardless of
# how many hyphenated words precede it (e.g. "corbin-carroll-682998" or
# "ketel-marte-606466") -- confirmed against real markup in
# show_ratings_team_probe.html before writing this.
PHOTO_ID_RE = re.compile(r'-(\d+)-80x80\.png')


class BlockedError(RuntimeError):
    pass


def fetch_with_retry(session, url, retries=3, retries_403=2, backoff=2):
    attempt = 0
    attempt_403 = 0
    while True:
        try:
            resp = session.get(url, timeout=30)
        except Exception as e:
            attempt += 1
            if attempt >= retries:
                raise
            print(f"  network error ({e}), retry {attempt}/{retries}")
            time.sleep(backoff ** attempt)
            continue

        if resp.status_code == 403:
            attempt_403 += 1
            if attempt_403 >= retries_403:
                raise BlockedError(f"403 Forbidden after {attempt_403} attempts: {url}")
            wait = backoff ** attempt_403
            print(f"  403, retry {attempt_403}/{retries_403} (waiting {wait}s)")
            time.sleep(wait)
            continue

        resp.raise_for_status()
        return resp


def parse_team_page(html, team_name):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="table-striped")
    if not table:
        print(f"  WARNING: no ratings table found for {team_name}")
        return [], 0

    loaded_at = datetime.now(timezone.utc).isoformat()
    rows_out = []
    skipped = 0

    for tr in table.find_all("tr")[1:]:  # skip header row
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue

        photo_img = tds[0].find("img", class_="entry-photo")
        data_src = photo_img.get("data-src") if photo_img else None
        m = PHOTO_ID_RE.search(data_src) if data_src else None
        if not m:
            skipped += 1
            continue

        mlbam_id = int(m.group(1))
        player_name = (photo_img.get("alt") or "").strip()

        ovr_text = tds[1].get_text(strip=True)
        try:
            ovr = int(ovr_text)
        except ValueError:
            ovr = None

        pot = tds[2].get_text(strip=True) or None

        rows_out.append({
            "row_id": mlbam_id,
            "person_id": mlbam_id,
            "player_name": player_name,
            "ovr": ovr,
            "pot": pot,
            "loaded_at": loaded_at,
        })

    return rows_out, skipped


if __name__ == "__main__":
    session = cffi_requests.Session(impersonate="chrome120")

    all_rows = []
    skipped_total = 0
    completed_teams = 0

    try:
        for i, (team_name, url) in enumerate(TEAM_URLS):
            resp = fetch_with_retry(session, url)
            rows, skipped = parse_team_page(resp.text, team_name)
            all_rows.extend(rows)
            skipped_total += skipped
            completed_teams += 1
            note = f" ({skipped} skipped, no photo id)" if skipped else ""
            print(f"{team_name}: {len(rows)} rows{note}")

            if i < len(TEAM_URLS) - 1:
                time.sleep(2.5)

    except BlockedError as e:
        print(f"\nBLOCKED: {e}")
        print(f"Stopping -- {completed_teams}/{len(TEAM_URLS)} teams completed before the block. Not retrying today.")

    conn = duckdb.connect(DB_PATH)
    if all_rows:
        df = pd.DataFrame(all_rows)
        conn.execute("CREATE OR REPLACE TABLE show_ratings AS SELECT * FROM df")
        print(f"\nshow_ratings: {len(df)} rows loaded from {completed_teams}/{len(TEAM_URLS)} teams")
        print(f"Skipped rows (no parseable photo id): {skipped_total}")
    else:
        print("\nNo rows collected -- show_ratings table not created.")
    conn.close()
