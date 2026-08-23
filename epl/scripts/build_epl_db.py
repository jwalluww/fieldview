"""epl/scripts/build_epl_db.py

Phase 1 raw ingestion (EPL): loads scrape_fpl.py's and
shared/scripts/scrape_sofifa.py's existing JSON output into
epl/data/fieldview.duckdb, one table per source, unmodified -- no joins,
no matching. Matching lives in build_epl_match.py. Mirrors
nba/scripts/build_nba_db.py's shape.

epl_players.json already carries a real per-player loaded_at (set at
scrape time in scrape_fpl.py) -- kept as-is rather than overwritten with
a fresh ingestion-time value, since a real per-player scrape timestamp
is strictly more useful than a same-for-every-row ingestion timestamp
would be.

sofifa_epl.json only has ONE top-level loaded_at (the whole scrape ran
in one pass, offset-paginated) -- folded onto every row as a constant
column, same convention as NBA's build_nba_db.py folding
nba_depth_chart.json's single top-level last_changed onto every row.

Run from the repo root: python epl/scripts/build_epl_db.py
"""
import json
import os

import duckdb
import pandas as pd

DB_PATH = os.path.join('epl', 'data', 'fieldview.duckdb')


def write_table(con, name, df):
    con.register('_tmp_df', df)
    con.execute(f'CREATE OR REPLACE TABLE {name} AS SELECT * FROM _tmp_df')
    con.unregister('_tmp_df')
    print(f"  {name}: {len(df)} rows")


def load_fpl_players():
    path = os.path.join('epl', 'data', 'epl_players.json')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    rows = list(data.values())
    for i, row in enumerate(rows):
        row['row_id'] = i
    return pd.DataFrame(rows)


def load_sofifa_ratings():
    path = os.path.join('epl', 'data', 'sofifa_epl.json')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    rows = []
    for i, p in enumerate(data['players']):
        row = dict(p)
        row['loaded_at'] = data.get('loaded_at')
        row['row_id'] = i
        rows.append(row)
    return pd.DataFrame(rows)


def build_db():
    con = duckdb.connect(DB_PATH)
    try:
        print("Loading fpl_players...")
        write_table(con, 'fpl_players', load_fpl_players())

        print("Loading sofifa_ratings...")
        write_table(con, 'sofifa_ratings', load_sofifa_ratings())
    finally:
        con.close()

    print(f"\nWrote {DB_PATH}")


if __name__ == '__main__':
    build_db()
