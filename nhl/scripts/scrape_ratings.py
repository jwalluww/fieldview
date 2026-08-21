"""
nhl/scripts/scrape_ratings.py

Pulls NHL 27 (video game) player ratings from nhlratings.net's 32 team
pages, loads them into nhl/data/fieldview.duckdb as a raw nhl_ratings
table. Site structure confirmed live: static HTML behind Cloudflare,
two `<table class="table-striped ...">` blocks per page (main roster +
a small reserve/IR table). Per row: player name (`.entry-font a`),
position code (`a[href^="/lists/"]`, single letter C/L/R/D/G), jersey
number (plain text `#NN`, absent for some reserve/incoming players --
not an error), OVR (int or `--`), POT (a letter grade like "Exact",
not numeric -- kept as text, mirrors MLB's POT handling).

No clean numeric join key, unlike MLB: the photo `data-src` URL embeds
a number (`{name-slug}-{NUMBER}-80x80.png`), confirmed NOT the NHL
API's `playerId` (checked live: William Nylander site `3114736` vs.
API `8477939`). Matches by name+team instead, via name_utils.py against
nhl_roster (already in the DB).

RUN LOCALLY ONLY -- NOT IN GITHUB ACTIONS. Cloud/datacenter IPs get
treated worse by this class of anti-bot protection than residential
IPs -- already confirmed the hard way in this project on
nba/scripts/fetch_stats.py (stats.nba.com started failing exclusively
on the hosted Actions runner with clean local runs on the same code,
same day -- see CLAUDE.md's "NBA Stats Scraper" section). Don't
"helpfully" move this into scrape.yml; run it locally via
schedule_ratings_scrape.bat (see bottom of this file for the suggested
-- not registered -- schtasks command).

PART 1 -- retry + fallback (mirrors nfl/scripts/scrape_madden.py's
actual pattern, not reinvented): each team gets a per-request
retry+backoff attempt (fetch_with_retry). Any team that still has no
rows after that gets ONE retry pass after a 20s cooldown. Whatever's
still empty after both passes falls back to that team's most recent
successful scrape already sitting in the nhl_ratings table, rather
than writing empty/null and erasing known-good data over a transient
block. Logged as fresh / stale-carryover / missing (no fallback
available either), same three-way breakdown Madden's script prints.

PART 2 -- daily-trickle mode: nhlratings.net's rate-limit-style
cooldown (confirmed last session -- 1/32 teams before a fresh 403,
after this same site worked cleanly earlier the same probe) means a
30-team run in one sitting is the wrong shape for this site. Instead,
each run pulls only 3 random teams from a persisted rolling pool
(nhl/data/ratings_scrape_state.json) and upserts them into
nhl_ratings immediately -- it does NOT wait for a full cycle before
writing anything, so a script that never finishes a 32-team cycle
still leaves real, fresh data behind after every run. When the pool
empties (every team pulled at least once), it's reshuffled and
refilled for the next cycle -- a continuous rolling refresh, not a
one-time build.
"""
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone

import duckdb
import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from name_utils import normalize_name, normalize_for_matching, NHL_NAME_ALIASES

DB_PATH = "nhl/data/fieldview.duckdb"
STATE_PATH = "nhl/data/ratings_scrape_state.json"
TEAMS_PER_RUN = 3

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nhlratings.net/",
}

