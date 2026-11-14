"""Cloud-friendly NBA stats/roster fetcher (ESPN). Replaces fetch_stats.py
(stats.nba.com blocks GitHub runners and, as of 2026-10, local runs too).

Writes nba/data/nba_stats.json in the same shape fetch_stats.py did
({"<player_id>": {player_id, name, team, ppg, rpg, apg, mpg, games_played,
games_started, position, jersey_number, height, weight, rotation_status}})
plus appended fields: nba_api_id, ts_pct, usg_pct, reb_rate, ast_ratio,
tov_ratio, per, vorp, stats_season, injury_status, injury_detail and a nested
prev_season block. Also writes nba/data/stats_meta.json.

Sources (all verified from a GitHub runner, 2026-10-31):
  rosters   site.api.espn.com/.../nba/teams/{id}/roster       (the universe)
  box       site.web.api.espn.com/.../statistics/byathlete    (season=END year)
  advanced  sports.core.api.espn.com/.../seasons/{end}/types/2/athletes/{id}/statistics

player_id is now the ESPN athlete id. nba_api_id is the old stats.nba.com id,
recovered by a name+team crosswalk against the previously committed file (and
carried forward on later runs, when the previous file is already ESPN-keyed).

Guards -- any failure keeps the old nba_stats.json and exits 0: < 450 roster
players or < 30 teams, current-season byathlete failing/empty, > 10% of
advanced calls failing. Page sizes are never assumed: each page advances by
what it returned.

Run from the repo root: python nba/scripts/fetch_espn_stats.py
"""
import json
import os
import sys
import time
from datetime import date

import requests

from name_utils import NBA_NAME_ALIASES, normalize_for_matching

OUT_PATH = os.path.join('nba', 'data', 'nba_stats.json')
META_PATH = os.path.join('nba', 'data', 'stats_meta.json')

HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'),
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
}
ESPN_SITE = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba'
ESPN_BYATHLETE = ('https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/'
                  'statistics/byathlete?region=us&lang=en&contentorigin=espn&isqualified=false'
                  '&limit=500&sort=offensive.avgPoints%3Adesc&seasontype=2')
ESPN_CORE = 'https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba'

# ESPN's team abbreviations that differ from ours (nba_api's). Covers all 30.
ESPN_TEAM_MAP = {
    'ATL': 'ATL', 'BOS': 'BOS', 'BKN': 'BKN', 'CHA': 'CHA', 'CHI': 'CHI',
    'CLE': 'CLE', 'DAL': 'DAL', 'DEN': 'DEN', 'DET': 'DET', 'GS': 'GSW',
    'HOU': 'HOU', 'IND': 'IND', 'LAC': 'LAC', 'LAL': 'LAL', 'MEM': 'MEM',
    'MIA': 'MIA', 'MIL': 'MIL', 'MIN': 'MIN', 'NO': 'NOP', 'NY': 'NYK',
    'OKC': 'OKC', 'ORL': 'ORL', 'PHI': 'PHI', 'PHX': 'PHX', 'POR': 'POR',
    'SAC': 'SAC', 'SA': 'SAS', 'TOR': 'TOR', 'UTAH': 'UTA', 'WSH': 'WAS',
}

# Same thresholds as fetch_stats.py (a starting guess, unchanged).
STARTER_MPG = 24
ROTATION_MPG = 15

MIN_ROSTER_PLAYERS = 450
MIN_TEAMS = 30
MAX_ADV_FAIL_FRAC = 0.10

ADV_FIELDS = ('ts_pct', 'usg_pct', 'reb_rate', 'ast_ratio', 'tov_ratio', 'per', 'vorp')
ZERO_MEANS_MISSING = {'usg_pct', 'reb_rate'}
# ESPN core stat name -> our field
ADV_MAP = {'trueShootingPct': 'ts_pct', 'usageRate': 'usg_pct', 'reboundRate': 'reb_rate',
           'assistRatio': 'ast_ratio', 'turnoverRatio': 'tov_ratio', 'PER': 'per', 'VORP': 'vorp'}


