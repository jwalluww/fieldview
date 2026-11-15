"""nfl/scripts/scrape_draft_prospects.py

Weekly draft-prospect refresh for the FormationView draft installer. Independent
of the player pipeline: touches only
  nfl/data/draft_prospects.json  one record per 2027 prospect (below)
  nfl/data/draft_order.json      [{pick, round, team, original_team}]
  nfl/data/draft_meta.json       board_last_changed (diff-based), counts, fetched_at

Sources (all verified 3edef0a / draft-recon run from a GitHub runner):
  - MockDraftHero (fan site, static files; keep-old-snapshot on ANY failure):
      players.csv           the universe (~840 prospects, bio + measurables)
      board-mockdrafthero.csv  its consensus order (weighted blend of other boards)
      draft-order.csv + rounds.csv  pick, team (current owner), odds_team (original)
    Its mirrored boards (board-drafttek.csv, board-pfsn.csv) are deliberately
    NOT fetched or republished.
  - PFN: /nfl-draft-hq/api/prospect-grades?year=2027 -> rank, grade, positionRank,
    playerComp. A PFN failure alone is not fatal: pfn_* become null, MDH stays.
  - EA College Football 27 (drop-api slug ea-sports-college-football via
    shared/scripts/ea_ratings.fetch_all with dedupe=True): only the overall is
    kept per prospect (cfb27_ovr); the ~11k cards are never stored. A failure
    leaves cfb27_ovr null for everybody.

Guards (keep the old files, exit 0, log why): an MDH file non-200 or unparsable,
< 400 MDH prospects, draft order not 224-262 picks / < 32 teams / an unknown team
code. `--simulate-fail mdh|pfn|cfb` forces a failure of one source (verification only).
"""
import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared', 'scripts'))
from name_utils import normalize_madden  # noqa: E402
import ea_ratings                        # noqa: E402

DATA = os.path.join('nfl', 'data')
PROSPECTS_PATH = os.path.join(DATA, 'draft_prospects.json')
ORDER_PATH = os.path.join(DATA, 'draft_order.json')
META_PATH = os.path.join(DATA, 'draft_meta.json')

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36')
HEADERS = {'User-Agent': UA, 'Accept': 'application/json,text/csv,text/plain,*/*',
           'Accept-Language': 'en-US,en;q=0.9'}
MDH = 'https://mockdrafthero.com/data/2027/'
PFN_URL = 'https://www.profootballnetwork.com/nfl-draft-hq/api/prospect-grades'
PFN_REFERER = 'https://www.profootballnetwork.com/nfl-draft-hq/prospect-grades'

MIN_MDH_PROSPECTS = 400
MIN_PFN_PROSPECTS = 150
ORDER_MIN, ORDER_MAX = 224, 262
CFB_MIN_CARDS = 9000
CFB_MARKER = 'college-football-27'

# MockDraftHero draft-order uses ARI; OurLads (our site-wide code) is ARZ.
# Every other code already matches OurLads (JAX, LV, LAR, LAC, WAS ...).
TEAM_MAP = {'ARI': 'ARZ'}
OUR_TEAMS = {'ARZ', 'ATL', 'BAL', 'BUF', 'CAR', 'CHI', 'CIN', 'CLE', 'DAL', 'DEN', 'DET', 'GB', 'HOU', 'IND',
             'JAX', 'KC', 'LAC', 'LAR', 'LV', 'MIA', 'MIN', 'NE', 'NO', 'NYG', 'NYJ', 'PHI', 'PIT', 'SEA',
             'SF', 'TB', 'TEN', 'WAS'}

