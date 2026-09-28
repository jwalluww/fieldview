"""Phase 3: export players_master.json from the DuckDB tables Phase 1
(build_db.py) loaded and Phase 2 (build_match.py) matched.

Joins player_match (matching results, keyed by row_id) back to
ourlads_players (row_id) for the passthrough fields (name, team, cap
number, stats, etc.), and reassembles the exact same per-player schema
build_master.py writes. build_master.py's own functions are still reused
directly (normalize_stats) and its file is untouched.

Writes to nfl/data/players_master_db.json by default -- the safe,
non-production verification path. The production pipeline (scrape.yml)
passes nfl/data/players_master.json explicitly as the first CLI arg to
write the real file the frontend reads:
    python nfl/scripts/export_master.py nfl/data/players_master.json
"""
import json
import os
import sys

import duckdb
import pandas as pd

from build_master import normalize_stats

DB_PATH = os.path.join('nfl', 'data', 'fieldview.duckdb')
DEFAULT_OUT_PATH = os.path.join('nfl', 'data', 'players_master_db.json')

# Field order mirrors build_master.py's entry dict construction exactly.
INT_FIELDS = {
    'depth', 'jersey', 'madden', 'madden_rank', 'madden_rank_total',
    'draft_year', 'years_pro', 'age', 'years_remaining', 'stats_season',
    'penalty_count', 'def_advanced_season', 'weight',
}
FLOAT_FIELDS = {
    'match_confidence', 'snap_pct', 'cash_total_remaining',
    'cash_guaranteed_remaining', 'avg_annual_remaining',
    'epa_per_play', 'success_rate', 'ngs_time_to_throw', 'cpoe', 'qbr',
    'ryoe_per_att', 'box_rate', 'yac_per_att', 'broken_tackle_rate', 'target_share',
    'adot', 'air_yards_share', 'avg_separation', 'yac_above_expectation',
    'drop_rate', 'broken_tackle_rate_rec',
    'pressures_per100', 'sacks_per100', 'tfl_per100', 'tkl_per100', 'missed_tackle_rate',
    'comp_pct_allowed', 'rating_allowed', 'yds_per_target_allowed', 'adot_allowed',
    'int_pd_per_target',
}


def clean(field, value):
    # pd.isna() unconditionally (not gated behind isinstance(value, float))
    # -- confirmed live this needs to catch pd.NA specifically, not just
    # NaN. build_db.py's load_pfr_rb_stats() divides by
    # touches.replace(0, pd.NA) to avoid a division-by-zero for a player
    # with zero combined rush+rec touches; that pd.NA is a distinct type
    # from float NaN (isinstance(pd.NA, float) is False) and was passing
    # through this check uncaught, crashing json.dump() with "Object of
    # type NAType is not JSON serializable" the first time this pipeline
    # ever produced a real (non-empty) PFR row hitting that edge case.
    if value is None or pd.isna(value):
        return None
    if hasattr(value, 'item'):  # numpy scalar -> native python
        value = value.item()
    if field in INT_FIELDS:
        return int(value)
    if field in FLOAT_FIELDS:
        return float(value)
    return value


