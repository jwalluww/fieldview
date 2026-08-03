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
              'overall_rating', 'contract_years_remaining'}


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
            pm.rotation_status,
            pm.rotation_source,
            pm.depth_rank,
            pm.overall_rating,
            pm.contract_salary,
            pm.contract_years_remaining
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
        master[str(pid)] = entry

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(master, f, indent=2, ensure_ascii=False)

    print(f"Wrote {out_path}: {len(master)} players")


if __name__ == '__main__':
    export_master(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT_PATH)
