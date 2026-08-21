"""
mlb/scripts/scrape_ratings.py

Pulls MLB The Show 26 ratings (OVR/POT) from theshowratings.com's 30
team pages, loads into mlb/data/fieldview.duckdb as a raw show_ratings
table. Join key is the mlbam_id embedded in each player's photo URL
(pattern: .../{slug}-{mlbam_id}-80x80.png), confirmed to equal
statsapi_roster.person_id for all 3 spot-checked players (Ketel Marte
606466, Corbin Carroll 682998, Geraldo Perdomo 672695) before writing
any of this -- no fuzzy name matching needed, unlike NFL/NBA.

PART 3 -- ScraperAPI proxy rebuild. curl_cffi's Chrome-120 TLS
impersonation was confirmed working on isolated single-page tests early
in this project, but every full 30-team run since then has been
blocked at 0/30 -- and a genuine headless-Chromium (Playwright) session
hit the identical 403 too, real evidence the block operates at the
IP-reputation/session layer, not the TLS-fingerprint layer curl_cffi
targets. Routes requests through ScraperAPI instead
(http://api.scraperapi.com?api_key={key}&url={target}), which proxies
through its own rotating IP pool -- a different mechanism than TLS
impersonation, worth trying given curl_cffi alone stopped working here.

API key is read from the SCRAPERAPI_KEY environment variable ONLY --
never hardcoded, never committed. Raises immediately with a clear
message if it's unset, rather than silently falling through to a
broken proxy URL.

Retry + fallback (Part 1, mirrors nfl/scripts/scrape_madden.py's actual
pattern, same as this round's nhl/scripts/scrape_ratings.py and
nba/scripts/scrape_2kratings.py rebuilds): each team gets a per-request
retry+backoff attempt. Any team still empty after a full pass gets ONE
retry after a 20s cooldown. Whatever's still empty after that falls
back to that team's existing rows already in show_ratings, rather than
writing empty and erasing known-good data. No daily-trickle mode here
(Part 2) -- unlike nhlratings.net/2kratings.com, this rebuild's whole
premise is that the proxy should get past the block that made a full
30-team run untenable in the first place, so a full run is the right
shape to try, not a 3-team-a-day sample.
"""
import os
import random
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import duckdb
import pandas as pd
import requests
from bs4 import BeautifulSoup

DB_PATH = "mlb/data/fieldview.duckdb"
PROXY_BASE = "http://api.scraperapi.com"

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


def get_api_key():
    key = os.environ.get("SCRAPERAPI_KEY")
    if not key:
        raise RuntimeError(
            "SCRAPERAPI_KEY environment variable is not set -- refusing to "
            "run without it rather than silently hitting a broken proxy URL."
        )
    return key


def proxy_url(target_url):
    return f"{PROXY_BASE}?{urlencode({'api_key': get_api_key(), 'url': target_url})}"


def fetch_with_retry(session, target_url, retries=3, retries_403=2, backoff=3):
    """Raises on total failure -- never returns None. Same shape as
    nhl/scripts/scrape_ratings.py's version. `backoff` starts at 3 (not
    2) because proxy round-trips are inherently slower than a direct
    request -- ScraperAPI often takes 10-30s per call as it rotates IPs
    and retries internally, so a tight retry schedule here would just
    stack proxy latency on top of proxy latency."""
    attempt = 0
    attempt_blocked = 0
    while True:
        try:
            resp = session.get(proxy_url(target_url), timeout=70)
        except Exception as e:
            attempt += 1
            if attempt >= retries:
                raise
            print(f"    network error ({e}), retry {attempt}/{retries}")
            time.sleep(backoff ** attempt)
            continue

        # ScraperAPI passes through the target site's status code when it
        # successfully completes a fetch; a 403 here means the *target*
        # (theshowratings.com) blocked even the proxy's request, not that
        # ScraperAPI itself failed. 5xx from ScraperAPI itself (couldn't
        # complete the proxied fetch at all) gets the same retry treatment.
        if resp.status_code == 403 or resp.status_code >= 500:
            attempt_blocked += 1
            print(f"    status {resp.status_code} via proxy, "
                  f"retry {attempt_blocked}/{retries_403}")
            if attempt_blocked >= retries_403:
                raise RuntimeError(f"Blocked/failed via proxy after {attempt_blocked} attempts "
                                    f"(status {resp.status_code}): {target_url}")
            time.sleep(backoff ** attempt_blocked)
            continue

        resp.raise_for_status()
        return resp


