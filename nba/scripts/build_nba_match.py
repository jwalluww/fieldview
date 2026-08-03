"""Phase 2 (NBA): recreate build_nba_master.py's join/resolution logic
against the DuckDB tables Phase 1 (build_nba_db.py) loaded, writing
results into a player_match table -- one row per nba_stats player,
keyed by player_id.

Reuses build_nba_master.py's own resolution functions directly
(resolve_position, resolve_rotation, resolve_team, format_salary,
DEPTH_RANK_TO_STATUS) so the resolution RULES are the same code, not a
transcription. Only the data-loading side is swapped from the static
JSON files to the DB snapshot Phase 1 captured.

Unlike NFL, there's no fuzzy name matching to port here -- each NBA
source scraper (scrape_contracts_spotrac.py, scrape_2kratings.py,
scrape_nbadepthcharts.py) already does its own name/team fuzzy match
against nba_stats.json's player universe and bakes the result (a
player_id, or null if unmatched) directly into its output file.
build_nba_master.py's own job is just to join those pre-matched sources
by player_id and resolve position/rotation/team conflicts -- confirmed
by reading all three scrapers' matching code: none of them filter or
gate on position the way NFL's EDGE/DI split did, so there's no
analogous position-taxonomy mismatch here to fix.
"""
import os

import duckdb
import pandas as pd

from build_nba_master import (
    resolve_position, resolve_rotation, resolve_team, format_salary,
)

DB_PATH = os.path.join('nba', 'data', 'fieldview.duckdb')


def to_int_or_none(v):
    return None if pd.isna(v) else int(v)


def build_dict_last_wins(df, id_col='player_id', drop_null=False):
    """Replicates Python's {row[id_col]: row for row in list} dict-comp
    semantics -- last row in file order wins for a duplicate id. df must
    already be ordered by row_id (original file order).

    Converts each row to a plain dict with NaN -> None, not a raw pandas
    Series -- format_salary()'s `if not cash_total_remaining` falsy check
    treats float('nan') as truthy (unlike real Python None from the
    original json.load), so leaving pandas' NaN in place would silently
    compute a garbage NaN salary instead of correctly returning None."""
    result = {}
    for _, row in df.iterrows():
        pid = to_int_or_none(row[id_col])
        if drop_null and pid is None:
            continue
        result[pid] = {k: (None if pd.isna(v) else v) for k, v in row.items()}
    return result


def build_match():
    con = duckdb.connect(DB_PATH)

    stats_df = con.execute("SELECT * FROM nba_stats").fetchdf()
    contracts_df = con.execute("SELECT * FROM nba_contracts ORDER BY row_id").fetchdf()
    ratings_df = con.execute("SELECT * FROM nba_ratings ORDER BY row_id").fetchdf()
    depth_df = con.execute("SELECT * FROM nba_depth_chart ORDER BY row_id").fetchdf()
    con.close()

    contracts_by_id = build_dict_last_wins(contracts_df)
    ratings_by_id = build_dict_last_wins(ratings_df)
    # Native-Python-typed dict, same shape resolve_rotation/resolve_team
    # expect (a fresh dict from json.load in the original) -- avoids
    # handing them raw pandas Series/numpy scalars.
    depth_by_id = {
        pid: {'depth_rank': int(row['depth_rank']), 'team': row['team']}
        for pid, row in build_dict_last_wins(depth_df, drop_null=True).items()
    }

    matches = []
    for _, raw_p in stats_df.iterrows():
        # Same NaN -> None sanitization as build_dict_last_wins -- a null
        # `position` (57 of 587 players) would otherwise reach
        # resolve_position() as float('nan'), which is truthy, and get
        # returned as-is (a garbage NaN "position") instead of correctly
        # falling through to the contract-position/None branches.
        p = {k: (None if pd.isna(v) else v) for k, v in raw_p.items()}
        pid = int(p['player_id'])
        contract = contracts_by_id.get(pid)
        rating = ratings_by_id.get(pid)

        rotation = resolve_rotation(pid, p.get('rotation_status'), depth_by_id)
        team = resolve_team(pid, p.get('team'), depth_by_id)

        matches.append({
            'player_id': pid,
            'team': team,
            'position': resolve_position(
                p.get('position'),
                contract['pos'] if contract is not None else None),
            'rotation_status': rotation['rotation_status'],
            'rotation_source': rotation['rotation_source'],
            'depth_rank': rotation['depth_rank'],
            'overall_rating': to_int_or_none(rating['overall_rating']) if rating is not None else None,
            'contract_salary': format_salary(
                contract['cash_total_remaining'] if contract is not None else None,
                contract['length_remaining'] if contract is not None else None),
            'contract_years_remaining': to_int_or_none(contract['length_remaining']) if contract is not None else None,
        })

    match_df = pd.DataFrame(matches)
    con = duckdb.connect(DB_PATH)
    con.register('_tmp_match', match_df)
    con.execute("CREATE OR REPLACE TABLE player_match AS SELECT * FROM _tmp_match")
    con.unregister('_tmp_match')
    con.close()

    total = len(match_df)
    matched_contract = match_df['contract_salary'].notna().sum()
    matched_rating = match_df['overall_rating'].notna().sum()
    from_depth_chart = (match_df['rotation_source'] == 'nbadepthchart.com').sum()
    print(f"player_match: {total} players")
    print(f"Matched contracts: {matched_contract} / {total}")
    print(f"Matched 2k ratings: {matched_rating} / {total}")
    print(f"rotation_status from nbadepthchart.com: {from_depth_chart} / {total}")


if __name__ == '__main__':
    build_match()
