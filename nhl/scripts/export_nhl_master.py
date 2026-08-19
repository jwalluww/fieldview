"""nhl/scripts/export_nhl_master.py

Phase 3 (NHL): export nhl_players_master.json from player_match, the
table Phase 2 (build_nhl_match.py) wrote. Same role as
mlb/scripts/export_mlb_master.py / nfl/scripts/export_master.py --
takes an output path as its first CLI arg, defaults to a safe
non-production _db.json path otherwise.
"""
import json
import os
import sys

import duckdb
import pandas as pd

DB_PATH = os.path.join('nhl', 'data', 'fieldview.duckdb')
DEFAULT_OUT_PATH = os.path.join('nhl', 'data', 'nhl_players_master_db.json')

INT_FIELDS = {'jersey_number', 'height_in_inches', 'weight_in_pounds'}


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
            'team_abbr': clean('team_abbr', r['team_abbr']),
            'position_group': clean('position_group', r['position_group']),
            'position_code': clean('position_code', r['position_code']),
            'jersey_number': clean('jersey_number', r['jersey_number']),
            'shoots_catches': clean('shoots_catches', r['shoots_catches']),
            'height_in_inches': clean('height_in_inches', r['height_in_inches']),
            'weight_in_pounds': clean('weight_in_pounds', r['weight_in_pounds']),
            'birth_date': clean('birth_date', r['birth_date']),
            'birth_city': clean('birth_city', r['birth_city']),
            'birth_country': clean('birth_country', r['birth_country']),
            'birth_state_province': clean('birth_state_province', r['birth_state_province']),
            'skater_stats': r['skater_stats'] if isinstance(r['skater_stats'], dict) else None,
            'goalie_stats': r['goalie_stats'] if isinstance(r['goalie_stats'], dict) else None,
            'stats_source': clean('stats_source', r['stats_source']),
            'overall_rating': clean('overall_rating', r['overall_rating']),
            'potential': clean('potential', r['potential']),
        }
        master[str(pid)] = entry

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(master, f, indent=2, ensure_ascii=False)

    print(f"Wrote {out_path}: {len(master)} players")


if __name__ == '__main__':
    export_master(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT_PATH)