# abbr (matches nhl_roster.team_abbr) -> nhlratings.net team-page slug.
# Cross referenced live against the site's own homepage nav -- 31/32
# auto-matched by slugifying teams.teams()'s full names, Montreal
# needed a manual fix (site drops the accent: "montreal-canadiens").
TEAM_SLUGS = {
    'ANA': 'anaheim-ducks',
    'BOS': 'boston-bruins',
    'BUF': 'buffalo-sabres',
    'CAR': 'carolina-hurricanes',
    'CBJ': 'columbus-blue-jackets',
    'CGY': 'calgary-flames',
    'CHI': 'chicago-blackhawks',
    'COL': 'colorado-avalanche',
    'DAL': 'dallas-stars',
    'DET': 'detroit-red-wings',
    'EDM': 'edmonton-oilers',
    'FLA': 'florida-panthers',
    'LAK': 'los-angeles-kings',
    'MIN': 'minnesota-wild',
    'MTL': 'montreal-canadiens',
    'NJD': 'new-jersey-devils',
    'NSH': 'nashville-predators',
    'NYI': 'new-york-islanders',
    'NYR': 'new-york-rangers',
    'OTT': 'ottawa-senators',
    'PHI': 'philadelphia-flyers',
    'PIT': 'pittsburgh-penguins',
    'SEA': 'seattle-kraken',
    'SJS': 'san-jose-sharks',
    'STL': 'st-louis-blues',
    'TBL': 'tampa-bay-lightning',
    'TOR': 'toronto-maple-leafs',
    'UTA': 'utah-mammoth',
    'VAN': 'vancouver-canucks',
    'VGK': 'vegas-golden-knights',
    'WPG': 'winnipeg-jets',
    'WSH': 'washington-capitals',
}

JERSEY_RE = re.compile(r'#(\d+)')
PHOTO_ID_RE = re.compile(r'-(\d+)-80x80\.png')


def fetch_with_retry(session, url, retries=3, retries_403=2, backoff=2):
    """Raises on total failure (network error after `retries` attempts,
    or a 403 after `retries_403` attempts) -- never returns None. Callers
    (scrape_team) are responsible for catching and turning that into an
    empty-list failure signal, same shape as Madden's scrape_team()."""
    attempt = 0
    attempt_403 = 0
    while True:
        try:
            resp = session.get(url, timeout=20)
        except Exception as e:
            attempt += 1
            if attempt >= retries:
                raise
            print(f"    network error ({e}), retry {attempt}/{retries}")
            time.sleep(backoff ** attempt)
            continue

        if resp.status_code == 403:
            attempt_403 += 1
            print(f"    403 -- server: {resp.headers.get('server')}, "
                  f"cf-ray: {resp.headers.get('cf-ray')}, "
                  f"cf-cache-status: {resp.headers.get('cf-cache-status')}")
            if attempt_403 >= retries_403:
                raise RuntimeError(f"403 Forbidden after {attempt_403} attempts: {url}")
            time.sleep(backoff ** attempt_403)
            continue

        resp.raise_for_status()
        return resp


def parse_roster_table(table, team_abbr, loaded_at):
    rows_out = []
    tbody = table.find('tbody')
    if not tbody:
        return rows_out

    for tr in tbody.find_all('tr'):
        tds = tr.find_all('td')
        if len(tds) < 3:
            continue

        entries = tds[1].find('div', class_='entries')
        if not entries:
            continue

        name_a = entries.select_one('.entry-font a')
        raw_name = name_a.get_text(strip=True) if name_a else None
        if not raw_name:
            continue

        subtext = entries.select_one('.entry-subtext-font')
        pos_a = subtext.select_one('a[href^="/lists/"]') if subtext else None
        position = pos_a.get_text(strip=True) if pos_a else None

        jersey = None
        if subtext:
            m = JERSEY_RE.search(subtext.get_text(' ', strip=True))
            jersey = int(m.group(1)) if m else None

        photo_img = entries.select_one('.entry-photo')
        data_src = photo_img.get('data-src') if photo_img else None
        m = PHOTO_ID_RE.search(data_src) if data_src else None
        site_photo_id = int(m.group(1)) if m else None

        ovr_el = tds[2].find('span', class_='attribute-box') if len(tds) > 2 else None
        ovr_text = ovr_el.get_text(strip=True) if ovr_el else None
        ovr = int(ovr_text) if ovr_text and ovr_text.isdigit() else None

        pot_el = tds[3].find('span', class_='attribute-box') if len(tds) > 3 else None
        pot_text = pot_el.get_text(strip=True) if pot_el else None
        pot = pot_text if pot_text and pot_text != '--' else None

        rows_out.append({
            'team_abbr': team_abbr,
            'raw_name': raw_name,
            'position': position,
            'jersey_number': jersey,
            'site_photo_id': site_photo_id,  # NOT the NHL API playerId -- see module docstring
            'overall_rating': ovr,
            'potential': pot,
            'loaded_at': loaded_at,
        })
    return rows_out


