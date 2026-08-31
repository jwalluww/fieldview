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

Runs in the cloud now (scrape.yml's scrape-nhl job), not local-only.
The original local-only call was a cloud-vs-residential IP theory
(borrowed from stats.nba.com's known behavior) -- that theory was
directly disproved on 2026-08-30: a real request from a genuine
residential IP with TLS impersonation already applied still got an
instant 403, ruling out both "it's a cloud IP" and "it's a TLS
fingerprint check." The block is a static Cloudflare WAF rule, most
likely keyed on IP-level scrape-attempt history, not IP class -- so a
GitHub Actions runner's IP is no more or less exposed to it than this
machine's was. ScraperAPI (Part 2 below) is what actually gets past
it, confirmed live 2026-08-31 across all 32 teams (31/32 clean on the
first pass, the 32nd -- OTT -- clean on an immediate retry, confirming
a transient blip, not a real per-team block).

PART 1 -- retry + fallback (mirrors nfl/scripts/scrape_madden.py's
actual pattern, not reinvented): each team gets a per-request
retry+backoff attempt (fetch_with_retry). Any team that still has no
rows after that gets ONE retry pass after a 20s cooldown. Whatever's
still empty after both passes falls back to that team's most recent
successful scrape already sitting in the nhl_ratings table, rather
than writing empty/null and erasing known-good data over a transient
block. Logged as fresh / stale-carryover / missing (no fallback
available either), same three-way breakdown Madden's script prints.
This is the one piece of the old design that's still needed --
ScraperAPI fixed the block, not the odd one-off miss.

PART 2 -- ScraperAPI proxy, full 32-team run every time (mirrors
mlb/scripts/scrape_ratings.py's rebuild exactly, not reinvented):
routes requests through
http://api.scraperapi.com?api_key={key}&url={target} instead of a
direct request, and pulls all 32 teams in one run. API key read from
the SCRAPERAPI_KEY environment variable ONLY, same as MLB's script --
raises immediately if unset. No custom target-site headers are sent
(also matching MLB) -- ScraperAPI manages the outbound request's own
fingerprint.

Replaces an earlier daily-trickle design (3 random teams/run from a
persisted rolling pool, nhl/data/ratings_scrape_state.json) that
existed because repeated direct requests from this machine's one IP
tripped nhlratings.net's rate-limiting. That constraint doesn't apply
here -- ScraperAPI's outbound IP isn't this machine's, and a full
30-team MLB run through the same proxy already proved a full run is
the right shape once the proxy is doing the work. The rolling-pool
state file and its 3-teams-per-run selection logic are gone entirely,
same as MLB never had them in its ScraperAPI rebuild. Fixed 2026-08-31.
"""
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import duckdb
import pandas as pd
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from name_utils import normalize_name, normalize_for_matching, NHL_NAME_ALIASES

DB_PATH = "nhl/data/fieldview.duckdb"
PROXY_BASE = "http://api.scraperapi.com"


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


def fetch_with_retry(session, url, retries=3, retries_403=2, backoff=3):
    """Raises on total failure (network error after `retries` attempts,
    or a 403/5xx after `retries_403` attempts) -- never returns None.
    Callers (scrape_team) are responsible for catching and turning that
    into an empty-list failure signal, same shape as Madden's
    scrape_team(). Mirrors mlb/scripts/scrape_ratings.py's version:
    requests go through proxy_url(url), not url directly; `backoff`
    starts at 3 (not 2) because proxy round-trips are inherently slower
    than a direct request."""
    attempt = 0
    attempt_403 = 0
    while True:
        try:
            resp = session.get(proxy_url(url), timeout=70)
        except Exception as e:
            attempt += 1
            if attempt >= retries:
                raise
            print(f"    network error ({e}), retry {attempt}/{retries}")
            time.sleep(backoff ** attempt)
            continue

        # ScraperAPI passes through the target site's status code when it
        # successfully completes a fetch; a 403 here means nhlratings.net
        # blocked even the proxy's request, not that ScraperAPI itself
        # failed. 5xx from ScraperAPI itself (couldn't complete the
        # proxied fetch at all) gets the same retry treatment.
        if resp.status_code == 403 or resp.status_code >= 500:
            attempt_403 += 1
            print(f"    status {resp.status_code} via proxy, "
                  f"retry {attempt_403}/{retries_403}")
            if attempt_403 >= retries_403:
                raise RuntimeError(f"Blocked/failed via proxy after {attempt_403} attempts "
                                    f"(status {resp.status_code}): {url}")
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
    """Base population for the stale-carryover fallback -- reads
    whatever's currently in nhl_ratings (from a prior run), grouped by
    team. Empty dict if the table doesn't exist yet (first run ever)."""
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


def single_page_test(session):
    """Confirms the proxy actually clears nhlratings.net's WAF block
    before spending a full 32-team run on it -- mirrors
    mlb/scripts/scrape_ratings.py's single_page_test() exactly: a raw
    one-shot request, not fetch_with_retry's full retry+backoff loop, so
    a still-blocked proxy fails fast instead of quietly burning that
    schedule before this run even gets to real teams."""
    abbr, slug = next(iter(TEAM_SLUGS.items()))
    url = f"https://www.nhlratings.net/teams/{slug}"
    print(f"Single-page test: {abbr} via ScraperAPI proxy...")
    try:
        resp = session.get(proxy_url(url), timeout=70)
    except Exception as e:
        print(f"  ERROR: {e}")
        return False
    print(f"  status: {resp.status_code}, content length: {len(resp.text)}")
    if resp.status_code != 200:
        print(f"  Non-200 status -- proxy did not clear the block.")
        return False
    loaded_at = datetime.now(timezone.utc).isoformat()
    rows = parse_team_page(resp.text, abbr, loaded_at)
    print(f"  Parsed {len(rows)} rows")
    if not rows:
        print(f"  No rows parsed -- either blocked (check saved HTML) or page structure changed.")
        return False
    print(f"  CLEARED -- sample row: {rows[0]}")
    return True


if __name__ == '__main__':
    session = requests.Session()

    if not single_page_test(session):
        print("\nSingle-page test did not clear the block via ScraperAPI. "
              "Stopping -- not attempting the full 32-team run, and not "
              "writing to nhl_ratings this run.")
        raise SystemExit(1)

    print(f"\nSingle-page test cleared -- proceeding with the full {len(TEAM_SLUGS)}-team run.")
    time.sleep(random.uniform(8, 15))

    players = load_roster_players()
    by_name, by_name_team = build_match_index(players)
    existing_by_team = load_existing_ratings_by_team()

    by_team = {}
    for i, (abbr, slug) in enumerate(TEAM_SLUGS.items()):
        by_team[abbr] = scrape_team(session, abbr, slug)
        print(f"{abbr}: {len(by_team[abbr])} rows")
        if i < len(TEAM_SLUGS) - 1:
            time.sleep(random.uniform(8, 15))

    failed = [abbr for abbr in TEAM_SLUGS if not by_team[abbr]]
    if failed:
        print(f"\n{len(failed)} team(s) failed in-run, retrying after a cooldown: {failed}")
        time.sleep(20)
        for abbr in failed:
            by_team[abbr] = scrape_team(session, abbr, TEAM_SLUGS[abbr])
            print(f"{abbr}: {len(by_team[abbr])} rows (retry)")
            time.sleep(random.uniform(8, 15))

    fresh, stale, missing = [], [], []
    for abbr in TEAM_SLUGS:
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

    all_rows = []
    for abbr in TEAM_SLUGS:
        all_rows.extend(by_team[abbr])

    conn = duckdb.connect(DB_PATH)
    if all_rows:
        df = pd.DataFrame(all_rows)
        conn.execute("CREATE OR REPLACE TABLE nhl_ratings AS SELECT * FROM df")
        print(f"\nnhl_ratings: {len(df)} rows loaded across {len(TEAM_SLUGS)} teams "
              f"({len(fresh)} fresh, {len(stale)} stale-carryover, {len(missing)} missing)")
    else:
        print("\nNo rows collected -- nhl_ratings table not created.")
    conn.close()