# Raw position label (MDH players.csv / MDH board / PFN) -> standard_pos.
# NB/CBN are nickel backs (mapped to CB); DE/OLB/DL5T are the ambiguous
# edge-vs-interior labels (DE and OLB -> EDGE, DL* -> DI, as in the rookie curve).
POS_MAP = {
    'QB': 'QB', 'RB': 'RB', 'HB': 'RB', 'FB': 'RB', 'WR': 'WR', 'TE': 'TE',
    'OT': 'OL', 'OG': 'OL', 'OC': 'OL', 'C': 'OL', 'G': 'OL', 'IOL': 'OL', 'OL': 'OL',
    'EDGE': 'EDGE', 'DE': 'EDGE', 'OLB': 'EDGE',
    'DT': 'DI', 'NT': 'DI', 'DL': 'DI', 'DL1T': 'DI', 'DL3T': 'DI', 'DL5T': 'DI',
    'LB': 'LB', 'ILB': 'LB', 'MLB': 'LB',
    'CB': 'CB', 'CBN': 'CB', 'NB': 'CB', 'NICK': 'CB',
    'S': 'S', 'SAF': 'S', 'FS': 'S', 'SS': 'S',
}
DROP_POS = {'K', 'P', 'LS'}
# EA CFB position label -> standard_pos (for the position-compat check only)
EA_POS = {'QB': 'QB', 'HB': 'RB', 'FB': 'RB', 'WR': 'WR', 'TE': 'TE', 'LT': 'OL', 'LG': 'OL', 'C': 'OL',
          'RG': 'OL', 'RT': 'OL', 'LEDG': 'EDGE', 'REDG': 'EDGE', 'DT': 'DI', 'SAM': 'LB', 'MIKE': 'LB',
          'WILL': 'LB', 'CB': 'CB', 'FS': 'S', 'SS': 'S', 'K': None, 'P': None}
COMPAT = {'EDGE': {'EDGE', 'LB', 'DI'}, 'DI': {'DI', 'EDGE'}, 'LB': {'LB', 'EDGE', 'S'}, 'S': {'S', 'CB', 'LB'},
          'CB': {'CB', 'S'}, 'RB': {'RB', 'WR'}, 'WR': {'WR', 'RB', 'TE'}, 'TE': {'TE', 'WR', 'OL'},
          'OL': {'OL', 'TE'}, 'QB': {'QB'}}
# MDH / PFN school label -> EA College Football label (others already agree)
SCHOOL_ALIAS = {'app state': 'appalachian state', 'california': 'cal', 'north carolina state': 'nc state',
                'uconn': 'connecticut', 'massachusetts': 'umass', 'south florida': 'usf',
                'florida atlantic': 'fau', 'miami fl': 'miami', 'miami (fl)': 'miami',
                'ole miss': 'ole miss', 'southern california': 'usc', 'louisiana state': 'lsu',
                'texas christian': 'tcu', 'brigham young': 'byu', 'central florida': 'ucf',
                'southern methodist': 'smu', 'texas-san antonio': 'utsa', 'ul monroe': 'ul monroe'}

session = requests.Session()
session.headers.update(HEADERS)


# ------------------------------------------------------------------ helpers
def log(*a):
    print(*a, flush=True)


def get(url, params=None, headers=None, what=''):
    """GET with 3 tries; returns the Response on 200, else None (and logs why)."""
    last = None
    for attempt in range(3):
        if attempt:
            time.sleep(2 ** attempt)
        try:
            r = session.get(url, params=params, headers=headers, timeout=60)
            if r.status_code == 200:
                return r
            last = f'HTTP {r.status_code}'
        except requests.RequestException as e:
            last = type(e).__name__
    log(f'  {what or url}: giving up ({last})')
    return None


def nname(name):
    return normalize_madden(name or '')


def nschool(s):
    s = (s or '').lower().strip()
    s = SCHOOL_ALIAS.get(s, s)
    return re.sub(r'[^a-z0-9]', '', s)


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', (s or '').lower().replace("'", '')).strip('-')


def to_float(x):
    try:
        return float(x) if x not in (None, '') else None
    except ValueError:
        return None