class FetchFailed(Exception):
    pass


session = requests.Session()
session.headers.update(HEADERS)


def get_json(url, retries=3, allow_404=False):
    last = None
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, timeout=40)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404 and allow_404:
                return None
            last = f'HTTP {r.status_code}'
        except Exception as e:  # network/JSON error -- retry
            last = f'{type(e).__name__}: {str(e)[:100]}'
        if attempt < retries:
            time.sleep(1.5 * attempt)
    raise FetchFailed(f'{last} for {url[:120]}')


def season_end_year():
    """ESPN names a season by its END year (2026-27 -> 2027)."""
    today = date.today()
    return today.year + 1 if today.month >= 10 else today.year


def season_label(end_year):
    return f'{end_year - 1}-{str(end_year)[-2:]}'


def num1(v):
    if v is None:
        return None
    return round(float(v), 1)


def fmt_height(inches):
    if not inches:
        return None
    inches = int(round(float(inches)))
    return f'{inches // 12}-{inches % 12}'


def fetch_rosters():
    teams_json = get_json(f'{ESPN_SITE}/teams')
    teams = teams_json['sports'][0]['leagues'][0]['teams']
    roster = {}
    team_codes = set()
    for t in teams:
        t = t['team']
        abbr = ESPN_TEAM_MAP.get(t['abbreviation'])
        if abbr is None:
            raise FetchFailed(f"unmapped ESPN team abbreviation {t['abbreviation']!r}")
        j = get_json(f"{ESPN_SITE}/teams/{t['id']}/roster")
        team_codes.add(abbr)
        for a in j.get('athletes', []):
            inj = (a.get('injuries') or [None])[0]
            roster[str(a['id'])] = {
                'name': a.get('displayName') or a.get('fullName'),
                'team': abbr,
                'jersey_number': a.get('jersey') or None,
                'position': (a.get('position') or {}).get('abbreviation'),
                'height': fmt_height(a.get('height')),
                'weight': int(a['weight']) if a.get('weight') else None,
                'injury_status': inj.get('status') if inj else None,
                'injury_detail': (inj.get('details') or {}).get('type') if inj and isinstance(inj.get('details'), dict)
                                 else (inj.get('shortComment') if inj else None),
            }
        time.sleep(0.1)
    print(f'rosters: {len(roster)} players on {len(team_codes)} teams')
    return roster, team_codes


def fetch_byathlete(end_year):
    """{espn_id: box dict}. Pages advance by what each one returned."""
    rows, page = {}, 1
    while True:
        j = get_json(f'{ESPN_BYATHLETE}&season={end_year}&page={page}')
        athletes = j.get('athletes') or []
        if not athletes:
            break
        # stat names live once at the top level; each athlete row carries
        # only values, in the same per-category order
        names_by_cat = {c['name']: c.get('names', []) for c in j.get('categories', [])}
        for r in athletes:
            vals = {}
            for cat in r.get('categories', []):
                for name, v in zip(names_by_cat.get(cat.get('name'), []), cat.get('values', [])):
                    vals.setdefault(name, v)
            rows[str(r['athlete']['id'])] = {
                'ppg': num1(vals.get('avgPoints')),
                'rpg': num1(vals.get('avgRebounds')),
                'apg': num1(vals.get('avgAssists')),
                'mpg': num1(vals.get('avgMinutes')),
                'spg': num1(vals.get('avgSteals')),
                'bpg': num1(vals.get('avgBlocks')),
                'fg_pct': num1(vals.get('fieldGoalPct')),
                'three_pct': num1(vals.get('threePointFieldGoalPct')),
                'ft_pct': num1(vals.get('freeThrowPct')),
                'tov': num1(vals.get('avgTurnovers')),
                'games_played': int(vals['gamesPlayed']) if vals.get('gamesPlayed') is not None else None,
            }
        pages = (j.get('pagination') or {}).get('pages') or page
        if page >= pages:
            break
        page += 1
    print(f'byathlete {end_year}: {len(rows)} players ({page} page(s))')
    return rows


