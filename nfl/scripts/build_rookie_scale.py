"""One-off (run by hand, NOT in the cloud job): projected 2027 NFL rookie wage scale by pick.

Source: Over the Cap's Draft page (https://overthecap.com/draft), which publishes a full projected contract
(total value, signing bonus, 4-year cap schedule) for every pick 1-257 under the current CBA.
Writes nfl/data/rookie_scale.json: {source, as_of, cap_year, picks: {"1": {years, total_value, apy,
signing_bonus, fifth_year_option}, ...}}. Keeps the old file (exit 0) if the page changed shape.
Refresh when OTC updates its projection (e.g. after the cap is set, or once the real draft order is final).
"""
import json, os, re, sys
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

URL = 'https://overthecap.com/draft'
OUT = os.path.join('nfl', 'data', 'rookie_scale.json')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/124.0 Safari/537.36')


def money(s):
    return int(re.sub(r'[^\d]', '', s))


def main():
    r = requests.get(URL, headers={'User-Agent': UA}, timeout=60)
    if r.status_code != 200:
        print(f'KEEPING old file: HTTP {r.status_code}'); return 0
    soup = BeautifulSoup(r.text, 'html.parser')
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
        total = money(tv.group(1))
        picks[n] = {'years': len(rows), 'total_value': total, 'apy': round(total / len(rows)),
                    'signing_bonus': money(sb.group(1)), 'fifth_year_option': None}
    rounds = {}
    for td in soup.select('td[data-round]'):
        ov = td.select_one('span.overall')
        if ov:
            rounds[int(ov.get_text())] = int(td['data-round'])
    ok = sorted(picks) == list(range(1, 258)) and all(p['years'] == 4 for p in picks.values())
    if not ok:
        print(f'KEEPING old file: parsed {len(picks)} picks / not exactly 1-257 x 4 years'); return 0
    for n, p in picks.items():
        p['fifth_year_option'] = rounds.get(n) == 1
    # sanity: monotone non-increasing total value by pick
    vals = [picks[i]['total_value'] for i in range(1, 258)]
    if any(b > a for a, b in zip(vals, vals[1:])):
        print('KEEPING old file: scale not monotone'); return 0
    out = {'source': 'overthecap.com/draft (OTC projected 2027 rookie scale)',
           'as_of': datetime.now(timezone.utc).strftime('%Y-%m-%d'), 'cap_year': 2027,
           'note': 'Estimate: OTC projection by overall pick; real contracts are set after the draft.',
           'picks': {str(n): picks[n] for n in sorted(picks)}}
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, separators=(',', ':'))
    r1 = sum(1 for p in picks.values() if p['fifth_year_option'])
    print(f'wrote {len(picks)} picks ({r1} with 5th-year option); #1 ${picks[1]["total_value"]:,} '
          f'#32 ${picks[32]["total_value"]:,} #257 ${picks[257]["total_value"]:,}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
