"""mlb/scripts/export_mlb_master.py

Phase 3 (MLB): export mlb_players_master.json from player_match, the
table Phase 2 (build_mlb_match.py) wrote. Same role as
nfl/scripts/export_master.py / nba/scripts/export_nba_master.py --
takes an output path as its first CLI arg, defaults to a safe
non-production _db.json path otherwise.
"""
import json
import os
import sys

import duckdb
import pandas as pd

DB_PATH = os.path.join('mlb', 'data', 'fieldview.duckdb')
DEFAULT_OUT_PATH = os.path.join('mlb', 'data', 'mlb_players_master_db.json')

INT_FIELDS = {'weight'}


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
    rows = con.execute("SELECT * FROM player_match ORDER BY person_id").fetchdf()
    con.close()

    master = {}
    for _, r in rows.iterrows():
        pid = int(r['person_id'])
        entry = {
            'player_id': pid,
            'name': clean('name', r['name']),
            'team': clean('team', r['team']),
            'team_abbr': clean('team_abbr', r['team_abbr']),
            'position': clean('position', r['position']),
            'position_group': clean('position_group', r['position_group']),
            'position_group_source': clean('position_group_source', r['position_group_source']),
            'player_type': clean('player_type', r['player_type']),
            'jersey_number': clean('jersey_number', r['jersey_number']),
            'height': clean('height', r['height']),
            'weight': clean('weight', r['weight']),
            'bats': clean('bats', r['bats']),
            'throws': clean('throws', r['throws']),
            'batting_stats': r['batting_stats'] if isinstance(r['batting_stats'], dict) else None,
            'pitching_stats': r['pitching_stats'] if isinstance(r['pitching_stats'], dict) else None,
            'match_source': clean('match_source', r['match_source']),
        }
        master[str(pid)] = entry

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(master, f, indent=2, ensure_ascii=False)

    print(f"Wrote {out_path}: {len(master)} players")


if __name__ == '__main__':
    export_master(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT_PATH)
