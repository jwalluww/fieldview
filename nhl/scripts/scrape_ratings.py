"""
nhl/scripts/scrape_ratings.py

Pulls NHL 27 (video game) player ratings from nhlratings.net's 32 team
pages, loads them into nhl/data/fieldview.duckdb as a raw nhl_ratings
table. Confirmed live (this session) that the site is plain static
HTML behind Cloudflare with no TLS-fingerprint challenge -- a normal
`requests.get()` with a realistic browser UA gets a clean 200 with the
full roster table already server-rendered, no curl_cffi needed here
(unlike mlb/scripts/scrape_ratings.py's theshowratings.com, which
really is TLS-fingerprint-blocked for plain requests).

No clean numeric join key, unlike MLB: the photo `data-src` URL does
embed a number (`{name-slug}-{NUMBER}-80x80.png`), but it's confirmed
NOT the NHL API's `playerId` -- checked 2 real players live (William
Nylander: site `3114736` vs. API `8477939`; Auston Matthews: site
`4024123` vs. API `8479318`), different id spaces entirely. So this
matches by name+team instead, same approach as
nba/scripts/scrape_2kratings.py, using nhl/scripts/name_utils.py
(ported from NBA's) against nhl_roster (already loaded in the DB) as
the match target rather than a live nba_stats.json-equivalent file.

Team page structure, confirmed live: two `<table class="table-striped
...">` blocks per page -- the main roster and a small reserve/IR table
(same shape, just fewer/blank stat cells) -- both parsed the same way
and combined. Per row: player name (`.entry-font a`), position code
(`a[href^="/lists/"]`, single letter C/L/R/D/G), jersey number (plain
text `#NN` inside `.entry-subtext-font`, absent for some reserve/
incoming players -- not an error), OVR (`.attribute-box` in the 3rd
`<td>`, int or `--`), POT (`.attribute-box` in the 4th `<td>`, a
letter grade like "Exact"/"A+", not numeric -- kept as text, mirrors
MLB's POT handling in mlb/scripts/scrape_ratings.py).

STATUS AS OF THIS SESSION: this script has NOT been run to completion.
While confirming the ID-space finding above (a handful of plain
requests against the homepage + one team page), the site started
returning a real Cloudflare 403 (Server: cloudflare, cf-ray present,
cf-cache-status: BYPASS -- a freshly-computed block, not a cached
page) on a follow-up request to a *different* team page that had never
been hit before. Same rate-triggered-cooldown pattern already seen
twice on this project (2kratings.com, theshowratings.com) -- standing
rule is one clean test then stop, not a retry loop, and NOT an
automatic reach for curl_cffi (this doesn't look like a TLS
fingerprint block -- it started passing, then failed after repeated
requests from the same IP in a short window, which is a rate/volume
signature, not a first-request rejection). Do not run this script
again same-day; give it a real multi-hour/overnight cooldown first.
"""
import os
import re
import sys
import time
from datetime import datetime, timezone

import duckdb
import pandas as pd
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from name_utils import normalize_name, normalize_for_matching, NHL_NAME_ALIASES

DB_PATH = "nhl/data/fieldview.duckdb"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nhlratings.net/",
}

# abbr (matches nhl_roster.team_abbr, from the same live teams.teams()
# call scrape_roster.py uses) -> nhlratings.net team-page slug. Cross
# referenced live: slugified full team names from teams.teams() against
# the real 32 /teams/ links found on the site's own homepage nav -- 31/32
# auto-matched, Montreal needed a manual fix (site drops the accent:
# "montreal-canadiens", not a slugified "Montréal").
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


class BlockedError(RuntimeError):
    pass


def fetch_with_retry(session, url, retries=3, retries_403=2, backoff=2):
    attempt = 0
    attempt_403 = 0
    while True:
        try:
            resp = session.get(url, timeout=20)
        except Exception as e:
            attempt += 1
            if attempt >= retries:
                raise
            print(f"  network error ({e}), retry {attempt}/{retries}")
            time.sleep(backoff ** attempt)
            continue

        if resp.status_code == 403:
            attempt_403 += 1
            print(f"  403 -- server: {resp.headers.get('server')}, "
                  f"cf-ray: {resp.headers.get('cf-ray')}, "
                  f"cf-cache-status: {resp.headers.get('cf-cache-status')}")
            if attempt_403 >= retries_403:
                raise BlockedError(f"403 Forbidden after {attempt_403} attempts: {url}")
            wait = backoff ** attempt_403
            time.sleep(wait)
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
        print(f"  WARNING: no ratings table found for {team_abbr}")
        return []

    rows = []
    for table in tables:
        rows.extend(parse_roster_table(table, team_abbr, loaded_at))
    return rows


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


if __name__ == '__main__':
    session = requests.Session()
    session.headers.update(HEADERS)

    players = load_roster_players()
    by_name, by_name_team = build_match_index(players)
    print(f"Matching against {len(players)} players from nhl_roster")

    all_rows = []
    completed_teams = 0
    try:
        for i, (abbr, slug) in enumerate(TEAM_SLUGS.items()):
            url = f"https://www.nhlratings.net/teams/{slug}"
            resp = fetch_with_retry(session, url)
            loaded_at = datetime.now(timezone.utc).isoformat()
            rows = parse_team_page(resp.text, abbr, loaded_at)
            all_rows.extend(rows)
            completed_teams += 1
            print(f"{abbr}: {len(rows)} rows")
            if i < len(TEAM_SLUGS) - 1:
                time.sleep(1.5)
    except BlockedError as e:
        print(f"\nBLOCKED: {e}")
        print(f"Stopping -- {completed_teams}/{len(TEAM_SLUGS)} teams completed before the block. Not retrying today.")

    matched = 0
    unmatched = []
    for row in all_rows:
        p = find_match(row['raw_name'], row['team_abbr'], by_name, by_name_team)
        if p:
            row['player_id'] = p['player_id']
            matched += 1
        else:
            row['player_id'] = None
            unmatched.append({'raw_name': row['raw_name'], 'team_abbr': row['team_abbr'], 'position': row['position']})
        row['row_id'] = f"{row['team_abbr']}_{normalize_for_matching(row['raw_name'])}"

    conn = duckdb.connect(DB_PATH)
    if all_rows:
        df = pd.DataFrame(all_rows)
        conn.execute("CREATE OR REPLACE TABLE nhl_ratings AS SELECT * FROM df")
        pct = matched / len(all_rows) * 100
        print(f"\nnhl_ratings: {len(df)} rows loaded from {completed_teams}/{len(TEAM_SLUGS)} teams")
        print(f"Matched: {matched} / {len(all_rows)} ({pct:.1f}%)")
        print(f"Unmatched ({len(unmatched)}): {unmatched}")
    else:
        print("\nNo rows collected -- nhl_ratings table not created.")
    conn.close()
