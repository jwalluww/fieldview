"""
ReView (NFL): weekly "what happened" data + season-to-date data from ESPN's public site API.

Writes into nfl/data/review/:
  week_<season>_<N>.json  one per regular-season week with at least one final game. A week
                          with games still to play carries partial: true, games_remaining and
                          pending[] (matchups only); it becomes a normal week once every game is final.
  index.json              {season, weeks[], latest_week (last complete), current_week (last with
                          any final), partial_weeks{week: games_remaining}, last_changed}
  season_<season>.json    standings (32 teams), playoff picture and stat leaders.
The latest 2 complete weeks and any partial week are re-fetched each run (stat corrections);
older weeks are never touched. Any failure keeps the old files (exit 0): weeks, standings and
leaders fail independently of each other.

Highlights are ESPN links + thumbnail URLs only (never downloaded/rehosted).
ESPN keeps clips only ~2 days, so a refetch MERGES highlights with those
already stored. Records are computed here from final scores (W-L[-T] through
that week) because the scoreboard's record is "as of now", not as of the week.
"""
import json, os, re, sys, time, unicodedata
from datetime import datetime, timezone

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(ROOT, 'nfl', 'data', 'review')
MASTER = os.path.join(ROOT, 'nfl', 'data', 'players_master.json')
BASE = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/'
STANDINGS_URL = ('https://site.api.espn.com/apis/v2/sports/football/nfl/standings'
                 '?level=3&season={season}&seasontype=2')
# site v3 (not sports.core): one request carries athlete names, positions and teams
LEADERS_URL = ('https://site.api.espn.com/apis/site/v3/sports/football/nfl/leaders'
               '?season={season}&seasontype=2')
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.espn.com/',
}
GAP = 1.0
REFETCH_LATEST = 2
MAX_WEEK = 18
# ESPN abbreviation -> ours (everything else is identical)
TEAM_MAP = {'ARI': 'ARZ', 'WSH': 'WAS'}
STAT_KEYS = ['totalYards', 'netPassingYards', 'rushingYards', 'turnovers', 'thirdDownEff', 'possessionTime']
LEADER_CATS = [('passingYards', 'pass'), ('rushingYards', 'rush'), ('receivingYards', 'rec'),
               ('sacks', 'sacks'), ('totalTackles', 'tackles')]
SEASON_CATS = ['passingYards', 'passingTouchdowns', 'rushingYards', 'rushingTouchdowns', 'receivingYards',
               'receptions', 'receivingTouchdowns', 'sacks', 'totalTackles', 'interceptions']
TOP_N = 10
PLAYOFF_SEEDS = 7
HUNT = 4  # teams listed just outside the playoff seeds

_last = [0.0]


def get_json(path):
    wait = GAP - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    url = path if path.startswith('https://') else BASE + path
    r = requests.get(url, headers=HEADERS, timeout=30)
    _last[0] = time.time()
    r.raise_for_status()
    return r.json()


def code(abbr):
    return TEAM_MAP.get(abbr, abbr)


def norm(name):
    s = unicodedata.normalize('NFKD', name or '').encode('ascii', 'ignore').decode().lower()
    s = re.sub(r"[.'`-]", '', s)
    s = re.sub(r'\b(jr|sr|ii|iii|iv|v)\b', '', s)
    return ' '.join(re.sub(r'[^a-z ]', '', s).split())


def load_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def write_json(path, obj):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write('\n')
    os.replace(tmp, path)


def utc_now(fmt='%Y-%m-%dT%H:%M:%SZ'):
    return datetime.now(timezone.utc).strftime(fmt)


def without_stamp(d):
    return {k: v for k, v in d.items() if k != 'fetched_at'}


