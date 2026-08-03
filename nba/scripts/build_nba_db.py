"""Phase 1 raw ingestion (NBA): load each source's existing scraper output
into its own DuckDB table, unmodified -- no joins, no matching. Matching
logic stays in build_nba_master.py until Phase 2 ports it into the DB
layer. Mirrors nfl/scripts/build_db.py's approach.

Unlike NFL, every NBA source already carries its own match result
(player_id, or null if unmatched) baked in by its own scraper -- there's
no separate live-pull crosswalk to ingest here. Also unlike NFL's
scrapers, each of contracts_nba.json/nba_ratings_2k.json/
nba_depth_chart.json's own "unmatched" list is a fully redundant subset
of its main list (verified: bag-equal to that list's player_id-null rows,
same field values) -- so only the main list is ingested per source, not
a separate "_unmatched" table, to avoid ingesting the same records twice.

Run from the repo root: python nba/scripts/build_nba_db.py
"""
import json
import os

import duckdb
import pandas as pd

DB_PATH = os.path.join('nba', 'data', 'fieldview.duckdb')


def write_table(con, name, df):
    df = df.copy()
    df['loaded_at'] = pd.Timestamp.now()
    con.register('_tmp_df', df)
    con.execute(f'CREATE OR REPLACE TABLE {name} AS SELECT * FROM _tmp_df')
    con.unregister('_tmp_df')
    print(f"  {name}: {len(df)} rows")


def load_nba_stats():
    """row_id preserves nba_stats.json's own key order -- build_nba_master.py
    iterates stats_by_id.items() in file order (nba_api's own return order,
    not sorted by id), and the export needs to reproduce that same order
    for a byte-identical diff, not just an equal-value one."""
    path = os.path.join('nba', 'data', 'nba_stats.json')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    rows = list(data.values())
    for i, row in enumerate(rows):
        row['row_id'] = i
    return pd.DataFrame(rows)


def load_nba_contracts():
    """row_id preserves original list order -- build_nba_master.py's
    {c["player_id"]: c for c in ...} join keeps the LAST duplicate
    player_id in file order (there are 3 real ones, with differing
    values), so Phase 2's port needs that same order to replicate it."""
    path = os.path.join('nba', 'data', 'contracts_nba.json')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    rows = data['contracts']
    for i, row in enumerate(rows):
        row['row_id'] = i
    return pd.DataFrame(rows)


def load_nba_ratings():
    path = os.path.join('nba', 'data', 'nba_ratings_2k.json')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    rows = data['ratings']
    for i, row in enumerate(rows):
        row['row_id'] = i
    return pd.DataFrame(rows)


def load_nba_depth_chart():
    """status_flags is a nested list per row -- kept as a JSON string
    column, same treatment as NFL's stats dict in build_db.py. Also folds
    in the file's single top-level last_changed value as a constant column
    so it's queryable without a separate metadata table."""
    path = os.path.join('nba', 'data', 'nba_depth_chart.json')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    rows = []
    for i, e in enumerate(data['depth_chart']):
        row = dict(e)
        row['status_flags_json'] = json.dumps(row.pop('status_flags', []))
        row['last_changed'] = data.get('last_changed')
        row['row_id'] = i
        rows.append(row)
    return pd.DataFrame(rows)


def build_db():
    con = duckdb.connect(DB_PATH)
    try:
        print("Loading nba_stats...")
        write_table(con, 'nba_stats', load_nba_stats())

        print("Loading nba_contracts...")
        write_table(con, 'nba_contracts', load_nba_contracts())

        print("Loading nba_ratings...")
        write_table(con, 'nba_ratings', load_nba_ratings())

        print("Loading nba_depth_chart...")
        write_table(con, 'nba_depth_chart', load_nba_depth_chart())
    finally:
        con.close()

    print(f"\nWrote {DB_PATH}")


if __name__ == '__main__':
    build_db()