def parse_team_page(html, team_abbr, loaded_at):
    soup = BeautifulSoup(html, 'html.parser')
    tables = soup.find_all('table', class_='table-striped')
    if not tables:
        print(f"    WARNING: no ratings table found for {team_abbr}")
        return []

    rows = []
    for table in tables:
        rows.extend(parse_roster_table(table, team_abbr, loaded_at))
    return rows


def scrape_team(session, abbr, slug):
    """Returns [] on any failure -- network error, exhausted retries, or a
    real block -- so one team's failure never crashes the run for the
    others. Mirrors scrape_madden.py's scrape_team()."""
    url = f"https://www.nhlratings.net/teams/{slug}"
    try:
        resp = fetch_with_retry(session, url)
    except Exception as e:
        print(f"    ERROR scraping {abbr}: {e}")
        return []
    loaded_at = datetime.now(timezone.utc).isoformat()
    return parse_team_page(resp.text, abbr, loaded_at)


def load_roster_players():
    con = duckdb.connect(DB_PATH)
    df = con.execute("SELECT player_id, first_name, last_name, team_abbr FROM nhl_roster").fetchdf()
    con.close()
    players = []
    for _, r in df.iterrows():
        players.append({
            'player_id': int(r['player_id']),
            'name': f"{r['first_name']} {r['last_name']}",
            'team': r['team_abbr'],
        })
    return players


def load_existing_ratings_by_team():
    """Base population for both the stale-carryover fallback and the
    merge step -- reads whatever's currently in nhl_ratings (built up
    incrementally by prior trickle runs), grouped by team. Empty dict if
    the table doesn't exist yet (first run ever)."""
    con = duckdb.connect(DB_PATH)
    exists = con.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = 'nhl_ratings'"
    ).fetchone() is not None
    if not exists:
        con.close()
        return {}
    df = con.execute("SELECT * FROM nhl_ratings").fetchdf()
    con.close()
    by_team = {}
    for _, r in df.iterrows():
        by_team.setdefault(r['team_abbr'], []).append(r.to_dict())
    return by_team


def build_match_index(players):
    by_name = {}
    by_name_team = {}
    for p in players:
        key = normalize_for_matching(p['name'])
        by_name.setdefault(key, []).append(p)
        by_name_team[(key, p['team'])] = p
    return by_name, by_name_team


def find_match(raw_name, team_abbr, by_name, by_name_team):
    lookup_name = NHL_NAME_ALIASES.get(raw_name, raw_name)
    if lookup_name is None:
        return None
    name_norm = normalize_for_matching(normalize_name(lookup_name))

    exact = by_name_team.get((name_norm, team_abbr))
    if exact:
        return exact

    candidates = by_name.get(name_norm, [])
    if len(candidates) == 1:
        return candidates[0]
    return None


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding='utf-8') as f:
            state = json.load(f)
        if state.get('remaining_pool'):
            return state
    pool = list(TEAM_SLUGS.keys())
    random.shuffle(pool)
    return {'remaining_pool': pool, 'cycle': 1, 'cycle_started': datetime.now(timezone.utc).isoformat()}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2)


