"""nba/scripts/scrape_nba2kapi.py

NBA 2K ratings from nba2kapi (https://api.nba2kapi.com), replacing
scrape_2kratings.py's 3-team-a-day trickle off 2kratings.com. nba2kapi
re-publishes 2kratings.com's data (same source we scraped before) as JSON,
for the whole current-era pool in one request, so the cloud scrape-nba job
can refresh every team every run instead of a local task covering ~10% a day.

Writes nba/data/nba_ratings_2k.json in EXACTLY the shape the old scraper
did -- {"ratings": [...], "unmatched": [...]} with the same per-rating
fields -- so build_nba_db / build_nba_match / export_nba_master consume it
unchanged -- plus a sidecar nba/data/ratings_meta.json:
    {"ratings_last_changed": "YYYY-MM-DD", "game_version": "2K27", ...}
read by CourtView's "2K ratings as of <date>" caption. ratings_last_changed
is diff-based (same pattern as nba_depth_chart.json's last_changed and
EPL/MLS's ea_fc snapshots): carried forward when no rating/team/position
changed, bumped to today when anything did.

Field mapping (verified 2026-10-24 against the old scraper's rows):
    name         normalize_name(api name)         2k_name   api name
    name_norm    normalize_for_matching(api name) team      NBA abbreviation
    positions    "/".join(positions + [height])   -- the old rows carried
                 the height link in the positions string ("SG/PG/6'5\\"")
    overall_rating <- overall      profile_url <- playerUrl
    attr_3pt <- attributes.threePointShot
    attr_dnk <- attributes.drivingDunk
    loaded_at <- the API's per-player lastUpdated (stable between runs, so
                 an unchanged pool rewrites a byte-identical file)
    jersey_number: null -- the API has none; the master takes jersey from
                 nba_stats.json, never from this file.
    player_id: matched against nba_stats.json exactly as before (alias ->
               name+team -> unique name-only).
Players on "Free Agency" (2K27's unsigned pool, 138 players with real
ratings) get team "FA" and can only match by unique name.

Auth/fetch: GET /api/players/bulk?teamType=curr with the X-API-Key header
(key from the NBA2KAPI_KEY environment variable, a repo secret in Actions --
never printed or written anywhere). If the key is missing, rejected or
rate-limited, falls back to the documented keyless /api/public/players
(paginated, 60 requests/minute/IP) -- the same data, 7 requests.

Guards (any failure keeps the previous nba_ratings_2k.json and exits 0, so
staleness shows up as an old ratings_last_changed): fewer than
max(500, 0.9x the previous pull) cards, fewer than 28 NBA teams, cards
spanning more than one gameVersion or not matching the API's declared
current version (/api/versions), or cards without a numeric overall.
"""
import json
import os
import sys
import time
from datetime import date, datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from name_utils import normalize_name, normalize_for_matching, NBA_NAME_ALIASES

BASE = 'https://api.nba2kapi.com'
USER_AGENT = 'fieldview-nba-ratings/1.0 (+https://github.com/jwalluww/fieldview)'
STATS_PATH = os.path.join('nba', 'data', 'nba_stats.json')
OUT_PATH = os.path.join('nba', 'data', 'nba_ratings_2k.json')
META_PATH = os.path.join('nba', 'data', 'ratings_meta.json')
ABS_MIN_CARDS = 500
MIN_TEAMS = 28

