"""NBA contracts from Basketball-Reference's contracts page (replaces Spotrac, which 403s runners).

ONE request (https://www.basketball-reference.com/contracts/players.html), same header set / UTF-8
decoding / comment-table handling / retry rules as scrape_bbr_advanced.py. Together with the two
advanced-stats requests that is 3 BBR requests per weekly run; this one is sent >= MIN_GAP seconds
after the advanced-stats scraper's last request (a sleep at the start guarantees it).

Writes nba/data/contracts_nba.json in the shape build_nba_db/build_nba_match read:
  {"contracts": [{name, spotrac_name, name_norm, pos, team, age, length_remaining,
                  cash_total_remaining, cash_guaranteed_remaining, pct_guaranteed_remaining, player_id}],
   "unmatched": [...]}
 length_remaining = seasons with a salary listed (y1 = the current season, incl. option years, like Spotrac)
 cash_total_remaining = sum of the listed salaries; cash_guaranteed_remaining = BBR's `Guaranteed` column
 pos = the ESPN-universe position, age = null (BBR's page has neither).
Guard (keep the old file, exit 0): non-200/429, no table, < 250 rows, missing columns, < 80% matched.
"""
import json
import os
import re
import sys
import time

import requests
from bs4 import BeautifulSoup, Comment

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from name_utils import normalize_for_matching  # noqa: E402
from scrape_bbr_advanced import (HEADERS, TEAM_MAP, MIN_GAP, STATS_PATH, build_universe_index,  # noqa: E402
                                 match_player)

URL = 'https://www.basketball-reference.com/contracts/players.html'
OUT_PATH = os.path.join('nba', 'data', 'contracts_nba.json')
MIN_ROWS = 250
YEAR_COLS = ('y1', 'y2', 'y3', 'y4', 'y5', 'y6')


class Failed(Exception):
    pass


def money(text):
    t = re.sub(r'[$,\s]', '', text or '')
    return int(t) if t.isdigit() else None


def fetch(session):
    last = None
    for attempt in (1, 2):
        try:
            r = session.get(URL, headers=HEADERS, timeout=40)
        except requests.RequestException as e:
            last = f'{type(e).__name__}: {str(e)[:100]}'
        else:
            if r.status_code == 200:
                return r.content.decode('utf-8', errors='replace')
            if r.status_code == 429:
                raise Failed(f'HTTP 429 (rate limited) for {URL}')
            last = f'HTTP {r.status_code}'
            if r.status_code < 500:
                break
        if attempt == 1:
            time.sleep(MIN_GAP)
    raise Failed(f'{last} for {URL}')


def find_table(html):
    soup = BeautifulSoup(html, 'html.parser')
    t = soup.find('table', id='player-contracts')
    if t is None:
        for c in soup.find_all(string=lambda s: isinstance(s, Comment) and 'id="player-contracts"' in s):
            t = BeautifulSoup(c, 'html.parser').find('table', id='player-contracts')
            if t is not None:
                break
    return t


def parse(html):
    t = find_table(html)
    if t is None:
        raise Failed('no player-contracts table (challenge page?)')
    rows = []
    for tr in t.find('tbody').find_all('tr'):
        if 'thead' in (tr.get('class') or []):
            continue
        cells = {c.get('data-stat'): c for c in tr.find_all(['th', 'td'])}
        if 'player' not in cells or 'remain_gtd' not in cells or 'y1' not in cells:
            continue
        name = cells['player'].get_text(strip=True)
        if not name:
            continue
        sal = [money(cells[c].get_text(strip=True)) if c in cells else None for c in YEAR_COLS]
        sal = [s for s in sal if s is not None]
        a = cells['player'].find('a')
        m = re.search(r'/players/\w/(\w+)\.html', a['href']) if a and a.get('href') else None
        team = cells['team_id'].get_text(strip=True) if 'team_id' in cells else None
        rows.append({'name': name, 'team': TEAM_MAP.get(team, team), 'bbr_id': m.group(1) if m else None,
                     'salaries': sal, 'guaranteed': money(cells['remain_gtd'].get_text(strip=True)) or 0})
    if not rows or any(c not in {x.get('data-stat') for x in t.find('thead').find_all('th')} for c in ('y1', 'remain_gtd')):
        raise Failed('missing contract columns')
    return rows


def main():
    time.sleep(MIN_GAP)  # the advanced-stats scraper (2 BBR requests) runs right before this one in the cloud job
    try:
        rows = parse(fetch(requests.Session()))
        print(f'{len(rows)} contract rows')
        if len(rows) < MIN_ROWS:
            raise Failed(f'only {len(rows)} rows (< {MIN_ROWS})')
        with open(STATS_PATH, encoding='utf-8') as f:
            stats = json.load(f)
        by_name_team, by_name = build_universe_index()
    except Failed as e:
        print(f'GUARD: {e}\nKeeping the existing {OUT_PATH}.')
        return 0
    except Exception as e:  # any other failure keeps the old file too
        print(f'GUARD: {type(e).__name__}: {str(e)[:150]}\nKeeping the existing {OUT_PATH}.')
        return 0

    contracts, unmatched = [], []
    for r in rows:
        pid = match_player({'name_display': r['name'], 'team': r['team']}, by_name_team, by_name)
        if pid is None:
            unmatched.append({'name': r['name'], 'team': r['team'], 'bbr_id': r['bbr_id']})
            continue
        cash = sum(r['salaries'])
        contracts.append({
            'name': r['name'], 'spotrac_name': r['name'], 'name_norm': normalize_for_matching(r['name']),
            'bbr_id': r['bbr_id'], 'pos': (stats.get(str(pid)) or stats.get(pid) or {}).get('position'),
            'team': r['team'], 'age': None, 'length_remaining': len(r['salaries']),
            'cash_total_remaining': cash, 'cash_guaranteed_remaining': r['guaranteed'],
            'pct_guaranteed_remaining': round(100 * r['guaranteed'] / cash, 2) if cash else 0.0,
            'player_id': pid,
        })
    if len(contracts) < 0.8 * len(rows):
        print(f'GUARD: only {len(contracts)}/{len(rows)} matched to the ESPN universe; keeping the existing {OUT_PATH}.')
        return 0
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump({'contracts': contracts, 'unmatched': unmatched}, f, indent=2, ensure_ascii=False)
    print(f'Wrote {OUT_PATH}: {len(contracts)} matched, {len(unmatched)} unmatched')
    return 0


if __name__ == '__main__':
    sys.exit(main())
