"""Phase 1 raw ingestion: load each source's existing scraper output into
its own DuckDB table, unmodified -- no joins, no matching. Matching logic
stays in build_master.py until Phase 2 ports it into the DB layer.

Run from the repo root: python nfl/scripts/build_db.py
"""
import glob
import json
import os

import duckdb
import pandas as pd

from season_utils import get_current_season

SEASON = get_current_season()
DB_PATH = os.path.join('nfl', 'data', 'fieldview.duckdb')

# Files under nfl/data/ that are not per-team OurLads depth charts.
NON_TEAM_FILES = {'madden.json', 'spotrac_contracts.json', 'players_master.json'}


def write_table(con, name, df):
    df = df.copy()
    df['loaded_at'] = pd.Timestamp.now()
    con.register('_tmp_df', df)
    con.execute(f'CREATE OR REPLACE TABLE {name} AS SELECT * FROM _tmp_df')
    con.unregister('_tmp_df')
    print(f"  {name}: {len(df)} rows")


def load_ourlads_players():
    """Flatten the 32 per-team depth-chart files into one row-per-player
    table. `stats` is a nested dict that varies by position, so it's kept
    as a JSON string column rather than exploded into columns here --
    faithful raw storage, not the position-aware normalization
    build_master.py's normalize_stats() does."""
    rows = []
    for filepath in sorted(glob.glob(os.path.join('nfl', 'data', '*.json'))):
        if os.path.basename(filepath) in NON_TEAM_FILES:
            continue
        with open(filepath, 'r') as f:
            team_data = json.load(f)
        if type(team_data) is list:
            team_data = team_data[0]

        team = team_data.get('team', '')
        abbr = team_data.get('abbr', '')
        source = team_data.get('source', '')
        base_defense = team_data.get('base_defense', '')

        for ourlads_pos, players in team_data.get('depth_chart', {}).items():
            for p in players:
                row = {
                    'team': team,
                    'abbr': abbr,
                    'source': source,
                    'base_defense': base_defense,
                    'ourlads_pos': ourlads_pos,
                    'name': p.get('name'),
                    'depth': p.get('depth'),
                    'injured': p.get('injured'),
                    'attainment': p.get('attainment'),
                    'standard_slot': p.get('standard_slot'),
                    'standard_pos': p.get('standard_pos'),
                    'cap_number': p.get('cap_number'),
                    'stats_json': json.dumps(p.get('stats', {})),
                    'stats_season': p.get('stats_season'),
                    'madden': p.get('madden'),
                    'jersey': p.get('jersey'),
                    'age': p.get('age'),
                    'years_pro': p.get('years_pro'),
                    'madden_rank': p.get('madden_rank'),
                    'madden_rank_total': p.get('madden_rank_total'),
                    'madden_pos_label': p.get('madden_pos_label'),
                }
                rows.append(row)
    for i, row in enumerate(rows):
        row['row_id'] = i
    return pd.DataFrame(rows)


def load_madden_ratings():
    path = os.path.join('nfl', 'data', 'madden.json')
    with open(path, 'r') as f:
        records = json.load(f)
    return pd.json_normalize(records)


def load_spotrac_contracts():
    path = os.path.join('nfl', 'data', 'spotrac_contracts.json')
    with open(path, 'r') as f:
        records = json.load(f)
    return pd.DataFrame(records)


def load_nflreadpy_rosters():
    """Same SEASON/SEASON+1 fallback build_master.py's load_nflreadpy_gsis()
    uses -- raw rows only, no name/team normalization columns added."""
    import nflreadpy as nfl
    try:
        df = nfl.load_rosters([SEASON, SEASON + 1]).to_pandas()
    except Exception:
        df = nfl.load_rosters([SEASON]).to_pandas()
    return df


def load_gsis_crosswalk():
    url = "https://github.com/dynastyprocess/data/raw/master/files/db_playerids.csv"
    return pd.read_csv(url)


def load_snap_counts():
    import nflreadpy as nfl
    try:
        return nfl.load_snap_counts([SEASON]).to_pandas()
    except ValueError as e:
        print(f"  {SEASON} snap counts not published yet ({e}) -- falling back to {SEASON - 1}")
        return nfl.load_snap_counts([SEASON - 1]).to_pandas()