TEAM_ABBR = {
    'Atlanta Hawks': 'ATL', 'Boston Celtics': 'BOS', 'Brooklyn Nets': 'BKN', 'Charlotte Hornets': 'CHA',
    'Chicago Bulls': 'CHI', 'Cleveland Cavaliers': 'CLE', 'Dallas Mavericks': 'DAL', 'Denver Nuggets': 'DEN',
    'Detroit Pistons': 'DET', 'Golden State Warriors': 'GSW', 'Houston Rockets': 'HOU', 'Indiana Pacers': 'IND',
    'Los Angeles Clippers': 'LAC', 'Los Angeles Lakers': 'LAL', 'Memphis Grizzlies': 'MEM', 'Miami Heat': 'MIA',
    'Milwaukee Bucks': 'MIL', 'Minnesota Timberwolves': 'MIN', 'New Orleans Pelicans': 'NOP',
    'New York Knicks': 'NYK', 'Oklahoma City Thunder': 'OKC', 'Orlando Magic': 'ORL',
    'Philadelphia 76ers': 'PHI', 'Phoenix Suns': 'PHX', 'Portland Trail Blazers': 'POR',
    'Sacramento Kings': 'SAC', 'San Antonio Spurs': 'SAS', 'Toronto Raptors': 'TOR', 'Utah Jazz': 'UTA',
    'Washington Wizards': 'WAS',
}
FA_TEAM = 'Free Agency'


def _get(path, params=None, key=None, retries=4):
    """GET with backoff; returns parsed JSON or None. Never logs headers."""
    headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}
    if key:
        headers['X-API-Key'] = key
    last = None
    for attempt in range(retries):
        if attempt:
            time.sleep(2 ** attempt)
        try:
            r = requests.get(BASE + path, params=params, headers=headers, timeout=60)
            if r.status_code == 200:
                return r.json()
            last = f'HTTP {r.status_code}'
            if r.status_code in (401, 403):
                break  # a bad/missing key won't fix itself on retry
            if r.status_code == 429:
                try:
                    time.sleep(min(int(r.json()['error']['details']['retryAfter']), 60))
                except (ValueError, KeyError, TypeError):
                    pass
        except (requests.RequestException, ValueError) as e:
            last = type(e).__name__
    print(f'  nba2kapi: {path} failed ({last})')
    return None


def fetch_via_bulk(key):
    j = _get('/api/players/bulk', {'teamType': 'curr'}, key=key)
    if not j or not j.get('success') or not isinstance(j.get('data'), list):
        return None
    total = ((j.get('meta') or {}).get('total'))
    if total is not None and total != len(j['data']):
        print(f'  nba2kapi: bulk returned {len(j["data"])} of {total} -- treating as truncated')
        return None
    return j['data']


def fetch_via_public():
    cards, cursor, total = [], None, None
    while True:
        params = {'teamType': 'curr', 'limit': 100}
        if cursor:
            params['cursor'] = cursor
        j = _get('/api/public/players', params)
        if not j or not j.get('success'):
            return None
        pg = (j.get('meta') or {}).get('pagination') or {}
        if total is None:
            total = pg.get('total')
        got = j.get('data') or []
        cards.extend(got)
        cursor = pg.get('nextCursor')
        if not got or not pg.get('hasMore') or not cursor:
            break
        time.sleep(1.2)  # well under 60 requests/minute
    if total is not None and len(cards) != total:
        print(f'  nba2kapi: public pull got {len(cards)} of {total} -- treating as truncated')
        return None
    return cards


def fetch_cards():
    key = os.environ.get('NBA2KAPI_KEY', '').strip()
    if key:
        cards = fetch_via_bulk(key)
        if cards is not None:
            print(f'Fetched {len(cards)} cards via /api/players/bulk')
            return cards
        print('Bulk fetch failed or key rejected -- falling back to the keyless public endpoint')
    else:
        print('NBA2KAPI_KEY not set -- using the keyless public endpoint')
    cards = fetch_via_public()
    if cards is not None:
        print(f'Fetched {len(cards)} cards via /api/public/players')
    return cards


def load_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def check_cards(cards, prev_total):
    """Returns None if the pull looks sane, else a reason string."""
    floor = max(ABS_MIN_CARDS, int(prev_total * 0.9))
    if len(cards) < floor:
        return f'only {len(cards)} cards (expected >= {floor})'
    if any(not isinstance(c.get('overall'), int) for c in cards):
        return 'cards without a numeric overall'
    versions = {c.get('gameVersion') for c in cards}
    if len(versions) != 1 or None in versions:
        return f'cards span gameVersions {sorted(map(str, versions))}'
    teams = {c.get('team') for c in cards} & set(TEAM_ABBR)
    if len(teams) < MIN_TEAMS:
        return f'only {len(teams)} NBA teams present (expected >= {MIN_TEAMS})'
    current = ((_get('/api/versions') or {}).get('meta') or {}).get('current')
    if current and current != next(iter(versions)):
        return f'cards are {next(iter(versions))} but the API\'s current edition is {current}'
    return None