def parse_height(h):
    """MDH heights are F-II-T: '6040' = 6 ft, 04 in, 0 tenths -> (76.0, "6'4\"")."""
    if not h or not re.fullmatch(r'\d{4}', h.strip()):
        return None, None
    h = h.strip()
    inches = int(h[0]) * 12 + int(h[1:3]) + int(h[3]) / 10
    ft, rem = divmod(inches, 12)
    return round(inches, 1), f"{int(ft)}'{rem:g}\""


def csv_rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def load_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))


# ------------------------------------------------------------------ MockDraftHero
def fetch_mdh(simulate):
    if simulate == 'mdh':
        log('  [simulated] MockDraftHero fetch failure')
        return None
    out = {}
    for key, fname in (('players', 'players.csv'), ('board', 'board-mockdrafthero.csv'),
                       ('order', 'draft-order.csv'), ('rounds', 'rounds.csv')):
        r = get(MDH + fname, what='MDH ' + fname)
        if r is None:
            return None
        out[key] = csv_rows(r.content.decode('utf-8-sig'))
        time.sleep(0.5)
    return out


def build_order(order_rows, round_rows):
    """-> list of {pick, round, team, original_team}, or (None, reason)."""
    n = len(order_rows)
    if not ORDER_MIN <= n <= ORDER_MAX:
        return None, f'draft order has {n} rows (expected {ORDER_MIN}-{ORDER_MAX})'
    # rounds.csv: standard + compensatory picks per round -> cumulative round ends
    ends, tot = [], 0
    for r in round_rows:
        tot += int(r['standard_picks'] or 0) + int(r['compensatory_picks'] or 0)
        ends.append(tot)
    if not ends or ends[-1] != n:
        ends = [32 * (i + 1) for i in range(7)]; ends[-1] = n   # fall back: 32 a round, remainder in R7
    out, bad = [], set()
    for r in sorted(order_rows, key=lambda x: int(x['pick'])):
        pick = int(r['pick'])
        rnd = next(i + 1 for i, e in enumerate(ends) if pick <= e)
        team, orig = TEAM_MAP.get(r['team'], r['team']), TEAM_MAP.get(r['odds_team'], r['odds_team'])
        if team not in OUR_TEAMS or orig not in OUR_TEAMS:
            bad.add(r['team'] if team not in OUR_TEAMS else r['odds_team'])
        out.append({'pick': pick, 'round': rnd, 'team': team, 'original_team': orig})
    if bad:
        return None, f'unknown team code(s) {sorted(bad)}'
    if len({o['team'] for o in out}) < 32:
        return None, f'only {len({o["team"] for o in out})} teams own picks'
    if len({o['pick'] for o in out}) != n:
        return None, 'duplicate pick numbers'
    return out, None


# ------------------------------------------------------------------ PFN
def fetch_pfn(simulate):
    if simulate == 'pfn':
        log('  [simulated] PFN fetch failure')
        return None
    r = get(PFN_URL, params={'year': 2027}, headers={'Accept': 'application/json', 'Referer': PFN_REFERER}, what='PFN prospect-grades')
    if r is None:
        return None
    try:
        players = r.json()['players']
    except (ValueError, KeyError):
        log('  PFN: unparsable response')
        return None
    if len(players) < MIN_PFN_PROSPECTS:
        log(f'  PFN: only {len(players)} prospects (< {MIN_PFN_PROSPECTS}) -- ignoring PFN this run')
        return None
    return players


# ------------------------------------------------------------------ CFB 27
def fetch_cfb(simulate):
    if simulate == 'cfb':
        log('  [simulated] CFB fetch failure')
        return None

    def validate(items):
        hit = sum(1 for c in items if CFB_MARKER in (c.get('avatarUrl') or ''))
        return None if hit >= 0.95 * len(items) else f'only {hit}/{len(items)} avatars carry {CFB_MARKER}'
    return ea_ratings.fetch_all('ea-sports-college-football', min_total=CFB_MIN_CARDS, validate=validate, dedupe=True)