class Mapper:
    """ESPN athlete id -> our player_id (gsis via nflreadpy espn_id, else name+team)."""

    def __init__(self, season):
        self.by_gsis, self.by_name = {}, {}
        master = load_json(MASTER) or {}
        self.teams = {p.get('team') for p in master.values()} - {None}
        for pid, p in master.items():
            if p.get('gsis_id'):
                self.by_gsis[p['gsis_id']] = pid
            for nm in (p.get('canonical_name'), p.get('ourlads_name'), p.get('nflreadpy_name')):
                if nm:
                    self.by_name.setdefault((norm(nm), p.get('team')), set()).add(pid)
        self.espn_to_gsis = {}
        try:
            import nflreadpy as n
            for df in (n.load_players().to_pandas(), n.load_rosters(season).to_pandas()):
                for e, g in zip(df['espn_id'], df['gsis_id']):
                    if e == e and g == g and e and g:
                        self.espn_to_gsis[str(int(float(e)))] = g
        except Exception as ex:
            print(f'  WARN: nflreadpy id crosswalk unavailable ({ex}); name+team only')

    def match(self, espn_id, name, team):
        g = self.espn_to_gsis.get(str(espn_id))
        if g and g in self.by_gsis:
            return self.by_gsis[g], g
        ids = self.by_name.get((norm(name), team))
        if ids and len(ids) == 1:
            return next(iter(ids)), g
        return None, g


# ---------------------------------------------------------------- weeks

def parse_game(ev, summary, mapper):
    comp = ev['competitions'][0]
    teams = {c['homeAway']: c for c in comp['competitors']}
    out = {'id': ev['id'], 'date': ev['date'], 'status': comp['status']['type']['detail'],
           'venue': (comp.get('venue') or {}).get('fullName')}
    for side in ('home', 'away'):
        c = teams[side]
        out[side] = {'team': code(c['team']['abbreviation']), 'name': c['team'].get('displayName'),
                     'score': int(c['score']), 'winner': bool(c.get('winner')),
                     'linescore': [int(float(l['value'])) for l in c.get('linescores', [])]}
    ts = {}
    for t in summary['boxscore']['teams']:
        side = 'home' if code(t['team']['abbreviation']) == out['home']['team'] else 'away'
        stats = {}
        for s in t['statistics']:
            if s['name'] in STAT_KEYS and s['name'] not in stats:
                stats[s['name']] = s['displayValue']
        ts[side] = stats
    out['team_stats'] = ts
    leaders = []
    for t in summary.get('leaders', []):
        tc = code(t['team']['abbreviation'])
        cats = {c['name']: c for c in t.get('leaders', [])}
        for key, short in LEADER_CATS:
            c = cats.get(key)
            if not c or not c.get('leaders'):
                continue
            l = c['leaders'][0]
            a = l['athlete']
            name = a.get('displayName') or a.get('fullName')
            pid, gsis = mapper.match(a['id'], name, tc)
            leaders.append({'cat': short, 'team': tc, 'name': name, 'espn_id': str(a['id']),
                            'gsis_id': gsis, 'player_id': pid,
                            'pos': (a.get('position') or {}).get('abbreviation'),
                            'line': l.get('displayValue')})
    out['leaders'] = leaders
    out['scoring_plays'] = [
        {'quarter': (p.get('period') or {}).get('number'), 'clock': (p.get('clock') or {}).get('displayValue'),
         'team': code(p['team']['abbreviation']), 'type': (p.get('type') or {}).get('abbreviation'),
         'text': p.get('text'), 'away': p.get('awayScore'), 'home': p.get('homeScore')}
        for p in summary.get('scoringPlays', [])]
    hl, seen = [], set()
    for v in list(summary.get('videos') or []) + list(comp.get('highlights') or []):
        web = ((v.get('links') or {}).get('web') or {}).get('href')
        title = v.get('headline') or v.get('title')
        if not web or not title or web in seen:
            continue
        seen.add(web)
        hl.append({'title': title, 'thumbnail': v.get('thumbnail'), 'url': web, 'duration': v.get('duration')})
    out['highlights'] = hl
    return out


def is_final(ev):
    return bool(ev['competitions'][0]['status']['type']['completed'])