def fetch_advanced(end_year, espn_id):
    """(fields dict, ok). 404 'No stats found' is a legitimate empty, not a failure."""
    j = get_json(f'{ESPN_CORE}/seasons/{end_year}/types/2/athletes/{espn_id}/statistics', allow_404=True)
    out = {f: None for f in ADV_FIELDS}
    out['games_started'] = None
    if j is None:
        return out
    for cat in j.get('splits', {}).get('categories', []):
        for s in cat.get('stats', []):
            n, v = s.get('name'), s.get('value')
            if n in ADV_MAP and v is not None:
                # ESPN serves a flat 0.0 for these two on every player (verified
                # 2026-10-31: 873/873 zeros) -- a placeholder, not data.
                if ADV_MAP[n] in ZERO_MEANS_MISSING and float(v) == 0:
                    continue
                out[ADV_MAP[n]] = round(float(v), 3)
            elif n == 'gamesStarted' and v is not None:
                out['games_started'] = int(v)
    return out


def fetch_advanced_many(end_year, ids):
    """{id: fields}; a failed individual call -> None for that player. Raises
    FetchFailed if more than MAX_ADV_FAIL_FRAC of the calls fail."""
    result, failed = {}, 0
    for i, pid in enumerate(ids, 1):
        try:
            result[pid] = fetch_advanced(end_year, pid)
        except FetchFailed as e:
            failed += 1
            result[pid] = None
            print(f'  advanced call failed for {pid}: {e}')
        time.sleep(0.03)
        if i % 100 == 0:
            print(f'  advanced {end_year}: {i}/{len(ids)}')
    if ids and failed / len(ids) > MAX_ADV_FAIL_FRAC:
        raise FetchFailed(f'{failed}/{len(ids)} advanced calls failed for {end_year} (> {MAX_ADV_FAIL_FRAC:.0%})')
    print(f'advanced {end_year}: {len(ids) - failed}/{len(ids)} ok')
    return result


def derive_rotation_status(mpg):
    if mpg is None:
        return 'bench'
    if mpg >= STARTER_MPG:
        return 'starter'
    if mpg >= ROTATION_MPG:
        return 'rotation'
    return 'bench'


def build_nba_api_crosswalk(old, roster):
    """{espn_id: nba_api_id or None}. Must read `old` BEFORE it is overwritten.
    Old file already ESPN-keyed -> carry its nba_api_id forward by id. Otherwise
    (first run) its player_id IS the nba_api id: match by normalized name+team
    (via NBA_NAME_ALIASES either direction), then by name alone if unique."""
    carried = {}
    by_name_team, by_name = {}, {}
    for key, p in old.items():
        if 'nba_api_id' in p:
            if p['nba_api_id'] is not None:
                carried[str(p['player_id'])] = p['nba_api_id']
            continue
        k = normalize_for_matching(p.get('name'))
        by_name_team.setdefault((k, p.get('team')), []).append(p['player_id'])
        by_name.setdefault(k, []).append(p['player_id'])

    inverse = {v: k for k, v in NBA_NAME_ALIASES.items()}
    out = {}
    for eid, r in roster.items():
        if eid in carried:
            out[eid] = carried[eid]
            continue
        names = {r['name'], NBA_NAME_ALIASES.get(r['name']), inverse.get(r['name'])} - {None}
        keys = {normalize_for_matching(n) for n in names}
        ids = {i for k in keys for i in by_name_team.get((k, r['team']), [])}
        if len(ids) != 1:
            ids = {i for k in keys for i in by_name.get(k, [])}
        out[eid] = next(iter(ids)) if len(ids) == 1 else None
    return out


def box_block(box, adv):
    """Shared by current-season entries and prev_season."""
    block = dict(box)
    block['games_started'] = adv.get('games_started') if adv else None
    for f in ADV_FIELDS:
        block[f] = adv.get(f) if adv else None
    return block