def load_pbp_cached():
    """Shared pbp load for load_penalties() and load_qb_dropback_stats()
    -- avoids fetching the same season file twice in one run."""
    import nflreadpy as nfl
    try:
        return nfl.load_pbp([SEASON]).to_pandas()
    except ValueError as e:
        print(f"  {SEASON} play-by-play not published yet ({e}) -- falling back to {SEASON - 1}")
        return nfl.load_pbp([SEASON - 1]).to_pandas()


def load_penalties(pbp):
    """Season penalty counts, filtered to the two types overwhelmingly
    attributable to a specific offensive lineman (Offensive Holding,
    False Start). penalty_player_id is already in the same 00-XXXXXXX
    gsis_id format used everywhere else in this pipeline."""
    pen = pbp[(pbp['penalty'] == 1) &
              (pbp['penalty_type'].isin(['Offensive Holding', 'False Start']))]
    return pen[['penalty_player_id', 'penalty_type']].dropna(subset=['penalty_player_id'])


def load_qb_dropback_stats(pbp):
    """Season EPA/dropback and success rate per QB. nflverse's pbp
    already has pre-computed qb_epa (isolated QB credit, not the
    generic epa column which mixes credit across play types) and
    success (nflverse's own standard success-rate flag) columns per
    play -- no manual down/distance formula needed. Dropback =
    pass_attempt or sack (a sack is a failed dropback by definition;
    excluding it would flatter sack-prone QBs)."""
    dropbacks = pbp[(pbp['pass_attempt'] == 1) | (pbp['sack'] == 1)]
    return dropbacks.groupby('passer_player_id').agg(
        epa_per_play=('qb_epa', 'mean'),
        success_rate=('success', 'mean'),
    ).reset_index()


def load_ngs_passing():
    """NGS Time to Throw + NFL's own official CPOE (completion_percentage
    _above_expectation -- the league's published model, not nflverse's
    separate pbp-derived cpoe column), keyed by player_gsis_id.

    IMPORTANT: load_nextgen_stats() mixes weekly rows (week=1,2,3...)
    and ONE season-aggregate row (week=0) in the same dataframe for a
    given season -- confirmed by real inspection. Must filter to
    week == 0, or every downstream lookup gets multiple rows per
    player and silently breaks."""
    import nflreadpy as nfl
    try:
        df = nfl.load_nextgen_stats(stat_type='passing', seasons=[SEASON]).to_pandas()
    except ValueError as e:
        print(f"  {SEASON} NGS passing stats not published yet ({e}) -- falling back to {SEASON - 1}")
        df = nfl.load_nextgen_stats(stat_type='passing', seasons=[SEASON - 1]).to_pandas()
    return df[df['week'] == 0]


def load_qbr_ratings():
    path = os.path.join('nfl', 'data', 'qbr.json')
    with open(path, 'r') as f:
        records = json.load(f)
    return pd.json_normalize(records)


def build_db():
    con = duckdb.connect(DB_PATH)
    try:
        print("Loading ourlads_players...")
        write_table(con, 'ourlads_players', load_ourlads_players())

        print("Loading madden_ratings...")
        write_table(con, 'madden_ratings', load_madden_ratings())

        print("Loading spotrac_contracts...")
        write_table(con, 'spotrac_contracts', load_spotrac_contracts())

        print("Loading nflreadpy_rosters...")
        write_table(con, 'nflreadpy_rosters', load_nflreadpy_rosters())

        print("Loading gsis_crosswalk...")
        write_table(con, 'gsis_crosswalk', load_gsis_crosswalk())

        print("Loading snap_counts...")
        write_table(con, 'snap_counts', load_snap_counts())

        print("Loading play-by-play (penalties + QB dropback stats)...")
        pbp = load_pbp_cached()
        write_table(con, 'penalties', load_penalties(pbp))
        write_table(con, 'qb_dropback_stats', load_qb_dropback_stats(pbp))

        print("Loading NGS passing (CPOE + Time to Throw)...")
        write_table(con, 'ngs_passing', load_ngs_passing())

        print("Loading QBR ratings...")
        write_table(con, 'qbr_ratings', load_qbr_ratings())
    finally:
        con.close()

    print(f"\nWrote {DB_PATH}")


if __name__ == '__main__':
    build_db()