def pending_game(ev):
    """A not-yet-final game of a partial week: matchup only (a stored live score would be stale)."""
    comp = ev['competitions'][0]
    teams = {c['homeAway']: c for c in comp['competitors']}
    out = {'id': ev['id'], 'date': ev['date'], 'state': comp['status']['type'].get('state')}
    for side in ('home', 'away'):
        out[side] = {'team': code(teams[side]['team']['abbreviation'])}
    return out


def tally(records, g):
    for s, o in (('home', 'away'), ('away', 'home')):
        r = records.setdefault(g[s]['team'], [0, 0, 0])
        a, b = g[s]['score'], g[o]['score']
        r[0 if a > b else 1 if a < b else 2] += 1
        g[s]['record'] = f'{r[0]}-{r[1]}-{r[2]}' if r[2] else f'{r[0]}-{r[1]}'


def update_weeks(season, mapper):
    idx = load_json(os.path.join(OUT_DIR, 'index.json')) or {}
    old_idx = idx if idx.get('season') == season else {}
    written = {}
    for w in sorted(old_idx.get('weeks') or []):
        d = load_json(os.path.join(OUT_DIR, f'week_{season}_{w}.json'))
        if d:
            written[w] = d
    complete = sorted(w for w, d in written.items() if not d.get('partial'))
    redo = set(complete[-REFETCH_LATEST:]) | {w for w, d in written.items() if d.get('partial')}
    changed = False
    records = {}
    for w in range(1, MAX_WEEK + 1):
        old = written.get(w)
        if old and w not in redo:
            for g in old['games']:
                tally(records, g)  # re-derives the same record strings
            continue
        events = get_json(f'scoreboard?seasontype=2&week={w}').get('events') or []
        finals = [e for e in events if is_final(e)]
        if old and len(finals) < len(old['games']):
            print(f'week {w}: GUARD: {len(finals)} final games but {len(old["games"])} stored; keeping the old file')
            for g in old['games']:
                tally(records, g)
            continue
        if not finals:
            print(f'week {w}: no final games yet ({len(events)} listed), stopping')
            break
        games = [parse_game(ev, get_json(f'summary?event={ev["id"]}'), mapper) for ev in finals]
        if old:  # ESPN expires and reorders clips: keep stored ones, in stored order, new ones last
            prev = {g['id']: g for g in old['games']}
            for g in games:
                fresh = {h['url']: h for h in g['highlights']}
                kept = [fresh.pop(h['url'], h) for h in (prev.get(g['id']) or {}).get('highlights', [])]
                g['highlights'] = kept + list(fresh.values())
        games.sort(key=lambda g: g['date'])
        for g in games:
            tally(records, g)
        wk = {'season': season, 'week': w, 'games': games}
        left = len(events) - len(finals)
        if left:
            wk['partial'] = True
            wk['games_remaining'] = left
            wk['pending'] = sorted((pending_game(e) for e in events if not is_final(e)), key=lambda g: g['date'])
        if old and without_stamp(old) == wk:
            print(f'week {w}: unchanged')
            continue
        wk['fetched_at'] = utc_now()
        write_json(os.path.join(OUT_DIR, f'week_{season}_{w}.json'), wk)
        written[w] = wk
        changed = True
        n_l = sum(len(g['leaders']) for g in games)
        n_m = sum(1 for g in games for l in g['leaders'] if l['player_id'])
        print(f'week {w}: wrote {len(games)} games' + (f' (partial, {left} remaining)' if left else '')
              + f', leaders mapped {n_m}/{n_l}, highlights {sum(len(g["highlights"]) for g in games)}')
    weeks = sorted(written)
    if not weeks:
        print('GUARD: no week with a final game; no week files written')
        return
    done = [w for w in weeks if not written[w].get('partial')]
    new_idx = {'season': season, 'weeks': weeks, 'latest_week': done[-1] if done else None,
               'current_week': weeks[-1],
               'partial_weeks': {str(w): written[w]['games_remaining'] for w in weeks if written[w].get('partial')}}
    new_idx['last_changed'] = (utc_now('%Y-%m-%d') if changed or not old_idx.get('last_changed')
                               else old_idx['last_changed'])
    if any(new_idx[k] != old_idx.get(k) for k in new_idx):
        write_json(os.path.join(OUT_DIR, 'index.json'), new_idx)
    print(f'index: season {season}, weeks {weeks[0]}-{weeks[-1]}, current {new_idx["current_week"]}, '
          f'latest complete {new_idx["latest_week"]}, last_changed {new_idx["last_changed"]}')


