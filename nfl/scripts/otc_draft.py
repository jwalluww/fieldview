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


def parse_order(soup, standings=None, log=None):
    """-> (list of {pick, round, team, original_team}, None) or (None, reason).
    standings = fetch_standings() result (None -> modal-owner method); log = list that collects notes."""
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
    modal_orig = _infer_modal(owner, rnd, start, rc, n)
    orig, notes, method = modal_orig, [], 'modal'
    groups = _standings_groups(standings)
    if groups:
        orig, notes = _infer_standings(owner, rnd, start, rc, n, groups)
        method = 'standings'
        for p in range(1, n + 1):
            if orig[p] != modal_orig[p]:
                notes.append(f'  differs from modal method: pick {p} owner {owner[p]} modal original {modal_orig[p]} standings original {orig[p]}')
    else:
        notes.append('  standings unavailable/incomplete: using the modal-owner method for original_team')
    out = [{'pick': p, 'round': rnd[p], 'team': owner[p], 'original_team': orig[p]} for p in range(1, n + 1)]
    if log is not None:
        log.append(f'  original_team method: {method}')
        log.extend(notes)
    return out, None


def _infer_modal(owner, rnd, start, rc, n):
    """Old heuristic: a slot whose modal owner across the 7 rounds is unambiguous is that team's own slot."""
    modal = []
    for i in range(32):
        c = Counter(owner[start[r] + i] for r in range(1, 8) if i < rc[r])
        mc = c.most_common(2)
        modal.append((mc[0][0], mc[0][1], mc[1][1] if len(mc) > 1 else 0))
    claims = Counter(t for t, n1, n2 in modal if n1 >= 4 and n1 - n2 >= 3)
    slot_own = {i: t for i, (t, n1, n2) in enumerate(modal) if n1 >= 4 and n1 - n2 >= 3 and claims[t] == 1}
    orig = {}
    for p in range(1, n + 1):
        r = rnd[p]
        i = p - start[r]
        orig[p] = slot_own.get(i, owner[p]) if i < 32 else owner[p]
    return orig


ESPN_STANDINGS = 'https://site.api.espn.com/apis/v2/sports/football/nfl/standings'
ESPN_TEAM_MAP = {'ARI': 'ARZ', 'WSH': 'WAS'}


def fetch_standings():
    """-> {our team code: (wins, losses, ties)} for all 32 teams, or None (plain requests, no key)."""
    try:
        r = requests.get(ESPN_STANDINGS, headers={'User-Agent': UA}, timeout=60)
        if r.status_code != 200:
            print(f'  ESPN standings: HTTP {r.status_code}')
            return None
        d = r.json()
    except (requests.RequestException, ValueError) as e:
        print(f'  ESPN standings: {type(e).__name__}')
        return None
    out = {}

    def walk(node):
        for c in node.get('children', []):
            walk(c)
        for e in node.get('standings', {}).get('entries', []):
            st = {x['name']: x.get('value') for x in e.get('stats', [])}
            ab = e['team']['abbreviation']
            ab = ESPN_TEAM_MAP.get(ab, ab)
            if st.get('wins') is not None and st.get('losses') is not None:
                out[ab] = (st['wins'], st['losses'], st.get('ties') or 0)
    walk(d)
    if len(out) != 32 or set(out) != OUR_TEAMS:
        print(f'  ESPN standings cover {len(out)} teams (need 32 known codes)')
        return None
    return out


def _standings_groups(standings):
    """-> list of groups (each a set of teams), worst win% first; None if standings are unusable."""
    if not standings or len(standings) != 32:
        return None
    pct = {}
    for t, (w, l, ti) in standings.items():
        g = w + l + ti
        pct[t] = (w + 0.5 * ti) / g if g else 0.5
    by = {}
    for t, v in pct.items():
        by.setdefault(round(v, 6), set()).add(t)
    return [by[k] for k in sorted(by)]


WOBBLE_SLOTS = 4   # a team with no pick in its own group's range, holding one this close, is just OTC's order wobbling


def _infer_standings(owner, rnd, start, rc, n, groups):
    orig = {p: owner[p] for p in range(1, n + 1)}
    notes, labelled = [], 0
    for r in range(1, 8):
        if rc[r] < 32:
            notes.append(f'  round {r}: only {rc[r]} picks (< 32 base slots), no labels')
            continue
        ranges, lo = [], 0
        for g in groups:
            ranges.append((g, [start[r] + i for i in range(lo, lo + len(g))]))
            lo += len(g)
        own_slots = {t: slots for g, slots in ranges for t in g}
        base = range(start[r], start[r] + 32)
        # OTC's order is its own projection, not exactly the standings: a team that owns nothing in its own range
        # but holds a pick within WOBBLE_SLOTS of it is treated as holding its own (displaced) pick, not a trade.
        wobble = {}
        for pk in base:
            t = owner[pk]
            sl = own_slots[t]
            if t in wobble or pk in sl or any(owner[x] == t for x in sl):
                continue
            if min(abs(pk - x) for x in sl) <= WOBBLE_SLOTS:
                wobble[t] = pk
        wob_picks = set(wobble.values())
        for g, slots in ranges:
            claimed, rest = set(), []
            for pk in slots:
                t = owner[pk]
                if pk in wob_picks:
                    continue
                if t in g and t not in claimed:
                    claimed.add(t)
                else:
                    rest.append(pk)
            missing = sorted(t for t in g if t not in claimed and t not in wobble)
            if len(rest) == 1 and len(missing) == 1:
                orig[rest[0]] = missing[0]
                labelled += 1
            elif rest:
                notes.append(f'  round {r} slots {slots[0]}-{slots[-1]} ({",".join(sorted(g))}): '
                             f'{len(rest)} outside pick(s) {[(x, owner[x]) for x in rest]}, missing {missing}: unlabeled')
        for t, pk in wobble.items():
            notes.append(f'  round {r}: {t} holds #{pk} outside its slot range (order wobble, own pick)')
    notes.append(f'  standings method labelled {labelled} picks')
    return orig, notes


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