def to_record(card):
    raw = card['name']
    attrs = card.get('attributes') or {}
    team = TEAM_ABBR.get(card.get('team'), 'FA')
    pos = list(card.get('positions') or [])
    if card.get('height'):
        pos.append(card['height'])
    return {
        'name': normalize_name(raw),
        '2k_name': raw,
        'name_norm': normalize_for_matching(raw),
        'team': team,
        'jersey_number': None,
        'positions': '/'.join(pos) or None,
        'overall_rating': card['overall'],
        'profile_url': card.get('playerUrl'),
        'loaded_at': card.get('lastUpdated'),
        'attr_3pt': attrs.get('threePointShot'),
        'attr_dnk': attrs.get('drivingDunk'),
    }


def build_index(players):
    by_name, by_name_team = {}, {}
    for p in players:
        key = normalize_for_matching(p['name'])
        by_name.setdefault(key, []).append(p)
        by_name_team[(key, p['team'])] = p
    return by_name, by_name_team


def find_match(record, by_name, by_name_team):
    """Same tiers as scrape_2kratings.find_match: alias, name+team, unique name."""
    lookup = NBA_NAME_ALIASES.get(record['2k_name'], record['2k_name'])
    if lookup is None:
        return None
    key = normalize_for_matching(normalize_name(lookup))
    exact = by_name_team.get((key, record['team']))
    if exact:
        return exact
    candidates = by_name.get(key, [])
    return candidates[0] if len(candidates) == 1 else None


def comparable(records):
    """Rating content only -- loaded_at/player_id aside -- for the diff."""
    drop = {'loaded_at', 'player_id'}
    return sorted(({k: v for k, v in r.items() if k not in drop} for r in records),
                  key=lambda r: (r['2k_name'], r['team']))


def main():
    prev_out = load_json(OUT_PATH) or {}
    prev_meta = load_json(META_PATH) or {}
    prev_total = prev_meta.get('source_total') or 0

    cards = fetch_cards()
    if cards is None:
        print(f'nba2kapi fetch failed -- keeping the previous {OUT_PATH}')
        return
    reason = check_cards(cards, prev_total)
    if reason:
        print(f'nba2kapi pull rejected ({reason}) -- keeping the previous {OUT_PATH}')
        return

    stats = load_json(STATS_PATH) or {}
    by_name, by_name_team = build_index(list(stats.values()))
    records = [to_record(c) for c in cards]
    records.sort(key=lambda r: (r['team'], -r['overall_rating'], r['2k_name']))
    for r in records:
        p = find_match(r, by_name, by_name_team)
        r['player_id'] = p['player_id'] if p else None
    unmatched = [{'2k_name': r['2k_name'], 'team': r['team'], 'positions': r.get('positions')}
                 for r in records if r['player_id'] is None]

    today = date.today().isoformat()
    old_records = prev_out.get('ratings') or []
    if old_records and prev_meta.get('ratings_last_changed') and comparable(old_records) == comparable(records):
        changed = prev_meta['ratings_last_changed']
        print(f'{len(records)} ratings unchanged since {changed}')
    else:
        changed = today
        print(f'{len(records)} ratings changed (or first run), ratings_last_changed={changed}')

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump({'ratings': records, 'unmatched': unmatched}, f, indent=2)
    meta = {
        'ratings_last_changed': changed,
        'game_version': cards[0].get('gameVersion'),
        'source': BASE,
        'source_total': len(cards),
    }
    with open(META_PATH, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)
    matched = len(records) - len(unmatched)
    print(f'{OUT_PATH}: {len(records)} records, matched to nba_stats.json: {matched} ({matched / len(records):.1%}), '
          f'unmatched: {len(unmatched)}')


if __name__ == '__main__':
    main()
