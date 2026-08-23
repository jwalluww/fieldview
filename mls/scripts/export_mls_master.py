"""mls/scripts/export_mls_master.py

Phase 3 (MLS): export mls_players_master.json from mls_player_match.json,
the file Phase 2 (build_mls_match.py) wrote. Same role as
epl/scripts/export_epl_master.py -- takes an output path as its first
CLI arg, defaults to a safe non-production _default.json path otherwise.

No DuckDB layer for MLS (unlike EPL/MLB/NBA/NFL) -- per spec, this reads
build_mls_match.py's JSON output directly rather than a database table.

standard_pos holds sofifa's granular position (ST/CAM/CDM/LB/CB/...);
position_group holds ESPN's coarse position (Forward/Defender/...) --
same two-tier convention as epl/scripts/build_epl_match.py, deliberately
the reverse of NFL's ourlads_pos(specific)/standard_pos(group) naming
(see that file's docstring for why).
"""
import json
import os
import sys

MATCH_PATH = os.path.join('mls', 'data', 'mls_player_match.json')
DEFAULT_OUT_PATH = os.path.join('mls', 'data', 'mls_players_master_default.json')


def export_master(out_path=DEFAULT_OUT_PATH):
    with open(MATCH_PATH, encoding='utf-8') as f:
        match_data = json.load(f)

    master = {}
    for p in match_data['players']:
        master[str(p['player_id'])] = {
            'player_id': p['player_id'],
            'name': p['name'],
            'team': p['team'],
            'team_abbreviation': p['team_abbreviation'],
            'jersey': p['jersey'],
            'age': p['age'],
            'height': p['height'],
            'weight': p['weight'],
            'citizenship': p['citizenship'],
            'position_group': p['position_group'],
            'standard_pos': p['standard_pos'],
            'overall_rating': p['overall_rating'],
            'potential': p['potential'],
            'sofifa_id': p['sofifa_id'],
            'sofifa_match_source': p['sofifa_match_source'],
            'asa_player_id': p['asa_player_id'],
            'asa_match_source': p['asa_match_source'],
            'stats': p['stats'],
        }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(master, f, indent=2, ensure_ascii=False)

    print(f"Wrote {out_path}: {len(master)} players")


if __name__ == '__main__':
    export_master(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT_PATH)