def main():
    try:
        old = {}
        if os.path.exists(OUT_PATH):
            with open(OUT_PATH, encoding='utf-8') as f:
                old = json.load(f)

        end_year = season_end_year()
        roster, team_codes = fetch_rosters()
        if len(roster) < MIN_ROSTER_PLAYERS or len(team_codes) < MIN_TEAMS:
            raise FetchFailed(f'roster too small: {len(roster)} players, {len(team_codes)} teams')

        cur_box = fetch_byathlete(end_year)
        if not cur_box:
            raise FetchFailed(f'byathlete returned 0 rows for {end_year}')
        # Prior season is a fallback while samples are tiny; its failure is not fatal.
        try:
            prev_box = fetch_byathlete(end_year - 1)
        except FetchFailed as e:
            print(f'prev-season byathlete failed ({e}); prev_season will be null')
            prev_box = {}

        cur_ids = [i for i in cur_box if i in roster]
        prev_ids = [i for i in prev_box if i in roster]
        cur_adv = fetch_advanced_many(end_year, cur_ids)
        prev_adv = fetch_advanced_many(end_year - 1, prev_ids) if prev_ids else {}
    except FetchFailed as e:
        print(f'GUARD: {e}\nKeeping the existing {OUT_PATH}.')
        return 0

    crosswalk = build_nba_api_crosswalk(old, roster)
    label = season_label(end_year)
    output = {}
    for eid, bio in roster.items():
        box = cur_box.get(eid)
        adv = cur_adv.get(eid)
        entry = {
            'player_id': int(eid),
            'name': bio['name'],
            'team': bio['team'],
            'ppg': box['ppg'] if box else None,
            'rpg': box['rpg'] if box else None,
            'apg': box['apg'] if box else None,
            'mpg': box['mpg'] if box else None,
            **{k: (box[k] if box else None)
               for k in ('spg', 'bpg', 'fg_pct', 'three_pct', 'ft_pct', 'tov')},
            'games_played': box['games_played'] if box else 0,
            'games_started': adv['games_started'] if adv else None,
            'position': bio['position'],
            'jersey_number': bio['jersey_number'],
            'height': bio['height'],
            'weight': bio['weight'],
        }
        entry['rotation_status'] = derive_rotation_status(entry['mpg'])
        entry['nba_api_id'] = crosswalk.get(eid)
        for f in ADV_FIELDS:
            entry[f] = adv.get(f) if adv else None
        entry['stats_season'] = label
        entry['injury_status'] = bio['injury_status']
        entry['injury_detail'] = bio['injury_detail']
        pbox = prev_box.get(eid)
        if pbox and pbox['games_played']:
            entry['prev_season'] = dict(season=season_label(end_year - 1),
                                        **box_block(pbox, prev_adv.get(eid)))
        else:
            entry['prev_season'] = None
        output[eid] = entry

    # Diff-based "stats as of": carry the date forward if nothing changed.
    today = date.today().isoformat()
    changed = output != {k: v for k, v in old.items()}
    last_changed = today
    if not changed and os.path.exists(META_PATH):
        with open(META_PATH, encoding='utf-8') as f:
            last_changed = json.load(f).get('stats_last_changed', today)
    meta = {'stats_last_changed': last_changed, 'stats_season': label, 'source_total': len(cur_box)}

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    with open(META_PATH, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)

    n = len(output)
    print(f'\nWrote {n} players to {OUT_PATH} (content {"changed" if changed else "identical"}; '
          f'stats_last_changed {last_changed})')
    print(f"with stats: {sum(1 for p in output.values() if p['mpg'] is not None)}; "
          f"games_started: {sum(1 for p in output.values() if p['games_started'] is not None)}; "
          f"nba_api_id: {sum(1 for p in output.values() if p['nba_api_id'] is not None)}; "
          f"prev_season: {sum(1 for p in output.values() if p['prev_season'])}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
