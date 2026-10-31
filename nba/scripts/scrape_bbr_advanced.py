"""NBA advanced stats from Basketball-Reference (BBR).

Exactly two requests per run -- the current season's NBA_<end year>_advanced.html
and the prior season's -- at least MIN_GAP seconds apart (BBR: 20 req/min limit,
violators jailed up to a day; robots.txt asks a 3s crawl delay). Plain requests
with a complete Chrome header set. At most one retry, never on a 429. A 429, a
non-200, or a challenge page (HTML without the advanced table) is a failure.

BBR specifics handled here:
  * tables may sit inside HTML comments -> comments are un-commented before parsing
  * traded players have a combined row (2TM/3TM/...) plus one row per team: the
    combined row supplies the stats, the LAST per-team row supplies the team
  * BBR team codes differ from ours (PHO, BRK, CHO) -> TEAM_MAP

Rows are matched to the ESPN universe in nba_stats.json upstream (like the other
NBA scrapers): normalized name + team via name_utils (folds BBR's accents, honours
NBA_NAME_ALIASES), then a unique-name fallback (also covers players who changed
teams since the prior season). Writes nba/data/bbr_advanced.json:
  {fetched_at, seasons, advanced: [rows incl. player_id or null], unmatched: [...]}
with BBR's raw field names plus bbr_id, season and team.

Any guard failure keeps the old file and exits 0. Run from the repo root:
  python nba/scripts/scrape_bbr_advanced.py
"""
import json
import os
import re
import sys
import time
from datetime import date, datetime, timezone

import requests
from bs4 import BeautifulSoup, Comment

from name_utils import NBA_NAME_ALIASES, normalize_for_matching

STATS_PATH = os.path.join('nba', 'data', 'nba_stats.json')
OUT_PATH = os.path.join('nba', 'data', 'bbr_advanced.json')
URL = 'https://www.basketball-reference.com/leagues/NBA_{year}_advanced.html'

HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
}
MIN_GAP = 4.5          # seconds between the two requests (>= 4 required)
MIN_CURRENT_ROWS = 150

TEAM_MAP = {'BRK': 'BKN', 'CHO': 'CHA', 'PHO': 'PHX'}  # everything else is identical

# Numeric columns kept (BBR raw names); name_display / team_name_abbr / bbr_id handled apart.
NUM_FIELDS = ('games', 'games_started', 'mp', 'per', 'ts_pct', 'orb_pct', 'drb_pct', 'trb_pct',
              'ast_pct', 'stl_pct', 'blk_pct', 'tov_pct', 'usg_pct', 'ows', 'dws', 'ws',
              'ws_per_48', 'obpm', 'dbpm', 'bpm', 'vorp')
REQUIRED = ('name_display', 'team_name_abbr', 'games', 'mp', 'per', 'ts_pct', 'orb_pct', 'drb_pct',
            'trb_pct', 'ast_pct', 'stl_pct', 'blk_pct', 'tov_pct', 'usg_pct', 'ws', 'ws_per_48',
            'obpm', 'dbpm', 'bpm', 'vorp')
COMBINED_RE = re.compile(r'^\dTM$')


class Failed(Exception):
    pass


def season_end_year():
    today = date.today()
    return today.year + 1 if today.month >= 10 else today.year


def season_label(end_year):
    return f'{end_year - 1}-{str(end_year)[-2:]}'


def fetch_page(session, year):
    """One request, at most one retry (never after a 429)."""
    url = URL.format(year=year)
    last = None
    for attempt in (1, 2):
        try:
            r = session.get(url, headers=HEADERS, timeout=40)
        except requests.RequestException as e:
            last = f'{type(e).__name__}: {str(e)[:100]}'
        else:
            if r.status_code == 200:
                return r.content.decode('utf-8', errors='replace')  # BBR sends no charset; requests would guess latin-1
            if r.status_code == 429:
                raise Failed(f'HTTP 429 (rate limited) for {url}')
            last = f'HTTP {r.status_code}'
            if r.status_code < 500:
                break
        if attempt == 1:
            time.sleep(MIN_GAP)
    raise Failed(f'{last} for {url}')


def find_table(html):
    soup = BeautifulSoup(html, 'html.parser')
    t = soup.find('table', id='advanced')
    if t is None:  # BBR sometimes ships tables inside HTML comments
        for c in soup.find_all(string=lambda s: isinstance(s, Comment) and 'id="advanced"' in s):
            t = BeautifulSoup(c, 'html.parser').find('table', id='advanced')
            if t is not None:
                break
    return t


