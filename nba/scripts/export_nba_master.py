"""Phase 3 (NBA): export nba_players_master.json from the DuckDB tables
Phase 1 (build_nba_db.py) loaded and Phase 2 (build_nba_match.py) matched.

Joins player_match (resolved team/position/rotation/rating/contract
fields, keyed by player_id) back to nba_stats (passthrough bio/box-score
fields) and reassembles the exact schema build_nba_master.py writes.
build_nba_master.py itself is untouched -- this writes to
nba_players_master_db.json by default (safe verification path), not the
live nba_players_master.json court-view.html/player-table.html read.
"""
import json
import os
import sys

import duckdb
import pandas as pd

DB_PATH = os.path.join('nba', 'data', 'fieldview.duckdb')
DEFAULT_OUT_PATH = os.path.join('nba', 'data', 'nba_players_master_db.json')


# Fields that are ints in the original schema but round-trip through
# DuckDB as DOUBLE (nullable numeric columns upcast to float64 in pandas).
INT_FIELDS = {'weight', 'games_played', 'games_started', 'depth_rank',
              'overall_rating', 'contract_years_remaining', 'adv_games', 'adv_mp'}

# Basketball-Reference advanced fields (nba_stats.json's own ESPN
# ts_pct/per/ast_ratio/tov_ratio/vorp/usg/reb stay raw there -- BBR replaces them).
BBR_FIELDS = ('ts_pct', 'usg_pct', 'trb_pct', 'ast_pct', 'tov_pct', 'stl_pct',
              'blk_pct', 'per', 'ws_per_48', 'obpm', 'dbpm', 'bpm', 'vorp',
              'adv_mp', 'adv_games', 'adv_season')
# The box-score part of nba_stats.json's prev_season block (its ESPN advanced
# fields are dropped for the same reason).
EXTRA_BOX = ('spg', 'bpg', 'fg_pct', 'three_pct', 'ft_pct', 'tov')
PREV_BOX_FIELDS = ('season', 'ppg', 'rpg', 'apg', 'mpg', 'games_played', 'games_started') + EXTRA_BOX


def clean(field, v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    if hasattr(v, 'item'):
        v = v.item()
    if field in INT_FIELDS:
        return int(v)
    return v


def export_master(out_path=DEFAULT_OUT_PATH):
    con = duckdb.connect(DB_PATH)
    rows = con.execute("""
        SELECT
            s.player_id,
            s.name,
            pm.team,
            pm.position,
            s.jersey_number,
            s.height,
            s.weight,
            s.ppg,
            s.rpg,
            s.apg,
            s.mpg,
            s.games_played,
            s.games_started,
            s.spg, s.bpg, s.fg_pct, s.three_pct, s.ft_pct, s.tov,
            pm.rotation_status,
            pm.rotation_source,
            pm.depth_rank,
            pm.overall_rating,
            pm.contract_salary,
            pm.contract_years_remaining,
            s.stats_season,
            s.prev_season,
            s.injury_status,
            pm.ts_pct,
            pm.usg_pct,
            pm.trb_pct,
            pm.ast_pct,
            pm.tov_pct,
            pm.stl_pct,
            pm.blk_pct,
            pm.per,
            pm.ws_per_48,
            pm.obpm,
            pm.dbpm,
            pm.bpm,
            pm.vorp,
            pm.adv_mp,
            pm.adv_games,
            pm.adv_season,
            pm.prev_ts_pct,
            pm.prev_usg_pct,
            pm.prev_trb_pct,
            pm.prev_ast_pct,
            pm.prev_tov_pct,
            pm.prev_stl_pct,
            pm.prev_blk_pct,
            pm.prev_per,
            pm.prev_ws_per_48,
            pm.prev_obpm,
            pm.prev_dbpm,
            pm.prev_bpm,
            pm.prev_vorp,
            pm.prev_adv_mp,
            pm.prev_adv_games,
            pm.prev_adv_season
        FROM nba_stats s
        JOIN player_match pm ON pm.player_id = s.player_id
        ORDER BY s.row_id
    """).fetchdf()
    con.close()

    master = {}
    for _, r in rows.iterrows():
        pid = int(r['player_id'])
        entry = {
            'player_id': pid,
            'name': clean('name', r['name']),
            'team': clean('team', r['team']),
            'position': clean('position', r['position']),
            'jersey_number': clean('jersey_number', r['jersey_number']),
            'height': clean('height', r['height']),
            'weight': clean('weight', r['weight']),
            'ppg': clean('ppg', r['ppg']),
            'rpg': clean('rpg', r['rpg']),
            'apg': clean('apg', r['apg']),
            'mpg': clean('mpg', r['mpg']),
            'games_played': clean('games_played', r['games_played']),
            'games_started': clean('games_started', r['games_started']),
            'rotation_status': clean('rotation_status', r['rotation_status']),
            'rotation_source': clean('rotation_source', r['rotation_source']),
            'depth_rank': clean('depth_rank', r['depth_rank']),
            'overall_rating': clean('overall_rating', r['overall_rating']),
            'contract_salary': clean('contract_salary', r['contract_salary']),
            'contract_years_remaining': clean('contract_years_remaining', r['contract_years_remaining']),
        }
        for f in EXTRA_BOX:
            entry[f] = clean(f, r[f])
        for f in BBR_FIELDS:
            entry[f] = clean(f, r[f])
        entry['adv_prev'] = ({f: clean(f, r['prev_' + f]) for f in BBR_FIELDS}
                             if pd.notna(r['prev_adv_season']) else None)
        entry['stats_season'] = clean('stats_season', r['stats_season'])
        prev = r['prev_season']
        entry['prev_season'] = ({f: clean(f, prev.get(f)) for f in PREV_BOX_FIELDS}
                                if isinstance(prev, dict) else None)
        entry['injury_status'] = clean('injury_status', r['injury_status'])
        master[str(pid)] = entry

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(master, f, indent=2, ensure_ascii=False)

    print(f"Wrote {out_path}: {len(master)} players")


if __name__ == '__main__':
    export_master(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT_PATH)