def attach_cfb(prospects, cards):
    by_exact, by_school = {}, {}
    for c in cards:
        nm = nname(f"{c.get('firstName', '')} {c.get('lastName', '')}")
        sk = nschool((c.get('team') or {}).get('label'))
        pos = EA_POS.get(((c.get('position') or {}).get('shortLabel')))
        rec = (nm, pos, c.get('overallRating'))
        by_exact.setdefault((nm, sk), []).append(rec)
        by_school.setdefault(sk, []).append(rec)
    schools_in_ea = set(by_school)
    tiers = {'exact': 0, 'token_set': 0, 'initial_lastname': 0}
    no_school = 0
    for p in prospects:
        p['cfb27_ovr'] = None
        sk, nm = nschool(p['school']), nname(p['name'])
        if sk not in schools_in_ea:
            no_school += 1
            continue
        compat = COMPAT.get(p['standard_pos'], {p['standard_pos']})
        cand = [c for c in by_exact.get((nm, sk), [])]
        tier = 'exact'
        if len(cand) > 1:
            cand = [c for c in cand if c[1] in compat] or cand
        if len(cand) != 1:
            cand, tier = [], None
            toks = set(nm.split())
            tcand = [c for c in by_school[sk] if set(c[0].split()) == toks]
            if len(tcand) == 1:
                cand, tier = tcand, 'token_set'
            else:
                parts = nm.split()
                if len(parts) >= 2:
                    fl = [c for c in by_school[sk] if c[0].split()[-1] == parts[-1] and c[0][:1] == parts[0][:1]
                          and len(c[0].split()) >= 2 and c[1] in compat]
                    if len(fl) == 1:
                        cand, tier = fl, 'initial_lastname'
        if len(cand) == 1 and cand[0][2] is not None:
            p['cfb27_ovr'] = int(cand[0][2]); tiers[tier] += 1
    matched = sum(1 for p in prospects if p['cfb27_ovr'] is not None)
    return {'matched': matched, 'tiers': tiers, 'school_not_in_ea': no_school,
            'cards': len(cards)}