def parse_team_page(html, team_name):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="table-striped")
    if not table:
        print(f"    WARNING: no ratings table found for {team_name}")
        return [], 0

    loaded_at = datetime.now(timezone.utc).isoformat()
    rows_out = []
    skipped = 0

    for tr in table.find_all("tr")[1:]:  # skip header row
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue

        # tds[0] is the counter cell ("1."), NOT the photo/name -- a real
        # off-by-one bug in the original version of this script, dormant
        # since day one because every prior run got Cloudflare-blocked
        # before ever reaching real content to parse. Confirmed against
        # real markup via the ScraperAPI proxy before fixing: tds[1] is
        # the div.entries cell (photo + name + subtext), tds[2] is OVR,
        # tds[3] is POT.
        photo_img = tds[1].find("img", class_="entry-photo")
        data_src = photo_img.get("data-src") if photo_img else None
        m = PHOTO_ID_RE.search(data_src) if data_src else None
        if not m:
            skipped += 1
            continue

        mlbam_id = int(m.group(1))
        player_name = (photo_img.get("alt") or "").strip()

        ovr_text = tds[2].get_text(strip=True)
        try:
            ovr = int(ovr_text)
        except ValueError:
            ovr = None

        pot = tds[3].get_text(strip=True) or None

        rows_out.append({
            "row_id": mlbam_id,
            "person_id": mlbam_id,
            "player_name": player_name,
            "team_name": team_name,
            "ovr": ovr,
            "pot": pot,
            "loaded_at": loaded_at,
        })

    return rows_out, skipped


def scrape_team(session, team_name, url):
    """Returns ([], 0) on any failure -- network error, exhausted
    retries, or a real block -- so one team's failure never crashes the
    run for the others. Mirrors nfl/scripts/scrape_madden.py's
    scrape_team()."""
    try:
        resp = fetch_with_retry(session, url)
    except Exception as e:
        print(f"    ERROR scraping {team_name}: {e}")
        return [], 0
    return parse_team_page(resp.text, team_name)


def load_existing_ratings_by_team():
    con = duckdb.connect(DB_PATH)
    exists = con.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = 'show_ratings'"
    ).fetchone() is not None
    if not exists:
        con.close()
        return {}
    df = con.execute("SELECT * FROM show_ratings").fetchdf()
    con.close()
    by_team = {}
    for _, r in df.iterrows():
        by_team.setdefault(r.get('team_name'), []).append(r.to_dict())
    return by_team


def single_page_test(session):
    """Confirms the proxy actually returns the real ratings table (not
    another block page) before spending a 30-team run on it."""
    team_name, url = TEAM_URLS[0]
    print(f"Single-page test: {team_name} via ScraperAPI proxy...")
    try:
        resp = session.get(proxy_url(url), timeout=70)
    except Exception as e:
        print(f"  ERROR: {e}")
        return False
    print(f"  status: {resp.status_code}, content length: {len(resp.text)}")
    if resp.status_code != 200:
        print(f"  Non-200 status -- proxy did not clear the block.")
        return False
    rows, skipped = parse_team_page(resp.text, team_name)
    print(f"  Parsed {len(rows)} rows ({skipped} skipped)")
    if not rows:
        print(f"  No rows parsed -- either blocked (check saved HTML) or page structure changed.")
        return False
    print(f"  CLEARED -- sample row: {rows[0]}")
    return True


if __name__ == "__main__":
    session = requests.Session()

    if not single_page_test(session):
        print("\nSingle-page test did not clear the block via ScraperAPI. "
              "Stopping -- not attempting the full 30-team run, and not "
              "trying a second proxy service without checking back first.")
        raise SystemExit(1)

    print(f"\nSingle-page test cleared -- proceeding with the full {len(TEAM_URLS)}-team run.")
    time.sleep(random.uniform(8, 15))

    existing_by_team = load_existing_ratings_by_team()

    by_team = {}
    for i, (team_name, url) in enumerate(TEAM_URLS):
        rows, skipped = scrape_team(session, team_name, url)
        by_team[team_name] = rows
        note = f" ({skipped} skipped, no photo id)" if skipped else ""
        print(f"{team_name}: {len(rows)} rows{note}")
        if i < len(TEAM_URLS) - 1:
            time.sleep(random.uniform(8, 15))

    failed = [name for name, _ in TEAM_URLS if not by_team[name]]
    if failed:
        print(f"\n{len(failed)} team(s) failed in-run, retrying after a cooldown: {failed}")
        time.sleep(20)
        for team_name in failed:
            url = dict(TEAM_URLS)[team_name]
            rows, skipped = scrape_team(session, team_name, url)
            by_team[team_name] = rows
            print(f"{team_name}: {len(rows)} rows (retry)")
            time.sleep(random.uniform(8, 15))

    fresh, stale, missing = [], [], []
    for team_name, _ in TEAM_URLS:
        if by_team[team_name]:
            fresh.append(team_name)
            continue
        fallback = existing_by_team.get(team_name)
        if fallback:
            by_team[team_name] = fallback
            stale.append(team_name)
        else:
            missing.append(team_name)

    if stale:
        print(f"\nWARNING: kept previous data for (fresh scrape failed both attempts): {stale}")
    if missing:
        print(f"\nWARNING: no data at all for (fresh scrape failed, no prior data to fall back to): {missing}")

    all_rows = []
    for team_name, _ in TEAM_URLS:
        all_rows.extend(by_team[team_name])

    conn = duckdb.connect(DB_PATH)
    if all_rows:
        df = pd.DataFrame(all_rows)
        conn.execute("CREATE OR REPLACE TABLE show_ratings AS SELECT * FROM df")
        print(f"\nshow_ratings: {len(df)} rows loaded across {len(TEAM_URLS)} teams "
              f"({len(fresh)} fresh, {len(stale)} stale-carryover, {len(missing)} missing)")
    else:
        print("\nNo rows collected -- show_ratings table not created.")
    conn.close()