if __name__ == '__main__':
    session = cffi_requests.Session(impersonate='chrome120')
    session.headers.update(HEADERS)

    state = load_state()
    remaining = state['remaining_pool']
    chosen = remaining[:TEAMS_PER_RUN]
    print(f"Cycle {state.get('cycle', 1)}: {len(remaining)} teams remaining before this run. "
          f"Picked: {chosen}")

    players = load_roster_players()
    by_name, by_name_team = build_match_index(players)
    existing_by_team = load_existing_ratings_by_team()

    by_team = {}
    for abbr in chosen:
        by_team[abbr] = scrape_team(session, abbr, TEAM_SLUGS[abbr])
        print(f"{abbr}: {len(by_team[abbr])} rows")
        time.sleep(random.uniform(8, 15))

    failed = [abbr for abbr in chosen if not by_team[abbr]]
    if failed:
        print(f"\n{len(failed)} team(s) failed in-run, retrying after a cooldown: {failed}")
        time.sleep(20)
        for abbr in failed:
            by_team[abbr] = scrape_team(session, abbr, TEAM_SLUGS[abbr])
            print(f"{abbr}: {len(by_team[abbr])} rows (retry)")
            time.sleep(random.uniform(8, 15))

    fresh, stale, missing = [], [], []
    for abbr in chosen:
        if by_team[abbr]:
            fresh.append(abbr)
            continue
        fallback = existing_by_team.get(abbr)
        if fallback:
            by_team[abbr] = fallback
            stale.append(abbr)
        else:
            missing.append(abbr)

    if stale:
        print(f"\nWARNING: kept previous data for (fresh scrape failed both attempts): {stale}")
    if missing:
        print(f"\nWARNING: no data at all for (fresh scrape failed, no prior data to fall back to): {missing}")

    # Only freshly-scraped rows need (re)matching -- stale/carried-over
    # rows already have player_id from their last successful match.
    for abbr in fresh:
        for row in by_team[abbr]:
            p = find_match(row['raw_name'], row['team_abbr'], by_name, by_name_team)
            row['player_id'] = p['player_id'] if p else None
            row['row_id'] = f"{row['team_abbr']}_{normalize_for_matching(row['raw_name'])}"

    # Upsert: keep every existing row for teams NOT touched this run,
    # replace rows only for the teams we did touch (fresh or
    # stale-fallback) -- a 3-team-per-run trickle must never wipe out
    # the other 29 teams' already-collected data.
    chosen_set = set(chosen)
    merged_rows = []
    for abbr, rows in existing_by_team.items():
        if abbr not in chosen_set:
            merged_rows.extend(rows)
    for abbr in chosen:
        merged_rows.extend(by_team.get(abbr, []))

    conn = duckdb.connect(DB_PATH)
    if merged_rows:
        df = pd.DataFrame(merged_rows)
        conn.execute("CREATE OR REPLACE TABLE nhl_ratings AS SELECT * FROM df")
        teams_covered = df['team_abbr'].nunique()
        print(f"\nnhl_ratings: {len(df)} total rows across {teams_covered}/{len(TEAM_SLUGS)} teams "
              f"({len(fresh)} fresh this run, {len(stale)} stale-carryover, {len(missing)} missing)")
    else:
        print("\nNo rows at all (fresh or stale) -- nhl_ratings table not written.")
    conn.close()

    # Advance the rolling pool -- refill+reshuffle once it empties so this
    # is a continuous rolling refresh, not a one-time 11-run build.
    state['remaining_pool'] = [a for a in remaining if a not in chosen_set]
    if not state['remaining_pool']:
        new_pool = list(TEAM_SLUGS.keys())
        random.shuffle(new_pool)
        state['remaining_pool'] = new_pool
        state['cycle'] = state.get('cycle', 1) + 1
        state['cycle_started'] = datetime.now(timezone.utc).isoformat()
        print(f"\nCycle complete -- starting cycle {state['cycle']} with a freshly shuffled 32-team pool.")
    save_state(state)
    print(f"{len(state['remaining_pool'])} teams remaining in current cycle.")

# ══════════════════════════════════════════════════════════════════════
# SCHEDULING (local machine only -- see the "RUN LOCALLY ONLY" note in
# the module docstring). This is a suggested command, NOT registered by
# this script or by Claude Code -- run it yourself if you want the daily
# trickle automated:
#
#   schtasks /create /tn "FieldView NHL Ratings Scrape" ^
#     /tr "C:\Users\wallj\DS_Projects\fieldview\nhl\scripts\schedule_ratings_scrape.bat" ^
#     /sc daily /st 09:00
#
# schedule_ratings_scrape.bat (see that file, same directory) adds its
# own random 0-30 minute delay before invoking this script, so the
# actual run time still drifts day to day even though the scheduled
# trigger itself fires at a fixed clock time -- schtasks' basic CLI has
# no native random-delay trigger option.
# ══════════════════════════════════════════════════════════════════════
