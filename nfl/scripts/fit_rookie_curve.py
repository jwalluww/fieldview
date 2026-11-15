"""nfl/scripts/fit_rookie_curve.py

ONE-OFF (run by hand, NOT in the cloud job): fits the "draft pick -> Madden
launch rating" curve used by the FormationView draft installer and writes
nfl/data/rookie_curve.json (+ a chart next to it when --chart PATH is given).

Data: the 2025 and 2026 draft classes (nflreadpy load_draft_picks) matched to
the rookies (yearsPro == 0) of two EA Madden *launch* iterations pulled from
the drop-api with shared/scripts/ea_ratings.py:
  - Madden 27 launch: slug madden-nfl, iteration=1-base, WITH drop-referrer
    (cards carry team + position)
  - Madden 26 launch: the same call WITHOUT the referrer (EA then serves last
    season; cards carry no team and no position, so the 2025 class matches by
    name only and takes its position from the draft label)
Matching reuses build_master.find_madden_player (aliases, team-first, then
league-wide) over the rookie pool only.

Model (predicts on the Madden 27 scale):
    overall = intercept[pos] + offset_m26 * is_madden26 + slope[pos] * ln(pick)
    slope[pos] = shared slope + a per-position deviation shrunk toward 0 (ridge,
    RIDGE_LAMBDA). A plain shared slope was tried first: the per-position slopes
    differ significantly (F-test p < 0.001) and win out-of-sample (leave-one-out
    RMSE, notably QB 3.3 -> 2.0 and picks <= 32 2.34 -> 2.0), so the published
    model lets them differ; the ridge keeps thin positions (QB/TE/S/LB top-of-
    draft n = 3-4) from chasing noise. resid_sd is the leave-one-out SD.

REFIT WHEN: a new Madden launch exists (Madden 28, ~August 2027) -- add that
class, bump EDITION markers, rerun. Otherwise leave it alone.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared', 'scripts'))
import build_master as bm          # noqa: E402
import ea_ratings                  # noqa: E402

OUT = os.path.join('nfl', 'data', 'rookie_curve.json')
POSITIONS = ['QB', 'RB', 'WR', 'TE', 'OL', 'EDGE', 'DI', 'LB', 'CB', 'S']
MAX_PICK = 257
RIDGE_LAMBDA = 20.0   # shrinkage of per-position slope deviations (best leave-one-out RMSE at picks <= 32 among 5/20/50)
RATING_CAP = 88.0     # EA's highest launch rookie across both classes is 84 (Travis Hunter, pick 2); predictions never exceed this

# Draft-label -> standard_pos. DE/OLB/DL/DB are the ambiguous ones (a 3-4 DE
# can be interior, an OLB can be off-ball, DB can be CB or S): for a matched
# 2026 rookie the Madden position label wins, for the unlabeled 2025 class the
# draft label is used (DB without a Madden label is dropped).
DRAFT_POS = {'QB': 'QB', 'RB': 'RB', 'FB': 'RB', 'WR': 'WR', 'TE': 'TE',
             'OL': 'OL', 'OT': 'OL', 'G': 'OL', 'OG': 'OL', 'C': 'OL',
             'DE': 'EDGE', 'OLB': 'EDGE', 'DT': 'DI', 'DL': 'DI', 'NT': 'DI',
             'LB': 'LB', 'ILB': 'LB', 'CB': 'CB', 'S': 'S', 'SAF': 'S', 'FS': 'S', 'SS': 'S'}
AMBIGUOUS = {'DE', 'OLB', 'DL', 'DB'}
DROPPED = {'K', 'P', 'LS'}
MADDEN_POS = {'QB': 'QB', 'HB': 'RB', 'FB': 'RB', 'WR': 'WR', 'TE': 'TE',
              'LT': 'OL', 'LG': 'OL', 'C': 'OL', 'RG': 'OL', 'RT': 'OL',
              'LEDG': 'EDGE', 'REDG': 'EDGE', 'DT': 'DI', 'SAM': 'LB', 'MIKE': 'LB',
              'WILL': 'LB', 'CB': 'CB', 'FS': 'S', 'SS': 'S'}


def pull(iteration, with_referrer, min_total, marker):
    """Pull one Madden iteration through ea_ratings.fetch_all. The shared
    header builder is swapped out for the no-referrer (previous edition) pull."""
    orig = ea_ratings.build_headers
    if not with_referrer:
        ea_ratings.build_headers = lambda slug: {'User-Agent': ea_ratings.USER_AGENT,
                                                 'Accept': 'application/json'}
    try:
        def validate(items):
            hit = sum(1 for c in items if marker in (c.get('avatarUrl') or ''))
            return None if hit >= 0.95 * len(items) else f'only {hit}/{len(items)} cards carry {marker}'
        return ea_ratings.fetch_all('madden-nfl', {'iteration': iteration}, min_total=min_total, validate=validate)
    finally:
        ea_ratings.build_headers = orig


def rookie_pool(cards):
    by, allp = {}, []
    for c in cards:
        if c.get('yearsPro') != 0:
            continue
        name = f"{c['firstName']} {c['lastName']}"
        ab = bm.MADDEN_TEAM_MAP.get((c.get('team') or {}).get('label', ''))
        p = dict(full_name=name, team=ab, normalized=bm.normalize_madden(name),
                 overall=c['overallRating'], position=(c.get('position') or {}).get('shortLabel', ''),
                 college=c.get('college'))
        allp.append(p)
        by.setdefault(ab, []).append(p)
    return by, allp


def match_class(season, cards, edition):
    d = nfl_picks(season)
    by, allp = rookie_pool(cards)
    rows = []
    for r in d.itertuples():
        if not isinstance(r.pfr_player_name, str):
            continue
        team = bm.normalize_team({'ARI': 'ARZ'}.get(r.team, r.team))
        m = bm.find_madden_player(r.pfr_player_name, by.get(team, []), allp, True)
        rows.append(dict(season=season, edition=edition, pick=int(r.pick), round=int(r.round),
                         name=r.pfr_player_name, draft_pos=r.position, college=r.college,
                         overall=m['overall'] if m else None,
                         madden_pos=MADDEN_POS.get(m['position']) if m else None))
    return pd.DataFrame(rows)


_PICKS = {}


def nfl_picks(season):
    if season not in _PICKS:
        import nflreadpy as nfl
        _PICKS[season] = nfl.load_draft_picks([season]).to_pandas()
    return _PICKS[season]


def assign_pos(row):
    dp = row.draft_pos
    if dp in DROPPED:
        return None
    if isinstance(row.madden_pos, str):
        return row.madden_pos
    if dp in DRAFT_POS and dp != 'DB':
        return DRAFT_POS[dp]
    return None


def design(df, per_pos_slope=False):
    X = [(df.pos == p).astype(float).values for p in POSITIONS]
    X.append(df.is26.astype(float).values)
    lp = np.log(df.pick.values.astype(float))
    if per_pos_slope:
        X += [lp * (df.pos == p).values for p in POSITIONS]
    else:
        X.append(lp)
    return np.column_stack(X)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--chart', help='write a PNG chart here')
    args = ap.parse_args()

    m27 = pull('1-base', True, 3000, 'madden-nfl-27')
    m26 = pull('1-base', False, 1800, 'madden-nfl-26')
    if m27 is None or m26 is None:
        print('a launch pull failed -- not refitting'); return 0
    print(f'Madden 27 launch cards {len(m27)}, Madden 26 launch cards {len(m26)}')

    df = pd.concat([match_class(2026, m27, 'M27'), match_class(2025, m26, 'M26')], ignore_index=True)
    for s, g in df.groupby('season'):
        print(f'{s}: {len(g)} picks, matched {g.overall.notna().sum()} ({g.overall.notna().mean():.1%})')
    df = df[df.overall.notna()].copy()
    df['pos'] = df.apply(assign_pos, axis=1)

    # mapping report
    print('\nDraft label -> standard_pos (count per class):')
    for lab, g in df.groupby('draft_pos'):
        print(f'  {lab:4s} -> {DRAFT_POS.get(lab, "DROP" if lab in DROPPED else "?"):5s}', g.groupby('season').size().to_dict(),
              '(ambiguous: Madden label wins when present)' if lab in AMBIGUOUS else '')
    dis = df[(df.season == 2026) & df.madden_pos.notna() & df.draft_pos.map(DRAFT_POS).notna() & (df.madden_pos != df.draft_pos.map(DRAFT_POS))]
    print(f'2026 rookies where the Madden position group != the draft-label group: {len(dis)}',
          dis[['name', 'draft_pos', 'madden_pos']].values.tolist()[:12])
    print('dropped (K/P/LS or unresolved DB):', df[df.pos.isna()][['season', 'name', 'draft_pos']].values.tolist())
    df = df[df.pos.notna()].copy()
    df['is26'] = (df.season == 2025).astype(int)   # edition offset: Madden 26 vs 27

    y = df.overall.values.astype(float)
    X = design(df)
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y - X @ b
    k = X.shape[1]
    sse = float(res @ res)
    r2 = 1 - sse / float(((y - y.mean()) ** 2).sum())
    Xf = design(df, True)
    bf, *_ = np.linalg.lstsq(Xf, y, rcond=None)
    ssef = float(((y - Xf @ bf) ** 2).sum())
    from scipy import stats
    dfn, dfd = Xf.shape[1] - k, len(y) - Xf.shape[1]
    F = ((sse - ssef) / dfn) / (ssef / dfd); pF = 1 - stats.f.cdf(F, dfn, dfd)
    offset = b[len(POSITIONS)]
    shared_slope = b[-1]
    # ridge: shared slope + penalized per-position deviation
    lp = np.log(df.pick.values.astype(float))
    base = np.column_stack([design(df)[:, :-1], lp])            # pos dummies, edition, shared slope
    dev = np.column_stack([lp * (df.pos == p).values for p in POSITIONS])
    XR = np.column_stack([base, dev])
    pen = np.diag([0.0] * base.shape[1] + [RIDGE_LAMBDA] * len(POSITIONS))
    A = np.linalg.inv(XR.T @ XR + pen)
    br = A @ XR.T @ y
    H = XR @ A @ XR.T
    res_r = y - H @ y
    loo = res_r / (1 - np.diag(H))
    Hs = X @ np.linalg.pinv(X.T @ X) @ X.T
    loo_s = (y - Hs @ y) / (1 - np.diag(Hs))
    Hp = Xf @ np.linalg.pinv(Xf.T @ Xf) @ Xf.T
    loo_p = (y - Hp @ y) / (1 - np.diag(Hp))
    top = df.pick.values <= 32
    rm = lambda e, m=slice(None): float(np.sqrt((e[m] ** 2).mean()))
    print(f'\nLOO RMSE  all / picks<=32:  shared {rm(loo_s):.2f}/{rm(loo_s, top):.2f}   per-position {rm(loo_p):.2f}/{rm(loo_p, top):.2f}   ridge(lam={RIDGE_LAMBDA:g}) {rm(loo):.2f}/{rm(loo, top):.2f}')
    inter = dict(zip(POSITIONS, br[:len(POSITIONS)]))
    offset = br[len(POSITIONS)]
    shared = br[len(POSITIONS) + 1]
    slope = {p: float(shared + br[len(POSITIONS) + 2 + i]) for i, p in enumerate(POSITIONS)}
    print('published slopes (shared %.2f):' % shared, {p: round(v, 2) for p, v in slope.items()}, ' offset M26 %+.2f' % offset)
    df['res'] = res_r
    df['loo'] = loo
    resid_sd, resid_sd_in, n_pos = {}, {}, {}
    for p in POSITIONS:
        g = df[df.pos == p]
        n_pos[p] = {'total': int(len(g)), 'm27': int((g.season == 2026).sum()), 'm26': int((g.season == 2025).sum())}
        resid_sd[p] = round(float(np.sqrt((g.loo ** 2).mean())), 2)
        resid_sd_in[p] = round(float(g.res.std(ddof=1)), 2)
    print('n per position:', {p: n_pos[p]['total'] for p in POSITIONS})
    print('resid SD (leave-one-out, published):', resid_sd)
    print('resid SD (in-sample):', resid_sd_in)

    point = {p: [round(float(min(RATING_CAP, max(40, inter[p] + slope[p] * np.log(k_)))), 1) for k_ in range(1, MAX_PICK + 1)] for p in POSITIONS}
    d26 = df[df.season == 2026]
    X26 = np.column_stack([(d26.pos == p).astype(float).values for p in POSITIONS] + [np.log(d26.pick.values.astype(float))])
    b26, *_ = np.linalg.lstsq(X26, d26.overall.values.astype(float), rcond=None)
    print('\nRating at pick 1/10/32/64/100/200   published (pooled, M27 scale) | 2026-only own fit (shared slope)')
    for i, p in enumerate(POSITIONS):
        pooled = [point[p][k_ - 1] for k_ in (1, 10, 32, 64, 100, 200)]
        only = [round(b26[i] + b26[-1] * np.log(k_), 1) for k_ in (1, 10, 32, 64, 100, 200)]
        print(f'  {p:5s} {pooled} | {only}')
    print(f'  2026-only shared slope {b26[-1]:.2f}')

    out = {
        'fitted_on': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        'model': 'overall = intercept[pos] + offset_madden26 * is_madden26 + slope[pos] * ln(pick); slope[pos] = shared slope + ridge-shrunk deviation; predictions are on the Madden 27 scale (is_madden26 = 0); resid_sd is leave-one-out',
        'classes': {'2026': 'Madden 27 launch (iteration 1-base)', '2025': 'Madden 26 launch (iteration 1-base, no referrer)'},
        'n': n_pos, 'n_total': int(len(y)), 'r2': round(r2, 3),
        'coefficients': {'intercept_at_pick1': {p: round(float(v), 3) for p, v in inter.items()},
                         'slope_per_ln_pick': {p: round(v, 4) for p, v in slope.items()},
                         'shared_slope': round(float(shared), 4), 'offset_madden26': round(float(offset), 3),
                         'ridge_lambda': RIDGE_LAMBDA, 'rating_cap': RATING_CAP},
        'slope_f_test_vs_shared': {'F': round(float(F), 2), 'df': [int(dfn), int(dfd)], 'p': round(float(pF), 5)},
        'loo_rmse': {'shared': round(rm(loo_s), 3), 'per_position': round(rm(loo_p), 3), 'ridge': round(rm(loo), 3)},
        'resid_sd': resid_sd, 'resid_sd_in_sample': resid_sd_in,
        'point_index': 'point[pos][i] is the rating for pick i+1 (picks 1..257), rounded to 0.1, clamped to 40..99',
        'point': point,
    }
    with open(OUT, 'w') as f:
        json.dump(out, f, separators=(',', ':'))
    print('wrote', OUT, os.path.getsize(OUT), 'bytes')

    if args.chart:
        import matplotlib; matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, axs = plt.subplots(2, 5, figsize=(17, 7.2), sharex=True, sharey=True)
        xs = np.arange(1, MAX_PICK + 1)
        for ax, p in zip(axs.flat, POSITIONS):
            g = df[df.pos == p]
            for s, col, lab in ((2025, '#9ca3af', '2025 class (Madden 26)'), (2026, '#2563eb', '2026 class (Madden 27)')):
                q = g[g.season == s]
                ax.scatter(q.pick, q.overall, s=14, color=col, alpha=.7, lw=0, label=lab)
            ax.plot(xs, point[p], color='#1f2937', lw=2, label='fit, Madden 27 scale')
            ax.plot(xs, np.array(point[p]) + offset, color='#6b7280', lw=1.5, ls='--', label='fit, Madden 26 scale')
            ax.set_xscale('log'); ax.set_xticks([1, 10, 32, 100, 250]); ax.set_xticklabels(['1', '10', '32', '100', '250'])
            ax.set_title(f'{p}  (n={len(g)}, SD {resid_sd[p]})', fontsize=11, loc='left')
            ax.grid(color='#e5e7eb', lw=.6); [ax.spines[s_].set_visible(False) for s_ in ('top', 'right')]
        axs[0, 0].legend(loc='lower left', fontsize=7.5, frameon=False)
        fig.supxlabel('Draft pick (log scale)'); fig.supylabel('Madden launch overall')
        fig.suptitle(f'Rookie curve (per-position slopes, ridge-shrunk), Madden 26 offset {offset:+.1f}', x=.01, ha='left', fontsize=13)
        fig.tight_layout(); fig.savefig(args.chart, dpi=130)
        print('chart', args.chart)
    return 0


if __name__ == '__main__':
    sys.exit(main())