# ---------------------------------------------------------------- season

def parse_standings(data, season, known_teams):
    rows = []
    for conf in data['children']:
        for div in conf['children']:
            table = div['standings']
            if table.get('season') != season or table.get('seasonType') != 2:
                raise ValueError(f'standings are for season {table.get("season")} type {table.get("seasonType")}')
            for e in table['entries']:
                st = {x['name']: x for x in e['stats']}
                w, l, t = (int(st[k]['value']) for k in ('wins', 'losses', 'ties'))
                seed = (st.get('playoffSeed') or {}).get('value')
                rows.append({'team': code(e['team']['abbreviation']), 'name': e['team'].get('displayName'),
                             'conference': conf['abbreviation'], 'division': div['name'],
                             'wins': w, 'losses': l, 'ties': t,
                             'pct': round((w + t / 2) / (w + l + t), 4) if w + l + t else 0.0,
                             'points_for': int(st['pointsFor']['value']),
                             'points_against': int(st['pointsAgainst']['value']),
                             'streak': (st.get('streak') or {}).get('displayValue'),
                             'seed': int(seed) if seed else None})
    teams = {r['team'] for r in rows}
    divisions = [r['division'] for r in rows]
    if len(rows) != 32 or len(teams) != 32 or (known_teams and teams - known_teams):
        raise ValueError(f'expected 32 known teams, got {len(rows)} (unknown: {sorted(teams - known_teams)})')
    if len(set(divisions)) != 8 or any(divisions.count(d) != 4 for d in set(divisions)):
        raise ValueError('expected 8 divisions of 4')
    if sorted({r['conference'] for r in rows}) != ['AFC', 'NFC']:
        raise ValueError('expected AFC and NFC')
    if sum(r['wins'] for r in rows) != sum(r['losses'] for r in rows):
        raise ValueError('wins and losses do not balance')
    if not any(r['wins'] or r['ties'] for r in rows):
        raise ValueError('no games played yet')
    return rows


def seed_conferences(rows):
    """Playoff picture per conference. ESPN's playoffSeed is used when it is a clean 1-16 with four
    different divisions on top; otherwise seeds are computed (division leaders, then best records; ties
    by point differential, NOT the NFL tiebreakers) and marked 'computed' (the page says "projected").
    Also sets each row's final seed and div_rank."""
    picture = {}
    for conf in ('AFC', 'NFC'):
        cr = [r for r in rows if r['conference'] == conf]
        order = sorted(cr, key=lambda r: r['seed'] or 99)
        ok = ([r['seed'] for r in order] == list(range(1, len(cr) + 1))
              and len({r['division'] for r in order[:4]}) == 4)
        if not ok:
            ranked = sorted(cr, key=lambda r: (-r['pct'], -(r['points_for'] - r['points_against']), r['team']))
            tops, seen_div = [], set()
            for r in ranked:
                if r['division'] not in seen_div:
                    seen_div.add(r['division'])
                    tops.append(r)
            order = tops + [r for r in ranked if r not in tops]
            for i, r in enumerate(order):
                r['seed'] = i + 1
        ranks = {}
        for r in order:
            ranks[r['division']] = r['div_rank'] = ranks.get(r['division'], 0) + 1
        picture[conf] = {'seeded_by': 'espn' if ok else 'computed',
                         'seeds': [r['team'] for r in order[:PLAYOFF_SEEDS]],
                         'hunt': [r['team'] for r in order[PLAYOFF_SEEDS:PLAYOFF_SEEDS + HUNT]]}
    return picture