def num(text):
    text = (text or '').strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_table(html, year):
    table = find_table(html)
    if table is None or table.tbody is None:
        raise Failed(f'{year}: no advanced table in page (challenge page or layout change)')
    players, order = {}, []   # bbr_id -> {'combined': row|None, 'teams': [row...]}
    seen_stats = set()
    for tr in table.tbody.find_all('tr'):
        if 'thead' in (tr.get('class') or []):
            continue
        cells = {c.get('data-stat'): c for c in tr.find_all(['th', 'td']) if c.get('data-stat')}
        seen_stats.update(cells)
        nm = cells.get('name_display')
        if nm is None or not nm.get_text(strip=True):
            continue
        if not cells.get('team_name_abbr') or not cells['team_name_abbr'].get_text(strip=True):
            continue  # 'League Average' footer row
        bbr_id = nm.get('data-append-csv') or nm.get_text(strip=True)
        team = cells['team_name_abbr'].get_text(strip=True) if 'team_name_abbr' in cells else ''
        row = {'name_display': nm.get_text(strip=True), 'bbr_id': bbr_id, 'bbr_team': team}
        for f in NUM_FIELDS:
            row[f] = num(cells[f].get_text()) if f in cells else None
        if bbr_id not in players:
            players[bbr_id] = {'combined': None, 'teams': []}
            order.append(bbr_id)
        if COMBINED_RE.match(team):
            players[bbr_id]['combined'] = row
        else:
            players[bbr_id]['teams'].append(row)
    missing = [c for c in REQUIRED if c not in seen_stats]
    if missing:
        raise Failed(f'{year}: required columns missing: {missing}')
    rows = []
    for bid in order:
        p = players[bid]
        if not p['teams'] and p['combined'] is None:
            continue
        base = p['combined'] or p['teams'][-1]
        last_team = p['teams'][-1]['bbr_team'] if p['teams'] else base['bbr_team']
        row = dict(base)
        row.pop('bbr_team')
        row['team'] = TEAM_MAP.get(last_team, last_team)
        rows.append(row)
    return rows


def build_universe_index():
    with open(STATS_PATH, encoding='utf-8') as f:
        stats = json.load(f)
    by_name_team, by_name = {}, {}
    for p in stats.values():
        k = normalize_for_matching(p.get('name'))
        by_name_team.setdefault((k, p.get('team')), []).append(p['player_id'])
        by_name.setdefault(k, []).append(p['player_id'])
    return by_name_team, by_name


def match_player(row, by_name_team, by_name):
    inverse = {v: k for k, v in NBA_NAME_ALIASES.items()}
    n = row['name_display']
    keys = {normalize_for_matching(x) for x in (n, NBA_NAME_ALIASES.get(n), inverse.get(n)) if x}
    ids = {i for k in keys for i in by_name_team.get((k, row['team']), [])}
    if len(ids) == 1:
        return next(iter(ids))
    ids = {i for k in keys for i in by_name.get(k, [])}   # unique-name fallback (also handles team changes)
    return next(iter(ids)) if len(ids) == 1 else None


def main():
    try:
        end_year = season_end_year()
        session = requests.Session()
        pages = []
        for i, year in enumerate((end_year, end_year - 1)):
            if i:
                time.sleep(MIN_GAP)
            rows = parse_table(fetch_page(session, year), year)
            print(f'{year}: {len(rows)} players')
            if i == 0 and len(rows) < MIN_CURRENT_ROWS:
                raise Failed(f'{year}: only {len(rows)} rows (< {MIN_CURRENT_ROWS})')
            pages.append((year, rows))
        by_name_team, by_name = build_universe_index()
    except Failed as e:
        print(f'GUARD: {e}\nKeeping the existing {OUT_PATH}.')
        return 0

    advanced, unmatched = [], []
    for year, rows in pages:
        label = season_label(year)
        matched = 0
        for r in rows:
            r['season'] = label
            r['player_id'] = match_player(r, by_name_team, by_name)
            advanced.append(r)
            if r['player_id'] is None:
                unmatched.append({'season': label, 'name_display': r['name_display'], 'team': r['team'],
                                  'bbr_id': r['bbr_id']})
            else:
                matched += 1
        print(f'{label}: matched {matched}/{len(rows)} to the ESPN universe')

    fetched_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    if os.path.exists(OUT_PATH):  # unchanged content keeps the old timestamp (no noise commits)
        with open(OUT_PATH, encoding='utf-8') as f:
            old = json.load(f)
        if old.get('advanced') == advanced:
            fetched_at = old.get('fetched_at', fetched_at)
    out = {'fetched_at': fetched_at, 'seasons': [season_label(y) for y, _ in pages],
           'advanced': advanced, 'unmatched': unmatched}
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f'Wrote {OUT_PATH}: {len(advanced)} rows, {len(unmatched)} unmatched')
    return 0


if __name__ == '__main__':
    sys.exit(main())
