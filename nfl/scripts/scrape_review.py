"""
ReView (NFL): weekly "what happened" data from ESPN's public site API.

Writes nfl/data/review/week_<season>_<N>.json (one per completed regular-season
week) and nfl/data/review/index.json. Only weeks where EVERY game is final are
written; the latest 2 stored weeks are re-fetched each run (stat corrections),
older weeks are never touched. Any failure keeps the old files (exit 0).

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

_last = [0.0]


def get_json(path):
    wait = GAP - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    r = requests.get(BASE + path, headers=HEADERS, timeout=30)
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


class Mapper:
    """ESPN athlete id -> our player_id (gsis via nflreadpy espn_id, else name+team)."""

    def __init__(self, season):
        self.by_gsis, self.by_name = {}, {}
        master = load_json(MASTER) or {}
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


def week_complete(events):
    return bool(events) and all(e['competitions'][0]['status']['type']['completed'] for e in events)


def tally(records, g):
    for s, o in (('home', 'away'), ('away', 'home')):
        r = records.setdefault(g[s]['team'], [0, 0, 0])
        a, b = g[s]['score'], g[o]['score']
        r[0 if a > b else 1 if a < b else 2] += 1
        g[s]['record'] = f'{r[0]}-{r[1]}-{r[2]}' if r[2] else f'{r[0]}-{r[1]}'


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    try:
        season = get_json('scoreboard')['season']['year']
        mapper = Mapper(season)
        idx = load_json(os.path.join(OUT_DIR, 'index.json')) or {}
        old_idx = idx if idx.get('season') == season else {}
        have = sorted(old_idx.get('weeks') or [])
        written = {}
        for w in have:
            d = load_json(os.path.join(OUT_DIR, f'week_{season}_{w}.json'))
            if d:
                written[w] = d
        redo = set(sorted(written)[-REFETCH_LATEST:])
        changed = False
        records = {}
        for w in range(1, MAX_WEEK + 1):
            old = written.get(w)
            if old and w not in redo:
                for g in old['games']:
                    tally(records, g)  # re-derives the same record strings
                continue
            events = get_json(f'scoreboard?seasontype=2&week={w}').get('events') or []
            if not week_complete(events):
                print(f'week {w}: not complete ({len(events)} games), stopping')
                break
            games = [parse_game(ev, get_json(f'summary?event={ev["id"]}'), mapper) for ev in events]
            if old:  # ESPN expires clips: keep ones already stored
                prev = {g['id']: g for g in old['games']}
                for g in games:
                    urls = {h['url'] for h in g['highlights']}
                    g['highlights'] += [h for h in (prev.get(g['id']) or {}).get('highlights', [])
                                        if h['url'] not in urls]
            games.sort(key=lambda g: g['date'])
            for g in games:
                tally(records, g)
            wk = {'season': season, 'week': w, 'games': games}
            if old and {k: v for k, v in old.items() if k != 'fetched_at'} == wk:
                print(f'week {w}: unchanged')
                continue
            wk['fetched_at'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            write_json(os.path.join(OUT_DIR, f'week_{season}_{w}.json'), wk)
            written[w] = wk
            changed = True
            n_l = sum(len(g['leaders']) for g in games)
            n_m = sum(1 for g in games for l in g['leaders'] if l['player_id'])
            print(f'week {w}: wrote {len(games)} games, leaders mapped {n_m}/{n_l}, '
                  f'highlights {sum(len(g["highlights"]) for g in games)}')
        weeks = sorted(written)
        if not weeks:
            print('GUARD: no completed weeks; nothing written')
            return
        new_idx = {'season': season, 'weeks': weeks, 'latest_week': weeks[-1]}
        new_idx['last_changed'] = (datetime.now(timezone.utc).strftime('%Y-%m-%d')
                                   if changed or not old_idx.get('last_changed') else old_idx['last_changed'])
        if any(new_idx[k] != old_idx.get(k) for k in new_idx):
            write_json(os.path.join(OUT_DIR, 'index.json'), new_idx)
        print(f'index: season {season}, weeks {weeks[0]}-{weeks[-1]}, last_changed {new_idx["last_changed"]}')
    except Exception as ex:
        print(f'GUARD: {type(ex).__name__}: {ex}; keeping existing review files')


if __name__ == '__main__':
    main()
    sys.exit(0)