def export_master(out_path=DEFAULT_OUT_PATH):
    con = duckdb.connect(DB_PATH)
    rows = con.execute("""
        SELECT
            pm.player_key AS player_id,
            pm.gsis_id,
            pm.match_confidence,
            pm.canonical_name,
            op.name AS ourlads_name,
            op.abbr AS team,
            op.team AS team_name,
            op.base_defense,
            op.ourlads_pos,
            op.standard_slot,
            pm.standard_pos,
            op.depth,
            pm.madden_jersey AS jersey,
            pm.madden,
            pm.madden_rank,
            pm.madden_rank_total,
            pm.madden_pos_label,
            op.cap_number,
            op.attainment,
            op.injured,
            op.stats_json,
            op.stats_season,
            pm.match_source,
            pm.draft_year,
            pm.college,
            pm.years_pro,
            pm.age,
            pm.snap_pct,
            pm.height,
            pm.weight,
            pm.injury_status,
            pm.injury_detail,
            pm.years_remaining,
            pm.cash_total_remaining,
            pm.cash_guaranteed_remaining,
            pm.avg_annual_remaining,
            pm.penalty_count,
            pm.epa_per_play,
            pm.success_rate,
            pm.ngs_time_to_throw,
            pm.cpoe,
            pm.qbr,
            pm.ryoe_per_att,
            pm.box_rate,
            pm.yac_per_att,
            pm.broken_tackle_rate,
            pm.target_share,
            pm.adot,
            pm.air_yards_share,
            pm.avg_separation,
            pm.yac_above_expectation,
            pm.drop_rate,
            pm.broken_tackle_rate_rec,
            pm.pressures_per100, pm.sacks_per100, pm.tfl_per100, pm.tkl_per100,
            pm.missed_tackle_rate, pm.comp_pct_allowed, pm.rating_allowed,
            pm.yds_per_target_allowed, pm.adot_allowed, pm.int_pd_per_target,
            pm.def_advanced_season
        FROM player_match pm
        JOIN ourlads_players op ON pm.row_id = op.row_id
        ORDER BY pm.row_id
    """).fetchdf()
    con.close()

    master = {}
    for _, r in rows.iterrows():
        standard_pos = r['standard_pos'] or ''
        raw_stats = json.loads(r['stats_json']) if r['stats_json'] else {}

        entry = {
            'player_id': r['player_id'],
            'gsis_id': clean('gsis_id', r['gsis_id']),
            'match_confidence': clean('match_confidence', r['match_confidence']),
            'canonical_name': clean('canonical_name', r['canonical_name']),
            'ourlads_name': clean('ourlads_name', r['ourlads_name']),
            'team': clean('team', r['team']),
            'team_name': clean('team_name', r['team_name']),
            'base_defense': clean('base_defense', r['base_defense']),
            'ourlads_pos': clean('ourlads_pos', r['ourlads_pos']),
            'standard_slot': clean('standard_slot', r['standard_slot']),
            'standard_pos': standard_pos,
            'depth': clean('depth', r['depth']) if pd.notna(r['depth']) else 99,
            'jersey': clean('jersey', r['jersey']),
            'madden': clean('madden', r['madden']),
            'madden_rank': clean('madden_rank', r['madden_rank']),
            'madden_rank_total': clean('madden_rank_total', r['madden_rank_total']),
            'madden_pos_label': clean('madden_pos_label', r['madden_pos_label']),
            'cap_number': clean('cap_number', r['cap_number']),
            'attainment': clean('attainment', r['attainment']),
            'injured': bool(r['injured']) if pd.notna(r['injured']) else False,
            'stats': normalize_stats(raw_stats, standard_pos),
            'stats_season': clean('stats_season', r['stats_season']),
            'nflreadpy_name': None,
            'match_source': clean('match_source', r['match_source']),
            'draft_year': clean('draft_year', r['draft_year']),
            'college': clean('college', r['college']),
            'years_pro': clean('years_pro', r['years_pro']),
            'age': clean('age', r['age']),
            'snap_pct': clean('snap_pct', r['snap_pct']),
            'height': clean('height', r['height']),
            'weight': clean('weight', r['weight']),
            'injury_status': clean('injury_status', r['injury_status']),
            'injury_detail': clean('injury_detail', r['injury_detail']),
            'years_remaining': clean('years_remaining', r['years_remaining']),
            'cash_total_remaining': clean('cash_total_remaining', r['cash_total_remaining']),
            'cash_guaranteed_remaining': clean('cash_guaranteed_remaining', r['cash_guaranteed_remaining']),
            'avg_annual_remaining': clean('avg_annual_remaining', r['avg_annual_remaining']),
            'penalty_count': clean('penalty_count', r['penalty_count']),
            'epa_per_play': clean('epa_per_play', r['epa_per_play']),
            'success_rate': clean('success_rate', r['success_rate']),
            'ngs_time_to_throw': clean('ngs_time_to_throw', r['ngs_time_to_throw']),
            'cpoe': clean('cpoe', r['cpoe']),
            'qbr': clean('qbr', r['qbr']),
            'ryoe_per_att': clean('ryoe_per_att', r['ryoe_per_att']),
            'box_rate': clean('box_rate', r['box_rate']),
            'yac_per_att': clean('yac_per_att', r['yac_per_att']),
            'broken_tackle_rate': clean('broken_tackle_rate', r['broken_tackle_rate']),
            'target_share': clean('target_share', r['target_share']),
            'adot': clean('adot', r['adot']),
            'air_yards_share': clean('air_yards_share', r['air_yards_share']),
            'avg_separation': clean('avg_separation', r['avg_separation']),
            'yac_above_expectation': clean('yac_above_expectation', r['yac_above_expectation']),
            'drop_rate': clean('drop_rate', r['drop_rate']),
            'broken_tackle_rate_rec': clean('broken_tackle_rate_rec', r['broken_tackle_rate_rec']),
            'pressures_per100': clean('pressures_per100', r['pressures_per100']),
            'sacks_per100': clean('sacks_per100', r['sacks_per100']),
            'tfl_per100': clean('tfl_per100', r['tfl_per100']),
            'tkl_per100': clean('tkl_per100', r['tkl_per100']),
            'missed_tackle_rate': clean('missed_tackle_rate', r['missed_tackle_rate']),
            'comp_pct_allowed': clean('comp_pct_allowed', r['comp_pct_allowed']),
            'rating_allowed': clean('rating_allowed', r['rating_allowed']),
            'yds_per_target_allowed': clean('yds_per_target_allowed', r['yds_per_target_allowed']),
            'adot_allowed': clean('adot_allowed', r['adot_allowed']),
            'int_pd_per_target': clean('int_pd_per_target', r['int_pd_per_target']),
            'def_advanced_season': clean('def_advanced_season', r['def_advanced_season']),
        }
        master[r['player_id']] = entry

    with open(out_path, 'w') as f:
        json.dump(master, f, indent=2)

    print(f"Wrote {out_path}: {len(master)} players")


if __name__ == '__main__':
    export_master(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT_PATH)