def parse_leaders(data, season, mapper):
    req = data['requestedSeason']
    if req.get('year') != season or (req.get('type') or {}).get('type') != 2:
        raise ValueError('leaders are not for this regular season')
    cats = {c['name']: c for c in data['leaders']['categories']}
    out = {}
    for key in SEASON_CATS:
        entries = (cats.get(key) or {}).get('leaders') or []
        rows = []
        for e in sorted(entries, key=lambda e: -e['value'])[:TOP_N]:
            a = e['athlete']
            name = a.get('displayName') or a.get('fullName')
            team = code((e.get('team') or {}).get('abbreviation'))
            pid, gsis = mapper.match(a['id'], name, team)
            # 'value', not displayValue: ESPN rounds half sacks away there (11.5 shows as "12")
            v = float(e['value'])
            v = int(v) if v.is_integer() else v
            rank = rows[-1]['rank'] if rows and rows[-1]['value'] == v else len(rows) + 1
            rows.append({'rank': rank, 'name': name, 'team': team,
                         'pos': (a.get('position') or {}).get('abbreviation'), 'value': v,
                         'espn_id': str(a['id']), 'gsis_id': gsis, 'player_id': pid})
        if rows:
            out[key] = rows
        else:
            print(f'  WARN: leaders category {key} is empty; keeping any old rows')
    if not out:
        raise ValueError('no leader categories')
    return out


def update_season(season, mapper):
    """Standings (+ playoff picture) and leaders each keep their old content when their fetch fails.
    The file is rewritten only when content changes."""
    path = os.path.join(OUT_DIR, f'season_{season}.json')
    old = load_json(path) or {}
    new = without_stamp(old)
    new['season'] = season
    today = utc_now('%Y-%m-%d')
    try:
        rows = parse_standings(get_json(STANDINGS_URL.format(season=season)), season, mapper.teams)
        picture = seed_conferences(rows)
        if rows != old.get('standings') or picture != old.get('playoff_picture'):
            new.update(standings=rows, playoff_picture=picture, standings_updated=today)
        print('standings: 32 teams, seeds ' + ', '.join(f'{c} {p["seeded_by"]}' for c, p in picture.items()))
    except Exception as ex:
        print(f'GUARD: standings: {type(ex).__name__}: {ex}; keeping the old standings')
    try:
        found = parse_leaders(get_json(LEADERS_URL.format(season=season)), season, mapper)
        merged = {**(old.get('leaders') or {}), **found}
        if merged != old.get('leaders'):
            new.update(leaders=merged, leaders_updated=today)
        n = sum(len(v) for v in found.values())
        m = sum(1 for v in found.values() for r in v if r['player_id'])
        print(f'leaders: {len(found)}/{len(SEASON_CATS)} categories, mapped {m}/{n}')
    except Exception as ex:
        print(f'GUARD: leaders: {type(ex).__name__}: {ex}; keeping the old leaders')
    if not (new.get('standings') or new.get('leaders')):
        return
    if new == without_stamp(old):
        print('season file: unchanged')
        return
    new['fetched_at'] = utc_now()
    write_json(path, new)
    print(f'season file: wrote {os.path.basename(path)}')


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    try:
        season = get_json('scoreboard')['season']['year']
        mapper = Mapper(season)
    except Exception as ex:
        print(f'GUARD: {type(ex).__name__}: {ex}; keeping existing review files')
        return
    for step in (update_weeks, update_season):
        try:
            step(season, mapper)
        except Exception as ex:
            print(f'GUARD: {step.__name__}: {type(ex).__name__}: {ex}; keeping existing files')


if __name__ == '__main__':
    main()
    sys.exit(0)
