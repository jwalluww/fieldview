"""NFL contracts from nflverse (OverTheCap) via nflreadpy.load_contracts() -- replaces Spotrac
(which answers 403 to GitHub runners and, later, to this machine too).

Writes nfl/data/spotrac_contracts.json in EXACTLY the shape the pipeline already reads
(name, spotrac_name, name_norm, pos, team, age, length_remaining, cash_total_remaining,
cash_guaranteed_remaining, pct_guaranteed_remaining) plus `gsis_id` so build_match can join by id.
The file name is kept on purpose: build_db / build_match / build_master stay untouched.

Field meaning (S = the current NFL season; per-year rows come from OTC's `season_history`):
  length_remaining          seasons >= S with cash_paid > 0 (1 = S is the last; void years carry cap but no cash)
  cash_total_remaining      sum of cash_paid over those seasons
  cash_guaranteed_remaining FUTURE guaranteed money: guaranteed_salary of seasons > S, plus min(base_salary,
                            guaranteed_salary) for S (the signing bonus guaranteed in S is already paid; this
                            reproduces Spotrac's definition: Hurts 23.2M, Mayfield 51.3M, Allen 53.8M)
  rows with no per-year data (rookies drafted this year) fall back to the active contract_history entry
  (years = yrs - (S - year_signed), cash/guarantees = total/guarantees prorated by years remaining).
Guard (keep the old file, exit 0): fetch failure, < 1,500 usable rows, < 1,200 with a gsis_id.
Run from the repo root: python nfl/scripts/scrape_contracts_nflverse.py
"""
import json
import os
import re
import sys
import unicodedata
from datetime import date

OUT_PATH = os.path.join('nfl', 'data', 'spotrac_contracts.json')
MIN_ROWS, MIN_GSIS = 1500, 1200

TEAMS = {'49ers': 'SF', 'Bears': 'CHI', 'Bengals': 'CIN', 'Bills': 'BUF', 'Broncos': 'DEN', 'Browns': 'CLE',
         'Buccaneers': 'TB', 'Cardinals': 'ARZ', 'Chargers': 'LAC', 'Chiefs': 'KC', 'Colts': 'IND',
         'Commanders': 'WAS', 'Cowboys': 'DAL', 'Dolphins': 'MIA', 'Eagles': 'PHI', 'Falcons': 'ATL',
         'Giants': 'NYG', 'Jaguars': 'JAX', 'Jets': 'NYJ', 'Lions': 'DET', 'Packers': 'GB', 'Panthers': 'CAR',
         'Patriots': 'NE', 'Raiders': 'LV', 'Rams': 'LAR', 'Ravens': 'BAL', 'Saints': 'NO', 'Seahawks': 'SEA',
         'Steelers': 'PIT', 'Texans': 'HOU', 'Titans': 'TEN', 'Vikings': 'MIN'}
CODE_FIX = {'ARI': 'ARZ', 'JAC': 'JAX', 'LA': 'LAR', 'OAK': 'LV', 'SD': 'LAC', 'STL': 'LAR'}
# OTC position -> the labels build_master.SPOTRAC_POS_MAP understands (K/P/LS stay unmapped = dropped there)
POS = {'IDL': 'DT', 'RG': 'G', 'LG': 'G'}


def norm(name):
    s = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    s = re.sub(r'\b(jr|sr|ii|iii|iv|v)\b\.?', '', s.lower())
    return re.sub(r'[^a-z0-9]', '', s)


def current_season():
    t = date.today()
    return t.year if t.month >= 3 else t.year - 1


def team_code(raw):
    t = (raw or '').split('/')[-1].strip()   # traded players: 'ARI/BAL' -> the last (current) team
    return TEAMS.get(t) or CODE_FIX.get(t) or (t if len(t) <= 3 else None)


def derive(x, S):
    """-> (years, cash, guaranteed) in millions, or None."""
    sh = []
    for s in (x.get('season_history') or []):
        y = str(s.get('year', ''))
        if y.isdigit() and int(y) >= S:
            sh.append((int(y), s))
    live = [(y, s) for y, s in sh if (s.get('cash_paid') or 0) > 0]
    if live:
        cash = sum(s['cash_paid'] or 0 for _, s in live)
        g = 0.0
        for y, s in live:
            gs = s.get('guaranteed_salary') or 0
            g += min(s.get('base_salary') or 0, gs) if y == S else gs
        return len(live), cash, g
    ch = [c for c in (x.get('contract_history') or []) if c.get('status') == 'Active']
    if not ch:
        return None
    c = ch[-1]
    yrs, ys = c.get('yrs') or 0, c.get('year_signed')
    if not yrs or ys is None:
        return None
    rem = yrs - (S - int(ys))
    if rem < 1:
        return None
    frac = rem / yrs
    return rem, (c.get('total') or 0) * frac, (c.get('guarantees') or 0) * frac


def main():
    try:
        import nflreadpy as nfl
        import polars as pl
        df = nfl.load_contracts().filter(pl.col('is_active') == True)  # noqa: E712
        recs = df.to_dicts()
    except Exception as e:
        print(f'GUARD: nflverse contracts fetch failed ({type(e).__name__}: {str(e)[:120]}); keeping existing {OUT_PATH}')
        return
    S = current_season()
    best = {}
    for x in recs:
        key = x.get('gsis_id') or ('n:' + norm(x['player']) + str(x.get('team')))
        if key not in best or (x.get('year_signed') or 0) > (best[key].get('year_signed') or 0):
            best[key] = x
    rows = []
    for x in best.values():
        d = derive(x, S)
        pos = POS.get(x['position'], x['position'])
        if d is None or pos in ('K', 'P', 'LS'):
            continue
        yrs, cash, g = d
        dob = x.get('date_of_birth')
        age = None
        if dob:
            try:
                age = S - int(str(dob)[:4])
            except ValueError:
                pass
        rows.append({
            'name': x['player'], 'spotrac_name': x['player'], 'name_norm': norm(x['player']),
            'pos': pos, 'team': team_code(x.get('team')), 'age': age,
            'length_remaining': int(yrs),
            'cash_total_remaining': int(round(cash * 1e6)),
            'cash_guaranteed_remaining': int(round(g * 1e6)),
            'pct_guaranteed_remaining': round(100 * g / cash, 2) if cash else 0.0,
            'gsis_id': x.get('gsis_id'),
        })
    n_gsis = sum(1 for r in rows if r['gsis_id'])
    if len(rows) < MIN_ROWS or n_gsis < MIN_GSIS:
        print(f'GUARD: only {len(rows)} usable rows / {n_gsis} with gsis_id (need {MIN_ROWS}/{MIN_GSIS}); keeping existing {OUT_PATH}')
        return
    rows.sort(key=lambda r: (r['team'] or '', r['name']))
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    print(f'Wrote {len(rows)} contracts ({n_gsis} with gsis_id) for season {S} to {OUT_PATH}')


if __name__ == '__main__':
    main()
