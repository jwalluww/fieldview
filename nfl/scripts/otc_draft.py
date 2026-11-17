"""Shared OverTheCap Draft page (https://overthecap.com/draft) parser.

One page pull feeds two things:
  - parse_order(): pick -> CURRENT owner (real traded picks; the order is OTC's projection from the standings)
  - parse_scale(): projected 2027 rookie contract by pick
OTC does not publish the ORIGINAL owner, so original_team is inferred: in every round the 32 base slots
go to teams in the same order, so a slot whose modal owner across the 7 rounds is strongly unambiguous
(>= 4 rounds and >= 3 ahead of the runner-up; OTC's tie-break order wobbles between rounds) is that team's own slot; a pick held by anyone else is "from" that team. Ambiguous slots (tied records, a team that
traded everything) and compensatory picks get original_team == team (no "from" label) - never a guess.
Every function returns None / (None, why) on a shape problem so callers keep their old files.
"""
import re
from collections import Counter

import requests
from bs4 import BeautifulSoup

URL = 'https://overthecap.com/draft'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/124.0 Safari/537.36')
TEAM_MAP = {'ARI': 'ARZ'}   # OTC -> OurLads (site-wide) code
OUR_TEAMS = {'ARZ', 'ATL', 'BAL', 'BUF', 'CAR', 'CHI', 'CIN', 'CLE', 'DAL', 'DEN', 'DET', 'GB', 'HOU', 'IND',
             'JAX', 'KC', 'LAC', 'LAR', 'LV', 'MIA', 'MIN', 'NE', 'NO', 'NYG', 'NYJ', 'PHI', 'PIT', 'SEA',
             'SF', 'TB', 'TEN', 'WAS'}


def fetch_soup():
    """-> BeautifulSoup of the page, or None (non-200 / network error)."""
    try:
        r = requests.get(URL, headers={'User-Agent': UA}, timeout=60)
    except requests.RequestException as e:
        print(f'  OTC draft page: {type(e).__name__}')
        return None
    if r.status_code != 200:
        print(f'  OTC draft page: HTTP {r.status_code}')
        return None
    return BeautifulSoup(r.text, 'html.parser')


def parse_order(soup):
    """-> (list of {pick, round, team, original_team}, None) or (None, reason)."""
    owner, rnd = {}, {}
    for td in soup.select('td[data-round]'):
        ov = td.select_one('span.overall')
        if not ov or not td.get('data-team'):
            continue
        n = int(ov.get_text())
        if n in owner:
            return None, f'duplicate pick {n}'
        owner[n] = TEAM_MAP.get(td['data-team'], td['data-team'])
        rnd[n] = int(td['data-round'])
    n = len(owner)
    if not 224 <= n <= 262 or sorted(owner) != list(range(1, n + 1)):
        return None, f'OTC order has {n} picks / not contiguous from 1'
    bad = {t for t in owner.values() if t not in OUR_TEAMS}
    if bad:
        return None, f'unknown team code(s) {sorted(bad)}'
    if len(set(owner.values())) < 32:
        return None, f'only {len(set(owner.values()))} teams own picks'
    rc = Counter(rnd.values())
    if sorted(rc) != list(range(1, 8)) or [rnd[i] for i in range(1, n + 1)] != sorted(rnd.values()):
        return None, 'rounds are not 1-7 in pick order'
    start, e = {}, 1
    for r in range(1, 8):
        start[r] = e
        e += rc[r]
    # slot i (0-31) -> its own team, from the modal owner across rounds
    slot_own = {}
    modal = []
    for i in range(32):
        c = Counter(owner[start[r] + i] for r in range(1, 8) if i < rc[r])
        mc = c.most_common(2)
        modal.append((mc[0][0], mc[0][1], mc[1][1] if len(mc) > 1 else 0))
    claims = Counter(t for t, n1, n2 in modal if n1 >= 4 and n1 - n2 >= 3)
    for i, (t, n1, n2) in enumerate(modal):
        if n1 >= 4 and n1 - n2 >= 3 and claims[t] == 1:
            slot_own[i] = t
    out = []
    for p in range(1, n + 1):
        r = rnd[p]
        i = p - start[r]
        orig = slot_own.get(i, owner[p]) if i < 32 else owner[p]
        out.append({'pick': p, 'round': r, 'team': owner[p], 'original_team': orig})
    return out, None


def _money(s):
    return int(re.sub(r'[^\d]', '', s))


def parse_scale(soup):
    """-> {'picks': {n: {...}}} for pick 1-257 x 4 years (the old build_rookie_scale shape) or None."""
    picks = {}
    for box in soup.select('div.pick-full-contract'):
        ov = box.select_one('strong span.overall')
        if not ov:
            continue
        n = int(ov.get_text())
        txt = box.get_text(' ', strip=True)
        tv = re.search(r'Total Value:\s*\$([\d,]+)', txt)
        sb = re.search(r'Signing Bonus:\s*\$([\d,]+)', txt)
        rows = [tr for tr in box.select('table.draft-pick-table tbody tr')
                if re.fullmatch(r'20\d\d', tr.td.get_text(strip=True) if tr.td else '')]
        if not (tv and sb and rows) or n in picks:
            continue
        total = _money(tv.group(1))
        picks[n] = {'years': len(rows), 'total_value': total, 'apy': round(total / len(rows)),
                    'signing_bonus': _money(sb.group(1)), 'fifth_year_option': None}
    rounds = {}
    for td in soup.select('td[data-round]'):
        ov = td.select_one('span.overall')
        if ov:
            rounds[int(ov.get_text())] = int(td['data-round'])
    if sorted(picks) != list(range(1, 258)) or not all(p['years'] == 4 for p in picks.values()):
        return None
    vals = [picks[i]['total_value'] for i in range(1, 258)]
    if any(b > a for a, b in zip(vals, vals[1:])):
        return None
    for n, p in picks.items():
        p['fifth_year_option'] = rounds.get(n) == 1
    return picks