# ------------------------------------------------------------------ main
def parse_college_stats(text):
    """MDH 'stats' string -> {season, school, gp, stats[[label, value]...], career[[label, value]...]} or None.
    Format: '2025: Ohio State | 13 GP | 87 Rec | ...; 2026: ...; Career: 38 GP | ...' (latest season block wins)."""
    if not text or not text.strip():
        return None
    def items(parts):
        out = []
        for part in parts:
            bits = part.strip().split(' ', 1)
            if len(bits) == 2 and bits[0]:
                out.append([bits[1].strip(), bits[0]])
        return out
    seasons, career = [], None
    for blk in text.split(';'):
        blk = blk.strip()
        if ':' not in blk:
            continue
        head, rest = blk.split(':', 1)
        head = head.strip()
        parts = [x for x in rest.split('|')]
        if head.lower() == 'career':
            career = items(parts)
        elif head.isdigit():
            seasons.append((head, parts[0].strip(), items(parts[1:])))
    if not seasons:
        return None
    season, school, rows = seasons[-1]
    gp = next((v for k, v in rows if k == 'GP'), None)
    return {'season': season, 'school': school, 'gp': gp,
            'stats': [r for r in rows if r[0] != 'GP'], 'career': career}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--simulate-fail', choices=['mdh', 'pfn', 'cfb'])
    ap.add_argument('--out-dir', default=DATA, help=argparse.SUPPRESS)
    args = ap.parse_args()
    global PROSPECTS_PATH, ORDER_PATH, META_PATH
    if args.out_dir != DATA:
        PROSPECTS_PATH, ORDER_PATH, META_PATH = (os.path.join(args.out_dir, n) for n in
                                                 ('draft_prospects.json', 'draft_order.json', 'draft_meta.json'))
    sim = args.simulate_fail
    now = datetime.now(timezone.utc)
    log('Draft prospects refresh')

    mdh = fetch_mdh(sim)
    if mdh is None:
        log('KEEPING old draft files: MockDraftHero fetch failed'); return 0
    players = mdh['players']
    if len(players) < MIN_MDH_PROSPECTS:
        log(f'KEEPING old draft files: only {len(players)} MDH prospects (< {MIN_MDH_PROSPECTS})'); return 0
    order, why = build_order(mdh['order'], mdh['rounds'])
    if order is None:
        log(f'KEEPING old draft files: {why}'); return 0
    log(f'  MDH: {len(players)} prospects, {len(mdh["board"])} board rows, {len(order)} picks')

    # ---- universe + position mapping
    prospects, ids, dropped, unmapped = [], set(), [], {}
    pos_counts = {}
    for r in players:
        raw = (r.get('position') or '').strip()
        name, school = (r.get('name') or '').strip(), (r.get('school') or '').strip()
        if not name:
            continue
        if raw in DROP_POS:
            dropped.append(f'{name} ({raw})'); continue
        sp = POS_MAP.get(raw)
        if sp is None:
            unmapped[raw] = unmapped.get(raw, 0) + 1; continue
        pos_counts.setdefault(raw, [sp, 0])[1] += 1
        pid = f'{slug(name)}-{slug(school)}'
        n = 2
        while pid in ids:
            pid = f'{slug(name)}-{slug(school)}-{n}'; n += 1
        ids.add(pid)
        hin, hdisp = parse_height(r.get('height'))
        prospects.append({
            'prospect_id': pid, 'name': name, 'school': school, 'standard_pos': sp,
            'raw_pos': {'mdh': raw, 'mdh_board': None, 'pfn': None},
            'consensus_rank': None, 'pfn_rank': None, 'pfn_grade': None,
            'pfn_position_rank': None, 'pfn_comp': None,
            'eligibility': (r.get('eligibility') or '').strip() or None,
            'dob': (r.get('dob') or '').strip() or None,
            'measurables': {
                'height_in': hin, 'height': hdisp, 'weight': to_float(r.get('weight')),
                'arm': to_float(r.get('arm_length')), 'hand': to_float(r.get('hand_size')),
                'wingspan': to_float(r.get('wingspan')), 'forty': to_float(r.get('forty_yard_dash')),
                'ten_split': to_float(r.get('ten_yard_split')), 'vert': to_float(r.get('vertical_jump')),
                'broad': to_float(r.get('broad_jump')), 'three_cone': to_float(r.get('three_cone')),
                'shuttle': to_float(r.get('shuttle')), 'bench': to_float(r.get('bench_press')),
                'ras': to_float(r.get('ras_score')),
            },
            'cfb27_ovr': None,
            'college_stats': parse_college_stats(r.get('stats')),
        })
    log('  position mapping (raw -> standard_pos: count):')
    for raw, (sp, n) in sorted(pos_counts.items(), key=lambda kv: -kv[1][1]):
        log(f'    {raw:5s} -> {sp:5s} {n}')
    log(f'  dropped (K/P/LS): {len(dropped)} {dropped}')
    if unmapped:
        log(f'  UNMAPPED labels (dropped): {unmapped}')

    # ---- MDH consensus board -> prospects (normalized name, position-compat if ambiguous)
    by_name = {}
    for p in prospects:
        by_name.setdefault(nname(p['name']), []).append(p)
    board_unmatched = []
    for i, b in enumerate(mdh['board'], 1):
        cands = by_name.get(nname(b['name']), [])
        rawb = (b.get('position') or '').strip()
        sp = POS_MAP.get(rawb)
        if len(cands) > 1 and sp:
            cands = [c for c in cands if c['standard_pos'] == sp] or cands
        if len(cands) == 1 and cands[0]['consensus_rank'] is None:
            cands[0]['consensus_rank'] = i
            cands[0]['raw_pos']['mdh_board'] = rawb
        else:
            board_unmatched.append(b['name'])
    n_cons = sum(1 for p in prospects if p['consensus_rank'] is not None)
    log(f'  consensus board: {n_cons}/{len(mdh["board"])} rows joined; unmatched {len(board_unmatched)} {board_unmatched[:10]}')

    # ---- PFN
    pfn = fetch_pfn(sim)
    pfn_stats = {'prospects': 0, 'matched': 0, 'unmatched': []}
    if pfn is not None:
        pfn_stats['prospects'] = len(pfn)
        tiers = {'name_school': 0, 'name_only_unique': 0}
        by_ns = {(nname(p['name']), nschool(p['school'])): p for p in prospects}
        for g in pfn:
            nm, sk = nname(g['name']), nschool(g.get('school'))
            sp = POS_MAP.get((g.get('position') or '').strip())
            p = by_ns.get((nm, sk))
            tier = 'name_school'
            if p is None:
                cands = [c for c in by_name.get(nm, [])]
                if len(cands) == 1 and (sp is None or sp in COMPAT.get(cands[0]['standard_pos'], {cands[0]['standard_pos']})):
                    p, tier = cands[0], 'name_only_unique'
            if p is None or p['pfn_rank'] is not None:
                pfn_stats['unmatched'].append(f"{g['name']} ({g.get('school')})")
                continue
            p['pfn_rank'] = g.get('rank')
            p['pfn_grade'] = g.get('grade')
            p['pfn_position_rank'] = g.get('positionRank')
            p['pfn_comp'] = g.get('playerComp')
            p['raw_pos']['pfn'] = g.get('position')
            tiers[tier] += 1
            pfn_stats['matched'] += 1
        pfn_stats['tiers'] = tiers
        log(f'  PFN: {pfn_stats["matched"]}/{len(pfn)} matched {tiers}; unmatched {len(pfn_stats["unmatched"])}: {pfn_stats["unmatched"][:15]}')
    else:
        log('  PFN unavailable: pfn_* left null')

    # ---- CFB 27
    cards = fetch_cfb(sim)
    cfb_stats = {'ok': cards is not None}
    if cards is not None:
        s = attach_cfb(prospects, cards)
        cfb_stats.update(s)
        elig = len(prospects) - s['school_not_in_ea']
        log(f'  CFB 27: {s["cards"]} cards; matched {s["matched"]}/{len(prospects)} prospects '
            f'({s["matched"] / len(prospects):.1%}; {s["matched"] / max(elig, 1):.1%} of the {elig} whose school has EA cards) {s["tiers"]}')
    else:
        log('  CFB unavailable: cfb27_ovr left null for everybody')

    # order prospects: consensus rank, then pfn rank, then name
    prospects.sort(key=lambda p: (p['consensus_rank'] is None, p['consensus_rank'] or 0,
                                  p['pfn_rank'] is None, p['pfn_rank'] or 0, p['name']))

    # ---- write (only now: every guard has passed)
    prev_meta = load_json(META_PATH) or {}
    digest = hashlib.sha256((dumps(prospects) + dumps(order)).encode('utf-8')).hexdigest()
    changed = prev_meta.get('content_hash') != digest
    meta = {
        'fetched_at': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'board_last_changed': now.strftime('%Y-%m-%d') if changed or not prev_meta.get('board_last_changed') else prev_meta['board_last_changed'],
        'content_hash': digest,
        'sources': {
            'mdh_players': len(players), 'mdh_board': len(mdh['board']), 'draft_order_picks': len(order),
            'pfn_prospects': pfn_stats['prospects'], 'pfn_matched': pfn_stats['matched'],
            'cfb27_cards': cfb_stats.get('cards', 0), 'cfb27_matched': cfb_stats.get('matched', 0),
        },
        'prospects': len(prospects), 'pfn_ok': pfn is not None, 'cfb_ok': cards is not None,
    }
    os.makedirs(os.path.dirname(PROSPECTS_PATH) or '.', exist_ok=True)
    for path, obj in ((PROSPECTS_PATH, prospects), (ORDER_PATH, order), (META_PATH, meta)):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(dumps(obj) if path != META_PATH else json.dumps(obj, indent=2))
    log(f'  wrote {len(prospects)} prospects, {len(order)} picks; board_last_changed={meta["board_last_changed"]} (changed={changed})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
