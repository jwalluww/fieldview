"""epl/scripts/export_epl_master.py

Phase 3 (EPL): export epl_players_master.json from player_match, the
table Phase 2 (build_epl_match.py) wrote. Same role as
mlb/scripts/export_mlb_master.py -- takes an output path as its first
CLI arg, defaults to a safe non-production _db.json path otherwise.
"""
import json
import os
import sys

import duckdb
import pandas as pd

DB_PATH = os.path.join('epl', 'data', 'fieldview.duckdb')
DEFAULT_OUT_PATH = os.path.join('epl', 'data', 'epl_players_master_db.json')

INT_FIELDS = {'overall_rating', 'potential', 'sofifa_id'}


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
    rows = con.execute("SELECT * FROM player_match ORDER BY player_id").fetchdf()
    con.close()

    master = {}
    for _, r in rows.iterrows():
        pid = int(r['player_id'])
        entry = {
            'player_id': pid,
            'name': clean('name', r['name']),
            'web_name': clean('web_name', r['web_name']),
            'team': clean('team', r['team']),
            'team_short': clean('team_short', r['team_short']),
            'position_group': clean('position_group', r['position_group']),
            'standard_pos': clean('standard_pos', r['standard_pos']),
            'overall_rating': clean('overall_rating', r['overall_rating']),
            'potential': clean('potential', r['potential']),
            'sofifa_id': clean('sofifa_id', r['sofifa_id']),
            'match_source': clean('match_source', r['match_source']),
            'stats': r['stats'] if isinstance(r['stats'], dict) else None,
        }
        master[str(pid)] = entry

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(master, f, indent=2, ensure_ascii=False)

    print(f"Wrote {out_path}: {len(master)} players")


if __name__ == '__main__':
    export_master(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT_PATH)
