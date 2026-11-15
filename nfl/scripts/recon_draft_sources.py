"""One-shot reachability probe for the NFL draft-prospect installer sources.
Hits each candidate once (DraftTek: its 4 pages) and logs status, latency and
row counts. Research only: writes nothing, prints no secrets. Run from the
manual-only workflow .github/workflows/draft-recon.yml."""
import io
import csv
import os
import random
import re
import time

import requests

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36')
HTML = {'User-Agent': UA, 'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9'}
JSON_H = {'User-Agent': UA, 'Accept': 'application/json,text/plain,*/*'}


def probe(label, url, headers, counter, params=None):
    t = time.time()
    try:
        r = requests.get(url, headers=headers, params=params, timeout=45)
        dt = time.time() - t
        try:
            n = counter(r)
        except Exception as e:  # parsing problem, not a network one
            n = f'parse error: {type(e).__name__}'
        print(f'{label:34s} HTTP {r.status_code}  {dt:5.1f}s  {len(r.content):>9,} B  rows={n}')
    except Exception as e:
        print(f'{label:34s} FAILED {type(e).__name__}: {str(e)[:80]}')
    time.sleep(1.5)


def csv_rows(r):
    return len(list(csv.reader(io.StringIO(r.text)))) - 1


def main():
    print('--- PFN (Next.js app; JSON behind the Prospect Scores page)')
    for y in (2027, 2026):
        probe(f'PFN prospect-grades {y}',
              'https://www.profootballnetwork.com/nfl-draft-hq/api/prospect-grades',
              dict(JSON_H, Referer='https://www.profootballnetwork.com/nfl-draft-hq/prospect-grades'),
              lambda r: len(r.json()['players']), params={'year': y})
    probe('PFN industry consensus page',
          'https://www.profootballnetwork.com/nfl-draft-hq/industry-consensus-big-board/',
          HTML, lambda r: r.text.count('"@type":"ListItem"'))
    probe('PFN mock draft sim (inline board)',
          'https://www.profootballnetwork.com/mockdraft/', HTML,
          lambda r: len(re.findall(r'"draftFrom":', r.text)))

    print('--- StickToTheModel / DraftTek')
    probe('STM big board (server HTML)',
          'https://sticktothemodel.com/draft/prospect-overview/big-board', HTML,
          lambda r: len(re.findall(r'<tr data-', r.text)))
    for p in range(1, 5):
        probe(f'DraftTek page {p}',
              f'https://www.drafttek.com/2027-NFL-Draft-Big-Board/Top-NFL-Draft-Prospects-2027-Page-{p}.asp',
              HTML, lambda r: (r.text.count('Bio') - 1) // 2)  # 'Bio' appears twice per row + header

    print('--- MockDraftHero static data')
    base = 'https://mockdrafthero.com/data/2027/'
    probe('MDH boards.json', base + 'boards.json', JSON_H, lambda r: len(r.json()['boards']))
    for f in ('players.csv', 'board-mockdrafthero.csv', 'board-drafttek.csv',
              'board-pfsn.csv', 'draft-order.csv'):
        probe('MDH ' + f, base + f, JSON_H, csv_rows)

    print('--- ESPN')
    probe('ESPN 2027 draft athletes',
          'https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/2027/draft/athletes',
          JSON_H, lambda r: r.json()['count'], params={'limit': 1})
    probe('ESPN 2026 draft athletes',
          'https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/2026/draft/athletes',
          JSON_H, lambda r: r.json()['count'], params={'limit': 1})

    print('--- EA drop-api (one page each, limit=1; totals only)')
    def ea(slug, ref, **extra):
        h = dict(JSON_H)
        if ref:
            h['drop-referrer'] = f'https://www.ea.com/games/{slug}/ratings'
        return h, dict(locale='en', limit=1, cb=random.randint(10**8, 10**9), **extra)
    for label, slug, ref, extra in [
        ('EA CFB (referrer)', 'ea-sports-college-football', True, {}),
        ('EA CFB launch (referrer)', 'ea-sports-college-football', True, {'iteration': '1-base'}),
        ('EA CFB (NO referrer)', 'ea-sports-college-football', False, {}),
        ('EA Madden 27 launch (referrer)', 'madden-nfl', True, {'iteration': '1-base'}),
        ('EA Madden 26 launch (no referrer)', 'madden-nfl', False, {'iteration': '1-base'}),
    ]:
        h, p = ea(slug, ref, **extra)
        probe(label, f'https://drop-api.ea.com/rating/{slug}', h,
              lambda r: r.json().get('totalItems'), params=p)

    print('--- CFBD (only if the secret is set; value never printed)')
    key = os.environ.get('CFBD_API_KEY', '')
    if not key:
        print('CFBD_API_KEY not set: skipped')
    else:
        h = {'Authorization': f'Bearer {key}', 'Accept': 'application/json', 'User-Agent': UA}
        probe('CFBD draft/picks 2026', 'https://api.collegefootballdata.com/draft/picks', h,
              lambda r: len(r.json()), params={'year': 2026})
        probe('CFBD stats/player/season 2025', 'https://api.collegefootballdata.com/stats/player/season', h,
              lambda r: len(r.json()), params={'year': 2025})


if __name__ == '__main__':
    main()
