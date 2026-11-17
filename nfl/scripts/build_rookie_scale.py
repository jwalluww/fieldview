"""One-off (run by hand, NOT in the cloud job): projected 2027 NFL rookie wage scale by pick.

Source: Over the Cap's Draft page (https://overthecap.com/draft), which publishes a full projected contract
(total value, signing bonus, 4-year cap schedule) for every pick 1-257 under the current CBA.
Writes nfl/data/rookie_scale.json: {source, as_of, cap_year, picks: {"1": {years, total_value, apy,
signing_bonus, fifth_year_option}, ...}}. Keeps the old file (exit 0) if the page changed shape.
Refresh when OTC updates its projection (e.g. after the cap is set, or once the real draft order is final).
"""
import json, os, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import otc_draft

OUT = os.path.join('nfl', 'data', 'rookie_scale.json')


def write_scale(picks):
    out = {'source': 'overthecap.com/draft (OTC projected 2027 rookie scale)',
           'as_of': datetime.now(timezone.utc).strftime('%Y-%m-%d'), 'cap_year': 2027,
           'note': 'Estimate: OTC projection by overall pick; real contracts are set after the draft.',
           'picks': {str(n): picks[n] for n in sorted(picks)}}
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, separators=(',', ':'))
    r1 = sum(1 for p in picks.values() if p['fifth_year_option'])
    print(f'wrote {len(picks)} picks ({r1} with 5th-year option); #1 ${picks[1]["total_value"]:,} '
          f'#32 ${picks[32]["total_value"]:,} #257 ${picks[257]["total_value"]:,}')


def main():
    soup = otc_draft.fetch_soup()
    if soup is None:
        print('KEEPING old file: OTC fetch failed'); return 0
    picks = otc_draft.parse_scale(soup)
    if picks is None:
        print('KEEPING old file: page changed shape (not exactly 1-257 x 4 years / not monotone)'); return 0
    write_scale(picks)
    return 0


if __name__ == '__main__':
    sys.exit(main())
